import hashlib
import hmac
import os
import random
import re
import smtplib
import sqlite3
import time
from email.message import EmailMessage

import streamlit as st

# ---------- settings ----------
DB_FILE = "users.db"
COLLEGE_DOMAIN = "mitwpu.edu.in"   # change this if your college email domain is different
OTP_VALID_SECONDS = 300            # otp works for 5 minutes
MAX_OTP_TRIES = 3


# ---------- database part ----------
def get_conn():
    return sqlite3.connect(DB_FILE)


def init_users_table():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def hash_password(password, salt):
    # never store the real password, only the hash
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()


def find_user(identifier):
    # identifier can be username or email
    conn = get_conn()
    row = conn.execute(
        "SELECT username, email, password_hash, salt, created_at FROM users "
        "WHERE username = ? OR email = ?",
        (identifier.strip(), identifier.strip().lower()),
    ).fetchone()
    conn.close()
    return row


def create_user(username, email, password):
    salt = os.urandom(16).hex()
    pw_hash = hash_password(password, salt)
    conn = get_conn()
    conn.execute(
        "INSERT INTO users (username, email, password_hash, salt, created_at) "
        "VALUES (?, ?, ?, ?, date('now'))",
        (username, email, pw_hash, salt),
    )
    conn.commit()
    conn.close()


def check_login(identifier, password):
    user = find_user(identifier)
    if user is None:
        return None
    username, email, stored_hash, salt, created_at = user
    if hmac.compare_digest(hash_password(password, salt), stored_hash):
        return {"username": username, "email": email, "created_at": created_at}
    return None


# ---------- validation ----------
def is_valid_college_email(email):
    pattern = r"^[A-Za-z0-9._%+-]+@" + re.escape(COLLEGE_DOMAIN) + r"$"
    return re.match(pattern, email) is not None


# ---------- otp part ----------
def make_otp():
    return str(random.SystemRandom().randint(100000, 999999))


def send_otp_email(to_email, otp):
    """Sends the otp using SMTP settings. Returns True if sent, False if not configured/failed.
    Put these in .streamlit/secrets.toml (or environment variables):
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
    """
    def get_setting(name):
        try:
            return st.secrets[name]
        except Exception:
            return os.environ.get(name)

    host = get_setting("SMTP_HOST")
    port = get_setting("SMTP_PORT") or 587
    user = get_setting("SMTP_USER")
    password = get_setting("SMTP_PASSWORD")

    if not (host and user and password):
        return False

    msg = EmailMessage()
    msg["Subject"] = "QueueWise verification code"
    msg["From"] = user
    msg["To"] = to_email
    msg.set_content(
        f"Your QueueWise verification code is {otp}.\n"
        f"It is valid for {OTP_VALID_SECONDS // 60} minutes. Do not share it with anyone."
    )

    try:
        with smtplib.SMTP(host, int(port), timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return True
    except Exception:
        return False


# ---------- pages ----------
def show_login_tab():
    st.subheader("Log in")
    identifier = st.text_input("Username or college email", key="login_id")
    password = st.text_input("Password", type="password", key="login_pw")

    if st.button("Log in", type="primary", use_container_width=True):
        if not identifier or not password:
            st.error("Please fill in both fields.")
            return
        user = check_login(identifier, password)
        if user is None:
            st.error("Wrong username/email or password.")
        else:
            st.session_state["user"] = user
            st.rerun()


def show_signup_tab():
    st.subheader("Create a new account")

    # step 2: user already got the otp, ask for it
    if "pending_signup" in st.session_state:
        show_otp_step()
        return

    # step 1: basic details
    email = st.text_input("College email", placeholder=f"name@{COLLEGE_DOMAIN}", key="su_email")
    username = st.text_input("Choose a username", key="su_username")
    password = st.text_input("Create password", type="password", key="su_pw")
    confirm = st.text_input("Confirm password", type="password", key="su_pw2")

    if st.button("Send verification code", type="primary", use_container_width=True):
        email = email.strip().lower()
        username = username.strip()

        if not is_valid_college_email(email):
            st.error(f"Please use your college email (@{COLLEGE_DOMAIN}).")
        elif len(username) < 3:
            st.error("Username must be at least 3 characters.")
        elif len(password) < 6:
            st.error("Password must be at least 6 characters.")
        elif password != confirm:
            st.error("Passwords do not match.")
        elif find_user(email) or find_user(username):
            st.error("This email or username is already registered. Try logging in.")
        else:
            otp = make_otp()
            sent = send_otp_email(email, otp)
            st.session_state["pending_signup"] = {
                "email": email,
                "username": username,
                "password": password,
                "otp": otp,
                "expires": time.time() + OTP_VALID_SECONDS,
                "tries": 0,
                "email_sent": sent,
            }
            st.rerun()


def show_otp_step():
    pending = st.session_state["pending_signup"]
    st.write(f"Enter the 6-digit code for **{pending['email']}**.")

    if pending["email_sent"]:
        st.caption("We have sent a verification code to your email.")
    else:
        # email is not set up yet, so we show the code here for testing
        st.warning("Email sending is not configured, so this is demo mode.")
        st.info(f"Demo verification code: **{pending['otp']}**")

    entered = st.text_input("Verification code", max_chars=6, key="otp_input")

    col1, col2 = st.columns(2)
    if col1.button("Verify and create account", type="primary", use_container_width=True):
        if time.time() > pending["expires"]:
            st.error("Code expired. Please go back and request a new one.")
        elif pending["tries"] >= MAX_OTP_TRIES:
            st.error("Too many wrong attempts. Please request a new code.")
        elif entered.strip() == pending["otp"]:
            create_user(pending["username"], pending["email"], pending["password"])
            st.session_state["user"] = {
                "username": pending["username"],
                "email": pending["email"],
                "created_at": time.strftime("%Y-%m-%d"),
            }
            del st.session_state["pending_signup"]
            st.rerun()
        else:
            pending["tries"] += 1
            st.error("Wrong code, try again.")

    if col2.button("Go back", use_container_width=True):
        del st.session_state["pending_signup"]
        st.rerun()


def show_auth_page():
    """First screen of the website. Nothing else loads until the user logs in."""
    init_users_table()

    _, middle, _ = st.columns([1, 2, 1])
    with middle:
        st.title("📚 QueueWise")
        st.caption("Smart Library Occupancy Monitor. Please log in to continue.")

        login_tab, signup_tab = st.tabs(["Log in", "Sign up"])
        with login_tab:
            show_login_tab()
        with signup_tab:
            show_signup_tab()


def logout():
    st.session_state.pop("user", None)
    st.session_state.pop("pending_signup", None)
    st.rerun()
