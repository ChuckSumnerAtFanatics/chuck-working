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
        for redis in $(aws-vault exec $CLUSTER.DBAdministrator -- aws elasticache describe-replication-groups --query "ReplicationGroups[*].ReplicationGroupId" --output text --region $REGION | xargs); do
            echo "  ${redis}"
            # Check for recommended updates
            # updates=$(aws-vault exec $CLUSTER.DBAdministrator -- aws elasticache describe-update-actions --replication-group-id "${redis}" --region $REGION --query "UpdateActions[?UpdateActionStatus=='not-applied'].ServiceUpdateName" --output text)
            # if [[ -n "$updates" ]]; then
            #     echo "    Recommended updates:"
            #     for update in $updates; do
            #         echo "      $update"
            #     done
            # else
            #     echo "    No updates recommended."
            # fi
            echo aws-vault exec $CLUSTER.DBAdministrator -- aws elasticache batch-apply-update-action --service-update-name elasticache-july-patch-update-202507 --replication-group-ids ${redis} --region $REGION
        done
    fi
done