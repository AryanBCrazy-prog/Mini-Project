import time
import random
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from src.database import init_db, fetch_occupancy_logs, fetch_recent_scans, MAX_CAPACITY
from src.simulator import record_scan_batch, simulate_random_turnstile_burst
from src.analytics import (
    get_current_status,
    compute_hourly_profile,
    recommend_visiting_hours,
    compute_day_hour_heatmap,
)
from src.auth import show_auth_page, logout
from src.credits import (
    init_credit_tables, seed_demo_sessions, expire_old_points,
    sync_credits_from_summaries, get_credit_balance,
    get_current_week_summary, get_current_month_summary,
    get_daily_hours_last_n_days, get_book_catalog,
    redeem_book, get_redemption_history, get_credit_history,
    WEEKLY_THRESHOLD, MONTHLY_THRESHOLD,
)

# 1. Page Configuration (must be the first streamlit command)
st.set_page_config(
    page_title="QueueWise – Smart Library Occupancy Monitor",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. Initialize Databases
init_db()
init_credit_tables()

# 3. Custom CSS for Badges and Cards
st.markdown("""
<style>
    .demo-banner {
        background-color: #FEF3C7;
        border-left: 5px solid #F59E0B;
        padding: 12px 16px;
        border-radius: 6px;
        color: #92400E;
        font-size: 0.95rem;
        margin-bottom: 20px;
    }
    .crowd-badge {
        display: inline-block;
        padding: 8px 18px;
        border-radius: 999px;
        font-weight: 700;
        font-size: 1.1rem;
        text-align: center;
    }
    .badge-low { background-color: #DCFCE7; color: #166534; border: 1px solid #86EFAC; }
    .badge-moderate { background-color: #FEF9C3; color: #854D0E; border: 1px solid #FDE047; }
    .badge-high { background-color: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; }
    .freshness-pill {
        font-size: 0.85rem;
        color: #475569;
        background: #F1F5F9;
        padding: 4px 10px;
        border-radius: 4px;
    }
    .pc-box {
        display: inline-block;
        width: 62px;
        padding: 10px 0;
        margin: 4px;
        border-radius: 8px;
        text-align: center;
        font-weight: 700;
        font-size: 0.9rem;
        color: white;
    }
    .pc-free { background-color: #16A34A; }
    .pc-busy { background-color: #DC2626; }
    .row-label {
        display: inline-block;
        width: 70px;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)

# 4. Login check - nobody gets past this without logging in
if "user" not in st.session_state:
    show_auth_page()
    st.stop()

user = st.session_state["user"]

# 4b. Per-user credit system init (runs once per login session)
if "credits_initialized" not in st.session_state:
    expire_old_points(user["username"])
    sync_credits_from_summaries(user["username"])
    # NOTE: seed_demo_sessions removed — fresh users start at 0 hours
    st.session_state["credits_initialized"] = True

# floors of the library (share = part of the total capacity on that floor)
FLOORS = [
    {"name": "Ground Floor", "share": 0.15},
    {"name": "First Floor", "share": 0.25},
    {"name": "Second Floor", "share": 0.30},
    {"name": "Third Floor", "share": 0.30},
]

# digital library layout
PC_ROWS = ["A", "B", "C", "D"]
PCS_PER_ROW = 10


# 5. Sidebar Controls & ID-Card Scanner Simulator
with st.sidebar:
    st.title("⚙️ QueueWise Controls")
    st.caption(f"Logged in as **{user['username']}**")
    if st.button("🚪 Log out", use_container_width=True):
        logout()
    st.divider()

    # Auto-refresh controls
    st.subheader("🔄 Live Refresh Settings")
    auto_refresh = st.toggle("Enable Auto-Refresh", value=False)
    refresh_interval = st.slider("Refresh Interval (seconds)", min_value=5, max_value=60, value=15, step=5)
    simulate_on_refresh = st.checkbox("Simulate gate traffic on auto-refresh", value=True)

    if st.button("🔄 Refresh Dashboard Now", use_container_width=True):
        st.rerun()

    st.divider()

    # Turnstile ID-Card Simulator Panel
    st.subheader("🪪 ID-Card Scanner Simulator")
    st.caption("Test how the dashboard responds when students scan their ID cards at the library entrance/exit.")

    if st.button("⚡ Simulate Random Turnstile Burst", use_container_width=True, type="primary"):
        result = simulate_random_turnstile_burst()
        st.toast(f"Recorded +{result['entries']} entries, -{result['exits']} exits!", icon="🪪")
        st.rerun()

    with st.expander("Manual Entry / Exit Injection"):
        manual_entries = st.number_input("Students Entering", min_value=0, max_value=50, value=5)
        manual_exits = st.number_input("Students Exiting", min_value=0, max_value=50, value=2)
        if st.button("Submit Manual Scan Count", use_container_width=True):
            record_scan_batch(int(manual_entries), int(manual_exits), source="MANUAL_TEST")
            st.success("Scan batch logged to SQLite!")
            st.rerun()

    st.divider()
    history_days = st.selectbox("Historical Analysis Window", options=[3, 7, 14], index=1, format_func=lambda x: f"Last {x} Days")

# 6. Load Data & Analytics
df_logs = fetch_occupancy_logs(days=history_days)
status = get_current_status(df_logs)
hourly_profile = compute_hourly_profile(df_logs)
recommendations = recommend_visiting_hours(hourly_profile)


# ---------- helper functions for the tabs ----------

def make_computer_status():
    # demo data: randomly decide which computers are occupied
    data = {}
    for row in PC_ROWS:
        for num in range(1, PCS_PER_ROW + 1):
            data[f"{row}{num}"] = random.random() < 0.45   # True = occupied
    return data


def show_floor_status():
    st.subheader("🏢 Floor-wise Seat Availability")
    st.caption("Demo split of the current occupancy across floors.")

    cols = st.columns(len(FLOORS))
    for col, floor in zip(cols, FLOORS):
        capacity = int(MAX_CAPACITY * floor["share"])
        occupied = min(capacity, round(status["occupancy"] * floor["share"]))
        percent = int(occupied / capacity * 100) if capacity else 0
        with col:
            st.markdown(f"**{floor['name']}**")
            st.metric("Occupied / Capacity", f"{occupied} / {capacity}", delta=f"{capacity - occupied} seats free", delta_color="normal")
            st.progress(percent / 100, text=f"{percent}% full")


def show_main_library():
    st.title("📚 QueueWise – Main Library")
    st.markdown("""
    <div class="demo-banner">
        <strong>ℹ️ Demonstration Mode Active:</strong> Live integration with the college's physical ID-card turnstile API is pending administrative access. The dashboard is currently running on <strong>clearly labelled demonstration and simulated turnstile scan data</strong>.
    </div>
    """, unsafe_allow_html=True)

    # Top Row: Crowd Badge, Freshness Indicator & Core KPI Metrics
    badge_class = {
        "Low": "badge-low",
        "Moderate": "badge-moderate",
        "High": "badge-high"
    }.get(status["crowd_level"], "badge-low")

    freshness_icon = "🟢 Fresh" if status["minutes_ago"] <= 15 else "🟡 Scheduled Snapshot"

    top_col1, top_col2 = st.columns([2, 3])
    with top_col1:
        st.markdown(
            f'Current Crowd Status: <span class="crowd-badge {badge_class}">{status["crowd_level"].upper()} CROWD</span>',
            unsafe_allow_html=True
        )
    with top_col2:
        st.markdown(
            f'<div style="text-align:right;"><span class="freshness-pill">{freshness_icon} • Last Updated: {status["last_updated"]} ({status["minutes_ago"]} min ago)</span></div>',
            unsafe_allow_html=True
        )

    st.write("")

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric(
        label="Estimated People Inside",
        value=f"{status['occupancy']} / {status['capacity']}",
        delta=f"{status['net_change_last']:+d} net last scan",
        delta_color="inverse"
    )
    kpi2.metric(
        label="Occupancy Rate",
        value=f"{status['percentage']}%",
        delta=f"{status['capacity'] - status['occupancy']} seats free",
        delta_color="normal"
    )
    kpi3.metric(
        label="Today's Total Entries",
        value=f"{status['today_entries']:,}",
        help="Cumulative ID card entry scans recorded today"
    )
    kpi4.metric(
        label="Today's Total Exits",
        value=f"{status['today_exits']:,}",
        help="Cumulative ID card exit scans recorded today"
    )

    st.divider()
    show_floor_status()
    st.divider()

    # Middle Row: Live Gauge + Smart Visiting Recommendations
    mid_left, mid_right = st.columns([1.2, 1.3])

    with mid_left:
        st.subheader("🎯 Live Occupancy Meter")
        gauge_fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=status["occupancy"],
            number={"suffix": f" / {MAX_CAPACITY}", "font": {"size": 34}},
            gauge={
                "axis": {"range": [0, MAX_CAPACITY], "tickwidth": 1},
                "bar": {"color": "#1E293B"},
                "steps": [
                    {"range": [0, int(MAX_CAPACITY * 0.40)], "color": "#86EFAC"},
                    {"range": [int(MAX_CAPACITY * 0.40), int(MAX_CAPACITY * 0.75)], "color": "#FDE047"},
                    {"range": [int(MAX_CAPACITY * 0.75), MAX_CAPACITY], "color": "#FCA5A5"},
                ],
                "threshold": {
                    "line": {"color": "#DC2626", "width": 4},
                    "thickness": 0.8,
                    "value": status["occupancy"]
                }
            }
        ))
        gauge_fig.update_layout(height=290, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(gauge_fig, use_container_width=True)

    with mid_right:
        st.subheader("💡 Smart Visit Planner (Best Times to Visit)")
        st.caption(f"Calculated from historical ID-card scan patterns over the last {history_days} days.")

        rec_col1, rec_col2 = st.columns(2)
        with rec_col1:
            st.markdown("##### ✅ Recommended Low-Crowd Hours")
            for slot in recommendations["best_slots"]:
                st.success(f"**{slot['time']}** — ~{slot['avg_occ']} students ({slot['pct']}%)")

        with rec_col2:
            st.markdown("##### ⚠️ Peak Hours to Avoid")
            for slot in recommendations["busy_slots"]:
                st.error(f"**{slot['time']}** — ~{slot['avg_occ']} students ({slot['pct']}%)")

        st.info(
            "**Tip:** Visiting during **Low Crowd (<40% capacity)** windows guarantees quieter study zones and immediate seat availability."
        )

    st.divider()

    # Bottom Row: Interactive Historical Analytics Tabs
    st.subheader("📊 Historical Occupancy & Gate Flow Analytics")
    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 Occupancy Timeline",
        "🕒 Hourly Crowd Profile",
        "🗓️ Weekly Heatmap",
        "🪪 Recent Gate Scans (Demo Log)"
    ])

    with tab1:
        if not df_logs.empty:
            fig_timeline = px.area(
                df_logs,
                x="timestamp",
                y="current_occupancy",
                title=f"Library Occupancy Trend (Last {history_days} Days)",
                labels={"timestamp": "Date & Time", "current_occupancy": "Estimated People Inside"},
                color_discrete_sequence=["#2563EB"]
            )
            fig_timeline.add_hline(
                y=int(MAX_CAPACITY * 0.75),
                line_dash="dash",
                line_color="#DC2626",
                annotation_text="High Crowd Threshold (75%)"
            )
            fig_timeline.add_hline(
                y=int(MAX_CAPACITY * 0.40),
                line_dash="dot",
                line_color="#16A34A",
                annotation_text="Moderate Crowd Threshold (40%)"
            )
            fig_timeline.update_layout(height=380, yaxis_range=[0, MAX_CAPACITY + 20])
            st.plotly_chart(fig_timeline, use_container_width=True)

    with tab2:
        if not hourly_profile.empty:
            fig_hourly = px.bar(
                hourly_profile,
                x="hour_label",
                y="avg_occupancy",
                color="occupancy_pct",
                color_continuous_scale=["#22C55E", "#EAB308", "#EF4444"],
                title="Average Library Occupancy by Hour of Day (8:00 AM – 8:00 PM)",
                labels={
                    "hour_label": "Hour of Day",
                    "avg_occupancy": "Avg People Inside",
                    "occupancy_pct": "Occupancy %"
                },
                text="avg_occupancy"
            )
            fig_hourly.update_layout(height=380, xaxis_tickangle=-30)
            st.plotly_chart(fig_hourly, use_container_width=True)

    with tab3:
        heatmap_df = compute_day_hour_heatmap(df_logs)
        if not heatmap_df.empty:
            fig_heat = px.imshow(
                heatmap_df,
                labels=dict(x="Operating Hour", y="Day of Week", color="Avg Occupancy"),
                color_continuous_scale="YlOrRd",
                aspect="auto",
                title="Weekly Crowd Density Heatmap"
            )
            fig_heat.update_layout(height=380)
            st.plotly_chart(fig_heat, use_container_width=True)

    with tab4:
        st.caption("Latest simulated ID-card scans recorded at library turnstiles (Student IDs are hashed for privacy).")
        recent_scans_df = fetch_recent_scans(limit=12)
        st.dataframe(recent_scans_df, use_container_width=True, hide_index=True)


def show_digital_library():
    st.title("💻 Digital Library (Ground Floor)")
    st.caption("Computers available for students. Green = free, Red = occupied. Demo data for now.")

    # keep the computer status in session so it does not change on every click
    if "computers" not in st.session_state:
        st.session_state["computers"] = make_computer_status()
    computers = st.session_state["computers"]

    if st.button("🔄 Refresh computer status"):
        st.session_state["computers"] = make_computer_status()
        st.rerun()

    total = len(computers)
    occupied = sum(computers.values())

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Computers", total)
    c2.metric("Occupied", occupied)
    c3.metric("Free", total - occupied)

    st.divider()

    # draw each row of computers
    for row in PC_ROWS:
        boxes = ""
        for num in range(1, PCS_PER_ROW + 1):
            name = f"{row}{num}"
            css_class = "pc-busy" if computers[name] else "pc-free"
            boxes += f'<span class="pc-box {css_class}">{name}</span>'
        st.markdown(f'<span class="row-label">Row {row}</span>{boxes}', unsafe_allow_html=True)

    st.write("")
    st.markdown("🟩 Free &nbsp;&nbsp; 🟥 Occupied")


def show_my_dashboard():
    import datetime as dt

    st.title("👤 My Dashboard")
    uname = user["username"]

    # ── Personal Information ─────────────────────────────────────────────────
    st.subheader("Personal Information")
    st.markdown("""
    <style>
        .info-card { text-align: center; padding: 14px 10px; }
        .info-label {
            font-size: 0.78rem; font-weight: 700;
            text-transform: uppercase; letter-spacing: 0.08em;
            color: #64748B; margin-bottom: 6px;
        }
        .info-value { font-size: 1.05rem; font-weight: 500; color: #1E293B; word-break: break-all; }
    </style>
    """, unsafe_allow_html=True)

    info1, info2, info3 = st.columns(3)
    for col, label, value in [
        (info1, "Username",      user["username"]),
        (info2, "College Email", user["email"]),
        (info3, "Member Since",  user["created_at"]),
    ]:
        col.markdown(
            f'<div class="info-card"><div class="info-label">{label}</div>'
            f'<div class="info-value">{value}</div></div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Live Credit Balance ───────────────────────────────────────────────────
    balance   = get_credit_balance(uname)
    week_sum  = get_current_week_summary(uname)
    month_sum = get_current_month_summary(uname)

    st.subheader("💎 Credit Points")
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Live Balance",          f"{balance} pts")
    b2.metric("This Week Hours",       f"{week_sum['total_hours']} h",
              delta="✅ Threshold met" if week_sum["threshold_met"] else f"⚠️ Need {week_sum['hours_to_threshold']}h more",
              delta_color="normal" if week_sum["threshold_met"] else "off")
    b3.metric("This Month Hours",      f"{month_sum['total_hours']} h",
              delta="✅ Safety-net met" if month_sum["total_hours"] >= MONTHLY_THRESHOLD else f"Need {month_sum['hours_to_monthly']}h for safety-net",
              delta_color="normal" if month_sum["total_hours"] >= MONTHLY_THRESHOLD else "off")
    b4.metric("Monthly Points Earned", f"{month_sum['final_credit']} pts",
              delta=f"+{month_sum['top_up_applied']} savior top-up" if month_sum["top_up_applied"] > 0 else "")

    # Weekly + Monthly progress bars
    prog_left, prog_right = st.columns(2)
    with prog_left:
        week_pct = min(1.0, week_sum["total_hours"] / WEEKLY_THRESHOLD)
        st.markdown(f"**Weekly threshold** — {week_sum['total_hours']}h / {WEEKLY_THRESHOLD}h needed")
        st.progress(week_pct,
                    text="✅ Unlocked!" if week_sum["threshold_met"] else f"{week_sum['hours_to_threshold']}h to unlock weekly points")
    with prog_right:
        month_pct = min(1.0, month_sum["total_hours"] / MONTHLY_THRESHOLD)
        st.markdown(f"**Monthly safety-net** — {month_sum['total_hours']}h / {MONTHLY_THRESHOLD}h needed")
        st.progress(month_pct,
                    text="✅ Safety-net active!" if month_sum["total_hours"] >= MONTHLY_THRESHOLD else f"{month_sum['hours_to_monthly']}h to activate safety-net")

    if month_sum["top_up_applied"] > 0:
        st.info(f"🛟 **Monthly Safety-Net saved you this month!** "
                f"Weekly streaks earned {month_sum['weekly_pts_sum']} pts, "
                f"but your {month_sum['total_hours']}h total triggered the safety-net — "
                f"topping up by **+{month_sum['top_up_applied']} pts** → {month_sum['final_credit']} pts total.")

    st.divider()

    # ── Daily Study Goal ──────────────────────────────────────────────────────
    today_str = dt.date.today().isoformat()
    goal_key  = f"study_goal_{uname}_{today_str}"

    st.subheader("🎯 Daily Study Goal")
    goal_col, _, _ = st.columns([1, 1, 1])
    with goal_col:
        if st.button("📋 Set Goal", use_container_width=True):
            st.session_state["show_goal_picker"] = not st.session_state.get("show_goal_picker", False)

    if st.session_state.get("show_goal_picker", False):
        goal_hours = st.selectbox(
            "How many hours do you want to study today?",
            options=list(range(1, 13)),
            index=st.session_state.get(goal_key, 4) - 1,
            format_func=lambda x: f"{x} hour{'s' if x > 1 else ''}",
            key="goal_selector",
        )
        if st.button("✅ Save Goal", type="primary"):
            st.session_state[goal_key] = goal_hours
            st.session_state["show_goal_picker"] = False
            st.success(f"Goal set: {goal_hours} hours for today!")
            st.rerun()

    daily_goal = st.session_state.get(goal_key, 4)

    st.divider()

    # ── Charts ────────────────────────────────────────────────────────────────
    st.subheader("📊 Study Analytics")
    daily_data  = get_daily_hours_last_n_days(uname, 7)
    today_hours = daily_data[-1]["hours"] if daily_data else 0

    chart_left, chart_right = st.columns(2)

    with chart_left:
        studied  = round(min(today_hours, daily_goal), 2)
        remain   = round(max(0, daily_goal - studied), 2)
        donut = go.Figure(go.Pie(
            values=[studied if studied > 0 else 0.001, remain],
            labels=["Studied", "Remaining"],
            hole=0.60, marker_colors=["#2563EB", "#E2E8F0"], textinfo="none",
        ))
        donut.update_layout(
            title_text="Today's Goal Progress",
            annotations=[{"text": f"{studied}h<br>/ {daily_goal}h",
                          "x": 0.5, "y": 0.5, "font_size": 18, "showarrow": False}],
            height=300, legend=dict(orientation="h", yanchor="bottom", y=-0.15),
            margin=dict(t=50, b=10, l=10, r=10),
        )
        st.plotly_chart(donut, use_container_width=True)

    with chart_right:
        wk_pts   = week_sum["points_earned"]
        wk_left  = max(0, 100 - wk_pts)
        credit_donut = go.Figure(go.Pie(
            values=[wk_pts if wk_pts > 0 else 0.001, wk_left],
            labels=["Earned this week", "Remaining to 100"],
            hole=0.60, marker_colors=["#16A34A", "#E2E8F0"], textinfo="none",
        ))
        credit_donut.update_layout(
            title_text="Weekly Credit Points",
            annotations=[{"text": f"{wk_pts} pts<br>this wk",
                          "x": 0.5, "y": 0.5, "font_size": 18, "showarrow": False}],
            height=300, legend=dict(orientation="h", yanchor="bottom", y=-0.15),
            margin=dict(t=50, b=10, l=10, r=10),
        )
        st.plotly_chart(credit_donut, use_container_width=True)

    # Line graph — daily hours last 7 days
    st.subheader("📈 Daily Study Hours (Last 7 Days)")
    day_labels = [d["date"].strftime("%a %d %b") for d in daily_data]
    day_hours  = [d["hours"] for d in daily_data]
    line_fig   = px.line(x=day_labels, y=day_hours, markers=True,
                         labels={"x": "Day", "y": "Hours Studied"},
                         title="Hours Studied Per Day",
                         color_discrete_sequence=["#2563EB"])
    line_fig.add_hline(y=daily_goal, line_dash="dash", line_color="#F59E0B",
                       annotation_text=f"Daily Goal ({daily_goal}h)",
                       annotation_position="top left")
    line_fig.add_hline(y=WEEKLY_THRESHOLD / 6, line_dash="dot", line_color="#94A3B8",
                       annotation_text="Avg needed for weekly threshold",
                       annotation_position="bottom right")
    line_fig.update_traces(line_width=2.5, marker_size=8)
    line_fig.update_layout(height=360, xaxis_tickangle=-20)
    st.plotly_chart(line_fig, use_container_width=True)

    # Archived credit history
    history = get_credit_history(uname)
    if history:
        st.divider()
        with st.expander("🗂️ Expired Points Archive (previous 6-month periods)"):
            for h in history:
                st.markdown(f"**{h['pts']} pts** — period {h['from']} → {h['to']} (archived {h['archived']})")


def show_book_catalog():
    st.title("📚 Book Catalog & Redemption")
    uname   = user["username"]
    balance = get_credit_balance(uname)
    catalog = get_book_catalog()
    redeemed_titles = {r["title"] for r in get_redemption_history(uname)}

    st.markdown(f"### Your Balance: **💎 {balance} pts**")
    st.caption("Books are a permanent gift — once redeemed, they are yours to keep.")
    st.divider()

    for book in catalog:
        can_afford = balance >= book["points"]
        already    = book["title"] in redeemed_titles

        # Card layout: cover image | book info | redeem button
        img_col, info_col, btn_col = st.columns([1, 4, 1.4])

        with img_col:
            if book.get("cover"):
                st.image(book["cover"], width=90)
            else:
                st.markdown("📖")

        with info_col:
            tier_colors = {
                "Starter": "#16A34A", "Consistent": "#2563EB",
                "Dedicated": "#EA580C", "Expert": "#DC2626"
            }
            tc = tier_colors.get(book["tier"], "#64748B")
            st.markdown(
                f"**{book['title']}**  \n"
                f"<span style='color:#64748B; font-size:0.88rem;'>{book['author']}</span>",
                unsafe_allow_html=True
            )
            if book.get("desc"):
                st.caption(book["desc"])
            st.markdown(
                f"<span style='font-weight:700; font-size:1rem;'>🏷️ {book['points']} pts</span> &nbsp;"
                f"<span style='background:{tc}22; color:{tc}; border:1px solid {tc}55; "
                f"border-radius:12px; padding:2px 10px; font-size:0.78rem; font-weight:600;'>"
                f"{book['emoji']} {book['tier']}</span>",
                unsafe_allow_html=True
            )
            if not can_afford and not already:
                st.caption(f"🔒 You need **{book['points'] - balance} more pts** to unlock this book")

        with btn_col:
            st.write("")   # vertical spacing
            if already:
                st.success("✅ Redeemed")
            elif can_afford:
                if st.button("Redeem 🎁", key=f"redeem_{book['id']}",
                             type="primary", use_container_width=True):
                    result = redeem_book(uname, book["id"])
                    if result["success"]:
                        st.success(result["message"])
                        st.rerun()
                    else:
                        st.error(result["message"])
            else:
                st.button("🔒 Locked", key=f"locked_{book['id']}",
                          disabled=True, use_container_width=True)

        st.divider()

    # Redemption history
    history = get_redemption_history(uname)
    if history:
        st.subheader("🧾 Your Redemption History")
        for r in history:
            st.markdown(f"📖 **{r['title']}** — {r['points']} pts spent on {r['date']}")


# 7. Navigation tabs
main_tab, digital_tab, dashboard_tab, catalog_tab = st.tabs([
    "🏛️ Main Library",
    "💻 Digital Library",
    "👤 My Dashboard",
    "📚 Book Catalog",
])

with main_tab:
    show_main_library()

with digital_tab:
    show_digital_library()

with dashboard_tab:
    show_my_dashboard()

with catalog_tab:
    show_book_catalog()

# 8. Automatic Refresh Loop
if auto_refresh:
    time.sleep(refresh_interval)
    if simulate_on_refresh:
        simulate_random_turnstile_burst()
    st.rerun()
