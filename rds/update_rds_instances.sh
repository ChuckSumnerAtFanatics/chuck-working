#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

usage() {
  cat <<EOF
Usage: $(basename "$0") --env ENVIRONMENT [--apply] [--skip-pattern REGEX] [--list-only]

Options:
  -e, --env            Environment name (e.g. dev, cert, prod)
      --apply          Actually apply the changes. Without this flag, runs in dry-run mode.
      --skip-pattern   Regex to skip clusters matching this pattern.
      --list-only      Only show current versions without planning updates.
  -h, --help           Show this help message and exit.
EOF
  exit 1
}

# Default settings
DRY_RUN=true
SKIP_PATTERN=""
ENV=""
LIST_ONLY=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    -e|--env)
      ENV="$2"
      shift 2
      ;;
    --apply)
      DRY_RUN=false
      shift
      ;;
    --skip-pattern)
      SKIP_PATTERN="$2"
      shift 2
      ;;
    --list-only)
      LIST_ONLY=true
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

if [[ -z "${ENV}" ]]; then
  echo "Error: --env is required."
  usage
fi

: "${DB_PROVISIONER_HOME:?Environment variable DB_PROVISIONER_HOME must be set}"
ENV_FILE="${DB_PROVISIONER_HOME}/envs/${ENV}-env.yaml"
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Error: Environment file not found: ${ENV_FILE}"
  exit 1
fi

# Version mapping: major -> target
declare -A VERSION_MAP=(
  
  [13]=13.20
  [14]=14.17
  [16]=16.8
  [17]=17.4
)

declare -A seen_clusters=()

# Collect planned commands
cmds=()

echo "Loading clusters from ${ENV_FILE}..."

if command -v yq &>/dev/null; then
  # Get all the various cluster types from the YAML structure with improved error handling
  
  # Process parent - use null check in yq to avoid null values
  mapfile -t parent_entry < <(yq e -o=tsv '.parent | select(.aws_account_name != null and .aws_region != null) | [.aws_account_name, .aws_region] | @tsv' "${ENV_FILE}")
  
  # Process debezium_parents with null check
  mapfile -t debezium_entries < <(yq e -o=tsv '.debezium_parents[] | select(.aws_account_name != null and .aws_region != null) | [.aws_account_name, .aws_region] | @tsv' "${ENV_FILE}")
  
  # Process data_parents with null check
  mapfile -t data_entries < <(yq e -o=tsv '.data_parents[] | select(.aws_account_name != null and .aws_region != null) | [.aws_account_name, .aws_region] | @tsv' "${ENV_FILE}")
  
  # Process children with null check
  mapfile -t child_entries < <(yq e -o=tsv '.children[] | select(.aws_account_name != null and .aws_region != null) | [.aws_account_name, .aws_region] | @tsv' "${ENV_FILE}")
  
  # Process data_compute_cluster with null check
  #mapfile -t compute_entry < <(yq e -o=tsv '.data_compute_cluster | select(.aws_account_name != null and .aws_region != null) | [.aws_account_name, .aws_region] | @tsv' "${ENV_FILE}")
  
  # Combine all entries with improved validation
  entries=()
  if [[ ${#parent_entry[@]} -gt 0 && "${parent_entry[0]}" != "null" ]]; then
    entries+=("${parent_entry[@]}")
  fi
  
  if [[ ${#debezium_entries[@]} -gt 0 && "${debezium_entries[0]}" != "null" ]]; then
    entries+=("${debezium_entries[@]}")
  fi
  
  if [[ ${#data_entries[@]} -gt 0 && "${data_entries[0]}" != "null" ]]; then
    entries+=("${data_entries[@]}")
  fi
  
  if [[ ${#child_entries[@]} -gt 0 && "${child_entries[0]}" != "null" ]]; then
    entries+=("${child_entries[@]}")
  fi
  
  parse_cmd="yq"
else
  mapfile -t entries < <(grep -A1 aws_account_name "${ENV_FILE}" | awk '{print $NF}' | grep -v '^--$')
  parse_cmd="grep/awk"
fi

if [[ ${parse_cmd} == "grep/awk" ]]; then
  for ((i=0; i < ${#entries[@]}; i+=2)); do
    cluster="${entries[i]}"
    region="${entries[i+1]}"
    
    # Trim any whitespace
    cluster=$(echo "$cluster" | tr -d '[:space:]')
    region=$(echo "$region" | tr -d '[:space:]')
    
    # Skip empty values
    if [[ -z "$cluster" || -z "$region" ]]; then
      echo "Skipping empty cluster or region"
      continue
    fi
    
    if [[ -n "${SKIP_PATTERN}" && "${cluster}" =~ ${SKIP_PATTERN} ]]; then
      echo "Skipping cluster ${cluster} (matches skip pattern)"
      continue
    fi
    
    # Add quotes to ensure proper array indexing
    seen_clusters["$cluster"]="$region"
  done
else
  for line in "${entries[@]}"; do
    cluster="${line%%$'\t'*}"
    region="${line##*$'\t'}"
    
    # Trim any whitespace and validate
    cluster=$(echo "$cluster" | tr -d '[:space:]')
    region=$(echo "$region" | tr -d '[:space:]')
    
    # Skip empty values
    if [[ -z "$cluster" || -z "$region" ]]; then
      echo "Skipping empty cluster or region"
      continue
    fi
    
    if [[ -n "${SKIP_PATTERN}" && "${cluster}" =~ ${SKIP_PATTERN} ]]; then
      echo "Skipping cluster ${cluster} (matches skip pattern)"
      continue
    fi
    
    # Debug what we're adding
    echo "Adding cluster: '$cluster' in region: '$region'"
    
    # Add to the associative array with proper quoting
    seen_clusters["$cluster"]="$region"
  done
fi

echo "Found ${#seen_clusters[@]} clusters to process."

# Store instance version information
declare -A instance_versions=()
declare -A instance_target_versions=()
declare -A instance_clusters=()
declare -A instance_types=()
declare -A instance_storage=()
declare -A instance_storage_type=()

for cluster in "${!seen_clusters[@]}"; do
  region="${seen_clusters[$cluster]}"
  
  # Skip null or empty values
  if [[ "$cluster" == "null" || -z "$cluster" || "$region" == "null" || -z "$region" ]]; then
    echo "Skipping invalid entry: cluster='$cluster', region='$region'"
    continue
  fi
  
  echo "Processing cluster ${cluster} in region ${region}..."
  
  # Add error handling for aws-vault command
  instances_json=$(aws-vault exec "${cluster}.DBAdministrator" -- aws rds describe-db-instances --region "${region}" 2>&1) || {
    echo "Error accessing AWS for cluster ${cluster}: $instances_json"
    continue
  }
  
  # Make sure we got valid JSON with instances
  if ! echo "$instances_json" | jq -e '.DBInstances' >/dev/null 2>&1; then
    echo "No instances found or invalid response for cluster ${cluster}"
    continue
  fi
  
  instances=$(echo "$instances_json" | jq -r '.DBInstances[].DBInstanceIdentifier')
  
  for instance in ${instances}; do
    # Add error handling for each instance query
    engine_json=$(aws-vault exec "${cluster}.DBAdministrator" -- aws rds describe-db-instances --db-instance-identifier "${instance}" --region "${region}" 2>&1) || {
      echo "Error getting details for instance ${instance}: $engine_json"
      continue
    }
    
    engine=$(echo "$engine_json" | jq -r '.DBInstances[0].EngineVersion')
    instance_type=$(echo "$engine_json" | jq -r '.DBInstances[0].DBInstanceClass')
    storage=$(echo "$engine_json" | jq -r '.DBInstances[0].AllocatedStorage')
    storage_type=$(echo "$engine_json" | jq -r '.DBInstances[0].StorageType')
    instance_versions["$instance"]="$engine"
    instance_clusters["$instance"]="$cluster"
    instance_types["$instance"]="$instance_type"
    instance_storage["$instance"]="$storage"
    instance_storage_type["$instance"]="$storage_type"
    
    # Only calculate target versions if we're not in list-only mode
    if [[ "${LIST_ONLY}" == false ]]; then
      major=${engine%%.*}
      target="${VERSION_MAP[${major}]:-}"
      
      if [[ -n "${target}" && "${engine}" != "${target}" ]]; then
        instance_target_versions["$instance"]="$target"
        cmd="aws-vault exec ${cluster}.DBAdministrator -- aws rds modify-db-instance \
--db-instance-identifier ${instance} \
--region ${region} \
--engine-version ${target} \
--apply-immediately"
        cmds+=( "${cmd}" )
      else
        instance_target_versions["$instance"]="no update needed"
      fi
    fi
  done
done

# Display current versions information
echo
echo "Current RDS instance versions:"
echo "-----------------------------"
if [[ "${LIST_ONLY}" == true ]]; then
  # Simpler output for list-only mode - no target version column
  printf "%-40s %-20s %-20s %-20s %-10s %-15s\n" "Instance" "Cluster" "Instance Type" "Current Version" "Storage" "Storage Type"
  for instance in $(printf "%s\n" "${!instance_versions[@]}" | sort); do
    printf "%-40s %-20s %-20s %-20s %-10s %-15s\n" \
      "$instance" \
      "${instance_clusters[$instance]}" \
      "${instance_types[$instance]}" \
      "${instance_versions[$instance]}" \
      "${instance_storage[$instance]}" \
      "${instance_storage_type[$instance]}"
  done
else
  # Complete output with current and target versions
  printf "%-40s %-20s %-20s %-20s %-20s %-10s %-15s\n" "Instance" "Cluster" "Instance Type" "Current Version" "Target Version" "Storage" "Storage Type"
  for instance in $(printf "%s\n" "${!instance_versions[@]}" | sort); do
    printf "%-40s %-20s %-20s %-20s %-20s %-10s %-15s\n" \
      "$instance" \
      "${instance_clusters[$instance]}" \
      "${instance_types[$instance]}" \
      "${instance_versions[$instance]}" \
      "${instance_target_versions[$instance]}" \
      "${instance_storage[$instance]}" \
      "${instance_storage_type[$instance]}"
  done
fi
echo

# Exit early if list-only mode
if [[ "${LIST_ONLY}" == true ]]; then
  exit 0
fi

echo "Planned ${#cmds[@]} update(s):"
for c in "${cmds[@]}"; do
  echo "  $c"
done

if [[ ${#cmds[@]} -eq 0 ]]; then
  echo "No updates needed."
  exit 0
fi

if [[ "${DRY_RUN}" == true ]]; then
  echo
  echo "Dry-run mode. No changes applied."
  exit 0
fi

echo
read -rp 'Apply these updates? [y/N] ' answer
if [[ ! "${answer}" =~ ^[Yy]$ ]]; then
  echo "Aborted."
  exit 1
fi

echo
echo "Applying updates..."
for c in "${cmds[@]}"; do
  eval "${c}"
done

echo "Done."