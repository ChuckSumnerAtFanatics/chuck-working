#!/bin/bash

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "Error: This script must be sourced. Please run: source $(basename ${0})" >&2
    exit 1
fi

# Parse arguments
usage() {
    cat << EOF
Usage: source getcreds [OPTIONS] [environment]

Options:
    -d, --database      Database to connect to (default: postgres)
    -h, --help          Show this help message
    -u, --user USER     Database user (default: postgres)

Arguments:
    environment         Full or partial environment name to connect to
EOF
    return 0
}

# Initialize variables
DB_USER="postgres"
DB_NAME="postgres"
ENV_NAME=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            return 0
            ;;
        -d|--database)
            DB_NAME="$2"
            shift 2
            ;;
        -u|--user)
            DB_USER="$2"
            shift 2
            ;;
        *)
            ENV_NAME="$1"
            shift
            ;;
    esac
done

# Get the current directory
OHOME=$(pwd)

# Set the terminal width
COLUMNS=$(tput cols)

# Set this env var to the path of db_provisioner
if [ -z "${DB_PROVISIONER_HOME}" ]; then
    echo "Error: DB_PROVISIONER_HOME environment variable must be set" >&2
    exit 1
fi
cd "${DB_PROVISIONER_HOME}"

# Get environment names and build array efficiently
env_array=()
while IFS= read -r line; do
    [[ -n "$line" ]] && env_array+=("$line")
done < <(grep -h 'environment_name:' "envs/"* | 
        cut -d':' -f2 | 
        sed 's/^ *//g' |
        grep -Ev 'data-compute|fbg-local' |
        sort)

# Function to connect to the environment
setup_env() {
    local env="$1"
    echo "Setting up vars for: $env ${DB_USER}@${DB_NAME}"
    export $(poetry run python get_db_creds.py --environment "$env" --user "${DB_USER}")
    export PGDATABASE="${DB_NAME}"
}

# Check if environment name is provided
if [[ -n "${ENV_NAME}" ]]; then
    matches=()
    exact_match=""

    for env in "${env_array[@]}"; do
        if [[ "$env" == "${ENV_NAME}" ]]; then
            exact_match="$env"
            break
        elif [[ "$env" == *"${ENV_NAME}"* ]]; then
            matches+=("$env")
        fi
    done

    # If there is an exact match, connect to it
    if [[ -n "$exact_match" ]]; then
        setup_env "$exact_match"
    elif [[ ${#matches[@]} -gt 0 ]]; then
        # Display menu of matching entries
        echo "Select an environment:"
        select env in "${matches[@]}"; do
            if [[ -n "$env" ]]; then
                setup_env "$env"
                break
            else
                echo "Invalid selection. Please try again."
            fi
        done
    else
        echo "No matching environments found for: ${ENV_NAME}" >&2
        exit 1
    fi
fi

# Add cleanup function at end of script
finish() {
    echo "Current PostgreSQL related environment variables:"
    env | grep PG
    cd "${OHOME}"
}

# Call finish function at end of script
finish