from flask import Flask, render_template, redirect, url_for, request, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os, hashlib, json, re
from datetime import datetime
from mailer import send_email
from qr_generator import generate_qr
from dotenv import load_dotenv
import os

# ================= CONFIG =================
load_dotenv()  # Load environment variables from .env

MAIL_USER = os.getenv("MAIL_USER")
MAIL_PASS = os.getenv("MAIL_PASS")
CREDENTIALS_FILE = os.getenv("GOOGLE_SHEET_CREDENTIALS", "credentials.json")
SHEET_NAME = os.getenv("SHEET_NAME")
SHEET_URL = os.getenv("SHEET_URL")
OUTPUT_DIR = "responses"
# ==========================================

app = Flask(__name__)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------- Google Sheets Setup ----------------
scope = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly"
]
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
client = gspread.authorize(creds)
sheet = client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

# ---------------- Utility Functions ----------------
def get_existing_ids():
    """Return a set of unique IDs already processed (from JSON filenames in OUTPUT_DIR)."""
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
    """Generate QR, save JSON, return info tuple"""
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
# ----------------------------------------------------

# ------------------ Routes ------------------
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/dashboard")
def dashboard():
    """Show list of Google Form submissions"""
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
    """Send QR code email for a specific submission"""
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
        # Check if sent
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
            # Check if sent
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

# ------------------ QR Scan Routes ------------------
@app.route("/scan")
def scan():
    """Page to scan QR codes"""
    return render_template("scan.html")

@app.route("/verify_qr", methods=["POST"])
def verify_qr():
    data = request.get_json()
    # Accept both 'qr_data' and 'qr_content'
    qr_content = data.get("qr_content") or data.get("qr_data") or ""
    print(f"Scanned QR content: {qr_content}")  # Print in terminal

    import json
    try:
        qr_json = json.loads(qr_content)
    except Exception:
        return jsonify({"valid": False, "message": "❌ Invalid QR code format", "qr_content": qr_content})

    unique_id = qr_json.get("id")
    name = qr_json.get("name")
    if not unique_id or not name:
        return jsonify({"valid": False, "message": "❌ QR code missing required fields.", "qr_content": qr_content})

    # Check if unique_id exists in submissions (responses folder)
    found = False
    for fname in os.listdir(OUTPUT_DIR):
        if fname.endswith('.json'):
            with open(os.path.join(OUTPUT_DIR, fname), encoding="utf-8") as f:
                data = json.load(f)
            timestamp = data.get('Timestamp', '')
            email = data.get('Email address', '')
            unique_hash = hashlib.sha1((timestamp + email).encode()).hexdigest()[:8]
            file_unique_id = f"{timestamp.replace('/', '').replace(':', '').replace(' ', '')}_{unique_hash}"
            if file_unique_id == unique_id and data.get('Name', '').strip() == name:
                found = True
                break
    if found:
        return jsonify({"valid": True, "message": f"✅ QR Verified! Name: {name}", "name": name, "qr_content": qr_content})
    else:
        return jsonify({"valid": False, "message": "❌ QR code not found.", "qr_content": qr_content})

def mark_as_sent(unique_id):
    # Find the JSON file for this unique_id and update it
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

# ------------------ Run App ------------------
if __name__ == "__main__":
    app.run(debug=True)
