# QR Ticket System

A Flask-based QR ticket system that reads Google Form submissions, generates QR codes, sends them via email, and allows QR code validation via webcam.

## Features

- Reads Google Form responses from Google Sheets
- Generates QR codes for each submission
- Sends QR codes to users via email
- Dashboard to view and manage submissions
- Scan and validate QR codes using your webcam
- Uses `.env` for sensitive configuration

## Setup

### 1. Clone the repository

```sh
git clone <your-repo-url>
cd QR_Ticket_System
```

### 2. Install dependencies

```sh
pip install -r requirements.txt
```

### 3. Set up your `.env` file

Create a `.env` file in the project root:

```
MAIL_USER=your_email@gmail.com
MAIL_PASS=app_password (https://support.google.com/accounts/answer/185833)
GOOGLE_SHEET_CREDENTIALS=credentials.json
SHEET_NAME=Form responses 1
SHEET_URL=https://docs.google.com/spreadsheets/d/your-sheet-id/edit?usp=sharing
```

- Download your Google service account credentials as `credentials.json` and place it in the project root.

### 4. Run the app

```sh
python dashboard.py
```

Visit [http://localhost:5000](http://localhost:5000) in your browser.

## Usage

- **Dashboard:** View all submissions and send QR codes.
- **Scan QR Code:** Scan and validate QR codes using your webcam.
- **View Submission:** See details of each submission.

## Deployment

You can deploy this app to [PythonAnywhere](https://www.pythonanywhere.com/), [Render](https://render.com/), [Railway](https://railway.app/), or [Heroku](https://heroku.com/).  
Make sure to set your environment variables and upload your `credentials.json` securely.

## License

MIT License