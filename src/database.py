import sqlite3
import os
import random
from datetime import datetime, timedelta
import pandas as pd

DB_DIR = "data"
DB_PATH = os.path.join(DB_DIR, "queuewise.db")
MAX_CAPACITY = 250  # Configurable college library maximum seating capacity


def get_connection():
    """Creates the data directory if missing and returns an SQLite connection."""
    os.makedirs(DB_DIR, exist_ok=True)
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    """Initializes SQLite tables and seeds 7 days of demo data if the DB is empty."""
    conn = get_connection()
    cursor = conn.cursor()

    # Table for historical & live occupancy snapshots
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS occupancy_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL,
            entries_interval INTEGER NOT NULL,
            exits_interval INTEGER NOT NULL,
            current_occupancy INTEGER NOT NULL,
            crowd_level TEXT NOT NULL,
            data_source TEXT DEFAULT 'DEMO_SIMULATION'
        )
    """)

    # Table for individual ID card scan events (Audit/Gate log)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scan_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id_hash TEXT NOT NULL,
            scan_type TEXT CHECK(scan_type IN ('ENTRY', 'EXIT')) NOT NULL,
            gate_name TEXT NOT NULL,
            timestamp DATETIME NOT NULL
        )
    """)

    conn.commit()

    # Check if we need to seed initial demonstration data
    cursor.execute("SELECT COUNT(*) FROM occupancy_logs")
    count = cursor.fetchone()[0]
    if count == 0:
        seed_demo_data(conn)

    conn.close()


def classify_crowd_level(occupancy: int, capacity: int = MAX_CAPACITY) -> str:
    """Classifies crowd level into Low, Moderate, or High based on percentage."""
    ratio = (occupancy / capacity) * 100
    if ratio < 40:
        return "Low"
    elif ratio < 75:
        return "Moderate"
    return "High"


def seed_demo_data(conn):
    """
    Generates 7 days of realistic hourly library traffic (8:00 AM to 8:00 PM)
    following a typical bimodal student traffic pattern (morning & afternoon peaks).
    """
    cursor = conn.cursor()
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    start_time = now - timedelta(days=7)

    # Hourly target occupancy profile (8 AM to 8 PM)
    hourly_targets = {
        8: 25,    # Opening - Low
        9: 65,    # Morning classes start
        10: 130,  # Mid-morning study rush
        11: 185,  # Peak morning crowd (High)
        12: 155,  # Pre-lunch
        13: 95,   # Lunch dip (Moderate)
        14: 165,  # Afternoon study session
        15: 210,  # Peak afternoon crowd (High)
        16: 195,  # Late afternoon
        17: 140,  # Classes wrap up
        18: 85,   # Evening taper
        19: 45,   # Night study
        20: 15    # Closing time
    }

    current_time = start_time
    current_occ = 0
    logs_to_insert = []
    scans_to_insert = []

    while current_time <= now:
        hour = current_time.hour
        is_weekend = current_time.weekday() >= 5  # Saturday=5, Sunday=6

        if 8 <= hour <= 20:
            if hour == 8:
                current_occ = 0  # Reset at opening

            base_target = hourly_targets.get(hour, 20)
            # Weekends typically see ~45% of weekday traffic
            if is_weekend:
                base_target = int(base_target * 0.45)

            # Add realistic noise
            target_occ = max(0, min(MAX_CAPACITY, base_target + random.randint(-15, 15)))
            net_change = target_occ - current_occ

            if net_change >= 0:
                entries = net_change + random.randint(4, 14)
                exits = entries - net_change
            else:
                exits = abs(net_change) + random.randint(4, 14)
                entries = exits + net_change

            current_occ = max(0, min(MAX_CAPACITY, current_occ + entries - exits))
            crowd_level = classify_crowd_level(current_occ)

            logs_to_insert.append((
                current_time.strftime("%Y-%m-%d %H:%M:%S"),
                entries,
                exits,
                current_occ,
                crowd_level,
                "DEMO_SIMULATION"
            ))

        current_time += timedelta(hours=1)

    cursor.executemany("""
        INSERT INTO occupancy_logs (
            timestamp, entries_interval, exits_interval,
            current_occupancy, crowd_level, data_source
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, logs_to_insert)

    # Seed 15 recent individual ID card scan events for the live feed table
    gates = ["Main Turnstile A", "Main Turnstile B", "Side Exit Gate"]
    for i in range(15):
        scan_time = datetime.now() - timedelta(minutes=(15 - i) * 2)
        scan_type = random.choice(["ENTRY", "ENTRY", "EXIT"])
        student_hash = f"STU-{random.randint(10000, 99999)}"
        gate = gates[0] if scan_type == "ENTRY" else random.choice(gates)
        scans_to_insert.append((
            student_hash,
            scan_type,
            gate,
            scan_time.strftime("%Y-%m-%d %H:%M:%S")
        ))

    cursor.executemany("""
        INSERT INTO scan_events (student_id_hash, scan_type, gate_name, timestamp)
        VALUES (?, ?, ?, ?)
    """, scans_to_insert)

    conn.commit()


def fetch_occupancy_logs(days: int = 7) -> pd.DataFrame:
    """Fetches occupancy logs for the specified number of past days."""
    conn = get_connection()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    query = """
        SELECT id, timestamp, entries_interval, exits_interval,
               current_occupancy, crowd_level, data_source
        FROM occupancy_logs
        WHERE timestamp >= ?
        ORDER BY timestamp ASC
    """
    df = pd.read_sql_query(query, conn, params=(cutoff,))
    conn.close()
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def fetch_recent_scans(limit: int = 10) -> pd.DataFrame:
    """Fetches the most recent ID-card scan events."""
    conn = get_connection()
    query = """
        SELECT timestamp, student_id_hash AS "Student ID (Masked)",
               scan_type AS "Action", gate_name AS "Scanner Gate"
        FROM scan_events
        ORDER BY id DESC
        LIMIT ?
    """
    df = pd.read_sql_query(query, conn, params=(limit,))
    conn.close()
    return df
