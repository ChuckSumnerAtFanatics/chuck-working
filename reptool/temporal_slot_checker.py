#! /Users/chuck.sumner/workspace/venvs/pypg/bin/python

import os
import re
import psycopg2
from psycopg2 import OperationalError
from psycopg2.extras import RealDictCursor
import logging
from typing import Dict, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def parse_conninfo(conninfo):
    """Parse a PostgreSQL connection string into its components."""
    params = {}
    for part in conninfo.split():
        key, value = part.split("=", 1)
        params[key] = value
    return params


def fetch_subscriber_slots(subscriber_conn):
    """Fetch temporal slots from a subscriber."""
    with subscriber_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT slot_name
            FROM pg_replication_slots
            WHERE slot_name ~ '^pg_\\d+_sync_\\d+_\\d+$'
        """)
        return cur.fetchall()


def fetch_publisher_slots(conn):
    """Fetch temporal slots from the publisher."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT slot_name
            FROM pg_replication_slots
            WHERE slot_name ~ '^pg_\\d+_sync_\\d+_\\d+$'
        """)
        return cur.fetchall()


def decode_temporal_slots(conn):
    # Fetch temporal slots from the publisher
    slots = fetch_publisher_slots(conn)
    print(f"Fetched slots from publisher: {[slot['slot_name'] for slot in slots]}")

    # Dictionary to track results
    results = {}

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Fetch subscriber connection info
        cur.execute("""
            SELECT subname, subconninfo
            FROM pg_subscription
        """)
        subscriptions = cur.fetchall()

        for subscription in subscriptions:
            subname = subscription["subname"]
            conninfo = subscription["subconninfo"]
            subscriber_params = parse_conninfo(conninfo)

            # Print the name and host of the subscriber being checked
            subscriber_host = subscriber_params.get("host", "unknown")
            print(f"Checking subscriber: {subname} (host: {subscriber_host})")

            # Connect to the subscriber
            try:
                with psycopg2.connect(
                    dbname=subscriber_params.get("dbname", "postgres"),
                    user=subscriber_params.get("user", "postgres"),
                    password=subscriber_params.get("password"),
                    host=subscriber_host,
                    port=int(subscriber_params.get("port", 5432)),
                ) as subscriber_conn:
                    for slot in slots:
                        slot_name = slot["slot_name"]
                        print(f"\nProcessing slot: {slot_name}")
                        match = re.match(r"^pg_(\d+)_sync_(\d+)_\d+$", slot_name)
                        if not match:
                            print(f"  [!] Slot {slot_name} does not match the expected regex pattern.")
                            continue

                        sub_oid, rel_oid = int(match.group(1)), int(match.group(2))
                        print(f"  Extracted OIDs → Subscription OID: {sub_oid}, Table OID: {rel_oid}")

                        # Initialize tracking for this slot
                        if slot_name not in results:
                            results[slot_name] = {
                                "sub_oid_found": False,
                                "rel_oid_found": False,
                                "subscribers": [],
                            }

                        # Check if the subscription OID exists on the subscriber
                        subscription = check_subscription_oid(subscriber_conn, sub_oid)
                        if subscription:
                            print(f"  [✓] Found subscription OID {sub_oid} on subscriber.")
                            results[slot_name]["sub_oid_found"] = True
                            results[slot_name]["subscribers"].append(
                                f"Subscription OID {sub_oid} found on {subname}"
                            )
                        else:
                            print(f"  [!] Subscription OID {sub_oid} not found on subscriber.")

                        # Lookup table on the subscriber
                        table = check_table_oid(subscriber_conn, rel_oid)
                        if table:
                            schema, relname = table["nspname"], table["relname"]
                            print(f"  [✓] Found table: {schema}.{relname}")
                            results[slot_name]["rel_oid_found"] = True
                            results[slot_name]["subscribers"].append(
                                f"Table OID {rel_oid} ({schema}.{relname}) found on {subname}"
                            )
                        else:
                            print(f"  [!] Table with OID {rel_oid} not found on subscriber.")
            except OperationalError as e:
                print(f"Database connection failed for subscriber {subname}: {e}")
            except Exception as e:
                print(f"An unexpected error occurred: {e}")

    print_summary(results)


def print_summary(results: Dict[str, Any]):
    print("\nSummary:")
    for slot_name, result in results.items():
        print(f"\nSlot: {slot_name}")
        if result["sub_oid_found"]:
            print("  [✓] Subscription OID found:")
            for location in result["subscribers"]:
                if "Subscription OID" in location:
                    print(f"    - {location}")
        else:
            print("  [!] Subscription OID not found on any subscriber.")

        if result["rel_oid_found"]:
            print("  [✓] Table OID found:")
            for location in result["subscribers"]:
                if "Table OID" in location:
                    print(f"    - {location}")
        else:
            print("  [!] Table OID not found on any subscriber.")


def check_subscription_oid(subscriber_conn, sub_oid):
    """Check if the subscription OID exists on the subscriber."""
    with subscriber_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT subname
            FROM pg_subscription
            WHERE oid = %s
        """, (sub_oid,))
        return cur.fetchone()


def check_table_oid(subscriber_conn, rel_oid):
    """Check if the table OID exists on the subscriber."""
    with subscriber_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT n.nspname, c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.oid = %s
        """, (rel_oid,))
        return cur.fetchone()


def get_env_variable(var_name, default=None):
    value = os.getenv(var_name, default)
    if value is None:
        raise ValueError(f"Environment variable {var_name} is not set.")
    return value


def main():
    try:
        conn = psycopg2.connect(
            dbname=get_env_variable("PGDATABASE", "postgres"),
            user=get_env_variable("PGUSER", "postgres"),
            password=get_env_variable("PGPASSWORD"),
            host=get_env_variable("PGHOST"),
            port=int(get_env_variable("PGPORT", 5432)),
        )
        try:
            decode_temporal_slots(conn)
        finally:
            conn.close()
    except OperationalError as e:
        logger.error(f"Failed to connect to the database: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred in main(): {e}")


if __name__ == "__main__":
    main()
