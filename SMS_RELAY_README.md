# SMS to Mastodon Relay

Automatically relay SMS messages from Google Voice to Mastodon by polling Gmail for forwarded text messages.

## Features

- 📧 Polls Gmail for SMS messages forwarded from Google Voice
- 📱 Filters messages by specific sender phone number
- 🐘 Posts messages to Mastodon
- 🔍 Deduplication to avoid posting the same message twice
- ⚙️ Configurable polling interval
- 🔐 OAuth 2.0 authentication for Gmail
- 📝 State tracking to persist across restarts

## Prerequisites

1. **Google Voice**: Configure to forward SMS to Gmail
   - Go to Google Voice settings
   - Enable "Forward messages to email"

2. **Gmail API Credentials**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project (or select existing)
   - Enable Gmail API
   - Create OAuth 2.0 credentials (Desktop app)
   - Download credentials as `credentials.json`

3. **Mastodon Account & App**:
   - Create account on any Mastodon instance
   - Go to Settings > Development > New Application
   - Give it a name (e.g., "SMS Relay")
   - Required scope: `write:statuses`
   - Copy the access token

## Setup

1. **Install dependencies**:
   ```bash
   uv sync
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Place Gmail credentials**:
   - Download `credentials.json` from Google Cloud Console
   - Place in the project root directory

4. **Configure `.env`**:
   ```bash
   SOURCE_PHONE_NUMBER=7152009057
   MASTODON_INSTANCE_URL=https://mastodon.social
   MASTODON_ACCESS_TOKEN=your_token_here
   POLL_INTERVAL_SECONDS=60
   ```

## Usage

### First Run

On first run, the script will open a browser for Gmail OAuth:

```bash
uv run sms-mastodon-relay.py
```

Follow the prompts to:
1. Select your Google account
2. Grant Gmail read-only access
3. Authorization complete!

A `token.json` file will be saved for future runs.

### Normal Operation

```bash
uv run sms-mastodon-relay.py
```

The script will:
- Check Gmail every 60 seconds (configurable)
- Filter for messages from `7152009057`
- Skip the Google Voice signup message
- Post new SMS to Mastodon
- Mark Gmail messages as read
- Track processed messages in `.processed_messages.txt`

### Example Output

```
============================================================
SMS to Mastodon Relay
============================================================
Source phone: 7152009057
Mastodon: https://mastodon.social
Poll interval: 60s
============================================================

✓ Gmail authenticated
✓ Mastodon authenticated as @youruser
Loaded 5 processed message IDs

Starting polling loop (Ctrl+C to stop)...

[2026-01-13 10:30:00] Checking for new messages...
Found 1 new message(s)

============================================================
New SMS from 7152009057
Date: Mon, 13 Jan 2026 10:29:45 -0800
Subject: SMS from 7152009057
Body: Hello from my phone!
============================================================
✓ Posted to Mastodon: https://mastodon.social/@youruser/123456789

[2026-01-13 10:31:00] Checking for new messages...
No new messages
```

## Configuration Options

| Variable | Description | Default |
|----------|-------------|---------|
| `SOURCE_PHONE_NUMBER` | 10-digit phone number to filter | Required |
| `MASTODON_INSTANCE_URL` | Your Mastodon instance URL | Required |
| `MASTODON_ACCESS_TOKEN` | Mastodon app access token | Required |
| `POLL_INTERVAL_SECONDS` | Seconds between Gmail checks | `60` |
| `STATE_FILE` | File to track processed messages | `.processed_messages.txt` |

## How It Works

1. **Gmail Polling**: Every N seconds, queries Gmail for unread messages from `txt.voice.google.com`
2. **Message Parsing**: Extracts sender phone number from email headers
3. **Filtering**:
   - Checks if sender matches `SOURCE_PHONE_NUMBER`
   - Ignores genesis message: "Thxs for texting. More mobile updates coming soon."
4. **Deduplication**: Tracks message IDs in state file
5. **Posting**: Posts SMS body to Mastodon via API
6. **Cleanup**: Marks Gmail message as read

## Files Created

- `token.json` - Gmail OAuth token (auto-generated)
- `.processed_messages.txt` - Processed message IDs (auto-generated)
- `.env` - Your configuration (you create this)

## Troubleshooting

### "credentials.json not found"
- Download OAuth 2.0 credentials from Google Cloud Console
- Make sure it's named exactly `credentials.json`

### "Gmail authentication failed"
- Delete `token.json` and re-authenticate
- Check that Gmail API is enabled in Google Cloud Console

### "Mastodon authentication failed"
- Verify `MASTODON_INSTANCE_URL` includes `https://`
- Check that access token has `write:statuses` scope
- Test token manually at your instance's API docs

### Messages not appearing
- Verify Google Voice is forwarding to Gmail
- Check Gmail for messages from `txt.voice.google.com`
- Verify sender phone number matches exactly (10 digits)

## Security Notes

- **OAuth tokens**: `token.json` contains sensitive credentials - don't commit to git
- **Access tokens**: `.env` contains Mastodon token - don't commit to git
- **Gmail scope**: Uses read-only scope for safety
- **State file**: `.processed_messages.txt` only contains message IDs

## Future Enhancements

- [ ] Push notifications via Google Pub/Sub (real-time delivery)
- [ ] Support multiple source phone numbers
- [ ] Custom message formatting/templates
- [ ] Direct message support on Mastodon
- [ ] Web dashboard for monitoring
- [ ] Docker container for easy deployment

## License

MIT - Feel free to modify and use as needed.
