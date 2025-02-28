import psycopg2
import json
from decimal import Decimal

import os
import sys
import argparse
import logging
from typing import Dict, List, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from psycopg2.extras import DictCursor
from psycopg2.pool import SimpleConnectionPool
import yaml  # Import the PyYAML library


def convert_decimal(obj):
    """Convert Decimal objects to float before JSON serialization."""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def assess_replication_health(report: Dict[str, Any]) -> Dict[str, Any]:
    health_status = {
        'overall': 'HEALTHY',
        'issues': []
    }

    for link, lag in report['replication_lag'].items():
        if lag is not None and lag > 1000000:  # More than 1MB behind
            health_status['issues'].append(f"High replication lag in {link}: {lag} bytes")
            health_status['overall'] = 'WARNING'

    for host, status in report['instance_statuses'].items():
        if status.get('inactive_replication', {}).get('inactive_slots'):
            health_status['issues'].append(f"Inactive replication slots on {host}")
            health_status['overall'] = 'WARNING'

        if status.get('schema_differences'):
            health_status['issues'].append(f"Schema differences detected on {host}")
            health_status['overall'] = 'WARNING'

        if 'error' in status:
            health_status['issues'].append(f"Error on {host}: {status['error']}")
            health_status['overall'] = 'CRITICAL'

    if len(health_status['issues']) > 5:
        health_status['overall'] = 'CRITICAL'

    return health_status

def load_config(config_file='config.yaml'):  # Changed default to config.yaml
    with open(config_file, 'r') as f:
        return yaml.safe_load(f)  # Use yaml.safe_load() for YAML

def setup_logging(log_level):
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def handle_exception(e: Exception, context: str) -> None:
    error_message = f"An error occurred during {context}: {str(e)}"
    logging.error(error_message)
    if isinstance(e, psycopg2.Error):
        logging.error(f"Database error details: {e.diag.message_primary}")

# Global connection pool
connection_pools: Dict[str, SimpleConnectionPool] = {}

def get_db_connection(host: str, user: Optional[str] = None, password: Optional[str] = None) -> psycopg2.extensions.connection:
    global connection_pools
    if host not in connection_pools:
        connection_pools[host] = SimpleConnectionPool(
            1, 5,
            host=host,
            port=os.environ.get('PGPORT', 5432),
            database=os.environ.get('PGDATABASE', 'postgres'),
            user=user or os.environ.get('PGUSER', 'postgres'),
            password=password or os.environ.get('PGPASSWORD'),
            cursor_factory=DictCursor
        )
    logging.info(f"Establishing connection to host: {host}")
    return connection_pools[host].getconn()

def discover_replication_topology(
    start_host: str, start_user: str, start_password: str
) -> Dict[str, Any]:
    topology = {"links": {}, "logical_publishers": [], "logical_subscribers": []}
    visited = set()

    def dfs(host: str, user: str, password: str):
        if host in visited:
            return
        visited.add(host)
        logging.info(f"Exploring host: {host}")

        try:
            conn = get_db_connection(host, user, password)
            try:
                with conn.cursor() as cur:
                    # Get logical subscriptions (subscribers)
                    cur.execute("SELECT subname, subconninfo FROM pg_subscription")
                    subscriptions = cur.fetchall()

                    if subscriptions:
                        topology["logical_subscribers"].append(host)

                    for subname, conninfo in subscriptions:
                        pub_host, pub_user, pub_pass = parse_conninfo(conninfo)
                        logging.info(f"{host} subscribes to {pub_host} via {subname}")

                        # Store replication link
                        topology["links"].setdefault(pub_host, []).append(host)

                        # Recursively explore the publisher
                        dfs(pub_host, pub_user, pub_pass)

                    # Check if this host is also a logical publisher
                    cur.execute("""
                        SELECT slot_name, active 
                        FROM pg_replication_slots 
                        WHERE slot_type = 'logical'
                    """)
                    slots = cur.fetchall()

                    if slots:
                        logging.info(f"Host {host} is a logical publisher")
                        topology["logical_publishers"].append(host)

                        # Identify its own subscribers
                        cur.execute("SELECT subname, subconninfo FROM pg_subscription")
                        new_subscriptions = cur.fetchall()

                        for subname, conninfo in new_subscriptions:
                            sub_host, sub_user, sub_pass = parse_conninfo(conninfo)
                            logging.info(
                                f"{host} also acts as a publisher for {sub_host} via {subname}"
                            )

                            # Store additional replication link
                            topology["links"].setdefault(host, []).append(sub_host)

                            # Recursively explore the subscriber (which is also a publisher)
                            dfs(sub_host, sub_user, sub_pass)

            finally:
                connection_pools[host].putconn(conn)
        except psycopg2.Error as e:
            logging.error(f"Error connecting to {host}: {e}")

    dfs(start_host, start_user, start_password)
    return topology

def parse_conninfo(conninfo: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    host = user = password = None
    parts = conninfo.split()
    for part in parts:
        if part.startswith('host='):
            host = part.split('=')[1]
        elif part.startswith('user='):
            user = part.split('=')[1]
        elif part.startswith('password='):
            password = part.split('=')[1]
    return host, user, password

def get_replication_status(host: str) -> Dict[str, Any]:
    status = {"replication_slots": {}, "lagging_slots": []}
    logging.info(f"Getting replication status for host: {host}")

    try:
        conn = get_db_connection(host)
        try:
            with conn.cursor() as cur:
                # Get LSN for the publisher
                cur.execute("SELECT pg_current_wal_lsn()")
                publisher_lsn = cur.fetchone()[0]

                # Get replication slot information
                cur.execute("""
                    SELECT slot_name, 
                        pg_current_wal_lsn() - COALESCE(confirmed_flush_lsn, '0/0') AS lag_bytes, 
                        confirmed_flush_lsn,
                        active
                    FROM pg_replication_slots
                    WHERE slot_type = 'logical'
                """)
                for slot_name, lag_bytes, flush_lsn, active in cur.fetchall():
                    if isinstance(lag_bytes, Decimal):
                        lag_bytes = float(lag_bytes)

                    # Convert bytes to MB, rounding to 2 decimal places
                    lag_mb = round(lag_bytes / 1_048_576, 2)

                    status["replication_slots"][slot_name] = {
                        "flush_lsn": str(
                            flush_lsn
                        ),  # Store as string for JSON compatibility
                        "lag_mb": lag_mb,  # Display lag in MB
                        "active": active,
                    }

                    if lag_mb > 1:  # More than 1MB behind
                        status["lagging_slots"].append(slot_name)

        finally:
            connection_pools[host].putconn(conn)
    except Exception as e:
        handle_exception(e, f"getting replication status for {host}")
        status["error"] = str(e)

    return status

def get_table_sync_status(conn: psycopg2.extensions.connection) -> Dict[str, Any]:
    sync_status = {"mismatched_tables": []}
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT schemaname, relname AS table_name, n_live_tup
                FROM pg_stat_user_tables
            """)
            table_counts = {row[1]: row[2] for row in cur.fetchall()}

            # Compare subscriber table row counts
            cur.execute("""
                SELECT schemaname, relname AS table_name, n_live_tup
                FROM pg_stat_subscription_tables
            """)
            for table, sub_count in cur.fetchall():
                pub_count = table_counts.get(table, None)
                if pub_count and abs(pub_count - sub_count) > 1000:  # Allow small drift
                    sync_status["mismatched_tables"].append(
                        {
                            "table": table,
                            "publisher_rows": pub_count,
                            "subscriber_rows": sub_count,
                            "difference": abs(pub_count - sub_count),
                        }
                    )

    except psycopg2.Error as e:
        logging.error(f"Error getting table sync status: {e}")
        sync_status["error"] = str(e)

    return sync_status

def check_inactive_replication(conn: psycopg2.extensions.connection) -> Dict[str, Any]:
    inactive = {}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT slot_name, active FROM pg_replication_slots WHERE NOT active")
            inactive['inactive_slots'] = cur.fetchall()

            cur.execute("SELECT subname, subenabled FROM pg_subscription WHERE NOT subenabled")
            inactive['disabled_subscriptions'] = cur.fetchall()
    except psycopg2.Error as e:
        logging.error(f"Error checking inactive replication: {e}")
        inactive['error'] = str(e)
    return inactive

def calculate_replication_lag(
    publisher_lsn: str, subscriber_lsn: Optional[str]
) -> Optional[int]:
    if not publisher_lsn or not subscriber_lsn:  # Handle NULL LSNs
        return None
    try:
        publisher_lsn = int(publisher_lsn, 16)
        subscriber_lsn = int(subscriber_lsn, 16)
        return publisher_lsn - subscriber_lsn
    except ValueError:
        return None

def compare_schemas(conn1: psycopg2.extensions.connection, conn2: psycopg2.extensions.connection) -> List[Tuple[str, str, str]]:
    differences = []
    
    def get_schema(conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
            """)
            return cur.fetchall()
    
    schema1 = get_schema(conn1)
    schema2 = get_schema(conn2)
    
    if schema1 != schema2:
        set1 = set(schema1)
        set2 = set(schema2)
        differences = list(set1 ^ set2)
    
    return differences

def generate_replication_report(topology: Dict[str, List[str]], statuses: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    report = {
        "topology": topology,
        "instance_statuses": statuses,
        "replication_lag": {}
    }

    for publisher in topology['logical_publishers']:
        publisher_status = statuses.get(publisher, {})
        if publisher_status.get('is_logical_publisher'):
            for rep_stat in publisher_status.get('logical_replication_stats', []):
                subscriber = rep_stat['client_addr']
                lag = calculate_replication_lag(rep_stat['sent_lsn'], rep_stat['replay_lsn'])
                report['replication_lag'][f"{publisher}->{subscriber}"] = lag

    return report

def get_password():
    return os.environ.get('PGPASSWORD') or input("Enter the password: ")

def process_host(host: str, password: str) -> Tuple[str, Dict[str, Any]]:
    try:
        status = get_replication_status(host)  # Remove the password argument here
        logging.info(f"Successfully processed host: {host}")
        return host, status
    except Exception as e:
        logging.error(f"Error processing host {host}: {str(e)}")
        return host, {"error": str(e)}

def main() -> None:
    parser = argparse.ArgumentParser(description="RDS Replication Overview Tool")
    parser.add_argument("--start-host", help="Starting host for topology discovery (overrides PGHOST)")
    parser.add_argument("--config", default="config.yaml", help="Path to configuration file")  # Changed default to config.yaml
    parser.add_argument("--log-level", choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help="Set the logging level (overrides config file)")
    parser.add_argument("--output", choices=['json', 'csv'],
                        help="Output format for the report (overrides config file)")
    args = parser.parse_args()

    config = load_config(args.config)

    log_level = args.log_level or config['logging']['level']
    setup_logging(log_level)

    start_host = args.start_host or os.environ.get('PGHOST')
    if not start_host:
        logging.error("No start host provided. Use --start-host or set PGHOST environment variable.")
        sys.exit(1)

    logging.info(f"Starting replication overview for host: {start_host}")

    password = get_password()
    if not password:
        logging.error("No password provided. Set PGPASSWORD environment variable or enter it when prompted.")
        sys.exit(1)

    try:
        start_user = os.environ.get('PGUSER', 'postgres')
        password = get_password()
        if not password:
            logging.error("No password provided. Set PGPASSWORD environment variable or enter it when prompted.")
            sys.exit(1)

        logging.info("Discovering replication topology...")
        topology = discover_replication_topology(start_host, start_user, password)
        logging.info("Topology discovery completed")
        logging.debug(f"Discovered topology: {json.dumps(topology, indent=2)}")

        max_workers = config['monitoring']['max_workers']
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_host = {executor.submit(process_host, host, password): host 
                              for host in topology['logical_publishers'] + topology['logical_subscribers']}
            statuses = {}
            for future in as_completed(future_to_host):
                host, status = future.result()
                statuses[host] = status

        report = generate_replication_report(topology, statuses)
        report['health_assessment'] = assess_replication_health(report)

        output_format = args.output or config['output']['default_format']
        if output_format == 'json':
            print(json.dumps(report, indent=2, default=convert_decimal))
            with open(config['output']['report_file'], 'w') as f:
                json.dump(report, f, indent=2, default=convert_decimal)
        elif output_format == 'csv':
            logging.warning("CSV output format is not yet implemented")
        else:
            logging.warning(f"Unsupported output format: {output_format}")

    except Exception as e:
        handle_exception(e, "main execution")
    finally:
        # Close all connection pools
        for pool in connection_pools.values():
            pool.closeall()

if __name__ == "__main__":
    main()
