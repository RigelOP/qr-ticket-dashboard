# QR Ticket Dashboard 🎟️

A **Flask-based web application** that automates the generation, emailing, and validation of QR code tickets from Google Form submissions. This system includes a comprehensive dashboard for managing event invites and a built-in QR code scanner for seamless event check-in.

---

## Features ✨

* **Google Form Integration:** Automatically reads responses from Google Sheets.
* **QR Code Generation:** Creates unique QR codes for each submission.
* **Email Automation:** Sends QR codes to users via Gmail securely.
* **Interactive Dashboard:** View, manage, and track submissions.
* **QR Code Scanner:** Validate tickets using a webcam directly from the dashboard.
* **Secure Configuration:** Uses `.env` to store sensitive information.

---

## Quick Start 🚀

### 1. Clone the repository

```bash
git clone https://github.com/RigelOP/qr-ticket-dashboard.git
cd qr-ticket-dashboard
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```
MAIL_USER=your_email@gmail.com
MAIL_PASS=your_app_password
GOOGLE_SHEET_CREDENTIALS=credentials.json
SHEET_NAME=Form responses 1
SHEET_URL=https://docs.google.com/spreadsheets/d/your-sheet-id/edit?usp=sharing
```

> **Note:**
>
> * Generate an **App Password** for Gmail [here](https://support.google.com/accounts/answer/185833) for secure authentication.
> * Download your **Google Service Account credentials** as `credentials.json` and place it in the project root.

### 4. Run the application

```bash
python dashboard.py
```

Open your browser and visit: [http://localhost:5000](http://localhost:5000)

---

## Usage 📝

* **Dashboard:**

  * View all Google Form submissions
  * Check if a QR code has been sent
  * Send QR codes via email

* **Scan QR Code:**

  * Use your webcam to scan a QR code
  * Instantly verify if the ticket is valid

* **View Submission Details:**

  * Access detailed info for each submission

---

## Deployment 🌐

This app can be deployed to cloud platforms such as:

* [PythonAnywhere](https://www.pythonanywhere.com/)
* [Render](https://render.com/)
* [Railway](https://railway.app/)
* [Heroku](https://www.heroku.com/)

**Important:**

* Upload `credentials.json` securely
* Set all `.env` variables in the deployment environment

---


## Security Tips 🔒

* Never commit `.env` or `credentials.json` to public repositories.
* Use Gmail App Passwords instead of your main password.
* Make sure the `qrcodes/` and `responses/` directories are secure if deploying publicly.

---

## License 📝

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

---

If you need assistance with deployment or have any questions, feel free to open an issue or contact me directly.
