#!/usr/bin/env python3
import os
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime
import argparse
import json

# Reuse the REPLICATION_STATE_DESCRIPTIONS from checkrep.py
REPLICATION_STATE_DESCRIPTIONS = {
    "startup": "Starting up replication",
    "catchup": "Catching up to the primary",
    "streaming": "Streaming replication in progress",
    "backup": "Performing a backup",
    "unknown": "State unknown",
}

def get_db_connection(db_params):
    """Establish a connection using provided database parameters."""
    conn = psycopg2.connect(**db_params)
    return conn

def fetch_publisher_info(conn):
    """Fetch replication information for the publisher."""
    with conn.cursor(cursor_factory=DictCursor) as cursor:
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

        # Fetch replication slots
        cursor.execute("""
            SELECT 
                slot_name,
                active,
                restart_lsn,
                confirmed_flush_lsn,
                slot_type,
                database,
                plugin
            FROM pg_replication_slots;
        """)
        replication_slots = cursor.fetchall()

    return {
        "publications": publications,
        "publication_tables": publication_tables,
        "replication_slots": replication_slots,
    }

def fetch_subscriber_info(conn):
    """Fetch replication information for the subscriber."""
    with conn.cursor(cursor_factory=DictCursor) as cursor:
        # Fetch subscriptions
        cursor.execute("""
            SELECT 
                subname AS subscription_name,
                subenabled AS is_enabled,
                subpublications AS publications,
                subconninfo AS connection_info
            FROM pg_subscription;
        """)
        subscriptions = cursor.fetchall()

        # Fetch subscription status
        cursor.execute("""
            SELECT 
                subname AS subscription_name,
                pid AS worker_pid,
                received_lsn,
                latest_end_lsn,
                latest_end_time
            FROM pg_stat_subscription;
        """)
        subscription_status = cursor.fetchall()

    return {
        "subscriptions": subscriptions,
        "subscription_status": subscription_status,
    }

def calculate_replication_lag(publisher_info, subscriber_info):
    """Calculate replication lag based on LSN differences."""
    lag_info = {}
    for slot in publisher_info['replication_slots']:
        for sub_status in subscriber_info['subscription_status']:
            if slot['slot_name'] == sub_status['subscription_name']:
                if slot['confirmed_flush_lsn'] and sub_status['received_lsn']:
                    lag = int(slot['confirmed_flush_lsn'], 16) - int(sub_status['received_lsn'], 16)
                    lag_info[slot['slot_name']] = lag
    return lag_info

def monitor_replication(publisher_params, subscriber_params):
    """Monitor replication status for publisher and subscriber."""
    try:
        with get_db_connection(publisher_params) as publisher_conn, \
             get_db_connection(subscriber_params) as subscriber_conn:
            
            publisher_info = fetch_publisher_info(publisher_conn)
            subscriber_info = fetch_subscriber_info(subscriber_conn)
            lag_info = calculate_replication_lag(publisher_info, subscriber_info)

            return {
                "timestamp": datetime.now().isoformat(),
                "publisher": publisher_info,
                "subscriber": subscriber_info,
                "replication_lag": lag_info
            }
    except Exception as e:
        print(f"Error monitoring replication: {e}")
        return None

def display_replication_status(status):
    """Display replication status in a formatted manner."""
    if not status:
        print("No replication status available.")
        return

    print(f"Replication Status as of {status['timestamp']}:")
    print("\nPublisher Information:")
    print("  Publications:")
    for pub in status['publisher']['publications']:
        print(f"    - {pub['publication_name']} (All tables: {pub['includes_all_tables']})")
    
    print("\n  Replication Slots:")
    for slot in status['publisher']['replication_slots']:
        print(f"    - {slot['slot_name']} (Active: {slot['active']}, LSN: {slot['confirmed_flush_lsn']})")

    print("\nSubscriber Information:")
    print("  Subscriptions:")
    for sub in status['subscriber']['subscriptions']:
        print(f"    - {sub['subscription_name']} (Enabled: {sub['is_enabled']})")
        print(f"      Publications: {', '.join(sub['publications'])}")

    print("\n  Subscription Status:")
    for sub_status in status['subscriber']['subscription_status']:
        print(f"    - {sub_status['subscription_name']}:")
        print(f"      Received LSN: {sub_status['received_lsn']}")
        print(f"      Latest End LSN: {sub_status['latest_end_lsn']}")
        print(f"      Latest End Time: {sub_status['latest_end_time']}")

    print("\nReplication Lag:")
    for slot_name, lag in status['replication_lag'].items():
        print(f"  {slot_name}: {lag} bytes")

def export_to_json(status, filename):
    """Export replication status to a JSON file."""
    with open(filename, 'w') as f:
        json.dump(status, f, indent=2, default=str)
    print(f"Replication status exported to {filename}")

def main():
    parser = argparse.ArgumentParser(description="Monitor PostgreSQL replication status")
    parser.add_argument("--publisher", required=True, help="Publisher connection string")
    parser.add_argument("--subscriber", required=True, help="Subscriber connection string")
    parser.add_argument("--output", help="Output JSON file")
    args = parser.parse_args()

    publisher_params = dict(param.split('=') for param in args.publisher.split())
    subscriber_params = dict(param.split('=') for param in args.subscriber.split())

    status = monitor_replication(publisher_params, subscriber_params)
    
    if status:
        display_replication_status(status)
        if args.output:
            export_to_json(status, args.output)

if __name__ == "__main__":
    main()
