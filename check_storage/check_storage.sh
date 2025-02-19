#!/bin/bash

# what env?
env="prod"

export AWS_PAGER=""

# Declare an associative array to store unique cluster-region pairs
declare -A seen_clusters

# Read cluster-region pairs properly
grep -A1 aws_account_name $DB_PROVISIONER_HOME/envs/${env}-env.yaml | awk '{ print $NF }' | grep -v -- "^--$" | while read -r cluster; do
    read -r region || break  # Read the next line as the region

    # Skip unwanted cluster
    [[ "$cluster" =~ ^data-compute-.*$ ]] && continue

    # Check if the cluster is already processed
    if [[ -z "${seen_clusters[$cluster]}" ]]; then
        seen_clusters["$cluster"]="$region"

        export CLUSTER="$cluster"
        export REGION="$region"

        echo ${cluster}
        for rds in $(aws-vault exec $CLUSTER.AdministratorAccess -- aws rds describe-db-instances --region ${REGION} | jq -r '.DBInstances[].DBInstanceIdentifier'); do
          for instance in $(aws-vault exec $CLUSTER.AdministratorAccess -- aws rds describe-db-instances --db-instance-identifier ${rds} --region ${REGION} | jq -r '.DBInstances[] | .DBInstanceIdentifier'); do
            aws-vault exec $CLUSTER.AdministratorAccess -- aws rds describe-db-instances --db-instance-identifier ${instance} --region ${REGION} | jq -r '.DBInstances[] | select(.AllocatedStorage == .MaxAllocatedStorage) | {DBInstanceIdentifier, AllocatedStorage, MaxAllocatedStorage}'
          done
        done

    fi
done