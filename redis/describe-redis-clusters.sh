#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <env>"
    exit 1
fi
env="$1"

: "${DB_PROVISIONER_HOME:?Environment variable DB_PROVISIONER_HOME must be set}"
ENV_FILE="${DB_PROVISIONER_HOME}/envs/${env}-env.yaml"

declare -A seen_clusters

# Collect cluster-region pairs
grep -A1 aws_account_name "$ENV_FILE" | awk '{ print $NF }' | grep -v -- "^--$" | while read -r cluster; do
    read -r region || break

    [[ "$cluster" =~ ^data-compute-.*$ ]] && continue

    if [[ -z "${seen_clusters[$cluster]:-}" ]]; then
        seen_clusters["$cluster"]="$region"

        export CLUSTER="$cluster"
        export REGION="$region"

        echo "Processing cluster: $CLUSTER in region: $REGION"
        redis_json=$(aws-vault exec $CLUSTER.DBAdministrator -- aws elasticache describe-replication-groups --region $REGION 2>&1) || {
            echo "Error accessing AWS for cluster $CLUSTER: $redis_json"
            continue
        }

        if ! echo "$redis_json" | jq -e '.ReplicationGroups' >/dev/null 2>&1; then
            echo "No replication groups found or invalid response for cluster $CLUSTER"
            continue
        fi

        echo
        printf "%-35s %-10s %-12s %-20s %-7s %-10s %-25s\n" "ReplicationGroupId" "Engine" "EngineVersion" "NodeType" "Nodes" "Status" "Cluster"
        while IFS=$'\t' read -r rg_id engine node_type nodes status member_clusters; do
            first_cluster=$(echo "$member_clusters" | awk '{print $1}')
            engine_version=$(aws-vault exec $CLUSTER.DBAdministrator -- aws elasticache describe-cache-clusters --cache-cluster-id "$first_cluster" --region $REGION | jq -r '.CacheClusters[0].EngineVersion // "unknown"')
            printf "%-35s %-10s %-13s %-20s %-7s %-10s %-25s\n" "$rg_id" "$engine" "$engine_version" "$node_type" "$nodes" "$status" "$CLUSTER"
        done < <(echo "$redis_json" | jq -r '.ReplicationGroups[] | [
  .ReplicationGroupId,
  .Engine,
  .CacheNodeType,
  (.NodeGroups[0].NodeGroupMembers | length),
  .Status,
  (.MemberClusters | join(" "))
] | @tsv')
        echo
    fi
done