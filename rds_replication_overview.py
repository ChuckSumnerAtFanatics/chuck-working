import psycopg2
import json
from psycopg2.extras import DictCursor
from psycopg2.pool import SimpleConnectionPool
import logging
from typing import Dict, List, Any, Optional

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Global connection pool
connection_pools: Dict[str, SimpleConnectionPool] = {}

def get_db_connection(host: str, password: str) -> psycopg2.extensions.connection:
    global connection_pools
    if host not in connection_pools:
        connection_pools[host] = SimpleConnectionPool(
            1, 5,
            host=host,
            database="postgres",
            user="postgres",
            password=password,
            cursor_factory=DictCursor
        )
    return connection_pools[host].getconn()

def discover_replication_topology(start_host: str, password: str) -> Dict[str, List[str]]:
    topology = {'publishers': [], 'subscribers': []}
    visited = set()

    def dfs(host: str) -> None:
        if host in visited:
            return
        visited.add(host)

        try:
            conn = get_db_connection(host, password)
            try:
                with conn.cursor() as cur:
                    # Check if it's a publisher
                    cur.execute("SELECT * FROM pg_replication_slots")
                    if cur.fetchone():
                        topology['publishers'].append(host)
                        
                        # Get subscribers
                        cur.execute("SELECT client_addr FROM pg_stat_replication")
                        subscribers = [row['client_addr'] for row in cur.fetchall() if row['client_addr']]
                        topology['subscribers'].extend(subscribers)
                        
                        # Recursively check subscribers
                        for subscriber in subscribers:
                            dfs(subscriber)
                    else:
                        topology['subscribers'].append(host)
                        
                        # Check if it's subscribed to any publisher
                        cur.execute("SELECT subconninfo FROM pg_subscription")
                        for row in cur.fetchall():
                            conninfo = row['subconninfo']
                            publisher = parse_conninfo(conninfo)
                            if publisher:
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

def get_replication_status(host: str, password: str) -> Dict[str, Any]:
    status = {}
    try:
        conn = get_db_connection(host, password)
        try:
            with conn.cursor() as cur:
                # Check if it's a publisher
                cur.execute("SELECT * FROM pg_replication_slots")
                is_publisher = cur.fetchone() is not None
                status['is_publisher'] = is_publisher

                if is_publisher:
                    cur.execute("""
                        SELECT slot_name, active, restart_lsn
                        FROM pg_replication_slots
                    """)
                    status['replication_slots'] = cur.fetchall()

                    cur.execute("""
                        SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn
                        FROM pg_stat_replication
                    """)
                    status['replication_stats'] = cur.fetchall()
                else:
                    cur.execute("""
                        SELECT subname, subenabled, subconninfo
                        FROM pg_subscription
                    """)
                    status['subscriptions'] = cur.fetchall()

                status['table_sync_status'] = get_table_sync_status(conn)
                status['inactive_replication'] = check_inactive_replication(conn)
        finally:
            connection_pools[host].putconn(conn)
    except psycopg2.Error as e:
        logging.error(f"Error getting replication status for {host}: {e}")
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

def main() -> None:
    start_host = input("Enter the starting host: ")
    password = input("Enter the password: ")

    try:
        topology = discover_replication_topology(start_host, password)
        
        statuses = {}
        for host in topology['publishers'] + topology['subscribers']:
            statuses[host] = get_replication_status(host, password)

        report = generate_replication_report(topology, statuses)

        print(json.dumps(report, indent=2))

        # Optionally, save the report to a file
        with open('replication_report.json', 'w') as f:
            json.dump(report, f, indent=2)
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    finally:
        # Close all connection pools
        for pool in connection_pools.values():
            pool.closeall()

if __name__ == "__main__":
    main()
