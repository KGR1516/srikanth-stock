"""Emails the daily breakout results (or a 'no breakouts' notice) as an Excel attachment.

Reads credentials from environment variables (set as GitHub Actions secrets):
    GMAIL_ADDRESS       - the Gmail address to send from
    GMAIL_APP_PASSWORD  - a Gmail App Password (not your normal password)
    RECIPIENT_EMAIL     - who receives the email (defaults to GMAIL_ADDRESS)

Run:
    python send_email.py --file breakouts.xlsx
"""

import argparse
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


def build_message(sender: str, recipient: str, attachment: Path) -> EmailMessage:
    msg = EmailMessage()
    status = "breakouts found" if attachment.exists() else "no breakouts"
    msg["Subject"] = f"NSE Volume Breakout Screener \u2014 {status}"
    msg["From"] = sender
    msg["To"] = recipient

    if attachment.exists():
        msg.set_content(
            "Attached is today's volume breakout screen.\n\n"
            "Educational tool only. Not investment advice."
        )
        msg.add_attachment(
            attachment.read_bytes(),
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=attachment.name,
        )
    else:
        msg.set_content(
            "No volume breakouts matched today's settings \u2014 nothing to attach.\n\n"
            "Educational tool only. Not investment advice."
        )
    return msg


def main():
    parser = argparse.ArgumentParser(description="Email the screener results")
    parser.add_argument("--file", default="breakouts.xlsx",
                         help="path to the Excel file produced by screener.py")
    args = parser.parse_args()

    sender = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ.get("RECIPIENT_EMAIL", sender)

    msg = build_message(sender, recipient, Path(args.file))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)

    print(f"Email sent to {recipient}")


if __name__ == "__main__":
    main()
