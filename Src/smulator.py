import random
from datetime import datetime
from src.database import get_connection, classify_crowd_level, MAX_CAPACITY


def record_scan_batch(entries: int, exits: int, source: str = "DEMO_SIMULATION") -> dict:
    """ Processes a batch of ID card entry and exit counts, updates current occupancy, and writes the reading to SQLite. """
    conn = get_connection()
    cursor = conn.cursor()

    # Retrieve latest occupancy reading
    cursor.execute(""" SELECT current_occupancy FROM occupancy_logs ORDER BY id DESC LIMIT 1 """)
    row = cursor.fetchone()
    last_occupancy = row[0] if row else 50

    # Calculate updated occupancy bounded between 0 and MAX_CAPACITY
    new_occupancy = max(0, min(MAX_CAPACITY, last_occupancy + entries - exits))
    crowd_level = classify_crowd_level(new_occupancy)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Insert updated snapshot
    cursor.execute(""" INSERT INTO occupancy_logs ( timestamp, entries_interval, exits_interval, current_occupancy, crowd_level, data_source ) VALUES (?, ?, ?, ?, ?, ?) """, (now_str, entries, exits, new_occupancy, crowd_level, source))

    # Log individual simulated ID card scans
    gates = ["Main Turnstile A", "Main Turnstile B"]
    for _ in range(entries):
        cursor.execute(""" INSERT INTO scan_events (student_id_hash, scan_type, gate_name, timestamp) VALUES (?, 'ENTRY', ?, ?) """, (f"STU-{random.randint(10000, 99999)}", random.choice(gates), now_str))

    for _ in range(exits):
        cursor.execute(""" INSERT INTO scan_events (student_id_hash, scan_type, gate_name, timestamp) VALUES (?, 'EXIT', 'Side Exit Gate', ?) """, (f"STU-{random.randint(10000, 99999)}", now_str))

    conn.commit()
    conn.close()

    return {
        "timestamp": now_str,
        "entries": entries,
        "exits": exits,
        "current_occupancy": new_occupancy,
        "crowd_level": crowd_level
    }


def simulate_random_turnstile_burst() -> dict:
    """Generates a realistic random burst of student entries and exits."""
    entries = random.randint(1, 8)
    exits = random.randint(1, 7)
    return record_scan_batch(entries, exits, source="DEMO_LIVE_BURST")
