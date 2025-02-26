export AWS_PAGER=""
# sportsbook-cert
aws-vault exec sportsbook-cert.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1-data-1-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
aws-vault exec sportsbook-cert.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1-debezium-1-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
aws-vault exec sportsbook-cert.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
aws-vault exec sportsbook-cert.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1-postgresql-data-replica --region us-east-2 --engine-version 13.19 --apply-immediately
aws-vault exec sportsbook-cert.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1-postgresql-read-replica --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-1
aws-vault exec sportsbook-cert-child-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1c-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-tn-1
aws-vault exec sportsbook-cert-child-tn-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1tn-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-va-1
aws-vault exec sportsbook-cert-child-va-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1va-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-oh-1
aws-vault exec sportsbook-cert-child-oh-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1oh-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-ma-1
aws-vault exec sportsbook-cert-child-ma-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1ma-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-md-1
aws-vault exec sportsbook-cert-child-md-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1md-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-mi-1
aws-vault exec sportsbook-cert-child-mi-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1mi-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-co-1
aws-vault exec sportsbook-cert-child-co-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1co-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-pa-1
aws-vault exec sportsbook-cert-child-pa-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1pa-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-nj-1
aws-vault exec sportsbook-cert-child-nj-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1nj-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-ks-1
aws-vault exec sportsbook-cert-child-ks-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1ks-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-ky-1
aws-vault exec sportsbook-cert-child-ky-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1ky-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-wv-1
aws-vault exec sportsbook-cert-child-wv-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1wv-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-ct-1
aws-vault exec sportsbook-cert-child-ct-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1ct-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-nc-1
aws-vault exec sportsbook-cert-child-nc-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1nc-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-ia-1
aws-vault exec sportsbook-cert-child-ia-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1ia-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-ny-1
aws-vault exec sportsbook-cert-child-ny-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1ny-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-vt-1
aws-vault exec sportsbook-cert-child-vt-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1vt-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-il-1
aws-vault exec sportsbook-cert-child-il-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1il-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-in-1
aws-vault exec sportsbook-cert-child-in-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1in-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-az-1
aws-vault exec sportsbook-cert-child-az-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1az-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-wy-1
aws-vault exec sportsbook-cert-child-wy-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1wy-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-la-1
aws-vault exec sportsbook-cert-child-la-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1la-postgresql --region us-east-2 --engine-version 13.19 --apply-immediately
# sportsbook-cert-child-dc-1
aws-vault exec sportsbook-cert-child-dc-1.AdministratorAccess -- aws rds modify-db-instance --db-instance-identifier fbg-cert-1dc-postgresql --region us-east-1 --engine-version 13.19 --apply-immediately
