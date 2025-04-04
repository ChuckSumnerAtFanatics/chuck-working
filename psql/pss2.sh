#!/bin/bash

DB_USER="postgres"
DB_NAME="postgres"
COLUMNS=$(tput cols)

# Parse arguments
usage() {
    cat << EOF
Usage: pss [OPTIONS] [environment]

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
    echo "Connecting to: $env ${DB_USER}@${instance}"
    export $(fbg postgres credentials get --skip-refresh --skip-test --env "$env" --user "${DB_USER}" "${instance}")

    if [[ -n "$ITERM_PROFILE" ]]; then
        echo -ne "\033]0;PG: ${env}: ${instance}\007"
    fi
    if [[ "$env" == *"prod"* ]]; then
        pgcli --prompt "\x1b[1;31m[${env}] \u@\d>\x1b[0m " -d "${DB_NAME}" -U "${DB_USER}"
    elif [[ "$env" == *"local"* ]]; then
        pgcli --prompt "\x1b[1;36m[${env}] \u@\d>\x1b[0m " -d "${DB_NAME}" -U "${DB_USER}"
    else
        pgcli --prompt "\x1b[1;32m[${env}] \u@\d>\x1b[0m " -d "${DB_NAME}" -U "${DB_USER}"
    fi
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
    while IFS= read -r line; do
        users+=("$line")
    done < <(echo "$CREDS_LIST" | jq -r --arg env "$env" --arg instance "$instance" \
        '.[] | select(.env == $env and .instance_name == $instance) | .username' | sort -u)
    
    echo "Select a user:"
    select user in "${users[@]}"; do
        if [[ -n "$user" ]]; then
            echo "You selected: $user"
            export DB_USER=$user
            connect_to_env "$env"
            break
        else
            echo "Invalid selection, try again."
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

if [[ -n "$ITERM_PROFILE" ]]; then
    echo -ne "\033]0;\007"
fi