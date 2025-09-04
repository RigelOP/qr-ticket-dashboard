import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv
import os
import re

load_dotenv()  # Load environment variables from .env

EMAIL_ADDRESS = os.getenv("MAIL_USER")
EMAIL_PASSWORD = os.getenv("MAIL_PASS")

def send_email(to_email, subject, body, attachment_path=None):
    try:
        # Email configuration
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        from_email = os.getenv("MAIL_USER")
        password = os.getenv("MAIL_PASS")
        
        print(f"DEBUG: Sending email to {to_email}")
        print(f"DEBUG: From email: {from_email}")
        print(f"DEBUG: Subject: {subject}")
        print(f"DEBUG: Attachment: {attachment_path}")
        
        if not from_email or not password:
            print("ERROR: Missing MAIL_USER or MAIL_PASS in environment variables")
            return False
        
        # Create message container
        msg = MIMEMultipart('alternative')
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Convert markdown-style bold to HTML properly
        html_body = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', body)
        html_body = html_body.replace('\n', '<br>')
        
        # Create both plain text and HTML versions
        text_part = MIMEText(body, 'plain')
        html_part = MIMEText(f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                {html_body}
            </body>
        </html>
        """, 'html')
        
        # Attach parts
        msg.attach(text_part)
        msg.attach(html_part)
        
        # Add attachment if provided
        if attachment_path and os.path.exists(attachment_path):
            print(f"DEBUG: Attaching file: {attachment_path}")
            with open(attachment_path, "rb") as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
                
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {os.path.basename(attachment_path)}'
            )
            msg.attach(part)
        else:
            print(f"DEBUG: No attachment or file not found: {attachment_path}")
        
        # Gmail SMTP configuration
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(from_email, password)
        
        # Send email
        text = msg.as_string()
        server.sendmail(from_email, to_email, text)
        server.quit()
        
        print(f"SUCCESS: Email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        print(f"ERROR: Failed to send email: {e}")
        return False
