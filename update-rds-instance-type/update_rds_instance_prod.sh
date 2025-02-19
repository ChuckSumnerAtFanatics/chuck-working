#!/bin/bash
CLUSTER=sportsbook-prod
REGION=us-east-2

instances=(fbg-prod-1-postgresql fbg-prod-1-postgresql-data-replica fbg-prod-1-postgresql-read-replica fbg-prod-1-data-1-postgresql fbg-prod-1-debezium-1-postgresql)

for instance in ${instances[@]}; do
  aws-vault exec $CLUSTER.AdministratorAccess -- aws rds describe-db-instances --db-instance-identifier ${instance} --region ${REGION} | jq -r '.DBInstances[] | "  \(.DBInstanceIdentifier): \(.DBInstanceClass)"'
done

### the actual resizing
#aws-vault exec $CLUSTER.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1-postgresql --region ${REGION} --db-instance-class db.r8g.24xlarge --apply-immediately
#aws-vault exec $CLUSTER.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1-postgresql-data-replica --region ${REGION} --db-instance-class db.r8g.4xlarge --apply-immediately
#aws-vault exec $CLUSTER.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1-postgresql-read-replica --region ${REGION} --db-instance-class db.r8g.16xlarge --apply-immediately
#aws-vault exec $CLUSTER.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1-data-1-postgresql --region ${REGION} --db-instance-class db.r8g.4xlarge --apply-immediately
#aws-vault exec $CLUSTER.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1-debezium-1-postgresql --region ${REGION} --db-instance-class db.r8g.xlarge --apply-immediately
