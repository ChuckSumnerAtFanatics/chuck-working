# sportsbook-prod
aws-vault exec sportsbook-prod.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1-postgresql --region us-east-2 --engine-version 13.19
aws-vault exec sportsbook-prod.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1-postgresql-data-replica --region us-east-2 --engine-version 13.19
aws-vault exec sportsbook-prod.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1-postgresql-read-replica --region us-east-2 --engine-version 13.19
aws-vault exec sportsbook-prod.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1-data-1-postgresql --region us-east-2 --engine-version 13.19
aws-vault exec sportsbook-prod.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1-debezium-1-postgresql --region us-east-2 --engine-version 13.19

aws-vault exec sportsbook-prod.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1-postgresql --region us-east-2 --db-instance-class db.r8g.24xlarge --apply-immediately
aws-vault exec sportsbook-prod.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1-postgresql-data-replica --region us-east-2 --db-instance-class db.r8g.4xlarge --apply-immediately
aws-vault exec sportsbook-prod.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1-postgresql-read-replica --region us-east-2 --db-instance-class db.r8g.16xlarge --apply-immediately
aws-vault exec sportsbook-prod.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1-data-1-postgresql --region us-east-2 --db-instance-class db.r8g.4xlarge --apply-immediately
aws-vault exec sportsbook-prod.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1-debezium-1-postgresql --region us-east-2 --db-instance-class db.r8g.xlarge --apply-immediately

aws-vault exec sportsbook-prod.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier retail-vault-prod-1-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately

# sportsbook-prod-child-az-1
aws-vault exec sportsbook-prod-child-az-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1az-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-prod-child-tn-1
aws-vault exec sportsbook-prod-child-tn-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1tn-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-prod-child-va-1
aws-vault exec sportsbook-prod-child-va-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1va-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-prod-child-oh-1
aws-vault exec sportsbook-prod-child-oh-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1oh-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-prod-child-ma-1
aws-vault exec sportsbook-prod-child-ma-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1ma-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-prod-child-md-1
aws-vault exec sportsbook-prod-child-md-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1md-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-prod-child-co-1
aws-vault exec sportsbook-prod-child-co-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1co-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-prod-child-ky-1
aws-vault exec sportsbook-prod-child-ky-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1ky-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-prod-child-wv-1
aws-vault exec sportsbook-prod-child-wv-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1wv-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
aws-vault exec sportsbook-prod-child-wv-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier payment-ledger-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
#aws-vault exec sportsbook-prod-child-wv-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier rock-fbg-prod-1wv-postgresql --region us-east-1 --engine-version 16.7 --apply-immediately
# sportsbook-prod-child-ct-1
aws-vault exec sportsbook-prod-child-ct-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1ct-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-prod-child-nc-1
aws-vault exec sportsbook-prod-child-nc-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1nc-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-prod-child-nj-1
aws-vault exec sportsbook-prod-child-nj-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1nj-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
#aws-vault exec sportsbook-prod-child-nj-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier rock-fbg-prod-1nj-postgresql --region us-east-1 --engine-version 16.7 --apply-immediately
# sportsbook-prod-child-mi-1
aws-vault exec sportsbook-prod-child-mi-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1mi-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
#aws-vault exec sportsbook-prod-child-mi-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier rock-fbg-prod-1mi-postgresql --region us-east-2 --engine-version 16.7 --apply-immediately
# sportsbook-prod-child-pa-1
aws-vault exec sportsbook-prod-child-pa-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1pa-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
#aws-vault exec sportsbook-prod-child-pa-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier rock-fbg-prod-1pa-postgresql --region us-east-1 --engine-version 16.7 --apply-immediately
# sportsbook-prod-child-il-1
aws-vault exec sportsbook-prod-child-il-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1il-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-prod-child-vt-1
aws-vault exec sportsbook-prod-child-vt-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1vt-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-prod-child-in-1
aws-vault exec sportsbook-prod-child-in-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1in-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-prod-child-ny-1
aws-vault exec sportsbook-prod-child-ny-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1ny-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-prod-child-ia-1
aws-vault exec sportsbook-prod-child-ia-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1ia-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-prod-child-ks-1
aws-vault exec sportsbook-prod-child-ks-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1ks-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-prod-child-wy-1
aws-vault exec sportsbook-prod-child-wy-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1wy-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-prod-child-la-1
aws-vault exec sportsbook-prod-child-la-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1la-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-prod-child-dc-1
aws-vault exec sportsbook-prod-child-dc-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-prod-1dc-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
