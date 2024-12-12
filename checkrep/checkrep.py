#!/usr/bin/env python3
import os
import psycopg2
from psycopg2.extras import DictCursor
from decimal import Decimal

# Mapping replication states to descriptions
REPLICATION_STATE_DESCRIPTIONS = {
    "startup": "Starting up replication",
    "catchup": "Catching up to the primary",
    "streaming": "Streaming replication in progress",
    "backup": "Performing a backup",
    "unknown": "State unknown",
}


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


def fetch_replication_slots_with_queries(conn):
    """Fetch replication slots and associated query information from pg_stat_activity."""
    query = """
        SELECT 
            slot.slot_name,
            slot.active,
            slot.restart_lsn,
            slot.slot_type,
            slot.database,
            slot.plugin,
            slot.active_pid,
            stat.query,
            stat.state_change,
            NOW() - stat.state_change AS query_duration
        FROM pg_replication_slots slot
        LEFT JOIN pg_stat_activity stat ON slot.active_pid = stat.pid
        ORDER BY slot.slot_name;
    """
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute(query)
    return cur.fetchall()


def fetch_replication_info(conn):
    """Fetch replication information including publications, subscriptions, and replication state."""
    with conn.cursor(cursor_factory=DictCursor) as cursor:
        # Fetch subscriptions and their states
        cursor.execute("""
            SELECT 
                sub.subname AS subscription_name,
                sub.subenabled AS is_enabled,
                sub.subpublications AS publications
            FROM pg_subscription sub;
        """)
        subscriptions = cursor.fetchall()

        # Fetch publications
        cursor.execute("""
            SELECT 
                pubname AS publication_name,
                puballtables AS includes_all_tables
            FROM pg_publication;
        """)
        publications = cursor.fetchall()

        # Fetch publication tables
        cursor.execute("""
            SELECT 
                pubname AS publication_name,
                tablename AS table_name
            FROM pg_publication_tables;
        """)
        publication_tables = cursor.fetchall()

        # Fetch replication slots with queries
        replication_slots = fetch_replication_slots_with_queries(conn)

        return {
            "subscriptions": subscriptions,
            "publications": publications,
            "publication_tables": publication_tables,
            "replication_slots": replication_slots,
        }

def fetch_subscription_queries(conn):
    """Fetch subscription queries from the database."""
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT
                subname AS subscription_name,
                pid AS active_pid,
                query,
                state,
                backend_start,
                xact_start,
                query_start,
                state_change
            FROM pg_stat_activity
            WHERE backend_type = 'logical replication worker';
        """)
        return cursor.fetchall()


def display_replication_info(info):
    """Display the collected replication information."""
    print("=== Subscriptions ===")
    for sub in info["subscriptions"]:
        print(f"- Subscription Name: {sub['subscription_name']}")
        print(f"  Enabled: {sub['is_enabled']}")
        print(f"  Publications: {', '.join(sub['publications'])}\n")

    print("=== Publications ===")
    for pub in info["publications"]:
        print(f"- Publication Name: {pub['publication_name']}")
        print(f"  Includes All Tables: {'Yes' if pub['includes_all_tables'] else 'No'}")

    print("\n=== Publication Tables ===")
    for table in info["publication_tables"]:
        print(
            f"- Publication: {table['publication_name']}, Table: {table['table_name']}"
        )

    print("\n=== Replication Slots ===")
    for slot in info["replication_slots"]:
        print(f"- Slot Name: {slot['slot_name']}")
        print(f"  Active: {slot['active']}")
        print(f"  Restart LSN: {slot['restart_lsn']}")
        print(f"  Slot Type: {slot['slot_type']}")
        print(f"  Database: {slot['database']}")
        print(f"  Plugin: {slot['plugin']}")
        print(f"  Active PID: {slot['active_pid']}")
        print(f"  Query: {slot['query']}")
        print(f"  Query Duration: {slot['query_duration']}\n")



def main():
    try:
        conn = get_db_connection()
        pg_host = os.getenv("PGHOST")
        print(f"Successfully connected to the PostgreSQL server at {pg_host}.\n")
        replication_info = fetch_replication_info(conn)
        display_replication_info(replication_info)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if "conn" in locals() and conn:
            conn.close()


if __name__ == "__main__":
    main()
