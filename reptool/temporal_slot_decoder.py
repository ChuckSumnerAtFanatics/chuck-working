#! /Users/chuck.sumner/workspace/venvs/pypg/bin/python

import os
import re
import psycopg2
from psycopg2.extras import RealDictCursor


def decode_temporal_slots(conn):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT slot_name
            FROM pg_replication_slots
            WHERE slot_name ~ '^pg_\\d+_sync_\\d+_\\d+$'
        """)
        slots = cur.fetchall()

        for slot in slots:
            slot_name = slot["slot_name"]
            match = re.match(r"^pg_(\d+)_sync_(\d+)_\d+$", slot_name)
            if not match:
                continue

            sub_oid, rel_oid = int(match.group(1)), int(match.group(2))

            # Lookup subscription
            cur.execute(
                "SELECT subname FROM pg_subscription WHERE oid = %s", (sub_oid,)
            )
            sub = cur.fetchone()
            subname = sub["subname"] if sub else None

            # Lookup table
            cur.execute(
                """
                SELECT n.nspname, c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.oid = %s
            """,
                (rel_oid,),
            )
            table = cur.fetchone()
            schema, relname = (
                (table["nspname"], table["relname"]) if table else (None, None)
            )

            print(f"Slot: {slot_name}")
            print(
                f"  Subscription OID: {sub_oid} → {'NOT FOUND' if not subname else subname}"
            )
            print(
                f"  Table OID: {rel_oid} → {'NOT FOUND' if not relname else f'{schema}.{relname}'}"
            )
            print(f"  Orphaned: {'Yes' if not subname or not relname else 'No'}\n")


if __name__ == "__main__":
    conn = psycopg2.connect(
        dbname=os.getenv("PGDATABASE", "postgres"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("PGHOST"),
        port=int(os.getenv("PGPORT", 5432)),
    )

    decode_temporal_slots(conn)
    conn.close()
