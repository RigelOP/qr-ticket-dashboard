from flask import Flask, render_template, redirect, url_for, request, jsonify, flash
import gspread
from google.oauth2.service_account import Credentials  # Changed from oauth2client
import os, hashlib, json, re, shutil
from datetime import datetime
from mailer import send_email
from qr_generator import generate_qr
from dotenv import load_dotenv

# ================= CONFIG =================
load_dotenv()  # Load environment variables from .env

MAIL_USER = os.getenv("MAIL_USER")
MAIL_PASS = os.getenv("MAIL_PASS")
SHEET_NAME = os.getenv("SHEET_NAME")
SHEET_URL = os.getenv("SHEET_URL")
OUTPUT_DIR = "responses"
QR_CODE_DIR = "qrcodes"

# Google Credentials from .env
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")  # Single-line JSON in .env
if not GOOGLE_CREDENTIALS_JSON:
    raise ValueError("Missing GOOGLE_CREDENTIALS_JSON in .env!")

# ==========================================

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Create necessary directories
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(QR_CODE_DIR, exist_ok=True)

# ---------------- Google Sheets Setup ----------------
scope = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly"
]

creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)

client = gspread.authorize(credentials)
sheet = client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

# ---------------- Utility Functions ----------------
def get_existing_ids():
    ids = set()
    for fname in os.listdir(OUTPUT_DIR):
        if fname.endswith('.json'):
            try:
                with open(os.path.join(OUTPUT_DIR, fname), encoding="utf-8") as f:
                    data = json.load(f)
                    timestamp = data.get('Timestamp', '')
                    email = data.get('Email address', '')
                    unique_hash = hashlib.sha1((timestamp + email).encode()).hexdigest()[:8]
                    unique_id = f"{timestamp.replace('/', '').replace(':', '').replace(' ', '')}_{unique_hash}"
                    ids.add(unique_id)
            except Exception:
                continue
    return ids

def get_next_submission_number():
    files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.json')]
    numbers = []
    for f in files:
        match = re.match(r"(\d+)", f)
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1

def process_submission(data):
    timestamp = data.get('Timestamp', str(datetime.now()))
    email = data.get('Email address', '')
    name = data.get('Name', 'unknown')

    unique_hash = hashlib.sha1((timestamp + email).encode()).hexdigest()[:8]
    unique_id = f"{timestamp.replace('/', '').replace(':', '').replace(' ', '')}_{unique_hash}"

    qr_content = json.dumps({"id": unique_id, "name": name})
    safe_name = re.sub(r'[\/:*?"<>|@ ]', "_", name)
    qr_filename = generate_qr(qr_content, filename=f"{unique_id}_{safe_name}.png")

    submission_number = get_next_submission_number()
    json_filename = f"{OUTPUT_DIR}/{submission_number:02d} {safe_name}.json"
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return name, email, qr_filename, json_filename, unique_id

def mark_as_sent(unique_id):
    for fname in os.listdir(OUTPUT_DIR):
        if fname.endswith('.json'):
            with open(os.path.join(OUTPUT_DIR, fname), encoding="utf-8") as f:
                data = json.load(f)
            timestamp = data.get('Timestamp', '')
            email = data.get('Email address', '')
            unique_hash = hashlib.sha1((timestamp + email).encode()).hexdigest()[:8]
            file_unique_id = f"{timestamp.replace('/', '').replace(':', '').replace(' ', '')}_{unique_hash}"
            if file_unique_id == unique_id:
                data['sent'] = True
                with open(os.path.join(OUTPUT_DIR, fname), "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                break

# ------------------ Routes ------------------
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/delete_all_data", methods=["POST"])
def delete_all_data():
    try:
        if os.path.exists(OUTPUT_DIR):
            shutil.rmtree(OUTPUT_DIR)
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        if os.path.exists(QR_CODE_DIR):
            shutil.rmtree(QR_CODE_DIR)
        os.makedirs(QR_CODE_DIR, exist_ok=True)

        flash("All generated responses and QR codes have been deleted.", "success")
    except Exception as e:
        flash(f"An error occurred while deleting files: {e}", "error")
        app.logger.error(f"Failed to delete all data: {e}")
    return redirect(url_for("home"))

@app.route("/dashboard")
def dashboard():
    values = sheet.get_all_values()
    headers, rows = values[0], values[1:]
    processed_ids = get_existing_ids()

    users = []
    for row in rows:
        data = dict(zip(headers, row))
        name, email, timestamp = data.get("Name", ""), data.get("Email address", ""), data.get("Timestamp", "")
        if not name or not email:
            continue
        unique_hash = hashlib.sha1((timestamp + email).encode()).hexdigest()[:8]
        unique_id = f"{timestamp.replace('/', '').replace(':', '').replace(' ', '')}_{unique_hash}"
        users.append({
            "name": name,
            "email": email,
            "timestamp": timestamp,
            "processed": unique_id in processed_ids,
            "id": unique_id
        })

    return render_template("dashboard.html", users=users)

@app.route("/send/<unique_id>")
def send(unique_id):
    values = sheet.get_all_values()
    headers, rows = values[0], values[1:]

    for row in rows:
        data = dict(zip(headers, row))
        email, name, timestamp = data.get("Email address", ""), data.get("Name", ""), data.get("Timestamp", "")
        uid_hash = hashlib.sha1((timestamp + email).encode()).hexdigest()[:8]
        generated_id = f"{timestamp.replace('/', '').replace(':', '').replace(' ', '')}_{uid_hash}"

        if generated_id == unique_id:
            name, email, qr_filename, json_filename, _ = process_submission(data)
            if email:
                send_email(
                    email,
                    "Your QR Code Ticket 🎟️",
                    f"Hello {name},\n\nHere is your unique QR code ticket.\n\nThanks!",
                    qr_filename
                )
            mark_as_sent(unique_id)
            break

    return redirect(url_for('submissions'))

@app.route("/submissions")
def submissions():
    values = sheet.get_all_values()
    headers, rows = values[0], values[1:]
    users = []
    for row in rows:
        data = dict(zip(headers, row))
        name = data.get('Name', '').strip()
        email = data.get('Email address', '').strip()
        timestamp = data.get('Timestamp', '')
        if not name or not email:
            continue
        unique_hash = hashlib.sha1((timestamp + email).encode()).hexdigest()[:8]
        unique_id = f"{timestamp.replace('/', '').replace(':', '').replace(' ', '')}_{unique_hash}"
        sent = False
        for fname in os.listdir(OUTPUT_DIR):
            if fname.endswith('.json'):
                with open(os.path.join(OUTPUT_DIR, fname), encoding="utf-8") as f:
                    file_data = json.load(f)
                file_timestamp = file_data.get('Timestamp', '')
                file_email = file_data.get('Email address', '')
                file_hash = hashlib.sha1((file_timestamp + file_email).encode()).hexdigest()[:8]
                file_unique_id = f"{file_timestamp.replace('/', '').replace(':', '').replace(' ', '')}_{file_hash}"
                if file_unique_id == unique_id and file_data.get('sent'):
                    sent = True
                    break
        users.append({
            "name": name,
            "email": email,
            "unique_id": unique_id,
            "sent": sent
        })
    return render_template("submissions.html", users=users)

@app.route("/view/<unique_id>")
def view_submission(unique_id):
    values = sheet.get_all_values()
    headers, rows = values[0], values[1:]
    for row in rows:
        data = dict(zip(headers, row))
        name = data.get('Name', '').strip()
        email = data.get('Email address', '').strip()
        timestamp = data.get('Timestamp', '')
        if not name or not email:
            continue
        unique_hash = hashlib.sha1((timestamp + email).encode()).hexdigest()[:8]
        row_unique_id = f"{timestamp.replace('/', '').replace(':', '').replace(' ', '')}_{unique_hash}"
        if row_unique_id == unique_id:
            sent = False
            for fname in os.listdir(OUTPUT_DIR):
                if fname.endswith('.json'):
                    with open(os.path.join(OUTPUT_DIR, fname), encoding="utf-8") as f:
                        file_data = json.load(f)
                    file_timestamp = file_data.get('Timestamp', '')
                    file_email = file_data.get('Email address', '')
                    file_hash = hashlib.sha1((file_timestamp + file_email).encode()).hexdigest()[:8]
                    file_unique_id = f"{file_timestamp.replace('/', '').replace(':', '').replace(' ', '')}_{file_hash}"
                    if file_unique_id == unique_id and file_data.get('sent'):
                        sent = True
                        break
            return render_template("view_submission.html", data=data, unique_id=unique_id, sent=sent)
    return "Submission not found", 404

@app.route("/scan")
def scan():
    return render_template("scan.html")

@app.route("/verify_qr", methods=["POST"])
def verify_qr():
    data = request.get_json()
    qr_content = data.get("qr_content") or data.get("qr_data") or ""
    print(f"Scanned QR content: {qr_content}")

    # Parse QR content as JSON
    try:
        qr_json = json.loads(qr_content)
        qr_id = qr_json.get("id")
        if not qr_id:
            raise ValueError("Missing 'id' in QR content")
    except Exception as e:
        return jsonify({
            "valid": False,
            "message": f"❌ Invalid QR code: {e}",
            "qr_content": qr_content
        })

    # Check if any PNG in QR_CODE_DIR starts with the unique_id
    found = False
    for fname in os.listdir(QR_CODE_DIR):
        if fname.startswith(qr_id) and fname.endswith(".png"):
            found = True
            break

    if found:
        return jsonify({
            "valid": True,
            "message": f"✅ QR Verified! ID: {qr_id}",
            "qr_content": qr_content
        })
    else:
        return jsonify({
            "valid": False,
            "message": "❌ QR code not found.",
            "qr_content": qr_content
        })


# ------------------ Run App ------------------
if __name__ == "__main__":
    app.run(debug=True)
