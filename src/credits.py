"""
QueueWise Credit System — src/credits.py
=========================================
Handles:
  - Study session logging (per student, multi-session days)
  - Weekly threshold check & point calculation
  - Monthly safety-net calculation
  - Credit ledger (earn / spend / expire)
  - 6-month point expiry with archival
  - Book catalog & redemption
"""

import sqlite3
import random
from datetime import datetime, timedelta, date
from src.database import get_connection

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
WEEKLY_THRESHOLD    = 20      # hours needed to unlock weekly points
MONTHLY_THRESHOLD   = 75      # hours needed for monthly safety-net
POINT_EXPIRY_DAYS   = 183     # ~6 months
MAX_DAILY_HOURS     = {5: 10.0}   # Saturday = 10h; all other open days = 12h
WEEKDAY_MAX_DEFAULT = 12.0
SUNDAY              = 6

BOOK_CATALOG = [
    {
        "id": 1,
        "title":  "Rich Dad Poor Dad",
        "author": "Robert Kiyosaki",
        "points": 60,
        "tier":   "Starter",
        "emoji":  "🟢",
        "cover":  "https://covers.openlibrary.org/b/isbn/9781612680194-M.jpg",
        "desc":   "What the rich teach their kids about money that the poor and middle class do not.",
    },
    {
        "id": 2,
        "title":  "The Psychology of Money",
        "author": "Morgan Housel",
        "points": 75,
        "tier":   "Consistent",
        "emoji":  "🔵",
        "cover":  "https://covers.openlibrary.org/b/isbn/9780857197689-M.jpg",
        "desc":   "Timeless lessons on wealth, greed, and happiness through 19 short stories.",
    },
    {
        "id": 3,
        "title":  "True Story",
        "author": "Ty Montague",
        "points": 110,
        "tier":   "Dedicated",
        "emoji":  "🟠",
        "cover":  "https://covers.openlibrary.org/b/isbn/9781591845973-M.jpg",
        "desc":   "How to combine story and action to transform your business.",
    },
    {
        "id": 4,
        "title":  "Executing Your Strategy",
        "author": "Morgan, Levitt & Malek",
        "points": 160,
        "tier":   "Expert",
        "emoji":  "🔴",
        "cover":  "https://covers.openlibrary.org/b/isbn/9781422101292-M.jpg",
        "desc":   "A framework to turn strategy into action — from planning through execution.",
    },
]


# ─────────────────────────────────────────────
# SCHEMA INIT
# ─────────────────────────────────────────────
def init_credit_tables():
    """Create credit-system tables if they don't exist and seed book catalog."""
    conn = get_connection()
    cur  = conn.cursor()

    cur.executescript("""
        -- Individual study sessions per student
        CREATE TABLE IF NOT EXISTS study_sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            username        TEXT    NOT NULL,
            session_date    DATE    NOT NULL,
            scan_in         DATETIME NOT NULL,
            scan_out        DATETIME,
            duration_hours  REAL,
            week_number     INTEGER,
            week_year       INTEGER,
            month_number    INTEGER,
            month_year      INTEGER
        );

        -- Weekly rollup cache (recalculated on each session end)
        CREATE TABLE IF NOT EXISTS weekly_summaries (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            username        TEXT    NOT NULL,
            week_number     INTEGER NOT NULL,
            week_year       INTEGER NOT NULL,
            total_hours     REAL    NOT NULL DEFAULT 0,
            points_earned   INTEGER NOT NULL DEFAULT 0,
            threshold_met   INTEGER NOT NULL DEFAULT 0,
            UNIQUE(username, week_number, week_year)
        );

        -- Monthly rollup cache
        CREATE TABLE IF NOT EXISTS monthly_summaries (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            username        TEXT    NOT NULL,
            month_number    INTEGER NOT NULL,
            month_year      INTEGER NOT NULL,
            total_hours     REAL    NOT NULL DEFAULT 0,
            weekly_pts_sum  INTEGER NOT NULL DEFAULT 0,
            monthly_pts     INTEGER NOT NULL DEFAULT 0,
            top_up_applied  INTEGER NOT NULL DEFAULT 0,
            final_credit    INTEGER NOT NULL DEFAULT 0,
            finalized       INTEGER NOT NULL DEFAULT 0,
            UNIQUE(username, month_number, month_year)
        );

        -- Append-only credit ledger
        CREATE TABLE IF NOT EXISTS credit_ledger (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            username        TEXT    NOT NULL,
            change_pts      INTEGER NOT NULL,
            reason          TEXT    NOT NULL,
            ref_week        INTEGER,
            ref_month       INTEGER,
            ref_year        INTEGER,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- Archived (expired) point history — read-only
        CREATE TABLE IF NOT EXISTS credit_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            username        TEXT    NOT NULL,
            archived_pts    INTEGER NOT NULL,
            period_start    DATE    NOT NULL,
            period_end      DATE    NOT NULL,
            archived_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- Book catalog
        CREATE TABLE IF NOT EXISTS book_catalog (
            id              INTEGER PRIMARY KEY,
            title           TEXT    NOT NULL,
            author          TEXT    NOT NULL,
            points_required INTEGER NOT NULL,
            tier            TEXT    NOT NULL,
            emoji           TEXT    NOT NULL,
            cover_url       TEXT,
            description     TEXT
        );

        -- Redemptions log
        CREATE TABLE IF NOT EXISTS redemptions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            username        TEXT    NOT NULL,
            book_id         INTEGER NOT NULL REFERENCES book_catalog(id),
            book_title      TEXT    NOT NULL,
            points_spent    INTEGER NOT NULL,
            redeemed_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Seed book catalog (upsert so re-runs are safe)
    for book in BOOK_CATALOG:
        cur.execute("""
            INSERT OR REPLACE INTO book_catalog
                (id, title, author, points_required, tier, emoji, cover_url, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (book["id"], book["title"], book["author"], book["points"],
              book["tier"], book["emoji"], book.get("cover", ""), book.get("desc", "")))

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _max_daily(day_of_week: int) -> float:
    if day_of_week == SUNDAY:
        return 0.0
    return MAX_DAILY_HOURS.get(day_of_week, WEEKDAY_MAX_DEFAULT)


def _iso_week(d: date):
    iso = d.isocalendar()
    return iso[1], iso[0]   # week_number, week_year


def calculate_weekly_points(hours: float) -> int:
    if hours < WEEKLY_THRESHOLD:
        return 0
    return WEEKLY_THRESHOLD + int(hours - WEEKLY_THRESHOLD)


def calculate_monthly_credit(weekly_hours: list) -> dict:
    total_hours     = sum(weekly_hours)
    weekly_pts_each = [calculate_weekly_points(h) for h in weekly_hours]
    track_a         = sum(weekly_pts_each)
    track_b         = int(total_hours) if total_hours >= MONTHLY_THRESHOLD else 0
    final_credit    = max(track_a, track_b)
    top_up          = max(0, track_b - track_a)
    return {
        "total_hours":     round(total_hours, 2),
        "track_a_weekly":  track_a,
        "track_b_monthly": track_b,
        "top_up_applied":  top_up,
        "final_credit":    final_credit,
        "monthly_met":     total_hours >= MONTHLY_THRESHOLD,
    }


# ─────────────────────────────────────────────
# SESSION LOGGING
# ─────────────────────────────────────────────
def start_session(username: str) -> int:
    """Open a new study session. Returns the session id."""
    now = datetime.now()
    if now.weekday() == SUNDAY:
        return -1   # library closed
    wn, wy = _iso_week(now.date())
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO study_sessions
            (username, session_date, scan_in, week_number, week_year, month_number, month_year)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (username, now.date().isoformat(), now.isoformat(), wn, wy, now.month, now.year))
    conn.commit()
    sid = cur.lastrowid
    conn.close()
    return sid


def end_session(session_id: int, username: str):
    """Close an open session, compute duration, update weekly/monthly summaries."""
    now  = datetime.now()
    conn = get_connection()
    cur  = conn.cursor()

    row = cur.execute(
        "SELECT scan_in, session_date FROM study_sessions WHERE id=? AND username=?",
        (session_id, username)
    ).fetchone()
    if not row:
        conn.close()
        return

    scan_in = datetime.fromisoformat(row[0])
    day_of_week = scan_in.weekday()
    duration = (now - scan_in).total_seconds() / 3600

    # Cap by remaining daily quota
    already = cur.execute("""
        SELECT COALESCE(SUM(duration_hours),0) FROM study_sessions
        WHERE username=? AND session_date=? AND id!=? AND duration_hours IS NOT NULL
    """, (username, row[1], session_id)).fetchone()[0]

    allowed = max(0, _max_daily(day_of_week) - already)
    duration = round(min(duration, allowed), 4)

    wn, wy = _iso_week(scan_in.date())
    cur.execute("""
        UPDATE study_sessions
        SET scan_out=?, duration_hours=?
        WHERE id=?
    """, (now.isoformat(), duration, session_id))
    conn.commit()
    conn.close()

    _recalculate_week(username, wn, wy)
    _recalculate_month(username, now.month, now.year)


# ─────────────────────────────────────────────
# WEEKLY & MONTHLY RECALCULATION
# ─────────────────────────────────────────────
def _recalculate_week(username: str, week_number: int, week_year: int):
    conn = get_connection()
    cur  = conn.cursor()

    total_hours = cur.execute("""
        SELECT COALESCE(SUM(duration_hours),0) FROM study_sessions
        WHERE username=? AND week_number=? AND week_year=? AND duration_hours IS NOT NULL
    """, (username, week_number, week_year)).fetchone()[0]

    pts_earned   = calculate_weekly_points(total_hours)
    threshold_met = 1 if total_hours >= WEEKLY_THRESHOLD else 0

    cur.execute("""
        INSERT INTO weekly_summaries (username, week_number, week_year, total_hours, points_earned, threshold_met)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(username, week_number, week_year)
        DO UPDATE SET total_hours=excluded.total_hours,
                      points_earned=excluded.points_earned,
                      threshold_met=excluded.threshold_met
    """, (username, week_number, week_year, total_hours, pts_earned, threshold_met))
    conn.commit()
    conn.close()


def _recalculate_month(username: str, month: int, year: int):
    conn = get_connection()
    cur  = conn.cursor()

    # Gather all weekly hours in this month
    rows = cur.execute("""
        SELECT total_hours FROM weekly_summaries ws
        WHERE ws.username=? AND EXISTS (
            SELECT 1 FROM study_sessions ss
            WHERE ss.username=ws.username AND ss.week_number=ws.week_number
              AND ss.week_year=ws.week_year AND ss.month_number=? AND ss.month_year=?
        )
    """, (username, month, year)).fetchall()

    weekly_hours = [r[0] for r in rows]
    result = calculate_monthly_credit(weekly_hours)

    cur.execute("""
        INSERT INTO monthly_summaries
            (username, month_number, month_year, total_hours, weekly_pts_sum,
             monthly_pts, top_up_applied, final_credit)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(username, month_number, month_year)
        DO UPDATE SET total_hours=excluded.total_hours,
                      weekly_pts_sum=excluded.weekly_pts_sum,
                      monthly_pts=excluded.monthly_pts,
                      top_up_applied=excluded.top_up_applied,
                      final_credit=excluded.final_credit
    """, (username, month, year,
          result["total_hours"], result["track_a_weekly"],
          result["track_b_monthly"], result["top_up_applied"], result["final_credit"]))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# CREDIT BALANCE
# ─────────────────────────────────────────────
def get_credit_balance(username: str) -> int:
    """Live balance = sum of all ledger entries."""
    conn = get_connection()
    bal  = conn.execute(
        "SELECT COALESCE(SUM(change_pts),0) FROM credit_ledger WHERE username=?",
        (username,)
    ).fetchone()[0]
    conn.close()
    return max(0, bal)


def _add_ledger_entry(conn, username: str, change: int, reason: str,
                      ref_week=None, ref_month=None, ref_year=None):
    conn.execute("""
        INSERT INTO credit_ledger (username, change_pts, reason, ref_week, ref_month, ref_year)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (username, change, reason, ref_week, ref_month, ref_year))


def sync_credits_from_summaries(username: str):
    """
    Push earned credits from monthly summaries into the ledger.
    Called on each month-end (or on login for past months not yet synced).
    """
    conn = get_connection()
    cur  = conn.cursor()

    # Find monthly summaries that have credit but no ledger entry yet
    rows = cur.execute("""
        SELECT ms.id, ms.month_number, ms.month_year, ms.final_credit
        FROM monthly_summaries ms
        WHERE ms.username=? AND ms.final_credit > 0
          AND NOT EXISTS (
              SELECT 1 FROM credit_ledger cl
              WHERE cl.username=ms.username
                AND cl.ref_month=ms.month_number
                AND cl.ref_year=ms.month_year
                AND cl.reason='MONTHLY_CREDIT'
          )
    """, (username,)).fetchall()

    for _, month, year, credit in rows:
        _add_ledger_entry(conn, username, credit, "MONTHLY_CREDIT",
                          ref_month=month, ref_year=year)

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# 6-MONTH EXPIRY
# ─────────────────────────────────────────────
def expire_old_points(username: str):
    """Archive and zero out points older than 6 months."""
    cutoff = datetime.now() - timedelta(days=POINT_EXPIRY_DAYS)
    conn   = get_connection()
    cur    = conn.cursor()

    rows = cur.execute("""
        SELECT id, change_pts, created_at FROM credit_ledger
        WHERE username=? AND created_at < ? AND reason != 'EXPIRY_6_MONTHS'
    """, (username, cutoff.isoformat())).fetchall()

    if not rows:
        conn.close()
        return

    expiring_sum = sum(r[1] for r in rows)
    if expiring_sum > 0:
        oldest = min(r[2] for r in rows)
        cur.execute("""
            INSERT INTO credit_history (username, archived_pts, period_start, period_end)
            VALUES (?, ?, ?, ?)
        """, (username, expiring_sum, oldest[:10], cutoff.date().isoformat()))
        _add_ledger_entry(conn, username, -expiring_sum, "EXPIRY_6_MONTHS")

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# BOOK CATALOG & REDEMPTION
# ─────────────────────────────────────────────
def get_book_catalog():
    conn   = get_connection()
    rows   = conn.execute(
        "SELECT id, title, author, points_required, tier, emoji, cover_url, description FROM book_catalog ORDER BY points_required"
    ).fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "author": r[2],
             "points": r[3], "tier": r[4], "emoji": r[5],
             "cover": r[6] or "", "desc": r[7] or ""} for r in rows]


def redeem_book(username: str, book_id: int) -> dict:
    """Attempt to redeem a book. Returns {success, message}."""
    conn = get_connection()
    cur  = conn.cursor()

    book = cur.execute(
        "SELECT title, points_required FROM book_catalog WHERE id=?", (book_id,)
    ).fetchone()
    if not book:
        conn.close()
        return {"success": False, "message": "Book not found."}

    title, cost = book
    balance = get_credit_balance(username)

    if balance < cost:
        conn.close()
        return {"success": False, "message": f"Need {cost} pts — you have {balance} pts ({cost - balance} more needed)."}

    # Check not already redeemed
    already = cur.execute(
        "SELECT id FROM redemptions WHERE username=? AND book_id=?", (username, book_id)
    ).fetchone()
    if already:
        conn.close()
        return {"success": False, "message": "You have already redeemed this book!"}

    cur.execute("""
        INSERT INTO redemptions (username, book_id, book_title, points_spent)
        VALUES (?, ?, ?, ?)
    """, (username, book_id, title, cost))
    _add_ledger_entry(conn, username, -cost, "REDEMPTION")
    conn.commit()
    conn.close()
    return {"success": True, "message": f"🎉 '{title}' is yours! {cost} pts spent."}


def get_redemption_history(username: str):
    conn  = get_connection()
    rows  = conn.execute("""
        SELECT book_title, points_spent, redeemed_at
        FROM redemptions WHERE username=? ORDER BY redeemed_at DESC
    """, (username,)).fetchall()
    conn.close()
    return [{"title": r[0], "points": r[1], "date": r[2][:10]} for r in rows]


# ─────────────────────────────────────────────
# DEMO DATA SEEDING (for testing without real scans)
# ─────────────────────────────────────────────
def seed_demo_sessions(username: str):
    """
    Seeds 4 weeks of realistic demo sessions for a user if none exist.
    Gives varied patterns so the savior mechanic is visible.
    """
    conn = get_connection()
    existing = conn.execute(
        "SELECT COUNT(*) FROM study_sessions WHERE username=?", (username,)
    ).fetchone()[0]
    conn.close()
    if existing > 0:
        return

    rng   = random.Random(username)
    today = date.today()
    # Go back 4 weeks
    week_patterns = [
        # (hours per open day pattern for the week)
        [3.5, 2.0, 0,   3.0, 3.5, 4.0],  # Week 4 (current): ~16h — misses threshold
        [4.0, 4.0, 3.5, 4.0, 4.0, 4.5],  # Week 3: ~24h — hits threshold
        [3.0, 3.0, 3.0, 3.0, 3.0, 3.0],  # Week 2: 18h — misses threshold
        [4.5, 4.5, 4.0, 4.5, 4.5, 5.0],  # Week 1 (oldest): ~27h — hits threshold
    ]

    # Days in each week going backwards (Mon=0 ... Sat=5, skip Sun=6)
    for w, pattern in enumerate(reversed(week_patterns)):
        # Find the Monday of that week
        days_back  = (today.weekday()) + (w * 7)
        week_start = today - timedelta(days=days_back)
        for day_offset, hours in enumerate(pattern):
            if hours <= 0:
                continue
            session_date = week_start + timedelta(days=day_offset)
            if session_date > today:
                continue
            if session_date.weekday() == SUNDAY:
                continue
            # Create a plausible scan_in / scan_out
            hour_in  = rng.randint(9, 11)
            scan_in  = datetime(session_date.year, session_date.month,
                                session_date.day, hour_in, rng.randint(0, 30))
            scan_out = scan_in + timedelta(hours=hours)
            wn, wy   = _iso_week(session_date)
            conn = get_connection()
            conn.execute("""
                INSERT INTO study_sessions
                    (username, session_date, scan_in, scan_out, duration_hours,
                     week_number, week_year, month_number, month_year)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (username, session_date.isoformat(), scan_in.isoformat(),
                  scan_out.isoformat(), hours, wn, wy,
                  session_date.month, session_date.year))
            conn.commit()
            conn.close()
            _recalculate_week(username, wn, wy)

    _recalculate_month(username, today.month, today.year)
    sync_credits_from_summaries(username)


# ─────────────────────────────────────────────
# DASHBOARD DATA HELPERS
# ─────────────────────────────────────────────
def get_current_week_summary(username: str) -> dict:
    today    = date.today()
    wn, wy   = _iso_week(today)
    conn     = get_connection()
    row      = conn.execute("""
        SELECT total_hours, points_earned, threshold_met
        FROM weekly_summaries WHERE username=? AND week_number=? AND week_year=?
    """, (username, wn, wy)).fetchone()
    conn.close()
    if not row:
        return {"total_hours": 0, "points_earned": 0, "threshold_met": False,
                "hours_to_threshold": WEEKLY_THRESHOLD}
    return {
        "total_hours":        round(row[0], 2),
        "points_earned":      row[1],
        "threshold_met":      bool(row[2]),
        "hours_to_threshold": max(0, round(WEEKLY_THRESHOLD - row[0], 2)),
    }


def get_current_month_summary(username: str) -> dict:
    today = date.today()
    conn  = get_connection()
    row   = conn.execute("""
        SELECT total_hours, weekly_pts_sum, monthly_pts, top_up_applied, final_credit
        FROM monthly_summaries WHERE username=? AND month_number=? AND month_year=?
    """, (username, today.month, today.year)).fetchone()
    conn.close()
    if not row:
        return {"total_hours": 0, "weekly_pts_sum": 0, "monthly_pts": 0,
                "top_up_applied": 0, "final_credit": 0,
                "hours_to_monthly": MONTHLY_THRESHOLD}
    return {
        "total_hours":       round(row[0], 2),
        "weekly_pts_sum":    row[1],
        "monthly_pts":       row[2],
        "top_up_applied":    row[3],
        "final_credit":      row[4],
        "hours_to_monthly":  max(0, round(MONTHLY_THRESHOLD - row[0], 2)),
    }


def get_daily_hours_last_n_days(username: str, n: int = 7) -> list:
    """Returns list of {date, hours} for the last n days."""
    conn  = get_connection()
    today = date.today()
    result = []
    for i in range(n - 1, -1, -1):
        d    = today - timedelta(days=i)
        hrs  = conn.execute("""
            SELECT COALESCE(SUM(duration_hours),0) FROM study_sessions
            WHERE username=? AND session_date=? AND duration_hours IS NOT NULL
        """, (username, d.isoformat())).fetchone()[0]
        result.append({"date": d, "hours": round(hrs, 2)})
    conn.close()
    return result


def get_credit_history(username: str) -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT archived_pts, period_start, period_end, archived_at
        FROM credit_history WHERE username=? ORDER BY archived_at DESC
    """, (username,)).fetchall()
    conn.close()
    return [{"pts": r[0], "from": r[1], "to": r[2], "archived": r[3][:10]} for r in rows]
