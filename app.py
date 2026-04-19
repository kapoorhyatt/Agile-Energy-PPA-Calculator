from urllib import response
from flask import Flask, render_template, request, redirect, session, url_for, send_file, jsonify
from xhtml2pdf import pisa
from io import BytesIO
import json
import os
from datetime import datetime
import pytz
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from calculator.assumptions import DEFAULT_ASSUMPTIONS
from calculator.model import run_model
import uuid
import psycopg2
import requests
from datetime import timedelta
from dateutil import parser




ABN_GUID = "9e4c9f11-a8e2-4e1d-a3f9-048a06d577c1"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")

BLOCKED_EMAIL_DOMAINS = ["gmail.com", "outlook.com", "hotmail.com", "live.com"]

APP_BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
FROM_EMAIL = "PPA App <noreply@agileenergy.io>"



def get_db_connection():
    return psycopg2.connect(
        os.environ["DATABASE_URL"].replace("postgres://", "postgresql://")
    )

app = Flask(__name__)
app.secret_key = "dev-secret-key"

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_PERMANENT=False
)
def link_callback(uri, rel):
    if uri.startswith('/static/'):
        return os.path.join(BASE_DIR, uri.lstrip('/'))
    return uri

# Temporary users
users = {
    "master@ppa.com": {"password": generate_password_hash("master123"), "role": "admin"},
    "demo@ppa.com": {"password": generate_password_hash("demo123"), "role": "company"}
}


def send_reset_email(email, token):
    reset_link = f"{APP_BASE_URL}/reset-password/{token}"

    payload = {
        "from": FROM_EMAIL,
        "to": email,
        "subject": "Password Reset Request",
        "html": f"""
            <p>Click below to reset your password:</p>
            <a href="{reset_link}">{reset_link}</a>
            <p>This link expires in 30 minutes.</p>
        """
    }

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    response = requests.post(
        "https://api.resend.com/emails",
        json=payload,
        headers=headers
    )

    if response.status_code not in [200, 202]:
        print("Email failed:", response.text)
    else:
        print("Reset email sent successfully")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def convert_html_to_pdf(source_html, output_filename):

    with open(output_filename, "wb") as result_file:
        pdf_status = pisa.CreatePDF(src=source_html, dest=result_file)
    return pdf_status.err

# =========================
# ROUTES
# =========================
@app.route("/")
@app.route("/home")
def home():
    return render_template("home.html")

@app.route("/learn-more")
def learn_more():
    return render_template("learn_more.html")

@app.route("/case_studies")
def case_studies():
    return render_template("case_studies.html")

@app.route("/results")
def results():
    if "user" not in session or session.get("role") != "company":
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT result
        FROM submissions
        WHERE email = %s
        ORDER BY submitted_at DESC
        LIMIT 1
    """, (session["user"],))

    row = cur.fetchone()

    cur.close()
    conn.close()

    rates = {}

    if row:
        result = json.loads(row[0])

        rates_data = []
        first_row = result["results"][0]

        for term in first_row["terms"]:
            rates_data.append({
                "term": term["term"],
                "ppa_rate": term["ppa_rate_dollars"]
            })

        rates = {"rates": rates_data}

    return render_template("results.html", rates=rates)

@app.route("/sign_up", methods=["GET", "POST"])
def sign_up():
    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()

        domain = email.split("@")[-1]

        if domain in BLOCKED_EMAIL_DOMAINS:
            return render_template(
            "sign_up.html",
            error="Please use your company email address (Gmail/Outlook not allowed).",
            form_data=request.form.to_dict()
        )

        password = request.form.get("password") or ""
        name = request.form.get("name") or ""
        company = request.form.get("company") or ""
        phone = request.form.get("phone") or ""
        abn = request.form.get("abn") or ""
        address = request.form.get("address") or ""

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        cur = conn.cursor()

        # CHECK IF USER EXISTS
        cur.execute("SELECT email FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return render_template(
                "sign_up.html",
                error="You already have an account created.",
                form_data=request.form.to_dict()
            )

        # =========================
        # ✅ ABN VALIDATION (ADDED)
        # =========================
        url = f"https://abr.business.gov.au/json/AbnDetails.aspx?abn={abn}&guid={ABN_GUID}"

        try:
            res = requests.get(url)
            text = res.text
            text = text[text.find("(")+1:text.rfind(")")]
            data = json.loads(text)

            if not (data.get("Abn") and data.get("AbnStatus") == "Active"):
                cur.close()
                conn.close()
                return render_template("sign_up.html", error="Invalid or inactive ABN")

        except Exception as e:
            cur.close()
            conn.close()
            return render_template("sign_up.html", error="ABN validation failed")

        # =========================
        # INSERT USER
        # =========================
        cur.execute("""
            INSERT INTO users (
                id, email, password, name, company, phone, abn, address, submitted_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            str(uuid.uuid4()),
            email,
            hashed_password,
            name,
            company,
            phone,
            abn,
            address,
            datetime.now(pytz.timezone("Australia/Sydney")).strftime("%Y-%m-%d %H:%M:%S")
        ))

        # CREATE DEFAULT ASSUMPTIONS (THIS IS WHAT YOU WANTED)
        cur.execute("""
            INSERT INTO assumptions (id, email, data, created_at)
            VALUES (%s,%s,%s,%s)
        """, (
            str(uuid.uuid4()),
            email,
            json.dumps(DEFAULT_ASSUMPTIONS),
            datetime.now(pytz.timezone("Australia/Sydney")).strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()
        cur.close()
        conn.close()

        return redirect("/login")

    return render_template("sign_up.html")

@app.route("/validate-abn", methods=["POST"])
def validate_abn():
    abn = request.json.get("abn")

    url = f"https://abr.business.gov.au/json/AbnDetails.aspx?abn={abn}&guid={ABN_GUID}"

    try:
        res = requests.get(url)
        text = res.text
        text = text[text.find("(")+1:text.rfind(")")]
        data = json.loads(text)

        # Check if valid
        if data.get("Abn") and data.get("AbnStatus") == "Active":
            return jsonify({
                "valid": True,
                "name": data.get("EntityName")
            })
        else:
            return jsonify({"valid": False})

    except Exception as e:
        return jsonify({"valid": False})
    
@app.route("/start-new-quote")
def start_new_quote():
    session.clear()
    return redirect(url_for("calculator"))

@app.route("/sign_up_responses")
def sign_up_responses():
    if "user" not in session or session.get("role") != "admin":
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, email, name, company, phone, abn, address, logo_filename, submitted_at
        FROM users
        ORDER BY submitted_at DESC
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    submissions = [
        {
            "id": r[0],
            "email": r[1],
            "name": r[2],
            "company": r[3],
            "phone": r[4],
            "abn": r[5],
            "address": r[6],
            "logo_filename": r[7],
            "submitted_at": r[8],
        }
        for r in rows
    ]

    return render_template("sign_up_responses.html", submissions=submissions)
# --- LOGIN ROUTE ---
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        # -------------------
        # ADMIN USERS (TEMP)
        # -------------------
        admin_user = users.get(email)

        if admin_user and check_password_hash(admin_user["password"], password):
            session["user"] = email
            session["user_name"] = email.split("@")[0]  # display name
            session["role"] = admin_user["role"]

            return redirect("/admin_menu") if admin_user["role"] == "admin" else redirect("/disclaimer")

        # -------------------
        # DATABASE USERS
        # -------------------
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()

        cur.close()
        conn.close()

        if user and check_password_hash(user[3], password):

            session["user"] = user[1]        # email
            session["user_name"] = user[2]   # ✅ THIS IS THE KEY FIX
            session["role"] = "company"

            return redirect("/disclaimer")

        error = "Invalid email or password"

    return render_template("login.html", error=error)

# --- DISCLAIMER ROUTE ---
@app.route("/disclaimer", methods=["GET", "POST"])
def disclaimer():
    if "user" not in session:
        return redirect("/login")
    if session.get("role") == "admin":
        return redirect("/admin_menu")

    if request.method == "POST":
        session["accepted"] = True
        return redirect("/calculator")

    return render_template("disclaimer.html")

# =========================
# CALCULATOR ROUTE (AUTOMATIC)
# =========================
@app.route("/calculator", methods=["GET", "POST"])
def calculator():
    if "user" not in session or session.get("role") != "company":
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT data FROM assumptions WHERE email = %s
    """, (session["user"],))

    row = cur.fetchone()
    company_assumptions = json.loads(row[0]) if row else DEFAULT_ASSUMPTIONS

    def safe_float(name, default=0.0):
        value = request.form.get(name)

        if value is None or value == "":
            return default

        try:
            return float(value)
        except:
            return default

    if request.method == "POST":

        # TEXT INPUTS (DO THIS FIRST ONCE ONLY)
        project_name = request.form.get("project_name", "")
        customer_name = request.form.get("customer_name", "")
        suburb = request.form.get("suburb", "")
        state = request.form.get("state", "")

        # NUMERIC INPUTS
        solar_kw = safe_float("system_size", 0.0)
        annual_generation_mwh = safe_float("generation", 0.0)
        total_capex = safe_float("total_capex", solar_kw * 600)
        bess_kwh = safe_float("battery_size", 0.0)
        specific_yield = safe_float("yield", 0.0)

        inputs = {
            "project_name": project_name,
            "customer_name": customer_name,
            "suburb": suburb,
            "state": state,
            "solar_kw": solar_kw,
            "annual_generation_mwh": annual_generation_mwh,
            "total_capex": total_capex,
            "bess_kwh": bess_kwh,
            "specific_yield": specific_yield
        }

        result = run_model(
            submission_file=None,
            inputs=inputs,
            assumptions=company_assumptions,
            debug=True
        )

        # EXTRACT RATES SAFELY
        rates = []
        try:
            first_row = result.get("results", [{}])[0]
            for term in first_row.get("terms", []):
                rates.append({
                    "term": term.get("term"),
                    "ppa_rate": term.get("ppa_rate_dollars")
                })
        except:
            rates = []

        submission_id = str(uuid.uuid4())

        cur.execute("""
            INSERT INTO submissions (
                id, email, inputs, result, assumptions, rates, submitted_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            submission_id,
            session["user"],
            json.dumps(inputs),
            json.dumps(result),
            json.dumps(company_assumptions),
            json.dumps(rates),
            datetime.now(pytz.timezone("Australia/Sydney")).strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()
        cur.close()
        conn.close()

        return redirect("/results")

    cur.close()
    conn.close()

    return render_template("company_form.html", assumptions=company_assumptions)

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    message = None

    if request.method == "POST":
        email = request.form.get("email")

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT email FROM users WHERE email = %s", (email,))
        user = cur.fetchone()

        if user:
            token = str(uuid.uuid4())
            expires = datetime.now(pytz.timezone("Australia/Sydney")) + timedelta(minutes=30)

            cur.execute("DELETE FROM password_resets WHERE email = %s", (email,))

            cur.execute("""
                INSERT INTO password_resets (id, email, token, expires_at)
                VALUES (%s, %s, %s, %s)
            """, (
                str(uuid.uuid4()),
                email,
                token,
                expires.isoformat()
            ))

            conn.commit()

            send_reset_email(email, token)

        cur.close()
        conn.close()

        message = "If that email exists, a reset link has been sent."

    return render_template("forgot_password.html", message=message)

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT email, expires_at
        FROM password_resets
        WHERE token = %s
    """, (token,))

    row = cur.fetchone()

    if not row:
        return "Invalid or expired link"

    email, expires_at = row

    if datetime.now(pytz.timezone("Australia/Sydney")) > parser.isoparse(expires_at):
        return "Link expired"

    if request.method == "POST":
        new_password = request.form.get("password")
        hashed = generate_password_hash(new_password)

        cur.execute("""
            UPDATE users
            SET password = %s
            WHERE email = %s
        """, (hashed, email))

        cur.execute("""
            DELETE FROM password_resets WHERE token = %s
        """, (token,))

        conn.commit()

        cur.close()
        conn.close()

        return redirect("/login")

    cur.close()
    conn.close()

    return render_template("reset_password.html")

@app.route("/download_ppa_pdf")
def download_ppa_pdf():
    if "user" not in session or session.get("role") != "company":
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    # USER DATA
    cur.execute("""
        SELECT logo_filename, name, company
        FROM users
        WHERE email = %s
    """, (session["user"],))

    user = cur.fetchone()

    logo_filename = user[0] if user else None
    user_name = user[1] if user else None
    company_name = user[2] if user else None

    user_logo_url = f"/static/uploads/{logo_filename}" if logo_filename else None

    # LATEST SUBMISSION
    cur.execute("""
        SELECT result
        FROM submissions
        WHERE email = %s
        ORDER BY submitted_at DESC
        LIMIT 1
    """, (session["user"],))

    row = cur.fetchone()

    cur.close()
    conn.close()

    rates_data = {}

    if row:
        result = json.loads(row[0])

        rates_list = []
        first_row = result["results"][0]

        for term in first_row["terms"]:
            rates_list.append({
                "term": term["term"],
                "ppa_rate": term["ppa_rate_dollars"]
            })

        rates_data = {"rates": rates_list}

    now = datetime.now()

    html = render_template(
        "ppa_pdf.html",
        rates=rates_data,
        user_logo_url=user_logo_url,
        now=now,
        user_name=user_name,
        company_name=company_name
    )

    PDF_FOLDER = os.path.join("static", "PDF")
    os.makedirs(PDF_FOLDER, exist_ok=True)

    pdf_filename = f"ppa_{session['user']}_{int(now.timestamp())}.pdf"
    pdf_path = os.path.join(PDF_FOLDER, pdf_filename)

    with open(pdf_path, "wb") as f:
        pisa.CreatePDF(html, dest=f, link_callback=link_callback)

    return send_file(pdf_path, as_attachment=True)

# --- ADMIN MENU ---
@app.route("/admin_menu")
def admin_menu():
    if "user" not in session or session.get("role") != "admin":
        return redirect("/login")
    return render_template("admin_menu.html")

# --- ADMIN DASHBOARD ---
@app.route("/admin")
def admin():
    if "user" not in session or session.get("role") != "admin":
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    # -------------------------
    # SUBMISSIONS
    # -------------------------
    cur.execute("""
        SELECT id, email, inputs, result, assumptions, rates, submitted_at
        FROM submissions
        ORDER BY submitted_at DESC
    """)

    submission_rows = cur.fetchall()

    submissions = []
    for r in submission_rows:

        submissions.append({
            "id": r[0],
            "email": r[1],
            "inputs": json.loads(r[2]) if r[2] else {},
            "result": json.loads(r[3]) if r[3] else {},
            "assumptions": json.loads(r[4]) if r[4] else {},
            "rates": json.loads(r[5]) if r[5] else [],
            "submitted_at": r[6]   # ✅ FIXED (was WRONG index)
        })

    # -------------------------
    # USERS
    # -------------------------
    cur.execute("""
        SELECT id, email, name, company, phone, abn, address, submitted_at
        FROM users
        ORDER BY submitted_at DESC
    """)

    user_rows = cur.fetchall()

    users_list = []
    for r in user_rows:
        users_list.append({
            "id": r[0],
            "email": r[1],
            "name": r[2],
            "company": r[3],
            "phone": r[4],
            "abn": r[5],
            "address": r[6],
            "submitted_at": r[7],
        })

    # -------------------------
    # ASSUMPTIONS
    # -------------------------
    cur.execute("""
        SELECT email, data
        FROM assumptions
    """)

    assumption_rows = cur.fetchall()

    assumptions_data = {}
    for r in assumption_rows:
        assumptions_data[r[0]] = json.loads(r[1]) if r[1] else {}

    cur.close()
    conn.close()

    return render_template(
        "admin_dashboard.html",
        submissions=submissions,
        users=users_list,
        assumptions=assumptions_data
    )

# --- ASSUMPTIONS PAGE ---
@app.route("/assumptions", methods=["GET", "POST"])
def assumptions():
    if "user" not in session or session.get("role") != "admin":
        return redirect("/login")

    conn = get_db_connection()
    cur = conn.cursor()

    # GET ALL ASSUMPTIONS
    cur.execute("""
        SELECT email, data
        FROM assumptions
    """)

    rows = cur.fetchall()

    assumptions_data = {
        r[0]: json.loads(r[1]) if r[1] else {}
        for r in rows
    }

    # UPDATE ASSUMPTIONS
    if request.method == "POST":

        for email, data in assumptions_data.items():
            updated = data.copy()

            for key in updated.keys():
                form_key = f"{email}_{key}"
                value = request.form.get(form_key)

                if value is not None:
                    try:
                        updated[key] = float(value)
                    except:
                        updated[key] = value

            cur.execute("""
                UPDATE assumptions
                SET data = %s
                WHERE email = %s
            """, (
                json.dumps(updated),
                email
            ))

        conn.commit()

    cur.close()
    conn.close()

    return render_template("assumptions.html", assumptions=assumptions_data)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

if __name__ == "__main__":
    from init_db import create_tables
    create_tables()
    port = int(os.environ.get("PORT", 5000))  # use Render's dynamic PORT
    app.run(host="0.0.0.0", port=port)