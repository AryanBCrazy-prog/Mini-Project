# Mini-Project
# 📚 QueueWise – Smart Library Occupancy Monitoring System

QueueWise is a Python and Streamlit application that helps college students check real-time library crowd levels before visiting. It processes entry and exit counts from the library's ID-card turnstile system, stores occupancy history in SQLite, and suggests the least crowded visiting hours.

## 🚀 Key Features
- **Live Occupancy & Crowd Indicator:** Displays estimated headcount and classifies status into **Low (<40%)**, **Moderate (40–75%)**, and **High (>75%)**.
- **Entry & Exit Turnstile Analytics:** Tracks daily cumulative entries, exits, and net flow.
- **Smart Visit Planner:** Analyses historical SQLite data with Pandas to recommend the top 3 quietest hours to visit.
- **Interactive Plotly Visualisations:** Occupancy timeline, hourly profile bar chart, and weekly crowd heatmap.
- **ID-Card Scanner Simulator:** Built-in sidebar simulator for demonstrating live student entry/exit bursts prior to production turnstile API integration.
- **Student Authentication:** Secure portal login & sign-up with college domain verification (`@mitwpu.edu.in`) and OTP verification.
- **Personal Student Dashboard:** Goal setting (1–12 hours), daily progress tracking, weekly study hours timeline, and 0-baseline logging.
- **Credit Hour & Book Redemption System:** Threshold-gated points mechanism (weekly ≥20h and monthly ≥75h safety-net) with an in-app catalog to redeem books as permanent gifts.
