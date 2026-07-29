"""One-time local script to mint a Gmail send-only OAuth refresh token.

Run this once on your own machine after creating a Desktop-app OAuth client in
Google Cloud Console (see dues_automation/README.md). It opens a browser for
you to log in and approve the gmail.send scope, then prints the values to add
to dues_automation/.env. This script is never run as part of the automated
daily pipeline.

Usage:
    # if you still have the downloaded client_secret_*.json:
    python -m dues_automation.get_gmail_token path/to/client_secret.json

    # or, if GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET are already in .env:
    python -m dues_automation.get_gmail_token
"""
import argparse

from google_auth_oauthlib.flow import InstalledAppFlow

from dues_automation import config

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "client_secret_file", nargs="?", default=None,
        help="Path to the client_secret_*.json downloaded from Google Cloud Console. "
        "Omit to use GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET from .env instead.",
    )
    args = parser.parse_args()

    if args.client_secret_file:
        flow = InstalledAppFlow.from_client_secrets_file(args.client_secret_file, SCOPES)
    else:
        if not config.GMAIL_CLIENT_ID or not config.GMAIL_CLIENT_SECRET:
            raise SystemExit(
                "No client_secret file given, and GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET "
                "are not set in dues_automation/.env either."
            )
        client_config = {
            "installed": {
                "client_id": config.GMAIL_CLIENT_ID,
                "client_secret": config.GMAIL_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    creds = flow.run_local_server(port=0)

    print("\nAdd these to dues_automation/.env (and as GitHub Actions secrets when ready):\n")
    print(f"GMAIL_CLIENT_ID={creds.client_id}")
    print(f"GMAIL_CLIENT_SECRET={creds.client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    print("GMAIL_SENDER_EMAIL=<the Gmail address you just logged in with>")


if __name__ == "__main__":
    main()
