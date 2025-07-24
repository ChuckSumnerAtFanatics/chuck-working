#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

usage() {
  cat <<EOF
Usage: $(basename "$0") --env ENVIRONMENT
Options:
  -e, --env            Environment name (e.g. dev, cert, prod)
  -h, --help           Show this help message and exit.
EOF
  exit 1
}

ENV=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    -e|--env)
      ENV="$2"
      shift 2
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

declare -A seen_clusters=()

echo "Loading clusters from ${ENV_FILE}..."

if command -v yq &>/dev/null; then
  mapfile -t parent_entry < <(yq e -o=tsv '.parent | select(.aws_account_name != null and .aws_region != null) | [.aws_account_name, .aws_region] | @tsv' "${ENV_FILE}")
  mapfile -t debezium_entries < <(yq e -o=tsv '.debezium_parents[] | select(.aws_account_name != null and .aws_region != null) | [.aws_account_name, .aws_region] | @tsv' "${ENV_FILE}")
  mapfile -t data_entries < <(yq e -o=tsv '.data_parents[] | select(.aws_account_name != null and .aws_region != null) | [.aws_account_name, .aws_region] | @tsv' "${ENV_FILE}")
  mapfile -t child_entries < <(yq e -o=tsv '.children[] | select(.aws_account_name != null and .aws_region != null) | [.aws_account_name, .aws_region] | @tsv' "${ENV_FILE}")
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
    cluster=$(echo "$cluster" | tr -d '[:space:]')
    region=$(echo "$region" | tr -d '[:space:]')
    if [[ -z "$cluster" || -z "$region" ]]; then
      continue
    fi
    seen_clusters["$cluster"]="$region"
  done
else
  for line in "${entries[@]}"; do
    cluster="${line%%$'\t'*}"
    region="${line##*$'\t'}"
    cluster=$(echo "$cluster" | tr -d '[:space:]')
    region=$(echo "$region" | tr -d '[:space:]')
    if [[ -z "$cluster" || -z "$region" ]]; then
      continue
    fi
    seen_clusters["$cluster"]="$region"
  done
fi

declare -A instance_versions=()
declare -A instance_clusters=()
declare -A instance_types=()
declare -A instance_storage=()
declare -A instance_storage_type=()

for cluster in "${!seen_clusters[@]}"; do
  region="${seen_clusters[$cluster]}"
  if [[ "$cluster" == "null" || -z "$cluster" || "$region" == "null" || -z "$region" ]]; then
    continue
  fi
  instances_json=$(aws-vault exec "${cluster}.DBAdministrator" -- aws rds describe-db-instances --region "${region}" 2>&1) || continue
  if ! echo "$instances_json" | jq -e '.DBInstances' >/dev/null 2>&1; then
    continue
  fi
  instances=$(echo "$instances_json" | jq -r '.DBInstances[].DBInstanceIdentifier')
  for instance in ${instances}; do
    engine_json=$(aws-vault exec "${cluster}.DBAdministrator" -- aws rds describe-db-instances --db-instance-identifier "${instance}" --region "${region}" 2>&1) || continue
    engine=$(echo "$engine_json" | jq -r '.DBInstances[0].EngineVersion')
    instance_type=$(echo "$engine_json" | jq -r '.DBInstances[0].DBInstanceClass')
    storage=$(echo "$engine_json" | jq -r '.DBInstances[0].AllocatedStorage')
    storage_type=$(echo "$engine_json" | jq -r '.DBInstances[0].StorageType')
    instance_versions["$instance"]="$engine"
    instance_clusters["$instance"]="$cluster"
    instance_types["$instance"]="$instance_type"
    instance_storage["$instance"]="$storage"
    instance_storage_type["$instance"]="$storage_type"
  done

done

echo
printf "%-40s %-35s %-20s %-20s %-10s %-15s\n" "Instance" "Cluster" "Instance Type" "Current Version" "Storage" "Storage Type"
for instance in $(printf "%s\n" "${!instance_versions[@]}" | sort); do
  printf "%-40s %-35s %-20s %-20s %-10s %-15s\n" \
    "$instance" \
    "${instance_clusters[$instance]}" \
    "${instance_types[$instance]}" \
    "${instance_versions[$instance]}" \
    "${instance_storage[$instance]}" \
    "${instance_storage_type[$instance]}"
done
