#!/usr/bin/env python3
"""
SMS to Mastodon Relay

Polls Gmail for SMS messages forwarded from Google Voice and posts them to Mastodon.

Setup:
1. Enable Gmail API in Google Cloud Console
2. Download OAuth 2.0 credentials as 'credentials.json'
3. Configure Google Voice to forward SMS to Gmail
4. Create Mastodon app and get access token
5. Copy .env.example to .env and configure
6. Run: uv run sms-mastodon-relay.py

Requirements:
- Gmail API credentials (credentials.json)
- Mastodon instance and access token
- Google Voice configured to forward SMS to Gmail

Configuration via .env:
- SOURCE_PHONE_NUMBER: Phone number to filter (e.g., 7152009057)
- MASTODON_INSTANCE_URL: Your Mastodon instance (e.g., https://mastodon.social)
- MASTODON_ACCESS_TOKEN: Your Mastodon app access token
- POLL_INTERVAL_SECONDS: Polling interval (default: 60)
- STATE_FILE: File to track processed messages (default: .processed_messages.txt)

Example usage:
    uv run sms-mastodon-relay.py
"""

import os
import sys
import time
import re
import base64
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Set

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from mastodon import Mastodon

# Gmail API scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Constants
GOOGLE_VOICE_EMAIL_PATTERN = r'@txt\.voice\.google\.com$'
GENESIS_MESSAGE = "Thxs for texting. More mobile updates coming soon."


class SMSMastodonRelay:
    """Relay SMS messages from Gmail to Mastodon."""

    def __init__(self):
        """Initialize the relay with configuration from environment."""
        load_dotenv()

        # Configuration
        self.source_phone = os.getenv('SOURCE_PHONE_NUMBER')
        self.mastodon_url = os.getenv('MASTODON_INSTANCE_URL')
        self.mastodon_token = os.getenv('MASTODON_ACCESS_TOKEN')
        self.poll_interval = int(os.getenv('POLL_INTERVAL_SECONDS', '60'))
        self.state_file = Path(os.getenv('STATE_FILE', '.processed_messages.txt'))

        # Validate configuration
        if not self.source_phone:
            print("ERROR: SOURCE_PHONE_NUMBER not set in .env")
            sys.exit(1)
        if not self.mastodon_url:
            print("ERROR: MASTODON_INSTANCE_URL not set in .env")
            sys.exit(1)
        if not self.mastodon_token:
            print("ERROR: MASTODON_ACCESS_TOKEN not set in .env")
            sys.exit(1)

        # Initialize services
        self.gmail_service = None
        self.mastodon_client = None
        self.processed_messages: Set[str] = set()

    def authenticate_gmail(self):
        """Authenticate with Gmail API using OAuth 2.0."""
        creds = None
        token_path = Path('token.json')
        creds_path = Path('credentials.json')

        # Check for existing token
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        # Refresh or get new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                print("Refreshing Gmail credentials...")
                creds.refresh(Request())
            else:
                if not creds_path.exists():
                    print("ERROR: credentials.json not found!")
                    print("Download OAuth 2.0 credentials from Google Cloud Console")
                    sys.exit(1)
                print("Starting OAuth flow for Gmail...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(creds_path), SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save credentials for next run
            with open(token_path, 'w') as token:
                token.write(creds.to_json())

        self.gmail_service = build('gmail', 'v1', credentials=creds)
        print("✓ Gmail authenticated")

    def authenticate_mastodon(self):
        """Authenticate with Mastodon API."""
        try:
            self.mastodon_client = Mastodon(
                access_token=self.mastodon_token,
                api_base_url=self.mastodon_url
            )
            # Test authentication
            account = self.mastodon_client.account_verify_credentials()
            print(f"✓ Mastodon authenticated as @{account['username']}")
        except Exception as e:
            print(f"ERROR: Failed to authenticate with Mastodon: {e}")
            sys.exit(1)

    def load_processed_messages(self):
        """Load the set of already processed message IDs."""
        if self.state_file.exists():
            with open(self.state_file, 'r') as f:
                self.processed_messages = set(line.strip() for line in f if line.strip())
            print(f"Loaded {len(self.processed_messages)} processed message IDs")

    def save_processed_message(self, message_id: str):
        """Save a message ID to the processed list."""
        self.processed_messages.add(message_id)
        with open(self.state_file, 'a') as f:
            f.write(f"{message_id}\n")

    def extract_phone_number(self, from_header: str) -> Optional[str]:
        """Extract phone number from email From header.

        Example: '"7152009057" <7152009057.12345678@txt.voice.google.com>'
        Returns: '7152009057'
        """
        match = re.search(r'["\']?(\d{10})["\']?\s*<', from_header)
        if match:
            return match.group(1)
        return None

    def decode_message_body(self, payload: dict) -> Optional[str]:
        """Decode message body from Gmail payload."""
        if 'body' in payload and 'data' in payload['body']:
            return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')

        # Handle multipart messages
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')

        return None

    def get_new_sms_messages(self) -> List[dict]:
        """Fetch new SMS messages from Gmail."""
        try:
            # Search for messages from Google Voice
            query = 'from:txt.voice.google.com is:unread'
            results = self.gmail_service.users().messages().list(
                userId='me',
                q=query,
                maxResults=10
            ).execute()

            messages = results.get('messages', [])
            if not messages:
                return []

            # Fetch full message details
            full_messages = []
            for msg in messages:
                msg_id = msg['id']

                # Skip if already processed
                if msg_id in self.processed_messages:
                    continue

                # Fetch full message
                full_msg = self.gmail_service.users().messages().get(
                    userId='me',
                    id=msg_id,
                    format='full'
                ).execute()

                full_messages.append(full_msg)

            return full_messages

        except HttpError as error:
            print(f"ERROR fetching Gmail messages: {error}")
            return []

    def mark_as_read(self, message_id: str):
        """Mark a Gmail message as read."""
        try:
            self.gmail_service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
        except HttpError as error:
            print(f"WARNING: Could not mark message as read: {error}")

    def process_message(self, message: dict) -> bool:
        """Process a single Gmail message and post to Mastodon if valid.

        Returns True if message was processed successfully.
        """
        msg_id = message['id']
        payload = message['payload']
        headers = {h['name']: h['value'] for h in payload['headers']}

        # Extract sender info
        from_header = headers.get('From', '')
        phone_number = self.extract_phone_number(from_header)

        # Filter by source phone number
        if phone_number != self.source_phone:
            print(f"Skipping message from {phone_number} (not {self.source_phone})")
            self.mark_as_read(msg_id)
            self.save_processed_message(msg_id)
            return False

        # Decode message body
        body = self.decode_message_body(payload)
        if not body:
            print(f"WARNING: Could not decode message body for {msg_id}")
            self.mark_as_read(msg_id)
            self.save_processed_message(msg_id)
            return False

        # Clean up message body
        body = body.strip()

        # Ignore genesis message
        if body == GENESIS_MESSAGE:
            print(f"Skipping genesis message from {phone_number}")
            self.mark_as_read(msg_id)
            self.save_processed_message(msg_id)
            return False

        # Post to Mastodon
        try:
            subject = headers.get('Subject', '')
            date_str = headers.get('Date', '')

            print(f"\n{'='*60}")
            print(f"New SMS from {phone_number}")
            print(f"Date: {date_str}")
            print(f"Subject: {subject}")
            print(f"Body: {body[:100]}...")
            print(f"{'='*60}")

            # Post to Mastodon
            status = self.mastodon_client.status_post(body)

            print(f"✓ Posted to Mastodon: {status['url']}")

            # Mark as processed
            self.mark_as_read(msg_id)
            self.save_processed_message(msg_id)

            return True

        except Exception as e:
            print(f"ERROR posting to Mastodon: {e}")
            return False

    def run(self):
        """Main polling loop."""
        print("\n" + "="*60)
        print("SMS to Mastodon Relay")
        print("="*60)
        print(f"Source phone: {self.source_phone}")
        print(f"Mastodon: {self.mastodon_url}")
        print(f"Poll interval: {self.poll_interval}s")
        print("="*60 + "\n")

        # Authenticate
        self.authenticate_gmail()
        self.authenticate_mastodon()
        self.load_processed_messages()

        print(f"\nStarting polling loop (Ctrl+C to stop)...\n")

        try:
            while True:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                print(f"[{timestamp}] Checking for new messages...")

                messages = self.get_new_sms_messages()
                if messages:
                    print(f"Found {len(messages)} new message(s)")
                    for msg in messages:
                        self.process_message(msg)
                else:
                    print("No new messages")

                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            print("\n\nStopping relay...")
            sys.exit(0)


def main():
    """Main entry point."""
    relay = SMSMastodonRelay()
    relay.run()


if __name__ == "__main__":
    main()
