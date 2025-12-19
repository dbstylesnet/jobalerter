# Job Alert System

Automated job alert system that monitors a configurable job board (`SITE_URL`) for new React job postings and sends email notifications.

## Features

- ✅ Monitors job board on a configurable interval (default: 180 minutes)
- ✅ Uses Firecrawl API for reliable web scraping
- ✅ Sends email notifications via Resend API
- ✅ Tracks seen jobs to avoid duplicate notifications
- ✅ Beautiful HTML email templates

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables:**
   Get the api-key from www.firecrawl.de after creating the account.
   Same for Resend from https://resend.com/.

   Then provide the keys to .env file as per example below.

   This repository already contains a tracked `.env` file at the project root. Edit that file to provide your API keys and configuration values.

   The repository includes example variables; edit them appropriately:
   ```
   FIRECRAWL_API_KEY=your_firecrawl_api_key_here
   RESEND_API_KEY=your_resend_api_key_here
   EMAIL=recipient@example.com
   SITE_URL=https://example.com
   CHECK_INTERVAL_MINUTES=180
   ```

   After editing `.env`, restart the script to pick up the new values.

3. **Run the job alert system:**
   ```bash
   python3 job_alert.py
   ```

## How It Works
1. The script checks the configured job board (`SITE_URL`) at the interval specified by `CHECK_INTERVAL_MINUTES` (minutes).
2. It first attempts to use Firecrawl's extract API to obtain structured job data; if that fails it falls back to an HTML scrape.
3. Found jobs are compared against previously seen jobs stored in `jobs_db.json`.
4. When new postings are detected, the script sends an email notification to the address configured in `EMAIL`.
5. New job IDs are saved in `jobs_db.json` to avoid duplicate notifications.

## Configuration

All configuration is read from the tracked `.env` file at the repository root. Edit that file and restart the script to apply changes.

Key variables (edit `.env`):

- `EMAIL`: Recipient email address for notifications (required).
- `CHECK_INTERVAL_MINUTES`: Interval in minutes between checks. Default is `180` (3 hours) when not provided or invalid.
- `SITE_URL`: URL of the job board to monitor (required).
- `FIRECRAWL_API_KEY`: API key for Firecrawl scraping (required).
- `RESEND_API_KEY`: API key for Resend email sending (required).

Example `.env` entries (already present in the repo; edit them):

```
FIRECRAWL_API_KEY=your_firecrawl_api_key_here
RESEND_API_KEY=your_resend_api_key_here
EMAIL=recipient@example.com
SITE_URL=https://example.com
CHECK_INTERVAL_MINUTES=180
```

Security note: because this repository currently tracks `.env`, avoid committing long-lived or production secrets here. Consider using a secrets manager or CI/CD protected variables for production deployments.

## Notes

- The script will run continuously until stopped (Ctrl+C)
- Job tracking data is stored in `jobs_db.json`

## Troubleshooting

- **No jobs found**: Check that Firecrawl API key is correct and the URL is accessible
- **Email not sending**: Verify Resend API key and check Resend dashboard for errors
- **Duplicate emails**: Clear `jobs_db.json` to reset the tracking database

