#!/bin/bash

DB_USER="postgres"
DB_NAME="postgres"
COLUMNS=$(tput cols)

# Parse arguments
usage() {
    cat << EOF
Usage: $0 [OPTIONS] [environment]

Options:
    -d, --database      Database to connect to (default: postgres)
    -h, --help          Show this help message

Arguments:
    environment         Full or partial environment name to connect to
EOF
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -d|--database)
            if [[ -z "$2" ]]; then
                echo "Error: --database requires an argument" >&2
                usage
                exit 1
            fi
            DB_NAME="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        -*)
            echo "Unknown option: $1" >&2
            usage
            exit 1
            ;;
        *)
            ENV_NAME="$1"
            shift
            ;;
    esac
done

connect_to_env() {
    local env="$1"
    export $(fbg postgres credentials get --skip-refresh --skip-test --env "$env" --user "${DB_USER}" "${instance}")

    echo "PGUSER=${DB_USER}"
    echo "PGPASSWORD='${PGPASSWORD}'"
    echo "PGHOST=${PGHOST}"
    echo "PGPORT=5432"
}

# Function to display menu of all environments
display_menu() {

    echo "Select an environment:"
    select env in "${env_array[@]}"; do
        if [[ -n "$env" ]]; then
            select_instance "$env"
            break
        else
            echo "Invalid selection. Please try again."
        fi
    done
}

# Function to select an instance
select_instance() {
    local env="$1"
    instances=()
    while IFS= read -r line; do
        instances+=("$line")
    done < <(echo "$CREDS_LIST" | jq -r --arg env "$env" '.[] | select(.env == $env) | .instance_name' | sort -u)

    echo "Select an instance:"
    select instance in "${instances[@]}"; do
        if [[ -n "$instance" ]]; then
            echo "You selected: $instance"
            export instance=$instance
            select_user "$env" "$instance"
            break
        else
            echo "Invalid selection, try again."
        fi
    done
}

select_user() {
    local env="$1"
    local instance="$2"
    users=()
    
    # Get unique usernames from the credentials list
    while IFS= read -r line; do
        users+=("$line")
    done < <(echo "$CREDS_LIST" | jq -r --arg env "$env" --arg instance "$instance" \
        '.[] | select(.env == $env and .instance_name == $instance) | .username' | sort -u)
    
    # If postgres is in the list, make it the first option
    postgres_index=-1
    for i in "${!users[@]}"; do
        if [[ "${users[$i]}" == "postgres" ]]; then
            postgres_index=$i
            break
        fi
    done
    
    if [[ $postgres_index -ne -1 ]]; then
        # Remove postgres from its current position
        postgres_user="${users[$postgres_index]}"
        unset 'users[$postgres_index]'
        # Recreate array with postgres first, followed by the rest
        users=("$postgres_user" "${users[@]}")
    fi
    
    echo "Select a user (default: postgres):"
    select user in "${users[@]}"; do
        if [[ -n "$user" ]]; then
            echo "You selected: $user"
            export DB_USER=$user
            connect_to_env "$env"
            break
        else
            echo "Invalid selection. Using default: postgres"
            export DB_USER="postgres"
            connect_to_env "$env"
            break
        fi
    done
}

# Get credentials list as JSON
CREDS_LIST=$(fbg postgres credentials list --skip-refresh --output-format json)

env_array=()
while IFS= read -r line; do
    [[ -n "$line" ]] && env_array+=("$line")
done < <(echo "$CREDS_LIST" | jq -r '.[].env' | sort -u)

# Check if environment name is provided
if [[ -z "${ENV_NAME}" ]]; then
    display_menu
else
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
        select_instance "$exact_match"
    elif [[ ${#matches[@]} -gt 0 ]]; then
        # Display menu of matching entries
        echo "Select an environment:"
        select env in "${matches[@]}"; do
            if [[ -n "$env" ]]; then
                echo "You selected: $env"
                select_instance "$env"
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