from datetime import datetime
import pandas as pd
from src.database import MAX_CAPACITY

def get_current_status(df: pd.DataFrame) -> dict:
    """Extracts the latest occupancy state, today's totals, and data freshness."""
    if df.empty:
        return {
            "occupancy": 0,
            "capacity": MAX_CAPACITY,
            "percentage": 0.0,
            "crowd_level": "Low",
            "last_updated": "N/A",
            "minutes_ago": 0,
            "today_entries": 0,
            "today_exits": 0,
            "net_change_last": 0
        }

    latest = df.iloc[-1]
    now = datetime.now()
    last_time = latest["timestamp"].to_pydatetime()
    minutes_ago = max(0, int((now - last_time).total_seconds() // 60))

    # Filter logs for today
    today_df = df[df["timestamp"].dt.date == now.date()]
    today_entries = int(today_df["entries_interval"].sum()) if not today_df.empty else int(latest["entries_interval"])
    today_exits = int(today_df["exits_interval"].sum()) if not today_df.empty else int(latest["exits_interval"])

    occ = int(latest["current_occupancy"])
    pct = round((occ / MAX_CAPACITY) * 100, 1)
    net_last = int(latest["entries_interval"]) - int(latest["exits_interval"])

    return {
        "occupancy": occ,
        "capacity": MAX_CAPACITY,
        "percentage": pct,
        "crowd_level": latest["crowd_level"],
        "last_updated": last_time.strftime("%d %b %Y, %I:%M:%S %p"),
        "minutes_ago": minutes_ago,
        "today_entries": today_entries,
        "today_exits": today_exits,
        "net_change_last": net_last
    }

def compute_hourly_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Calculates average occupancy and crowd level for each operating hour (8 AM - 8 PM)."""
    if df.empty:
        return pd.DataFrame()

    temp = df.copy()
    temp["hour"] = temp["timestamp"].dt.hour
    temp = temp[(temp["hour"] >= 8) & (temp["hour"] <= 20)]

    hourly = (
        temp.groupby("hour", as_index=False)
        .agg(
            avg_occupancy=("current_occupancy", "mean"),
            peak_occupancy=("current_occupancy", "max"),
            avg_entries=("entries_interval", "mean"),
            avg_exits=("exits_interval", "mean")
        )
    )
    hourly["avg_occupancy"] = hourly["avg_occupancy"].round(0).astype(int)
    hourly["occupancy_pct"] = ((hourly["avg_occupancy"] / MAX_CAPACITY) * 100).round(1)
    hourly["hour_label"] = hourly["hour"].apply(
        lambda h: datetime.strptime(str(h), "%H").strftime("%I:00 %p")
    )
    return hourly

def recommend_visiting_hours(hourly_df: pd.DataFrame, top_n: int = 3) -> dict:
    """Identifies the least crowded hours to recommend to students and the busiest hours to avoid."""
    if hourly_df.empty:
        return {"best_slots": [], "busy_slots": []}

    sorted_asc = hourly_df.sort_values(by="avg_occupancy", ascending=True)
    sorted_desc = hourly_df.sort_values(by="avg_occupancy", ascending=False)

    best_slots = []
    for _, row in sorted_asc.head(top_n).iterrows():
        best_slots.append({
            "time": row["hour_label"],
            "avg_occ": int(row["avg_occupancy"]),
            "pct": float(row["occupancy_pct"])
        })

    busy_slots = []
    for _, row in sorted_desc.head(top_n).iterrows():
        busy_slots.append({
            "time": row["hour_label"],
            "avg_occ": int(row["avg_occupancy"]),
            "pct": float(row["occupancy_pct"])
        })

    return {"best_slots": best_slots, "busy_slots": busy_slots}

def compute_day_hour_heatmap(df: pd.DataFrame) -> pd.DataFrame:
    """Creates a Day-of-Week vs Hour pivot table for heatmap visualization."""
    if df.empty:
        return pd.DataFrame()

    temp = df.copy()
    temp["day_name"] = temp["timestamp"].dt.day_name()
    temp["hour"] = temp["timestamp"].dt.hour
    temp = temp[(temp["hour"] >= 8) & (temp["hour"] <= 20)]

    days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot = temp.pivot_table(
        index="day_name",
        columns="hour",
        values="current_occupancy",
        aggfunc="mean"
    ).reindex(days_order)

    pivot.columns = [datetime.strptime(str(h), "%H").strftime("%I %p") for h in pivot.columns]
    return pivot.fillna(0).round(0)
