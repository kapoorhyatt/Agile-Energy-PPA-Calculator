from flask import Flask, render_template, request, redirect, session, url_for, send_file
from xhtml2pdf import pisa
from io import BytesIO
import json
import os
from datetime import datetime
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from calculator.assumptions import DEFAULT_ASSUMPTIONS
from calculator.model import run_model
import uuid


app = Flask(__name__)
app.secret_key = "dev-secret-key"

# Temporary users
users = {
    "master@ppa.com": {"password": generate_password_hash("master123"), "role": "admin"},
    "demo@ppa.com": {"password": generate_password_hash("demo123"), "role": "company"}
}

# =========================
# FILES & UPLOADS
# =========================
SUBMISSIONS_FILE = "submissions.json"
ASSUMPTIONS_FILE = "assumptions.json"
DATA_FILE = "sign_up_responses.json"
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)



# =========================
# HELPER FUNCTIONS
# =========================
def load_json(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_json(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)

RATES_FILE = "rates.json"

def load_rates():
    return load_json(RATES_FILE)

def save_rates(data):
    save_json(RATES_FILE, data)

def load_submissions():
    return load_json(SUBMISSIONS_FILE)

def save_submissions(submissions):
    save_json(SUBMISSIONS_FILE, submissions)

def load_assumptions():
    return load_json(ASSUMPTIONS_FILE)

def save_assumptions(data):
    save_json(ASSUMPTIONS_FILE, data)

# Ensure the file is initialized as a list
if not os.path.exists(DATA_FILE) or os.stat(DATA_FILE).st_size == 0:
    with open(DATA_FILE, "w") as f:
        json.dump([], f, indent=4)

def load_data():
    """Load sign-up submissions as a list."""
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            # If the file was {}, convert to empty list
            return []
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_data(data):
    """Save sign-up submissions."""
    if not isinstance(data, list):
        raise ValueError("Data must be a list")
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)



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

    rates = load_rates()
    return render_template("results.html", rates=rates)

# --- SIGN UP PAGE ---
@app.route("/sign_up", methods=["GET", "POST"])
def sign_up():
    if request.method == "POST":
        try:
            print("[DEBUG] Received POST to /sign_up")
            # Load existing submissions as a list
            data = load_data()
            print(f"[DEBUG] Current submissions loaded: {len(data)}")

            submission_id = str(uuid.uuid4())

            # Handle logo upload
            logo = request.files.get("logo")
            logo_filename = None
            if logo and logo.filename:
                filename = secure_filename(logo.filename)
                logo_filename = f"{submission_id}_{filename}"
                logo_path = os.path.join(UPLOAD_FOLDER, logo_filename)
                logo.save(logo_path)
                print(f"[DEBUG] Logo saved at {logo_path}")

            # Collect form data
            password_raw = request.form.get("password")
            submission = {
                "id": submission_id,
                "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "name": request.form.get("name", ""),
                "email": request.form.get("email", ""),
                "phone": request.form.get("phone", ""),
                "company": request.form.get("company", ""),
                "abn": request.form.get("abn", ""),
                "address": request.form.get("address", ""),
                "logo_filename": logo_filename,
                "password": generate_password_hash(password_raw) if password_raw else ""
            }

            print(f"[DEBUG] New submission: {submission}")

            # Append new submission
            data.append(submission)

            # Save to JSON
            save_data(data)
            print(f"[DEBUG] sign_up_responses.json now has {len(data)} submissions")
            print(f"[DEBUG] JSON content preview: {data[-1]}")

            # Default assumptions
            assumptions = load_assumptions()
            if submission["email"] not in assumptions:
                assumptions[submission["email"]] = DEFAULT_ASSUMPTIONS.copy()
                save_assumptions(assumptions)
                print(f"[DEBUG] Default assumptions set for {submission['email']}")

            return redirect(url_for("home"))

        except Exception as e:
            print(f"[ERROR] Exception in /sign_up POST: {e}")
            return "Internal Server Error during sign up", 500

    # GET request
    print("[DEBUG] GET request to /sign_up")
    return render_template("sign_up.html")

@app.route("/sign_up_responses")
def sign_up_responses():
    try:
        submissions = load_data()  # returns a list
        print(f"[DEBUG] Loaded {len(submissions)} submissions for /sign_up_responses")

        # Quick check for content type
        if not isinstance(submissions, list):
            print("[ERROR] submissions is not a list!")
            submissions = []

        return render_template("sign_up_responses.html", submissions=submissions)

    except Exception as e:
        print(f"[ERROR] Exception in /sign_up_responses: {e}")
        return "Internal Server Error while loading submissions", 500

# --- LOGIN ROUTE ---
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        # Check admin/demo users first
        user = users.get(email)
        if user and check_password_hash(user["password"], password):
            session["user"] = email
            session["role"] = user["role"]
            return redirect("/admin_menu") if user["role"] == "admin" else redirect("/disclaimer")

        # Check user-submitted accounts
        data = load_data()
        matched_user = next((u for u in data if u.get("email") == email), None)
        if matched_user and check_password_hash(matched_user.get("password", ""), password):
            session["user"] = email
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

    # Load company assumptions
    company_assumptions = load_assumptions().get(session["user"], {})

    def safe_form_float(field_name, default=0.0):
        val = request.form.get(field_name)
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    if request.method == "POST":
        # Capture inputs safely using the HTML form names
        solar_kw = safe_form_float("system_size", 0.0)             # HTML 'system_size'
        annual_generation_mwh = safe_form_float("generation", 0.0) # HTML 'generation'
        total_capex = safe_form_float("total_capex", solar_kw * 600) # HTML 'total_capex'
        bess_kwh = safe_form_float("battery_size", 0.0)
        specific_yield = safe_form_float("yield", 0.0)
        state = request.form.get("state", "")

        # Map to the keys that model.py expects
        inputs = {
            "solar_kw": solar_kw,
            "annual_generation_mwh": annual_generation_mwh,
            "total_capex": total_capex,
            "bess_kwh": bess_kwh,
            "state": state,
            "specific_yield": specific_yield
        }

        # Run the model
        result = run_model(submission_file=None, inputs=inputs, assumptions=company_assumptions, debug=True)

        # Save submissions
        submissions = load_submissions()
        submission_id = f"{session['user']}_{datetime.now().timestamp()}"
        submissions[submission_id] = {
            "email": session["user"],
            "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "inputs": inputs,
            "result": result,
            "assumptions_used": company_assumptions
        }
        save_submissions(submissions)

        # Save rates for results page
        rates_data = []
        first_row = result["results"][0]
        for term_obj in first_row["terms"]:
            rates_data.append({
                "term": term_obj["term"],
                "ppa_rate": term_obj["ppa_rate_dollars"]
            })
        save_rates({"rates": rates_data})

        return redirect("/results")

    # GET request: show the form
    return render_template("company_form.html", assumptions=company_assumptions)


@app.route("/download_ppa_pdf")
def download_ppa_pdf():
    if "user" not in session or session.get("role") != "company":
        return redirect("/login")

    # Load user data
    all_users = load_data()  # load list of all sign-ups
    data = next((u for u in all_users if u.get("email") == session["user"]), {})

    # Get current datetime
    now = datetime.now()

    # HTML content for PDF
    html = render_template(
        "ppa_pdf.html",
        business_name=data.get("company", "Business Name"),
        address=data.get("address", "Project Address"),
        ppa_terms=[7,10,12,15,20,25],
        ppa_rates=[None]*6,  # empty for now
        benefits=[
            "No upfront capital, operating, or insurance costs",
            "Fixed, discounted electricity rate for the full term",
            "System ownership transfers at end of term (no fees)",
            "Monitoring, maintenance, and replacements included",
            "Guaranteed generation and performance",
            "Optional battery storage with no capital outlay",
            "Improved sustainability outcomes and NABERS rating"
        ],
        now=now  # <--- pass now here
    )

    # Generate PDF
    PDF_FOLDER = os.path.join("static", "PDF")
    os.makedirs(PDF_FOLDER, exist_ok=True)
    pdf_filename = f"ppa_{session['user']}_{int(now.timestamp())}.pdf"
    pdf_path = os.path.join(PDF_FOLDER, pdf_filename)

    with open(pdf_path, "wb") as f:
        pisa_status = pisa.CreatePDF(src=html, dest=f)

    if pisa_status.err:
        return "Error generating PDF", 500

    return send_file(pdf_path, download_name=pdf_filename, as_attachment=True)

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

    submissions = load_submissions()
    assumptions_data = load_assumptions()


    return render_template("admin_dashboard.html", submissions=submissions)

# --- ASSUMPTIONS PAGE ---
@app.route("/assumptions", methods=["GET", "POST"])
def assumptions():
    if "user" not in session or session.get("role") != "admin":
        return redirect("/login")

    assumptions_data = load_assumptions()

    # Merge defaults for all users
    for email, user_data in users.items():
        if user_data["role"] != "company":
            continue
        if email not in assumptions_data:
            assumptions_data[email] = {}
        for key, value in DEFAULT_ASSUMPTIONS.items():
            if key not in assumptions_data[email]:
                assumptions_data[email][key] = value

    if request.method == "POST":
        for company, company_data in assumptions_data.items():
            for key in company_data:
                form_key = f"{company}_{key}"
                value = request.form.get(form_key)
                if value is not None:
                    try:
                        value = float(value)
                    except ValueError:
                        pass
                    assumptions_data[company][key] = value
        save_assumptions(assumptions_data)

    save_assumptions(assumptions_data)
    return render_template("assumptions.html", assumptions=assumptions_data)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # use Render's dynamic PORT
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)  # <- debug=True