from flask import Flask, render_template, redirect, url_for, request, jsonify, flash
import gspread
from google.oauth2.service_account import Credentials  # Changed from oauth2client
import os, hashlib, json, re, shutil
from datetime import datetime
from mailer import send_email
from qr_generator import generate_qr
from dotenv import load_dotenv
import importlib.util
import requests
import urllib.parse

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

UNIQUE_IDS_FILE = "unique_ids.json"
SENT_IDS_FILE = "sent_ids.json"  # New file to track sent submissions

# Ensure the file exists
if not os.path.exists(UNIQUE_IDS_FILE):
    with open(UNIQUE_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)

if not os.path.exists(SENT_IDS_FILE):
    with open(SENT_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)

def save_unique_id(unique_id):
    """Add unique_id to the JSON file if not already present."""
    try:
        with open(UNIQUE_IDS_FILE, "r", encoding="utf-8") as f:
            ids = json.load(f)
    except Exception:
        ids = []

    if unique_id not in ids:
        ids.append(unique_id)
        with open(UNIQUE_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump(ids, f, indent=2)
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
    # extract fields from form row (update keys to your sheet headers)
    timestamp = data.get("Timestamp", "")
    email = data.get("Email address", "")
    leader_name = data.get("Team Leader's Name", "").strip()
    team_name = data.get("Team Name", "").strip()
    member1 = data.get("Team Member 1 Name", "").strip()
    member2 = data.get("Team Member 2 Name", "").strip()
    member3 = data.get("Team Member 3 Name", "").strip()
    member4 = data.get("Team Member 4 Name", "").strip()
    member5 = data.get("Team Member 5 Name", "").strip()

    unique_hash = hashlib.sha1((timestamp + email).encode()).hexdigest()[:8]
    unique_id = f"{timestamp.replace('/', '').replace(':', '').replace(' ', '')}_{unique_hash}"

    # prepare JSON payload for QR (includes id, team and members)
    qr_payload = {
        "id": unique_id,
        "team_name": team_name,
        "leader_name": leader_name,
        "members": [member1, member2, member3, member4, member5]
    }

    qr_content = json.dumps(qr_payload, ensure_ascii=False)
    safe_name = re.sub(r'[\/:*?"<>|@ ]', "_", team_name or leader_name or unique_id)
    qr_filename = generate_qr(qr_content, filename=f"{unique_id}_{safe_name}.png")
    # Save unique_id to central JSON file
    save_unique_id(unique_id)

    submission_number = get_next_submission_number()
    json_filename = f"{OUTPUT_DIR}/{submission_number:02d} {safe_name}.json"
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return leader_name, email, qr_filename, json_filename, unique_id

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

    # Mark as sent in the SENT_IDS_FILE
    try:
        with open(SENT_IDS_FILE, 'r', encoding='utf-8') as f:
            sent_ids = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        sent_ids = []

    if unique_id not in sent_ids:
        sent_ids.append(unique_id)
        with open(SENT_IDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(sent_ids, f, indent=2)

def is_sent(unique_id):
    """Check if a submission has been sent"""
    try:
        with open(SENT_IDS_FILE, 'r') as f:
            sent_ids = json.load(f)
        return unique_id in sent_ids
    except (FileNotFoundError, json.JSONDecodeError):
        return False

def _load_module(path, name):
    """Load a Python module from file path"""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def download_and_save_image(image_url, unique_id):
    """Download image from Google Drive and save locally"""
    print(f"=== DEBUG: Starting download for {unique_id} ===")
    print(f"Original URL: {image_url}")
    
    if not image_url:
        print("No image URL provided")
        return None
    
    try:
        # Convert Google Drive share URL to direct download URL
        file_id = None
        if "drive.google.com" in image_url:
            print("Google Drive URL detected")
            if "/file/d/" in image_url:
                file_id = image_url.split("/file/d/")[1].split("/")[0]
                print(f"Extracted file_id from /file/d/: {file_id}")
            elif "id=" in image_url:
                file_id = image_url.split("id=")[1].split("&")[0]
                print(f"Extracted file_id from id=: {file_id}")
            elif "/open?id=" in image_url:
                file_id = image_url.split("/open?id=")[1].split("&")[0]
                print(f"Extracted file_id from /open?id=: {file_id}")
            
            if file_id:
                # Try multiple download methods
                urls_to_try = [
                    f"https://drive.google.com/uc?export=download&id={file_id}",
                    f"https://drive.google.com/uc?id={file_id}&export=download",
                    f"https://docs.google.com/uc?export=download&id={file_id}"
                ]
                
                for direct_url in urls_to_try:
                    print(f"Trying URL: {direct_url}")
                    try:
                        response = requests.get(direct_url, timeout=30, allow_redirects=True)
                        print(f"Response status: {response.status_code}")
                        print(f"Content-Type: {response.headers.get('content-type', 'Unknown')}")
                        print(f"Content-Length: {len(response.content)}")
                        
                        # Check if we got actual image content
                        content_type = response.headers.get('content-type', '').lower()
                        if any(img_type in content_type for img_type in ['image/', 'jpeg', 'png', 'gif']):
                            print("Valid image content detected")
                            break
                        elif response.content.startswith(b'\x89PNG') or response.content.startswith(b'\xff\xd8\xff'):
                            print("Image content detected by file signature")
                            break
                        else:
                            print(f"Content preview: {response.content[:100]}")
                            continue
                    except Exception as e:
                        print(f"Failed to download from {direct_url}: {e}")
                        continue
                else:
                    print("All download URLs failed")
                    return None
                    
            else:
                print("Could not extract file_id")
                return None
        else:
            direct_url = image_url
            response = requests.get(direct_url, timeout=30)
        
        response.raise_for_status()
        
        # Save locally
        images_dir = os.path.join(os.path.dirname(__file__), "static", "uploaded_images")
        os.makedirs(images_dir, exist_ok=True)
        print(f"Images directory: {images_dir}")
        
        # Determine file extension
        content_type = response.headers.get('content-type', '')
        if 'jpeg' in content_type or 'jpg' in content_type or response.content.startswith(b'\xff\xd8\xff'):
            ext = '.jpg'
        elif 'png' in content_type or response.content.startswith(b'\x89PNG'):
            ext = '.png'
        else:
            ext = '.jpg'  # default
        
        local_filename = f"{unique_id}_uploaded{ext}"
        local_path = os.path.join(images_dir, local_filename)
        
        with open(local_path, 'wb') as f:
            f.write(response.content)
        
        print(f"Successfully saved to: {local_path}")
        print(f"File size: {os.path.getsize(local_path)} bytes")
        
        return f"uploaded_images/{local_filename}"  # Remove 'static/' prefix
        
    except Exception as e:
        print(f"Failed to download image: {e}")
        import traceback
        traceback.print_exc()
        return None

# ------------------ Routes ------------------
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/delete_all_data", methods=["POST"])
def delete_all_data():
    try:
        # Delete individual files instead of removing the entire directory
        if os.path.exists(OUTPUT_DIR):
            for filename in os.listdir(OUTPUT_DIR):
                file_path = os.path.join(OUTPUT_DIR, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except PermissionError:
                    print(f"Could not delete {file_path}: Permission denied")
                    continue

        if os.path.exists(QR_CODE_DIR):
            for filename in os.listdir(QR_CODE_DIR):
                file_path = os.path.join(QR_CODE_DIR, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except PermissionError:
                    print(f"Could not delete {file_path}: Permission denied")
                    continue

        # Clear the tracking files
        try:
            with open(UNIQUE_IDS_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)
        except Exception as e:
            print(f"Could not clear unique_ids.json: {e}")

        try:
            with open(SENT_IDS_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)
        except Exception as e:
            print(f"Could not clear sent_ids.json: {e}")

        # Clear uploaded images
        uploaded_images_dir = os.path.join("static", "uploaded_images")
        if os.path.exists(uploaded_images_dir):
            for filename in os.listdir(uploaded_images_dir):
                file_path = os.path.join(uploaded_images_dir, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except PermissionError:
                    print(f"Could not delete {file_path}: Permission denied")
                    continue

        # Clear ticket output
        ticket_output_dir = "ticket_output"
        if os.path.exists(ticket_output_dir):
            for filename in os.listdir(ticket_output_dir):
                file_path = os.path.join(ticket_output_dir, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except PermissionError:
                    print(f"Could not delete {file_path}: Permission denied")
                    continue

        flash("All generated responses and QR codes have been deleted.", "success")
    except Exception as e:
        flash(f"An error occurred while deleting files: {e}", "error")
        app.logger.error(f"Failed to delete all data: {e}")
    return redirect(url_for("home"))

@app.route("/dashboard")
def dashboard():
    values = sheet.get_all_values()
    if not values:
        return render_template("dashboard.html", users=[])
    headers, rows = values[0], values[1:]
    processed_ids = get_existing_ids()

    users = []
    for row in rows:
        data = dict(zip(headers, row))
        # use Name or Team Leader's Name or Team Name
        display_name = (data.get("Name") or data.get("Team Leader's Name") or data.get("Team Name") or "").strip()
        email = data.get("Email address", "").strip()
        timestamp = data.get("Timestamp", "").strip()
        if not display_name or not email:
            continue
        unique_hash = hashlib.sha1((timestamp + email).encode()).hexdigest()[:8]
        unique_id = f"{timestamp.replace('/', '').replace(':', '').replace(' ', '')}_{unique_hash}"
        users.append({
            "name": display_name,
            "email": email,
            "timestamp": timestamp,
            "processed": unique_id in processed_ids,
            "id": unique_id
        })

    return render_template("dashboard.html", users=users)

@app.route("/send/<unique_id>", methods=["GET", "POST"])
def send(unique_id):
    print(f"=== SEND ROUTE CALLED FOR: {unique_id} ===")
    print(f"Request method: {request.method}")
    print(f"Request referrer: {request.referrer}")
    print(f"Request form data: {request.form}")
    print(f"Request args: {request.args}")
    
    values = sheet.get_all_values()
    if not values:
        print("No sheet values found")
        flash("No data found in sheet", "error")
        return redirect(url_for('submissions'))
    
    # Check if the request came from the view page
    came_from_view = request.referrer and '/view/' in request.referrer
    print(f"Came from view: {came_from_view}")
    
    headers, rows = values[0], values[1:]
    print(f"Processing {len(rows)} rows from sheet")

    found_submission = False
    for row in rows:
        data = dict(zip(headers, row))
        email = data.get("Email address", "").strip()
        name = (data.get("Name") or data.get("Team Leader's Name") or data.get("Team Name") or "").strip()
        timestamp = data.get("Timestamp", "").strip()
        
        if not email or not timestamp:
            continue
            
        uid_hash = hashlib.sha1((timestamp + email).encode()).hexdigest()[:8]
        generated_id = f"{timestamp.replace('/', '').replace(':', '').replace(' ', '')}_{uid_hash}"
        print(f"Generated ID: {generated_id} for email: {email}")

        if generated_id == unique_id:
            found_submission = True
            print(f"✅ Found matching submission for {unique_id}")
            print(f"Email: {email}")
            print(f"Name: {name}")
            
            # Process submission to generate QR and JSON
            try:
                name, email, qr_filename, json_filename, _ = process_submission(data)
                print(f"Processed submission - QR file: {qr_filename}")
                
                if not qr_filename or not os.path.exists(qr_filename):
                    print(f"❌ QR file not found: {qr_filename}")
                    flash("QR code file not found. Please regenerate.", "error")
                    break
                
            except Exception as e:
                print(f"❌ Error processing submission: {e}")
                flash(f"Error processing submission: {e}", "error")
                break
            
            # Generate ticket
            ticket_file = None
            if qr_filename:
                try:
                    print("🎫 Starting ticket generation...")
                    base_dir = os.path.dirname(__file__)
                    stamp_mod = _load_module(os.path.join(base_dir, "scripts", "stamp_ticket.py"), "stamp_ticket")
                    
                    template = stamp_mod.pick_template()
                    team_name = data.get("Team Name") or data.get("Team Leader's Name") or ""
                    ticket_output_dir = os.path.join(base_dir, "ticket_output")
                    os.makedirs(ticket_output_dir, exist_ok=True)
                    ticket_file = os.path.join(ticket_output_dir, f"ticket_{unique_id}.png")
                    
                    # Fix QR path
                    if os.path.exists(qr_filename):
                        qr_path = qr_filename
                    else:
                        qr_path = os.path.join(base_dir, "qrcodes", os.path.basename(qr_filename))
                    
                    print(f"Using QR path: {qr_path}")
                    
                    if not os.path.exists(qr_path):
                        print(f"❌ QR file not found at: {qr_path}")
                        ticket_file = None
                    else:
                        stamp_mod.compose_ticket(
                            template, qr_path, team_name, ticket_file,
                            qr_anchor_x_pct=getattr(stamp_mod, "QR_ANCHOR_X_PCT", None),
                            qr_anchor_y_pct=getattr(stamp_mod, "QR_ANCHOR_Y_PCT", None),
                            offset_x_px=getattr(stamp_mod, "OFFSET_X_PX", 0),
                            offset_y_px=getattr(stamp_mod, "OFFSET_Y_PX", 0)
                        )
                        print(f"✅ Generated ticket: {ticket_file}")
                        
                except Exception as e:
                    print(f"❌ Ticket generation failed: {e}")
                    import traceback
                    traceback.print_exc()
                    ticket_file = None
            
            # Send email
            if email and qr_filename:
                print(f"📧 Attempting to send email to: {email}")
                try:
                    if ticket_file and os.path.exists(ticket_file):
                        print(f"Sending ticket file: {ticket_file}")
                        send_email(
                            email,
                            "Your Event Ticket 🎟️",
                            f"Hello {name},\n\nHere is your event ticket with QR code.\n\nThanks!",
                            ticket_file
                        )
                        flash(f"Ticket sent successfully to {email}!", "success")
                        print(f"✅ Ticket sent successfully to {email}")
                    else:
                        print(f"Sending QR file: {qr_filename}")
                        send_email(
                            email,
                            "Your QR Code Ticket 🎟️",
                            f"Hello {name},\n\nHere is your unique QR code ticket.\n\nThanks!",
                            qr_filename
                        )
                        flash(f"QR code sent successfully to {email}!", "success")
                        print(f"✅ QR code sent successfully to {email}")
                        
                    # Mark as sent
                    mark_as_sent(unique_id)
                    print(f"Marked {unique_id} as sent")
                    
                except Exception as e:
                    print(f"❌ Email sending failed: {e}")
                    import traceback
                    traceback.print_exc()
                    flash(f"Failed to send email to {email}: {e}", "error")
            else:
                print(f"❌ Missing email ({email}) or QR filename ({qr_filename})")
                flash("Missing email or QR code file", "error")
            
            break
    
    if not found_submission:
        print(f"❌ No matching submission found for {unique_id}")
        flash("Submission not found", "error")

    # Redirect back to the appropriate page
    print(f"Redirecting - came_from_view: {came_from_view}")
    if came_from_view:
        return redirect(url_for('view_submission', unique_id=unique_id))
    else:
        return redirect(url_for('submissions'))

@app.route("/submissions")
def submissions():
    values = sheet.get_all_values()
    if not values:
        return render_template("submissions.html", users=[])
    
    headers, rows = values[0], values[1:]
    users = []
    
    for row in rows:
        data = dict(zip(headers, row))
        email = data.get("Email address", "").strip()
        timestamp = data.get("Timestamp", "").strip()
        if not email or not timestamp:
            continue
        
        uid_hash = hashlib.sha1((timestamp + email).encode()).hexdigest()[:8]
        unique_id = f"{timestamp.replace('/', '').replace(':', '').replace(' ', '')}_{uid_hash}"
        
        # Show actual team name, not leader name
        team_name = (data.get("Team Name") or data.get("Name") or "").strip()
        leader_name = data.get("Team Leader's Name", "").strip()
        
        users.append({
            "unique_id": unique_id,
            "name": team_name,  # Template expects 'name' field
            "email": email,
            "timestamp": timestamp,
            "sent": is_sent(unique_id)
        })
    
    return render_template("submissions.html", users=users)

@app.route("/view/<unique_id>")
def view_submission(unique_id):
    values = sheet.get_all_values()
    if not values:
        return redirect(url_for('submissions'))
    
    headers, rows = values[0], values[1:]
    
    for row in rows:
        data = dict(zip(headers, row))
        email = data.get("Email address", "").strip()
        timestamp = data.get("Timestamp", "").strip()
        if not email or not timestamp:
            continue
        
        uid_hash = hashlib.sha1((timestamp + email).encode()).hexdigest()[:8]
        generated_id = f"{timestamp.replace('/', '').replace(':', '').replace(' ', '')}_{uid_hash}"
        
        if generated_id == unique_id:
            # Check all possible screenshot field names
            image_url = (data.get("Screenshot of payment (Rs.50 / team)") or 
                        data.get("Upload Screenshot") or 
                        data.get("Screenshot") or "").strip()
            
            print(f"Found image URL: {image_url}")
            
            # Download and save any uploaded images
            local_image_path = None
            if image_url:
                print(f"Attempting to download image for {unique_id}")
                local_image_path = download_and_save_image(image_url, unique_id)
                print(f"Download result: {local_image_path}")
            
            data['local_image_path'] = local_image_path
            
            # Check if file actually exists locally
            if local_image_path:
                full_path = os.path.join(os.path.dirname(__file__), "static", local_image_path)
                if os.path.exists(full_path):
                    print(f"Image file exists at: {full_path}")
                else:
                    print(f"Image file NOT found at: {full_path}")
                    data['local_image_path'] = None
            
            return render_template("view_submission.html", data=data, submission=data, unique_id=unique_id)
    
    return redirect(url_for('submissions'))

@app.route("/scan")
def scan():
    return render_template("scan.html")

@app.route("/verify_qr", methods=["POST"])
def verify_qr():
    payload = request.get_json() or {}
    qr_content = payload.get("qr_content") or payload.get("qr_data") or ""
    print("Scanned QR raw content:", qr_content)  # prints in terminal

    try:
        qr_json = json.loads(qr_content)
    except Exception:
        return jsonify({"valid": False, "message": "❌ Invalid QR code format", "qr_content": qr_content})

    unique_id = qr_json.get("id")
    team_name = qr_json.get("team_name")
    leader_name = qr_json.get("leader_name")
    members = qr_json.get("members", [])

    if not unique_id:
        return jsonify({"valid": False, "message": "❌ QR missing id", "qr_content": qr_content})

    # check existence in responses (same logic you use already)
    found = False
    for fname in os.listdir(OUTPUT_DIR):
        if fname.endswith('.json'):
            with open(os.path.join(OUTPUT_DIR, fname), encoding="utf-8") as f:
                file_data = json.load(f)
            # build file unique id same way you did when creating it
            ts = file_data.get('Timestamp', '')
            em = file_data.get('Email address', '')
            file_hash = hashlib.sha1((ts + em).encode()).hexdigest()[:8]
            file_unique_id = f"{ts.replace('/', '').replace(':', '').replace(' ', '')}_{file_hash}"
            if file_unique_id == unique_id:
                found = True
                # optional: compare team/leader/members if you want stricter match
                break

    if found:
        return jsonify({
            "valid": True,
            "message": "✅ QR Verified",
            "id": unique_id,
            "team_name": team_name,
            "leader_name": leader_name,
            "members": members,
            "qr_content": qr_content
        })
    else:
        return jsonify({"valid": False, "message": "❌ QR not found", "qr_content": qr_content})


# ------------------ Run App ------------------
if __name__ == "__main__":
    app.run(debug=True)
