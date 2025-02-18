#!/bin/bash

# what env?
env="prod"

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
        for redis in $(aws-vault exec $CLUSTER.AdministratorAccess -- aws elasticache describe-replication-groups --query "ReplicationGroups[*].ReplicationGroupId" --output text --region $REGION | xargs); do
            echo "  ${redis}"
            #aws-vault exec $CLUSTER.AdministratorAccess -- aws elasticache batch-apply-update-action --service-update-name elasticache-patch-update-2-202501 --replication-group-ids ${redis} --region $REGION
        done
    fi
done