import psycopg2
from psycopg2.extras import DictCursor
import argparse
import yaml

# The config.yaml file should look like this:
# server_a:
#   host: 'hostname'
#   port: 5432
#   dbname: 'dbname'x
#   user: 'user'
#   password: 'password'
# server_b:
#   host: 'hostname'
#   port: 5432
#   dbname: 'dbname'
#   user: 'user'
#   password: 'password'

# Load configuration from YAML file
with open('config.yaml', 'r') as file:
    config = yaml.safe_load(file)

server_a_config = config['server_a']
server_b_config = config['server_b']

# Create variables for each server host stripping everything after the first period
server_a_short_host = server_a_config['host'].split('.')[0]
server_b_short_host = server_b_config['host'].split('.')[0]

# Print the hosts for each server
print(f"Server A Host: {server_a_short_host}")
print(f"Server B Host: {server_b_short_host}")

def get_tables_and_columns(conn, schema):
    """
    Retrieve tables and their columns (with data types) from the given schema.
    Returns a structure like:
    {
        table_name: {
            'columns': {
                column_name: data_type
            },
            'order': [column_name1, column_name2 ...]  # column order
        }
    }
    """
    query = """
    SELECT table_name, column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = %s
    ORDER BY table_name, ordinal_position;
    """

    schema_info = {}
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute(query, (schema,))
        for row in cur:
            t = row['table_name']
            c = row['column_name']
            dt = row['data_type']
            if t not in schema_info:
                schema_info[t] = {'columns': {}, 'order': []}
            schema_info[t]['columns'][c] = dt
            schema_info[t]['order'].append(c)
    return schema_info

def get_indexes(conn, schema):
    """
    Retrieve indexes and their definitions.
    Returns:
    {
        table_name: {
            index_name: index_def (CREATE INDEX ... )
        }
    }
    """
    query = """
    SELECT tablename, indexname, indexdef
    FROM pg_indexes
    WHERE schemaname = %s;
    """
    indexes = {}
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute(query, (schema,))
        for row in cur:
            t = row['tablename']
            i = row['indexname']
            d = row['indexdef']
            if t not in indexes:
                indexes[t] = {}
            indexes[t][i] = d
    return indexes

def get_constraints(conn, schema):
    """
    Retrieve constraints and their definitions using pg_get_constraintdef.
    Returns:
    {
       table_name: {
           constraint_name: constraint_definition
       }
    }
    """
    query = """
    SELECT
        t.relname as table_name,
        c.conname,
        pg_get_constraintdef(c.oid, true) as condef
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = c.connamespace
    WHERE n.nspname = %s
    ORDER BY t.relname, c.conname;
    """
    constraints = {}
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute(query, (schema,))
        for row in cur:
            t = row['table_name']
            cn = row['conname']
            cd = row['condef']
            if t not in constraints:
                constraints[t] = {}
            constraints[t][cn] = cd
    return constraints

def generate_create_table_sql(table_name, table_info, schema):
    """
    Generate a CREATE TABLE statement from table_info structure.
    """
    cols = []
    for c in table_info['order']:
        dt = table_info['columns'][c]
        cols.append(f"    {c} {dt}")
    cols_str = ",\n".join(cols)
    return f"CREATE TABLE {schema}.{table_name} (\n{cols_str}\n);"

def main():
    parser = argparse.ArgumentParser(description='Compare PostgreSQL schemas between two servers and generate SQL sync statements.')
    parser.add_argument('--schema-a', default='public', help='Schema name in Server A (default: public)')
    parser.add_argument('--schema-b', default='public', help='Schema name in Server B (default: public)')
    args = parser.parse_args()

    schema_a_name = args.schema_a
    schema_b_name = args.schema_b

    conn_a = psycopg2.connect(**server_a_config)
    conn_b = psycopg2.connect(**server_b_config)

    try:
        schema_a = get_tables_and_columns(conn_a, schema_a_name)
        schema_b = get_tables_and_columns(conn_b, schema_b_name)

        indexes_a = get_indexes(conn_a, schema_a_name)
        indexes_b = get_indexes(conn_b, schema_b_name)

        constraints_a = get_constraints(conn_a, schema_a_name)
        constraints_b = get_constraints(conn_b, schema_b_name)

        differences = []
        sync_sql = []

        # Compare tables
        # Tables in A not in B
        for table in sorted(schema_a.keys()):
            if table not in schema_b:
                differences.append(f"Table {table} missing in {server_b_short_host}.")
                # Generate CREATE TABLE
                create_sql = generate_create_table_sql(table, schema_a[table], schema_b_name)
                sync_sql.append(create_sql)
            else:
                # Compare columns
                cols_a = schema_a[table]['columns']
                cols_b = schema_b[table]['columns']

                # Columns in A not in B
                for col, dt_a in cols_a.items():
                    if col not in cols_b:
                        differences.append(f"Column {table}.{col} missing in {server_b_short_host}.")
                        sync_sql.append(f"ALTER TABLE {schema_b_name}.{table} ADD COLUMN {col} {dt_a};")
                    else:
                        dt_b = cols_b[col]
                        if dt_a != dt_b:
                            differences.append(f"Column {table}.{col} type differs: {server_a_short_host}({dt_a}) vs {server_b_short_host}({dt_b})")
                            sync_sql.append(f"ALTER TABLE {schema_b_name}.{table} ALTER COLUMN {col} TYPE {dt_a};")

                # Columns in B not in A
                for col in cols_b:
                    if col not in cols_a:
                        differences.append(f"Column {table}.{col} is extra in {server_b_short_host} (not in {server_a_short_host}).")
                        # Optionally remove from B:
                        # sync_sql.append(f"ALTER TABLE {schema_b_name}.{table} DROP COLUMN {col};")

        # Tables in B not in A
        for table in sorted(schema_b.keys()):
            if table not in schema_a:
                differences.append(f"Table {table} is extra in {server_b_short_host} (not in {server_a_short_host}).")
                # Optionally drop it from B:
                # sync_sql.append(f"DROP TABLE {schema_b_name}.{table};")

        # Compare indexes
        for table in sorted(schema_a.keys()):
            idx_a = indexes_a.get(table, {})
            idx_b = indexes_b.get(table, {})
            # Indexes in A not in B
            for ixname, ixdef in idx_a.items():
                if ixname not in idx_b:
                    differences.append(f"Index {ixname} on {table} missing in {server_b_short_host}.")
                    # ixdef typically looks like "CREATE INDEX indexname ON schema.table ..."
                    # Just run it as-is, or replace schema with schema_b_name if needed:
                    # Ensure the schema name in ixdef is correct. If ixdef includes the original schema,
                    # we may need to adjust it.
                    # Typically ixdef is something like:
                    # CREATE INDEX indexname ON public.table (col)
                    # We can try a simple replacement:
                    ixdef_b = ixdef.replace(f" ON {schema_a_name}.", f" ON {schema_b_name}.")
                    sync_sql.append(ixdef_b)

            # Indexes in B not in A
            for ixname in idx_b.keys():
                if ixname not in idx_a:
                    differences.append(f"Index {ixname} on {table} is extra in {server_b_short_host}.")
                    # Optionally:
                    # sync_sql.append(f"DROP INDEX {schema_b_name}.{ixname};")

        # Compare constraints
        for table in sorted(constraints_a.keys()):
            con_a = constraints_a[table]
            con_b = constraints_b.get(table, {})
            for conname, condef in con_a.items():
                if conname not in con_b:
                    differences.append(f"Constraint {conname} on {table} missing in {server_b_short_host}.")
                    sync_sql.append(f"ALTER TABLE {schema_b_name}.{table} ADD CONSTRAINT {conname} {condef};")

            # Constraints in B not in A
            for conname in constraints_b.get(table, {}):
                if conname not in con_a:
                    differences.append(f"Constraint {conname} on {table} is extra in {server_b_short_host}.")
                    # Optionally:
                    # sync_sql.append(f"ALTER TABLE {schema_b_name}.{table} DROP CONSTRAINT {conname};")

        # Constraints on tables not in A
        for table in constraints_b:
            if table not in constraints_a:
                for conname in constraints_b[table]:
                    differences.append(f"Constraint {conname} on {table} is extra in {server_b_short_host} (table missing in {server_a_short_host}).")
                    # Optionally:
                    # sync_sql.append(f"ALTER TABLE {schema_b_name}.{table} DROP CONSTRAINT {conname};")

        # Print differences and suggested SQL
        if not differences:
            print("No differences found between the two schemas.")
        else:
            print("Differences found:")
            for diff in differences:
                print(" - " + diff)

            print("\nSQL statements to apply to %s to match %s:" % (server_b_short_host, server_a_short_host))
            for stmt in sync_sql:
                print(stmt)

    finally:
        conn_a.close()
        conn_b.close()

if __name__ == '__main__':
    main()