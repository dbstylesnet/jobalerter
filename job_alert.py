#!/usr/bin/env python3
"""
Job Alert System
Monitors https://it.pracuj.pl/praca/react;kw for new job postings
and sends email notifications via Resend API.
"""

import os
import json
import time
import schedule
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# Load environment variables
load_dotenv()

# Configuration
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_TO = os.getenv("EMAIL")

# Interval in minutes between checks (env may be a string)
try:
    CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES"))
except (TypeError, ValueError):
    CHECK_INTERVAL_MINUTES = 180

JOBS_DB_FILE = Path("jobs_db.json")

# URL of the job board to monitor
JOB_BOARD_URL = os.getenv("SITE_URL")


class JobAlert:
    def __init__(self):
        self.seen_job_ids: Set[str] = set()
        self.load_seen_jobs()
    
    def load_seen_jobs(self):
        """Load previously seen job IDs from database file."""
        if JOBS_DB_FILE.exists():
            try:
                with open(JOBS_DB_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.seen_job_ids = set(data.get('seen_job_ids', []))
            except Exception as e:
                print(f"Error loading jobs database: {e}")
    
    def save_seen_jobs(self):
        """Save seen job IDs to database file."""
        try:
            with open(JOBS_DB_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    'seen_job_ids': list(self.seen_job_ids),
                    'last_updated': datetime.now().isoformat()
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving jobs database: {e}")
    
    def scrape_jobs_with_firecrawl(self) -> List[Dict]:
        """Scrape job listings using Firecrawl API."""
        if not FIRECRAWL_API_KEY:
            raise ValueError("FIRECRAWL_API_KEY not set in environment variables")
        
        # Try v2 endpoint first, then fall back to v1
        endpoints = [
            "https://api.firecrawl.dev/v2/scrape",
            "https://api.firecrawl.dev/v1/scrape"
        ]
        
        headers = {
            "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Try v2 format first with selector to only get offers-list element
        payloads = [
            {
                "url": JOB_BOARD_URL,
                "formats": ["html", "markdown"],
                "selectors": ["#offers-list"]
            },
            {
                "url": JOB_BOARD_URL,
                "formats": ["html", "markdown"]
            },
            {
                "url": JOB_BOARD_URL,
                "pageOptions": {
                    "onlyMainContent": False
                }
            }
        ]
        
        # Try each endpoint with each payload format
        for endpoint in endpoints:
            for payload in payloads:
                try:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Scraping jobs from {JOB_BOARD_URL}...")
                    response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
                    
                    # Get error details if request failed
                    if response.status_code != 200:
                        error_text = response.text
                        try:
                            error_json = response.json()
                            print(f"Firecrawl API error ({response.status_code}): {error_json}")
                        except:
                            print(f"Firecrawl API error ({response.status_code}): {error_text}")
                        continue
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    # Handle different response formats
                    if isinstance(data, dict):
                        if not data.get('success', True):  # v1 uses 'success', v2 might not
                            error_msg = data.get('error', 'Unknown error')
                            print(f"Firecrawl API error: {error_msg}")
                            continue
                        
                        # Extract content - try different response structures
                        content_data = data.get('data', data)
                        html_content = (
                            content_data.get('html', '') or 
                            content_data.get('markdown', '') or
                            content_data.get('content', '')
                        )
                    else:
                        html_content = str(data)
                    
                    if html_content:
                        jobs = self.parse_jobs_from_html(html_content)
                        if jobs:
                            print(f"Found {len(jobs)} job listings")
                            return jobs
                    
                except requests.exceptions.RequestException as e:
                    print(f"Error with {endpoint}: {e}")
                    continue
        
        return []
    
    def parse_jobs_from_html(self, html_content: str) -> List[Dict]:
        """
        Parse job listings from HTML content returned by Firecrawl.
        Only scrapes from the element with id="offers-list".
        """
        jobs = []
        
        if not html_content:
            return jobs
        
        try:
            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Find the offers-list element - this is the main container for job listings
            offers_list = soup.find(id='offers-list')
            
            # if not offers_list:
            #     print("Warning: Element with id='offers-list' not found in HTML")
            #     return jobs
            
            # Only search for job listings within the offers-list element
            # Look for links that might be job postings
            job_links = offers_list.find_all('a', href=re.compile(r'/praca/|/oferta/|/job/'))
            
            seen_titles = set()
            for link in job_links:
                # Extract job information
                title = link.get_text(strip=True)
                href = link.get('href', '')
                
                # Skip if no meaningful title or duplicate
                if not title or len(title) < 5 or title in seen_titles:
                    continue
                
                # Make URL absolute if relative
                if href.startswith('/'):
                    href = f"https://it.pracuj.pl{href}"
                elif not href.startswith('http'):
                    continue
                
                # Try to find company name nearby
                company = "Unknown"
                parent = link.find_parent()
                if parent:
                    company_elem = parent.find(['span', 'div', 'p'], class_=re.compile(r'company|firma', re.I))
                    if company_elem:
                        company = company_elem.get_text(strip=True)
                
                # Try to find location
                location = "Location not specified"
                if parent:
                    location_elem = parent.find(['span', 'div', 'p'], class_=re.compile(r'location|miasto|city', re.I))
                    if location_elem:
                        location = location_elem.get_text(strip=True)
                
                job = {
                    'title': title,
                    'company': company,
                    'location': location,
                    'link': href
                }
                
                jobs.append(job)
                seen_titles.add(title)
                
        except Exception as e:
            print(f"Error parsing HTML: {e}")
        
        return jobs
    
    def scrape_jobs_with_firecrawl_extract(self) -> List[Dict]:
        """Use Firecrawl's extract endpoint for better structured data."""
        if not FIRECRAWL_API_KEY:
            raise ValueError("FIRECRAWL_API_KEY not set in environment variables")
        
        # Try v2 endpoint first
        endpoints = [
            "https://api.firecrawl.dev/v2/extract",
            "https://api.firecrawl.dev/v1/extract"
        ]
        
        headers = {
            "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Define schema to extract job information
        schema = {
            "type": "object",
            "properties": {
                "jobs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "company": {"type": "string"},
                            "location": {"type": "string"},
                            "link": {"type": "string"},
                            "description": {"type": "string"}
                        }
                    }
                }
            }
        }
        
        # Try different payload formats
        payloads = [
            {
                "url": JOB_BOARD_URL,
                "extractorOptions": {
                    "mode": "llm-extract",
                    "schema": schema
                }
            },
            {
                "urls": [JOB_BOARD_URL],
                "extractorOptions": {
                    "mode": "llm-extract",
                    "schema": schema
                }
            }
        ]
        
        for endpoint in endpoints:
            for payload in payloads:
                try:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Extracting jobs from {JOB_BOARD_URL}...")
                    response = requests.post(endpoint, json=payload, headers=headers, timeout=60)
                    
                    # Get error details if request failed
                    if response.status_code != 200:
                        error_text = response.text
                        try:
                            error_json = response.json()
                            print(f"Firecrawl extract API error ({response.status_code}): {error_json}")
                        except:
                            print(f"Firecrawl extract API error ({response.status_code}): {error_text}")
                        continue
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    # Handle different response formats
                    if isinstance(data, dict):
                        if not data.get('success', True):
                            error_msg = data.get('error', 'Unknown error')
                            print(f"Firecrawl API error: {error_msg}")
                            continue
                        
                        # Extract jobs from response
                        extracted_data = data.get('data', data)
                        
                        # Handle array response (v2 might return array)
                        if isinstance(extracted_data, list):
                            extracted_data = extracted_data[0] if extracted_data else {}
                        
                        jobs = extracted_data.get('jobs', [])
                        
                        # Generate unique IDs for jobs if not present
                        for job in jobs:
                            if 'id' not in job:
                                job_id = f"{job.get('title', '')}_{job.get('company', '')}_{job.get('link', '')}"
                                job['id'] = hash(job_id) % (10 ** 10)
                        
                        if jobs:
                            print(f"Found {len(jobs)} job listings")
                            return jobs
                    
                except requests.exceptions.RequestException as e:
                    print(f"Error with {endpoint}: {e}")
                    continue
        
        return []
    
    def get_job_id(self, job: Dict) -> str:
        """Generate a unique ID for a job posting."""
        # Use link if available, otherwise create from title + company
        if 'link' in job and job['link']:
            return str(hash(job['link']) % (10 ** 10))
        return str(hash(f"{job.get('title', '')}_{job.get('company', '')}") % (10 ** 10))
    
    def send_email(self, jobs: List[Dict]):
        """Send email notification via Resend API."""
        if not RESEND_API_KEY:
            raise ValueError("RESEND_API_KEY not set in environment variables")
        
        if not jobs:
            return
        
        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Create email content
        subject = f"New React Job Postings Found ({len(jobs)} new)"
        
        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .job {{ margin: 20px 0; padding: 15px; border-left: 4px solid #007bff; background-color: #f8f9fa; }}
                .job-title {{ font-size: 18px; font-weight: bold; color: #007bff; }}
                .job-company {{ font-size: 14px; color: #666; margin: 5px 0; }}
                .job-location {{ font-size: 14px; color: #666; }}
                .job-link {{ margin-top: 10px; }}
                .job-link a {{ color: #007bff; text-decoration: none; }}
            </style>
        </head>
        <body>
            <h2>New React Job Postings Found</h2>
            <p>Found {len(jobs)} new job posting(s) on {JOB_BOARD_URL}</p>
        """
        
        for job in jobs:
            title = job.get('title', 'No title')
            company = job.get('company', 'Unknown company')
            location = job.get('location', 'Location not specified')
            link = job.get('link', JOB_BOARD_URL)
            
            html_body += f"""
            <div class="job">
                <div class="job-title">{title}</div>
                <div class="job-company">{company}</div>
                <div class="job-location">{location}</div>
                <div class="job-link"><a href="{link}">View Job →</a></div>
            </div>
            """
        
        html_body += """
            <hr>
            <p style="color: #666; font-size: 12px;">
                This is an automated job alert. Checked at: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """
            </p>
        </body>
        </html>
        """
        
        text_body = f"New React Job Postings Found\n\nFound {len(jobs)} new job posting(s):\n\n"
        for job in jobs:
            text_body += f"- {job.get('title', 'No title')} at {job.get('company', 'Unknown')}\n"
            if job.get('link'):
                text_body += f"  Link: {job.get('link')}\n"
            text_body += "\n"
        
        payload = {
            "from": "Job Alert <onboarding@resend.dev>",  # Update with your verified domain
            "to": [EMAIL_TO],
            "subject": subject,
            "html": html_body,
            "text": text_body
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            print(f"Email sent successfully! ID: {result.get('id')}")
            
        except requests.exceptions.RequestException as e:
            print(f"Error sending email: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
    
    def check_for_new_jobs(self):
        """Main function to check for new jobs and send notifications."""
        try:
            # Try extract endpoint first (better structured data)
            jobs = self.scrape_jobs_with_firecrawl_extract()
            
            # If extract fails or returns no jobs, fall back to scrape
            if not jobs:
                jobs = self.scrape_jobs_with_firecrawl()
            
            if not jobs:
                print("No jobs found or error occurred")
                return
            
            # Filter out jobs we've already seen
            new_jobs = []
            for job in jobs:
                job_id = self.get_job_id(job)
                if job_id not in self.seen_job_ids:
                    new_jobs.append(job)
                    self.seen_job_ids.add(job_id)
            
            if new_jobs:
                print(f"Found {len(new_jobs)} new job(s)! Sending email...")
                self.send_email(new_jobs)
                self.save_seen_jobs()
            else:
                print("No new jobs found")
            
        except Exception as e:
            print(f"Error in check_for_new_jobs: {e}")
            import traceback
            traceback.print_exc()
    
    def run(self):
        """Start the job alert scheduler."""
        print(f"Starting Job Alert System")
        print(f"Checking every {CHECK_INTERVAL_MINUTES} minutes")
        print(f"Target URL: {JOB_BOARD_URL}")
        print(f"Email notifications to: {EMAIL_TO}")
        print(f"Already tracking {len(self.seen_job_ids)} jobs")
        print("-" * 50)
        
        # Run immediately on start
        self.check_for_new_jobs()
        
        # Schedule recurring checks
        schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(self.check_for_new_jobs)
        
        # Keep running
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute for scheduled tasks


if __name__ == "__main__":
    alert = JobAlert()
    alert.run()

