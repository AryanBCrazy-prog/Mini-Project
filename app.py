import time
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

# 1. Page Configuration
st.set_page_config(
    page_title="QueueWise – Smart Library Occupancy Monitor",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. Initialize Database & Seed Demo Data if Needed
init_db()

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
</style>
""", unsafe_allow_html=True)

# 4. Sidebar Controls & ID-Card Scanner Simulator
with st.sidebar:
    st.title("⚙️ QueueWise Controls")
    st.caption("Smart Library Occupancy System")
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

# 5. Load Data & Analytics
df_logs = fetch_occupancy_logs(days=history_days)
status = get_current_status(df_logs)
hourly_profile = compute_hourly_profile(df_logs)
recommendations = recommend_visiting_hours(hourly_profile)

# 6. Header & Demonstration Data Notice
st.title("📚 QueueWise – Smart Library Occupancy Monitoring System")
st.markdown("""
<div class="demo-banner">
    <strong>ℹ️ Demonstration Mode Active:</strong> Live integration with the college's physical ID-card turnstile API is pending administrative access. The dashboard is currently running on <strong>clearly labelled demonstration and simulated turnstile scan data</strong>.
</div>
""", unsafe_allow_html=True)

# 7. Top Row: Crowd Badge, Freshness Indicator & Core KPI Metrics
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

# 8. Middle Row: Live Gauge + Smart Visiting Recommendations
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

# 9. Bottom Row: Interactive Historical Analytics Tabs
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

# 10. Automatic Refresh Loop
if auto_refresh:
    time.sleep(refresh_interval)
    if simulate_on_refresh:
        simulate_random_turnstile_burst()
    st.rerun()
