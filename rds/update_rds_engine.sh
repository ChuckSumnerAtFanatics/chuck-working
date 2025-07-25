#!/bin/bash

# 13.x -> 13.20
# 14.x -> 14.16
# 16.x -> 16.7
# 17.x -> 17.3

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
for instance in $(aws-vault exec $CLUSTER.AdministratorAccess -- aws rds describe-db-instances --db-instance-identifier ${rds} --region ${REGION} | jq -r '.DBInstances[] | select(.EngineVersion and (.DBInstanceClass | startswith("db.t4g."))) | .DBInstanceIdentifier'); do
          #for instance in $(aws-vault exec $CLUSTER.AdministratorAccess -- aws rds describe-db-instances --db-instance-identifier ${rds} --region ${REGION} | jq -r '.DBInstances[] | select(.EngineVersion) | .DBInstanceIdentifier'); do
          #for instance in $(aws-vault exec $CLUSTER.AdministratorAccess -- aws rds describe-db-instances --db-instance-identifier ${rds} --region ${REGION} | jq -r '.DBInstances[] | select(.EngineVersion | startswith("13.")) | .DBInstanceIdentifier'); do
            #aws-vault exec $CLUSTER.AdministratorAccess -- aws rds describe-db-instances --db-instance-identifier ${instance} --region ${REGION} | jq -r '.DBInstances[] | "  \(.DBInstanceIdentifier): \(.EngineVersion)"'
            aws-vault exec $CLUSTER.AdministratorAccess -- aws rds describe-db-instances --db-instance-identifier ${instance} --region ${REGION} | jq -r '.DBInstances[] | "  \(.DBInstanceIdentifier): \(.EngineVersion) [\(.DBInstanceClass)]"'
            
          done
        done

        # echo ${cluster}
        # for rds in $(aws-vault exec $CLUSTER.AdministratorAccess -- aws rds describe-db-instances --region ${REGION} | jq -r '.DBInstances[].DBInstanceIdentifier'); do
        #   for instance in $(aws-vault exec $CLUSTER.AdministratorAccess -- aws rds describe-db-instances --db-instance-identifier ${rds} --region ${REGION} | jq -r '.DBInstances[] | select(.EngineVersion | startswith("13.")) | .DBInstanceIdentifier'); do
        #     aws-vault exec $CLUSTER.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier ${instance} --region ${REGION} --engine-version "13.19" --apply-immediately
        #   done
        #   for instance in $(aws-vault exec $CLUSTER.AdministratorAccess -- aws rds describe-db-instances --db-instance-identifier ${rds} --region ${REGION} | jq -r '.DBInstances[] | select(.EngineVersion | startswith("14.")) | .DBInstanceIdentifier'); do
        #     aws-vault exec $CLUSTER.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier ${instance} --region ${REGION} --engine-version "14.16" --apply-immediately
        #   done
        #   for instance in $(aws-vault exec $CLUSTER.AdministratorAccess -- aws rds describe-db-instances --db-instance-identifier ${rds} --region ${REGION} | jq -r '.DBInstances[] | select(.EngineVersion | startswith("16.")) | .DBInstanceIdentifier'); do
        #     aws-vault exec $CLUSTER.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier ${instance} --region ${REGION} --engine-version "16.7" --apply-immediately
        #   done
        #   for instance in $(aws-vault exec $CLUSTER.AdministratorAccess -- aws rds describe-db-instances --db-instance-identifier ${rds} --region ${REGION} | jq -r '.DBInstances[] | select(.EngineVersion | startswith("17.")) | .DBInstanceIdentifier'); do
        #     aws-vault exec $CLUSTER.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier ${instance} --region ${REGION} --engine-version "17.3" --apply-immediately
        #   done
        # done
    fi
done