#!/usr/bin/env python3

import os
import re
import psycopg2
from psycopg2 import OperationalError
from psycopg2.extras import RealDictCursor
import logging
from typing import Dict, Any, Optional, List, Tuple

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Global Summary Storage ---
SUMMARY = []

# --- Helper Functions ---


def get_required_env_variable(var_name: str) -> str:
    value = os.getenv(var_name)
    if value is None:
        raise ValueError(f"Required environment variable {var_name} is not set.")
    return value


def get_env_variable(var_name: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(var_name, default)


def connect_db(
    conn_params: Dict[str, Any], connection_desc: str, sub_oid: Optional[int] = None
) -> Optional[psycopg2.extensions.connection]:
    safe_params = {
        k: ("*****" if k == "password" else v) for k, v in conn_params.items()
    }
    logger.info(f"Connecting to {connection_desc} with parameters: {safe_params}")
    logger.debug(f"Raw connection parameters: {conn_params}")

    if not conn_params.get("password") and sub_oid:
        env_var_name = f"SUB_PASSWORD_{sub_oid}"
        dynamic_password = os.getenv(env_var_name)
        if dynamic_password:
            conn_params["password"] = dynamic_password
            logger.info(
                f"  [✓] Retrieved password for subscription OID {sub_oid} from env var {env_var_name}"
            )
        else:
            logger.warning(
                f"  [!] No dynamic password found for subscription OID {sub_oid}"
            )

    try:
        conn = psycopg2.connect(**conn_params)
        logger.info(f"Successfully connected to {connection_desc}")
        return conn
    except OperationalError as e:
        logger.error(f"Failed to connect to {connection_desc}: {e}")
        logger.error(f"  [!] Connection parameters used: {conn_params}")
        logger.info(f"Retrying connection to {connection_desc} after 2 seconds...")
        import time
        time.sleep(2)
        try:
            conn = psycopg2.connect(**conn_params)
            logger.info(f"Successfully connected to {connection_desc} on retry")
            return conn
        except Exception as e2:
            logger.error(f"Retry failed: {e2}")
            return None
    except Exception as e:
        logger.error(f"Unexpected error connecting to {connection_desc}: {e}")
        return None


def gather_temporal_replication_slots(
    conn: psycopg2.extensions.connection,
) -> List[Dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT slot_name, plugin, active, active_pid, database
            FROM pg_replication_slots
            WHERE plugin = 'pgoutput'
        """)
        return cur.fetchall()


def gather_active_subscribers(
    conn: psycopg2.extensions.connection,
) -> List[Dict[str, Any]]:
    """Get active subscriber connections from pg_stat_replication."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT
                pid,
                application_name,
                client_addr,
                client_hostname
            FROM
                pg_stat_replication
        """)
        return cur.fetchall()


def get_subscription_name_from_oid(conn, sub_oid) -> Optional[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT subname FROM pg_subscription WHERE oid = %s", (sub_oid,))
        result = cur.fetchone()
        return result[0] if result else None


def get_table_details_from_oid(conn, rel_oid) -> Optional[Tuple[str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT n.nspname, c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.oid = %s
        """,
            (rel_oid,),
        )
        result = cur.fetchone()
        return (result[0], result[1]) if result else None


def get_subscription_connection_info(conn, sub_oid):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT subconninfo FROM pg_subscription WHERE oid = %s", (sub_oid,)
        )
        result = cur.fetchone()
        return result["subconninfo"] if result else None


def parse_conninfo(conninfo: str) -> Dict[str, str]:
    params = {}
    if conninfo:
        for part in conninfo.split():
            if "=" in part:
                key, value = part.split("=", 1)
                params[key] = value
    if "password" not in params:
        params["password"] = None
    return params


# --- Core Logic ---


def analyze_publisher_slots(conn):
    logger.info("Gathering temporal replication slots...")
    temporal_slots = gather_temporal_replication_slots(conn)

    if not temporal_slots:
        logger.info("No temporal replication slots found.")
        return

    logger.info(
        f"Found {len(temporal_slots)} temporal slots. Gathering active subscribers..."
    )
    active_subscribers = gather_active_subscribers(conn)
    slot_active_pids = {sub["pid"] for sub in active_subscribers}
    logger.info(f"Found {len(active_subscribers)} active subscriber connections.")

    for slot in temporal_slots:
        slot_name = slot["slot_name"]
        db_name = slot.get("database", "N/A")
        active_pid = slot.get("active_pid")

        logger.info(f"\n--- Analyzing Slot: '{slot_name}' (DB: {db_name}) ---")

        manually_connect_if_no_pid = False
        if not active_pid or active_pid not in slot_active_pids:
            logger.warning(
                f"  [!] No active subscriber process found for slot {slot_name}. Attempting manual subscriber connection..."
            )
            manually_connect_if_no_pid = True

        match = re.match(r"^pg_(\d+)_sync_(\d+)_\d+$", slot_name)

        if match:
            # TEMPORAL SLOT
            sub_oid = int(match.group(1))
            rel_oid = int(match.group(2))
            slot_type = "TEMPORAL"

            sub_name = get_subscription_name_from_oid(conn, sub_oid)
            if not sub_name:
                logger.warning(
                    f"  [!] Could not find subscription for slot {slot_name}. Skipping."
                )
                continue

            table_details = get_table_details_from_oid(conn, rel_oid)
            if not table_details:
                logger.warning(
                    f"  [!] Could not find table for slot {slot_name}. Skipping."
                )
                continue
            schema, table_name = table_details

        else:
            # REGULAR SLOT
            slot_type = "REGULAR"
            sub_name = slot_name  # Assume default 1:1 mapping
            schema = "N/A"
            table_name = "N/A"

        # Get subconninfo (you need sub_oid only for temporal, but you can fake it if needed)
        if match:
            conninfo = get_subscription_connection_info(conn, sub_oid)
        else:
            # Lookup subconninfo by subscription name
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT subconninfo FROM pg_subscription WHERE subname = %s",
                    (sub_name,),
                )
                result = cur.fetchone()
                if result:
                    conninfo = result["subconninfo"]
                else:
                    conninfo = None

        if not conninfo:
            logger.warning(
                f"  [!] Missing connection info for subscription {sub_name}. Skipping."
            )
            continue

        conn_params = parse_conninfo(conninfo)

        subscriber_conn = connect_db(
            {
                "host": conn_params.get("host"),
                "port": int(conn_params.get("port", "5432")),
                "dbname": conn_params.get("dbname"),
                "user": conn_params.get("user"),
                "password": conn_params.get("password"),
            },
            f"Subscriber {conn_params.get('host', 'unknown')}",
            sub_oid=sub_oid if match else None,
        )

        if subscriber_conn:
            logger.info(
                f"  [✓] Connected to subscriber: {conn_params.get('host', 'unknown')}"
            )
            sub_status = check_subscriber_status(subscriber_conn, sub_name)
            subscriber_conn.close()
            if sub_status:
                status = (
                    "ACTIVE" if not manually_connect_if_no_pid else "DISCONNECTED-BUT-ALIVE"
                )
            else:
                status = "ORPHANED"
        else:
            logger.error(f"  [!] Failed to connect to subscriber.")
            status = "ORPHANED"

        # Save result
        SUMMARY.append(
            {
                "Slot Name": slot_name,
                "Subscription": sub_name,
                "Subscriber Host": conn_params.get("host", "unknown"),
                "Table": f"{schema}.{table_name}",
                "Status": status,
            }
        )


def check_subscriber_status(conn, sub_name) -> bool:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT received_lsn, latest_end_lsn, latest_end_time
            FROM pg_stat_subscription
            WHERE subname = %s
        """,
            (sub_name,),
        )
        result = cur.fetchone()
        if result:
            logger.info(
                f"      - Subscription LSN: received={result['received_lsn']}, latest={result['latest_end_lsn']}"
            )
            return True
        else:
            logger.warning(f"      - No subscription status found for {sub_name}")
            return False


def print_summary():
    if not SUMMARY:
        logger.info("\nNo slots analyzed. No summary to print.")
        return

    logger.info("\nFinal Summary:\n")
    headers = ["Slot Name", "Subscription", "Subscriber Host", "Table", "Status"]
    row_format = "{:<40} {:<25} {:<20} {:<35} {:<8}"

    print(row_format.format(*headers))
    print("-" * 130)

    for row in SUMMARY:
        print(
            row_format.format(
                row["Slot Name"],
                row["Subscription"],
                row["Subscriber Host"],
                row["Table"],
                row["Status"],
            )
        )


# --- Entry Point ---


def main():
    logger.info("Starting temporal slot checker...")
    conn = None
    try:
        db_host = get_required_env_variable("PGHOST")
        db_password = get_required_env_variable("PGPASSWORD")
        db_name = get_env_variable("PGDATABASE", "postgres")
        db_user = get_env_variable("PGUSER", "postgres")
        db_port = int(get_env_variable("PGPORT", 5432))

        conn = connect_db(
            {
                "host": db_host,
                "port": db_port,
                "dbname": db_name,
                "user": db_user,
                "password": db_password,
            },
            "Publisher",
        )

        if conn:
            analyze_publisher_slots(conn)
        else:
            logger.error("Failed to connect to publisher. Exiting.")

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()
            logger.debug("Closed publisher connection.")

    print_summary()


if __name__ == "__main__":
    main()
