#!/usr/bin/env python3
import os
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime, timedelta


def get_db_connection():
    """Establish a connection using PostgreSQL environment variables."""
    conn = psycopg2.connect(
        dbname=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        host=os.getenv("PGHOST"),
        port=os.getenv("PGPORT", "5432"),
    )
    return conn

def fetch_publications(conn):
    """Fetch publication information for PostgreSQL 13"""
    query = """
        SELECT 
            pubname AS name,
            pubowner::regrole AS owner,
            puballtables AS all_tables,
            pubinsert AS inserts,
            pubupdate AS updates,
            pubdelete AS deletes,
            pubtruncate AS truncates
        FROM pg_publication
        ORDER BY pubname;
    """
    cur = conn.cursor()
    cur.execute(query)
    return cur.fetchall()

def fetch_subscriptions(conn):
    """Fetch subscription information from pg_subscription and pg_stat_subscription."""
    with conn.cursor(cursor_factory=DictCursor) as cursor:
        cursor.execute("""
            SELECT
                sub.subname AS subscription_name,
                sub.subenabled AS is_enabled,
                array_to_string(sub.subpublications, ', ') AS publications,  -- Convert array to string
                stat.pid AS worker_pid,
                stat.received_lsn AS last_received_lsn,
                stat.latest_end_lsn AS latest_end_lsn,
                stat.latest_end_time AS latest_end_time,
                EXTRACT(EPOCH FROM (NOW() - stat.latest_end_time)) AS lag_seconds
            FROM pg_subscription sub
            LEFT JOIN pg_stat_subscription stat
            ON sub.oid = stat.subid;
        """)
        subscriptions = cursor.fetchall()
    return subscriptions


def fetch_replication_slots_and_wal_rate(conn):
    """Fetch replication slots and calculate an average WAL generation rate."""
    with conn.cursor(cursor_factory=DictCursor) as cursor:
        # Estimate the WAL generation rate using the size of WAL written since last checkpoint
        cursor.execute("""
            SELECT
                (buffers_checkpoint * current_setting('block_size')::int) AS wal_written_bytes,
                EXTRACT(EPOCH FROM (NOW() - stats_reset)) AS elapsed_time
            FROM pg_stat_bgwriter;
        """)
        result = cursor.fetchone()
        wal_written_bytes = float(result["wal_written_bytes"])  # Convert to float
        elapsed_time = float(result["elapsed_time"])  # Convert to float
        wal_rate = wal_written_bytes / elapsed_time if elapsed_time > 0 else 0

        # Fetch replication slots
        cursor.execute("""
            SELECT 
                slot_name,
                active,
                restart_lsn,
                pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) AS lag_size
            FROM pg_replication_slots;
        """)
        slots = cursor.fetchall()

    return slots, wal_rate


def display_subscriptions(subscriptions):
    """Display subscription information in a formatted table."""
    print("\n=== Subscriptions ===")
    print(f"{'Name':<20} {'Enabled':<8} {'Publications':<20} {'Worker PID':<10} {'Last Received LSN':<20} {'Latest End LSN':<20} {'Latest End Time':<25} {'Lag':<15}")
    print("-" * 140)
    for sub in subscriptions:
        lag_seconds = sub["lag_seconds"]
        lag_display = f"{int(lag_seconds)} seconds" if lag_seconds is not None else "Unknown"
        print(f"{sub['subscription_name']:<20} {str(sub['is_enabled']):<8} {sub['publications'][:18]+'...' if len(sub['publications'])>18 else sub['publications']:<20} {str(sub['worker_pid']):<10} {str(sub['last_received_lsn']):<20} {str(sub['latest_end_lsn']):<20} {str(sub['latest_end_time']):<25} {lag_display:<15}")
    print()


def display_replication_slots(slots, wal_rate):
    """Display replication slot information."""
    print("=== Replication Slots ===")
    for slot in slots:
        time_in_state = estimate_time_in_state(slot["lag_size"], wal_rate)
        state_description = "Active" if slot["active"] else "Inactive"
        print(f"- Slot Name: {slot['slot_name']}")
        print(f"  State: {state_description}")
        print(f"  Restart LSN: {slot['restart_lsn']}")
        print(f"  Lag Size: {format_bytes(slot['lag_size'])}")
        print(f"  Estimated Time in State: {time_in_state}\n")


def estimate_time_in_state(lag_size, wal_rate):
    """Estimate the time a slot has been in the current state."""
    if lag_size is None or wal_rate <= 0:
        return "Unknown"
    lag_size = float(lag_size)  # Ensure lag_size is a float
    seconds = lag_size / wal_rate
    return str(timedelta(seconds=seconds))

def display_publications(publications):
    """Display publication details in a formatted table."""
    print("\n=== Publications ===")
    print(f"{'Name':<20} {'Owner':<20} {'All Tables':<12} {'Inserts':<8} {'Updates':<8} {'Deletes':<8} {'Truncates':<10}")
    print("-" * 86)
    for pub in publications:
        name, owner, all_tables, inserts, updates, deletes, truncates = pub
        print(f"{name:<20} {owner:<20} {str(all_tables):<12} {str(inserts):<8} {str(updates):<8} {str(deletes):<8} {str(truncates):<10}")
    print()

def format_bytes(size):
    """Convert a size in bytes to a human-readable format."""
    if size is None:
        return "Unknown"
    size = float(size)  # Ensure size is a float
    for unit in ["Bytes", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def main():
    try:
        conn = get_db_connection()
        pg_host = os.getenv("PGHOST")
        print(f"Successfully connected to the PostgreSQL server at {pg_host}.\n")

        # Fetch and display subscription details
        subscriptions = fetch_subscriptions(conn)
        display_subscriptions(subscriptions)

        # Fetch and display replication slot details
        slots, wal_rate = fetch_replication_slots_and_wal_rate(conn)
        display_replication_slots(slots, wal_rate)

        # Fetch and display publication details
        publications = fetch_publications(conn)
        display_publications(publications)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if "conn" in locals() and conn:
            conn.close()


if __name__ == "__main__":
    main()
