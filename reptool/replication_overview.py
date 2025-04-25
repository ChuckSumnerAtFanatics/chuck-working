#! /Users/chuck.sumner/workspace/venvs/pypg/bin/python

import os
import re
import sys
import json
import yaml
import logging
import argparse
import datetime
from decimal import Decimal
from typing import Dict, List, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
from psycopg2.extras import DictCursor
from psycopg2.pool import SimpleConnectionPool
from pygments import highlight
from pygments.lexers import JsonLexer
from pygments.formatters import Terminal256Formatter


def convert_decimal(obj):
    """Convert Decimal objects to float before JSON serialization."""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def assess_replication_health(report: Dict[str, Any]) -> Dict[str, Any]:
    health_status = {
        'overall': 'HEALTHY',
        'issues': [],
        'recommendations': set()  # Using a set to avoid duplicates
    }
    
    # Track affected slots by issue type
    slots_with_lag = []
    inactive_slots = []
    slot_states = {}  # Track slot states for reporting
    
    # Helper function to get shortened hostname
    def get_short_hostname(host):
        if '.' in host:
            return host.split('.')[0]
        return host
    
    # Check for slot lag issues
    for host, status in report['instance_statuses'].items():
        short_host = get_short_hostname(host)
        for slot_name, slot_info in status.get('replication_slots', {}).items():
            # Track the connection state of each slot
            if slot_info.get('connection_state'):
                slot_states[slot_name] = slot_info['connection_state']
            elif slot_info.get('active') is False:
                slot_states[slot_name] = 'inactive'
            else:
                slot_states[slot_name] = 'unknown'
                
            if slot_info.get('lag_mb', 0) > 100:  # More than 100MB behind
                health_status['issues'].append(f"Critical replication lag in slot {slot_name} on {short_host}: {slot_info['lag']} ({slot_info['lag_mb']:.2f} MB), state: {slot_states[slot_name]}")
                slots_with_lag.append((slot_name, host))
                health_status['overall'] = 'CRITICAL'
            elif slot_info.get('lag_mb', 0) > 10:  # More than 10MB behind
                health_status['issues'].append(f"High replication lag in slot {slot_name} on {short_host}: {slot_info['lag']} ({slot_info['lag_mb']:.2f} MB), state: {slot_states[slot_name]}")
                slots_with_lag.append((slot_name, host))
                if health_status['overall'] != 'CRITICAL':
                    health_status['overall'] = 'WARNING'
    
    # Check for WAL generation rate issues
    high_wal_hosts = []
    for host, status in report['instance_statuses'].items():
        short_host = get_short_hostname(host)
        wal_rate_mb = status.get('wal_generation_rate_mb_per_sec', 0)
        if wal_rate_mb > 10:  # More than 10MB/s
            health_status['issues'].append(f"High WAL generation rate on {short_host}: {wal_rate_mb:.2f}MB/s")
            high_wal_hosts.append(short_host)
            if health_status['overall'] != 'CRITICAL':
                health_status['overall'] = 'WARNING'
    
    # Check for inactive replication
    for host, status in report['instance_statuses'].items():
        short_host = get_short_hostname(host)
        inactive_info = status.get('inactive_replication', {})
        
        for slot in inactive_info.get('inactive_slots', []):
            if isinstance(slot, dict):
                slot_name = slot['name']
                slot_desc = f"{slot_name} ({slot['retained_wal']} WAL retained)"
            else:
                # Handle old format for backward compatibility
                slot_name = slot[0]
                slot_desc = slot_name
                
            health_status['issues'].append(f"Inactive replication slot {slot_desc} on {short_host}")
            inactive_slots.append((slot_name, host))
            if health_status['overall'] != 'CRITICAL':
                health_status['overall'] = 'WARNING'
    
    # Add consolidated recommendations with state information (avoiding duplicates)
    if slots_with_lag:
        if len(slots_with_lag) <= 3:
            for slot_name, host in slots_with_lag:
                short_host = get_short_hostname(host)
                state = slot_states.get(slot_name, 'unknown')
                health_status['recommendations'].add(
                    f"Check for blocking transactions on subscriber connected to {slot_name} on {short_host} (state: {state})"
                )
        else:
            # Group lagging slots by state
            by_state = {}
            for slot_name, host in slots_with_lag:
                state = slot_states.get(slot_name, 'unknown')
                by_state.setdefault(state, []).append(slot_name)
            
            for state, slots in by_state.items():
                slot_list = ", ".join(slots[:3])
                if len(slots) > 3:
                    slot_list += f" and {len(slots) - 3} more"
                health_status['recommendations'].add(
                    f"Check for blocking transactions on subscribers in {state} state: {slot_list}"
                )
            
    if inactive_slots:
        if len(inactive_slots) <= 3:
            for slot_name, host in inactive_slots:
                short_host = get_short_hostname(host)
                health_status['recommendations'].add(
                    f"Check if the subscriber connected to {slot_name} on {short_host} is down or reactivate the slot"
                )
        else:
            slot_list = ", ".join([name for name, _ in inactive_slots[:3]])
            if len(inactive_slots) > 3:
                slot_list += f" and {len(inactive_slots) - 3} more"
            health_status['recommendations'].add(f"Inactive replication slots detected: {slot_list}")
            health_status['recommendations'].add("Check if subscribers are down or reactivate slots if needed")
    
    # Add a summary of slot states if there are any issues
    if slots_with_lag or inactive_slots:
        state_counts = {}
        for state in slot_states.values():
            state_counts[state] = state_counts.get(state, 0) + 1
        
        state_summary = "; ".join([f"{count} slots in '{state}' state" for state, count in sorted(state_counts.items())])
        health_status['recommendations'].add(f"Connection state summary: {state_summary}")
        
        # Add specific recommendations based on connection states (just once per state)
        state_recommendations = {
            'startup': "Startup state indicates subscribers are initializing connections. If stuck in this state, check for network connectivity issues.",
            'catchup': "Catchup state means subscribers are actively catching up with WAL. If persistently lagging, check subscriber server resources.",
            'streaming': "Streaming is the normal operating state. High lag in this state may indicate insufficient resources on subscribers.",
            'backup': "Backup state indicates a backup operation is in progress. This may temporarily increase replication lag.",
            'stopping': "Stopping state means replication is being terminated. Check if this is intentional or if there's an error on subscribers.",
            'inactive': "Inactive slots are not currently connected. Check if the subscriber service is running and has network connectivity.",
            'unknown': "Unknown state could indicate connection issues or permission problems. Check subscription status on both ends."
        }
        
        # Add only one recommendation per state that exists in the topology
        for state in sorted(set(slot_states.values())):
            if state in state_recommendations:
                health_status['recommendations'].add(f"For {state} slots: {state_recommendations[state]}")
    
    # Convert the set back to a list before returning, and sort the recommendations
    health_status['recommendations'] = sorted(list(health_status['recommendations']))
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
    start_host: str, start_user: str, start_password: str, reuse_connections: bool = True
) -> Dict[str, Any]:
    topology = {"links": {}, "logical_publishers": [], "logical_subscribers": []}
    visited = set()
    link_pairs = set()
    connection_cache = {}  # Store connections to reuse

    def dfs(host: str, user: str, password: str):
        if host in visited:
            return
        visited.add(host)
        logging.info(f"Exploring host: {host}")

        try:
            # Reuse existing connection if available
            if reuse_connections and host in connection_cache:
                conn = connection_cache[host]
            else:
                conn = get_db_connection(host, user, password)
                # Set autocommit to True here to avoid transaction blocks
                conn.autocommit = True
                if reuse_connections:
                    connection_cache[host] = conn
            
            try:
                with conn.cursor() as cur:
                    # Get logical subscriptions (subscribers)
                    cur.execute("SELECT subname, subconninfo FROM pg_subscription")
                    subscriptions = cur.fetchall()

                    if subscriptions and host not in topology["logical_subscribers"]:
                        topology["logical_subscribers"].append(host)

                    for subname, conninfo in subscriptions:
                        pub_host, pub_user, pub_pass = parse_conninfo(conninfo)
                        logging.info(f"{host} subscribes to {pub_host} via {subname}")

                        # Store replication link only if not already recorded
                        link_pair = (pub_host, host)
                        if link_pair not in link_pairs:
                            link_pairs.add(link_pair)
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

                    if slots and host not in topology["logical_publishers"]:
                        logging.info(f"Host {host} is a logical publisher")
                        topology["logical_publishers"].append(host)

            finally:
                if not reuse_connections:
                    connection_pools[host].putconn(conn)
                    
        except psycopg2.Error as e:
            logging.error(f"Error connecting to {host}: {e}")

    dfs(start_host, start_user, start_password)
    
    # Return both topology and connections for reuse
    if reuse_connections:
        return topology, connection_cache
    return topology, {}

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

def _get_current_lsn(cur, status, host):
    try:
        cur.execute("SELECT pg_current_wal_lsn()")
        publisher_lsn = cur.fetchone()[0]
        status["current_lsn"] = str(publisher_lsn)
    except Exception as e:
        logging.warning(f"Could not get current LSN for {host}: {e}")
        status["current_lsn"] = "unknown"

def _get_wal_generation_rate(cur, status, host):
    try:
        cur.execute("SELECT pg_current_wal_lsn() AS start_lsn")
        start_lsn = cur.fetchone()['start_lsn']
        
        cur.execute("SELECT pg_sleep(1)")
        
        cur.execute("SELECT pg_current_wal_lsn() AS end_lsn, pg_wal_lsn_diff(pg_current_wal_lsn(), %s) AS diff", 
                   (start_lsn,))
        row = cur.fetchone()
        status["wal_generation_rate_bytes_per_sec"] = row['diff']
        status["wal_generation_rate_mb_per_sec"] = row['diff'] / (1024 * 1024)
    except Exception as e:
        logging.warning(f"Could not calculate WAL generation rate for {host}: {e}")
        status["wal_generation_rate_bytes_per_sec"] = 0
        status["wal_generation_rate_mb_per_sec"] = 0

def _get_replication_slots(cur, status, host, decoded_temporal_slots):
    try:
        cur.execute("""
            SELECT 
                rs.slot_name, 
                pg_wal_lsn_diff(pg_current_wal_lsn(), rs.confirmed_flush_lsn) as lag_bytes,
                rs.confirmed_flush_lsn,
                rs.active,
                pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), rs.confirmed_flush_lsn)) as lag_pretty,
                pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), rs.restart_lsn)) as retained_wal_size,
                sr.application_name,
                sr.client_addr,
                sr.usename as connected_user,
                sr.state as connection_state,
                rs.plugin
            FROM pg_replication_slots rs
            LEFT JOIN pg_stat_replication sr ON 
                rs.slot_name = sr.application_name
            WHERE rs.slot_type = 'logical'
        """)

        slots = cur.fetchall()
        status["replication_slots"] = {}
        status["lagging_slots"] = []
        
        for slot in slots:
            slot_info = dict(slot)
            if slot_info.get('lag_bytes') is not None:
                slot_info['lag_mb'] = slot_info['lag_bytes'] / (1024 * 1024)
                slot_info['lag'] = slot_info['lag_pretty']
                slot_info.pop('lag_bytes', None)
                slot_info.pop('lag_pretty', None)

            # Merge decoded temporal slot info if applicable
            if slot_info['slot_name'] in decoded_temporal_slots:
                slot_info.update(decoded_temporal_slots[slot_info['slot_name']])

            status["replication_slots"][slot_info['slot_name']] = slot_info
            
            if slot_info.get('lag_mb', 0) > 1:
                status["lagging_slots"].append(slot_info['slot_name'])
    except Exception as e:
        logging.warning(f"Could not get replication slot information for {host}: {e}")
        status["replication_slots"] = {}
        status["lagging_slots"] = []

def _get_subscription_ownership(cur, status, host):
    try:
        cur.execute("""
            SELECT 
                sub.subname, 
                roles.rolname as owner
            FROM pg_subscription sub
            JOIN pg_roles roles ON sub.subowner = roles.oid
        """)
        
        sub_owners = {row['subname']: row['owner'] for row in cur.fetchall()}
        
        for slot_name, slot_info in status["replication_slots"].items():
            if slot_name in sub_owners:
                slot_info['owner'] = sub_owners[slot_name]
                slot_info['owner_source'] = 'subscription_owner'
    except Exception as e:
        logging.warning(f"Could not get subscription ownership info for {host}: {e}")

def _check_inactive_replication(cur, status, host):
    try:
        inactive = {
            "inactive_slots": [],
            "disabled_subscriptions": []
        }
        
        cur.execute("""
            SELECT 
                slot_name, 
                slot_type,
                pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal
            FROM pg_replication_slots 
            WHERE NOT active
        """)
        
        for row in cur.fetchall():
            inactive['inactive_slots'].append({
                "name": row[0],
                "type": row[1],
                "retained_wal": row[2]
            })

        cur.execute("""
            SELECT 
                subname, 
                subslotname
            FROM pg_subscription 
            WHERE NOT subenabled
        """)
        
        for row in cur.fetchall():
            inactive['disabled_subscriptions'].append({
                "name": row[0],
                "slot_name": row[1]
            })
        
        status["inactive_replication"] = inactive
    except Exception as e:
        logging.warning(f"Error checking inactive replication on {host}: {str(e)}")
        status["inactive_replication"] = {"error": str(e)}

def process_host(host: str, password: str) -> Tuple[str, Dict[str, Any]]:
    status = {}
    
    try:
        conn = get_db_connection(host)
        conn.autocommit = True
        
        try:
            with conn.cursor() as cur:
                # Decode temporal slots for this host
                decoded_temporal_slots = decode_temporal_slots(conn)

                # Process all queries
                for query_func in [
                    lambda c, s, h: _get_replication_slots(c, s, h, decoded_temporal_slots),  # Pass decoded_temporal_slots here
                    _get_current_lsn,
                    _get_wal_generation_rate,
                    _get_subscription_ownership,
                    _check_inactive_replication
                ]:
                    query_func(cur, status, host)
        finally:
            connection_pools[host].putconn(conn)
            
        logging.info(f"Successfully processed host: {host}")
        return host, status
    except Exception as e:
        logging.error(f"Error processing host {host}: {str(e)}")
        return host, {"error": str(e)}

def process_host_with_conn(host: str, conn) -> Tuple[str, Dict[str, Any]]:
    """Process a host using an existing database connection."""
    status = {}
    
    try:
        # Don't set autocommit here; it should be set when connection is first created
        # Instead, make sure we're outside any transaction
        if conn.status != psycopg2.extensions.STATUS_READY:
            # If we're in a transaction, roll it back to get to a clean state
            conn.rollback()
        
        with conn.cursor() as cur:
            # Decode temporal slots for this host
            decoded_temporal_slots = decode_temporal_slots(conn)
            
            # Process all queries with the existing connection
            for query_func in [
                lambda c, s, h: _get_replication_slots(c, s, h, decoded_temporal_slots),  # Pass decoded_temporal_slots here
                _get_current_lsn,
                _get_wal_generation_rate,
                _get_subscription_ownership,
                _check_inactive_replication
            ]:
                try:
                    query_func(cur, status, host)
                except psycopg2.Error as e:
                    logging.warning(f"Error in {query_func.__name__} for {host}: {e}")
                    # If an error occurred, try to rollback to get back to a clean state
                    conn.rollback()
                    
        logging.info(f"Successfully processed host: {host}")
        return host, status
    except Exception as e:
        logging.error(f"Error processing host {host}: {str(e)}")
        # Try to rollback in case of error
        try:
            conn.rollback()
        except:
            pass
        return host, {"error": str(e)}

def decode_temporal_slots(conn):
    """Decode temporal slots and provide details about subscriptions and tables."""
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute("""
            SELECT slot_name
            FROM pg_replication_slots
            WHERE slot_name ~ '^pg_\\d+_sync_\\d+_\\d+$'
        """)
        slots = cur.fetchall()

        decoded_slots = {}
        for slot in slots:
            slot_name = slot['slot_name']
            match = re.match(r'^pg_(\d+)_sync_(\d+)_\d+$', slot_name)
            if not match:
                continue

            sub_oid, rel_oid = int(match.group(1)), int(match.group(2))

            # Lookup subscription
            cur.execute("SELECT subname FROM pg_subscription WHERE oid = %s", (sub_oid,))
            sub = cur.fetchone()
            subname = sub['subname'] if sub else None

            # Lookup table
            cur.execute("""
                SELECT n.nspname, c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.oid = %s
            """, (rel_oid,))
            table = cur.fetchone()
            schema, relname = (table['nspname'], table['relname']) if table else (None, None)

            decoded_slots[slot_name] = {
                "subscription_oid": sub_oid,
                "subscription_name": subname,
                "table_oid": rel_oid,
                "table_name": f"{schema}.{relname}" if schema and relname else None,
                "orphaned": not subname or not relname
            }

        return decoded_slots

def main() -> None:
    parser = argparse.ArgumentParser(description="RDS Replication Overview Tool")
    parser.add_argument("--start-host", help="Starting host for topology discovery (overrides PGHOST)")
    parser.add_argument("--config", default="config.yaml", help="Path to configuration file")
    parser.add_argument("--log-level", choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help="Set the logging level (overrides config file)")
    parser.add_argument("--only-lagging", action="store_true", 
                        help="Only show information about lagging replication slots")
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

    # Get the PGHOST value and truncate it at the first '.'
    pg_host = os.environ.get('PGHOST', 'default_host')
    if '.' in pg_host:
        report_name = pg_host.split('.')[0]
    else:
        report_name = pg_host  # Use the full value if no '.' is present

    # Add a timestamp to the report name
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    replication_report = f"{report_name}_replication_report_{timestamp}"
    logging.info(f"Replication report name set to: {replication_report}")

    try:
        start_user = os.environ.get('PGUSER', 'postgres')
        password = get_password()
        if not password:
            logging.error("No password provided. Set PGPASSWORD environment variable or enter it when prompted.")
            sys.exit(1)

        logging.info("Discovering replication topology...")
        topology, connection_cache = discover_replication_topology(start_host, start_user, password, True)
        logging.info("Topology discovery completed")

        # Decode temporal slots for the starting host
        conn = get_db_connection(start_host, start_user, password)
        temporal_slots = decode_temporal_slots(conn)
        conn.close()

        logging.info("Decoded temporal slots:")
        for slot in temporal_slots:
            logging.info(json.dumps(slot, indent=2))

        max_workers = config['monitoring'].get('max_workers', 10)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_host = {}
            hosts_to_process = topology['logical_publishers'] + topology['logical_subscribers']
            
            # Use cached connections where available
            for host in hosts_to_process:
                if host in connection_cache:
                    # Reuse existing connection
                    future = executor.submit(process_host_with_conn, host, connection_cache[host])
                else:
                    # Create new connection
                    future = executor.submit(process_host, host, password)
                future_to_host[future] = host
                
            statuses = {}
            for future in as_completed(future_to_host):
                host, status = future.result()
                statuses[host] = status

        report = generate_replication_report(topology, statuses)
        report['health_assessment'] = assess_replication_health(report)

        if args.only_lagging:
            # Filter the report to only show lagging slots
            for host, status in report["instance_statuses"].items():
                if "replication_slots" in status:
                    lagging_slots = {
                        slot_name: info for slot_name, info in status["replication_slots"].items() 
                        if info.get("lag_mb", 0) > 1
                    }
                    if lagging_slots:
                        status["replication_slots"] = lagging_slots
                    else:
                        status["replication_slots"] = {"message": "No lagging slots detected"}

        # Simplified output handling - always JSON
        # Generate the JSON string
        json_str = json.dumps(report, indent=2, default=convert_decimal)
        
        # Print colorized JSON to terminal
        colored_json = highlight(
            json_str, JsonLexer(), Terminal256Formatter(style="one-dark")
        )
        print(colored_json)
        
        # Save the regular JSON to file
        report_filename = f"{replication_report}.json"
        logging.info(f"Saving report to: {report_filename}")
        with open(report_filename, 'w') as f:
            json.dump(report, f, indent=2, default=convert_decimal)

    except Exception as e:
        handle_exception(e, "main execution")
    finally:
        # Close all connection pools
        for pool in connection_pools.values():
            pool.closeall()

if __name__ == "__main__":
    main()
