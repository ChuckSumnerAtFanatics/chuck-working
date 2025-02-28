import psycopg2
import json
import os
import sys
import argparse
import yaml
from psycopg2.extras import DictCursor
from psycopg2.pool import SimpleConnectionPool
import logging
from typing import Dict, List, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

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

def load_config(config_file='config.yaml'):
    with open(config_file, 'r') as f:
        return yaml.safe_load(f)

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

def get_db_connection(host: str) -> psycopg2.extensions.connection:
    global connection_pools
    if host not in connection_pools:
        connection_pools[host] = SimpleConnectionPool(
            1, 5,
            host=host,
            port=os.environ.get('PGPORT', 5432),
            database=os.environ.get('PGDATABASE', 'postgres'),
            user=os.environ.get('PGUSER', 'postgres'),
            password=os.environ.get('PGPASSWORD'),
            cursor_factory=DictCursor
        )
    logging.info(f"Establishing connection to host: {host}")
    return connection_pools[host].getconn()

def discover_replication_topology(start_host: str, password: str) -> Dict[str, List[str]]:
    topology = {'publishers': [], 'subscribers': []}
    visited = set()

    def dfs(host: str) -> None:
        if host in visited:
            return
        visited.add(host)
        logging.info(f"Exploring host: {host}")

        try:
            conn = get_db_connection(host)
            try:
                with conn.cursor() as cur:
                    # Check if it's a publisher
                    cur.execute("SELECT * FROM pg_replication_slots")
                    if cur.fetchone():
                        logging.info(f"Host {host} is a publisher")
                        topology['publishers'].append(host)
                        
                        # Get subscribers
                        cur.execute("SELECT client_addr FROM pg_stat_replication")
                        subscribers = [row['client_addr'] for row in cur.fetchall() if row['client_addr']]
                        logging.info(f"Found subscribers for {host}: {subscribers}")
                        topology['subscribers'].extend(subscribers)
                        
                        # Recursively check subscribers
                        for subscriber in subscribers:
                            dfs(subscriber)
                    else:
                        logging.info(f"Host {host} is a subscriber")
                        topology['subscribers'].append(host)
                        
                        # Check if it's subscribed to any publisher
                        cur.execute("SELECT subconninfo FROM pg_subscription")
                        for row in cur.fetchall():
                            conninfo = row['subconninfo']
                            publisher = parse_conninfo(conninfo)
                            if publisher:
                                logging.info(f"Found publisher for {host}: {publisher}")
                                topology['publishers'].append(publisher)
                                dfs(publisher)
            finally:
                connection_pools[host].putconn(conn)
        except psycopg2.Error as e:
            logging.error(f"Error connecting to {host}: {e}")

    dfs(start_host)
    return topology

def parse_conninfo(conninfo: str) -> Optional[str]:
    parts = conninfo.split()
    for part in parts:
        if part.startswith('host='):
            return part.split('=')[1]
    return None

def get_replication_status(host: str) -> Dict[str, Any]:
    status = {}
    logging.info(f"Getting replication status for host: {host}")
    try:
        conn = get_db_connection(host)
        try:
            with conn.cursor() as cur:
                # Check if it's a publisher
                cur.execute("SELECT * FROM pg_replication_slots")
                is_publisher = cur.fetchone() is not None
                status['is_publisher'] = is_publisher
                logging.info(f"Host {host} is {'a publisher' if is_publisher else 'not a publisher'}")

                if is_publisher:
                    logging.info(f"Fetching replication slots for {host}")
                    cur.execute("SELECT slot_name, active, restart_lsn FROM pg_replication_slots")
                    status['replication_slots'] = cur.fetchall()

                    logging.info(f"Fetching replication stats for {host}")
                    cur.execute("SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn FROM pg_stat_replication")
                    status['replication_stats'] = cur.fetchall()

                    # Compare schema with subscribers
                    for subscriber in status['replication_stats']:
                        subscriber_host = subscriber['client_addr']
                        logging.info(f"Comparing schema between {host} and {subscriber_host}")
                        subscriber_conn = get_db_connection(subscriber_host)
                        try:
                            status['schema_differences'] = compare_schemas(conn, subscriber_conn)
                        finally:
                            connection_pools[subscriber_host].putconn(subscriber_conn)
                else:
                    logging.info(f"Fetching subscriptions for {host}")
                    cur.execute("SELECT subname, subenabled, subconninfo FROM pg_subscription")
                    status['subscriptions'] = cur.fetchall()

                logging.info(f"Fetching table sync status for {host}")
                status['table_sync_status'] = get_table_sync_status(conn)
                logging.info(f"Checking inactive replication for {host}")
                status['inactive_replication'] = check_inactive_replication(conn)
        finally:
            connection_pools[host].putconn(conn)
    except Exception as e:
        handle_exception(e, f"getting replication status for {host}")
        status['error'] = str(e)

    return status

def get_table_sync_status(conn: psycopg2.extensions.connection) -> Dict[str, Any]:
    sync_status = {}
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT schemaname, tablename, 
                       (pg_size_pretty(pg_total_relation_size('"' || schemaname || '"."' || tablename || '"'))),
                       n_live_tup, n_dead_tup, last_vacuum, last_analyze
                FROM pg_stat_user_tables
                ORDER BY pg_total_relation_size('"' || schemaname || '"."' || tablename || '"') DESC
            """)
            sync_status['tables'] = cur.fetchall()
    except psycopg2.Error as e:
        logging.error(f"Error getting table sync status: {e}")
        sync_status['error'] = str(e)
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

def calculate_replication_lag(publisher_lsn: str, subscriber_lsn: str) -> Optional[int]:
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

    for publisher in topology['publishers']:
        publisher_status = statuses.get(publisher, {})
        if publisher_status.get('is_publisher'):
            for rep_stat in publisher_status.get('replication_stats', []):
                subscriber = rep_stat['client_addr']
                lag = calculate_replication_lag(rep_stat['sent_lsn'], rep_stat['replay_lsn'])
                report['replication_lag'][f"{publisher}->{subscriber}"] = lag

    return report

def get_password():
    return os.environ.get('PGPASSWORD') or input("Enter the password: ")

def process_host(host: str, password: str) -> Tuple[str, Dict[str, Any]]:
    try:
        status = get_replication_status(host, password)
        logging.info(f"Successfully processed host: {host}")
        return host, status
    except Exception as e:
        logging.error(f"Error processing host {host}: {str(e)}")
        return host, {"error": str(e)}

def main() -> None:
    parser = argparse.ArgumentParser(description="RDS Replication Overview Tool")
    parser.add_argument("--start-host", help="Starting host for topology discovery (overrides PGHOST)")
    parser.add_argument("--config", default="config.yaml", help="Path to configuration file")
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
        logging.info("Discovering replication topology...")
        topology = discover_replication_topology(start_host, password)
        logging.info("Topology discovery completed")
        logging.debug(f"Discovered topology: {json.dumps(topology, indent=2)}")

        max_workers = config['monitoring']['max_workers']
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_host = {executor.submit(process_host, host): host 
                              for host in topology['publishers'] + topology['subscribers']}
            statuses = {}
            for future in as_completed(future_to_host):
                host, status = future.result()
                statuses[host] = status

        report = generate_replication_report(topology, statuses)
        report['health_assessment'] = assess_replication_health(report)

        output_format = args.output or config['output']['default_format']
        if output_format == 'json':
            print(json.dumps(report, indent=2))
            with open(config['output']['report_file'], 'w') as f:
                json.dump(report, f, indent=2)
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
