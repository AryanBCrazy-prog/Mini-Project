# 📚 QueueWise – Smart Library Occupancy Monitoring & Student Portal

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://mini-project-dgkeuhqfkm7v58qmcp8kyk.streamlit.app/)

> **Live Deployment:** [https://mini-project-dgkeuhqfkm7v58qmcp8kyk.streamlit.app/](https://mini-project-dgkeuhqfkm7v58qmcp8kyk.streamlit.app/)

QueueWise is a modern library management and smart student occupancy portal built using **Python** and **Streamlit**. It solves real-world campus overcrowding by providing real-time turnstile analytics, floor-wise seat tracking, historical visit planning, personalized study goals, and a gamified credit hour book redemption system.

---

## 🌐 Live Demo
Access the live application directly in your browser:
👉 **[Launch QueueWise on Streamlit Cloud](https://mini-project-dgkeuhqfkm7v58qmcp8kyk.streamlit.app/)**

---

## 🚀 Key Features

### 1. 🏛️ Main Library & Real-Time Crowd Analytics
- **Live Occupancy Meter:** Interactive gauge meter displaying live student headcount with dynamic crowd level status: **Low (<40%)**, **Moderate (40–75%)**, and **High (>75%)**.
- **Floor-wise Availability:** Real-time occupancy breakdown across Ground, First, Second, and Third floors.
- **Smart Visit Planner:** Pandas-driven analysis recommending optimal low-crowd visiting slots and highlighting peak hours to avoid.
- **Turnstile Gate Analytics:** Live stream of turnstile scan bursts with daily entry/exit totals.
- **Interactive Historical Charts:** Area timeline of occupancy over time, hourly traffic bar profiles (8:00 AM – 8:00 PM), and weekly density heatmaps.

### 2. 💻 Digital Library Monitoring
- Interactive seat and PC status grid (Rows A–D) indicating busy vs. free computer terminals.

### 3. 🔐 Secure Student Authentication & Email Verification
- College domain restriction (`@mitwpu.edu.in`) with automated email OTP verification via SMTP/TLS.
- Secure PBKDF2-SHA256 password hashing with unique salt generation.

### 4. 👤 Personal Student Dashboard
- **Daily Study Goals:** Daily customizable targets (1 to 12 hours) with circular donut completion progress.
- **7-Day Trend:** Historical line graph of hours studied per day compared to the daily goal threshold.
- **Zero-Baseline Integrity:** Clean, verified study session accumulation without artificial counts.

### 5. 💎 Credit Hour System & Book Catalog
- **Threshold-Gated Points:** Earn points by logging study hours (weekly threshold: ≥20 hours).
- **Monthly Safety-Net:** Automatic catch-up mechanism guaranteeing full credit for consistent monthly attendance (≥75 hours).
- **Book Redemption Catalog:** Redeem books as permanent gifts across tiered milestones (Starter, Consistent, Dedicated, and Expert) with cover art and point ledger auditing.
- **6-Month Expiry & Archival:** Live point validity for 6 months with read-only historical archive logging.

---

## 🛠️ Tech Stack
- **Frontend & App Framework:** Streamlit
- **Data Visualizations:** Plotly Express & Plotly Graph Objects
- **Data Processing:** Pandas, NumPy
- **Database:** SQLite
- **Security:** hashlib (PBKDF2), hmac, secrets
- **Email Delivery:** Python `smtplib` with TLS encryption

---

## 👥 Project Team & Contributors
Developed by First-Year Computer Science and Engineering Students:
- **Aryan Bhagwat** ([@AryanBCrazy-prog](https://github.com/AryanBCrazy-prog)) — *Team Leader, Streamlit App Architecture, UI Integration & Deployment*
- **Piyush Chavan** ([@Piyush19279](https://github.com/Piyush19279)) — *Database Engine, Credit Calculation & Book Redemption Backend*
- **Unnati Hurdale** ([@hurdaleunnati-AIDS](https://github.com/hurdaleunnati-AIDS)) — *Authentication Flow, Analytics Engine & Heatmap Visualizations*
- **Kazi Mubeen** ([@kazimubeen16-ai](https://github.com/kazimubeen16-ai)) — *Turnstile Gate Simulator & Environment Configuration*

---

## 💻 Local Setup & Running

1. **Clone the repository:**
   ```bash
   git clone https://github.com/QueueWise/Mini-Project.git
   cd Mini-Project
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **(Optional) Configure Email Secrets:**
   Create `.streamlit/secrets.toml` with your credentials:
   ```toml
   SMTP_HOST = "smtp.gmail.com"
   SMTP_PORT = 587
   SMTP_USER = "your-email@gmail.com"
   SMTP_PASSWORD = "your-app-password"
   ```

4. **Run the Streamlit application:**
   ```bash
   streamlit run app.py
   ```
