import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
import json
import logging
from datetime import datetime
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Optional, Tuple
import sys
from config import CLIENT_TYPES, get_priority_score

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scrape_contacts.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Configuration
CONFIG = {
    'request_delay': 0.6,  # seconds between requests
    'timeout': 15,  # seconds for each request
    'max_retries': 2,
    'max_pages_per_institution': 10,  # limit crawling depth
    'min_priority_score': 0,  # minimum score to include contact
    'user_agents': [
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ],
    'contact_page_patterns': [
        '/staff', '/directory', '/faculty', '/administration', '/contact',
        '/about/staff', '/people', '/team', '/leadership', '/our-team',
        '/faculty-staff', '/departments', '/workforce-development/staff',
        '/about/leadership', '/about/administration', '/contacts',
        '/staff-directory', '/employee-directory', '/faculty-directory'
    ],
    'law_school_patterns': [
        '/law/', '/school-of-law/', '/law-school/', '/college-of-law/',
        '/lawschool/', '/law/faculty', '/law/staff', '/law/directory',
        '/academics/law/', '/programs/law/', '/law/administration',
        '/law/people', '/law/contact', '/law/about'
    ],
    'paralegal_patterns': [
        '/paralegal/', '/legal-studies/', '/paralegal-program/',
        '/paralegal-studies/', '/legal-assistant/', '/paralegal/faculty',
        '/paralegal/staff', '/legal-studies/faculty', '/academics/paralegal/',
        '/programs/paralegal/', '/paralegal/contact'
    ]
}

class ContactScraper:
    def __init__(self, resume=False):
        self.resume = resume
        self.progress_file = 'scrape_progress.json'
        self.progress = self.load_progress() if resume else {}
        self.contacts = []
        self.stats = {
            'total_institutions': 0,
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'contacts_found': 0,
            'start_time': datetime.now()
        }

    def load_progress(self) -> Dict:
        """Load progress from JSON file for resume capability"""
        try:
            with open(self.progress_file, 'r') as f:
                progress = json.load(f)
                logger.info(f"Loaded progress: {progress.get('processed', 0)} institutions processed")
                return progress
        except FileNotFoundError:
            logger.info("No progress file found, starting fresh")
            return {}
        except json.JSONDecodeError:
            logger.warning("Progress file corrupted, starting fresh")
            return {}

    def save_progress(self):
        """Save current progress to JSON file"""
        self.progress.update({
            'processed': self.stats['processed'],
            'successful': self.stats['successful'],
            'failed': self.stats['failed'],
            'contacts_found': self.stats['contacts_found'],
            'last_updated': datetime.now().isoformat()
        })
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress, f, indent=2)

    def normalize_url(self, url: str) -> Optional[str]:
        """Normalize and validate URL"""
        if not url or pd.isna(url):
            return None

        url = url.strip()

        # Add protocol if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        # Remove trailing slashes
        url = url.rstrip('/')

        # Validate URL format
        try:
            result = urlparse(url)
            if result.scheme and result.netloc:
                return url
        except Exception:
            pass

        return None

    def detect_page_context(self, url: str, soup: BeautifulSoup = None) -> str:
        """
        Detect if a page is from a law school, paralegal program, or general context.

        Args:
            url: The page URL
            soup: Optional BeautifulSoup object for content analysis

        Returns:
            'Law School', 'Paralegal Program', or 'General'
        """
        url_lower = url.lower()

        # Check URL for law school patterns
        law_indicators = ['/law/', '/school-of-law/', '/law-school/', '/college-of-law/',
                         '/lawschool/', '/law/', 'law.', '/academics/law', '/programs/law']
        if any(indicator in url_lower for indicator in law_indicators):
            return 'Law School'

        # Check URL for paralegal patterns
        paralegal_indicators = ['/paralegal/', '/legal-studies/', '/paralegal-program/',
                               '/legal-assistant/', 'paralegal.', '/academics/paralegal',
                               '/programs/paralegal']
        if any(indicator in url_lower for indicator in paralegal_indicators):
            return 'Paralegal Program'

        # Check page content if soup is provided
        if soup:
            page_text = soup.get_text().lower()
            title = soup.find('title')
            title_text = title.get_text().lower() if title else ''

            # Check for law school indicators in content
            law_keywords = ['law school', 'school of law', 'college of law', 'juris doctor', 'j.d.', 'jd program']
            if any(keyword in title_text or keyword in page_text[:1000] for keyword in law_keywords):
                return 'Law School'

            # Check for paralegal indicators in content
            paralegal_keywords = ['paralegal program', 'paralegal studies', 'legal studies', 'legal assistant program']
            if any(keyword in title_text or keyword in page_text[:1000] for keyword in paralegal_keywords):
                return 'Paralegal Program'

        return 'General'

    def fetch_page(self, url: str, retry_count: int = 0) -> Optional[BeautifulSoup]:
        """Fetch and parse a webpage with retry logic"""
        try:
            headers = {
                'User-Agent': CONFIG['user_agents'][retry_count % len(CONFIG['user_agents'])],
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            }

            response = requests.get(
                url,
                headers=headers,
                timeout=CONFIG['timeout'],
                allow_redirects=True
            )

            # Check for rate limiting or blocking
            if response.status_code == 429:
                logger.warning(f"Rate limited at {url}, waiting 30 seconds...")
                time.sleep(30)
                if retry_count < CONFIG['max_retries']:
                    return self.fetch_page(url, retry_count + 1)
                return None

            if response.status_code == 403:
                logger.warning(f"Access forbidden at {url}")
                return None

            response.raise_for_status()

            # Parse with BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')
            return soup

        except requests.exceptions.Timeout:
            logger.warning(f"Timeout fetching {url}")
            if retry_count < CONFIG['max_retries']:
                time.sleep(5)
                return self.fetch_page(url, retry_count + 1)
            return None

        except requests.exceptions.RequestException as e:
            logger.warning(f"Request error for {url}: {str(e)[:100]}")
            return None

        except Exception as e:
            logger.error(f"Unexpected error fetching {url}: {str(e)[:100]}")
            return None

    def find_contact_pages(self, base_url: str, homepage_soup: BeautifulSoup) -> List[Tuple[str, int]]:
        """
        Discover potential contact/staff directory pages.

        Returns:
            List of tuples (url, priority) where priority is:
            3 = Law school or paralegal specific page
            2 = General contact page
            1 = Homepage
        """
        contact_urls = {}  # url -> priority

        # Method 1: Check law school and paralegal specific patterns (HIGHEST PRIORITY)
        for pattern in CONFIG['law_school_patterns']:
            potential_url = base_url + pattern
            contact_urls[potential_url] = 3

        for pattern in CONFIG['paralegal_patterns']:
            potential_url = base_url + pattern
            contact_urls[potential_url] = 3

        # Method 2: Check common URL patterns (MEDIUM PRIORITY)
        for pattern in CONFIG['contact_page_patterns']:
            potential_url = base_url + pattern
            if potential_url not in contact_urls:
                contact_urls[potential_url] = 2

        # Method 3: Search for links in homepage
        if homepage_soup:
            for link in homepage_soup.find_all('a', href=True):
                href = link['href'].lower()
                text = link.get_text().lower()

                # Look for law school and paralegal keywords (HIGHEST PRIORITY)
                law_keywords = ['law school', 'school of law', 'college of law', 'law faculty',
                               'paralegal', 'legal studies', 'legal assistant']
                has_law_keyword = any(keyword in href or keyword in text for keyword in law_keywords)

                # Look for general contact keywords (MEDIUM PRIORITY)
                contact_keywords = ['staff', 'directory', 'faculty', 'administration',
                                   'contact', 'people', 'team', 'leadership', 'employee']
                has_contact_keyword = any(keyword in href or keyword in text for keyword in contact_keywords)

                if has_law_keyword or has_contact_keyword:
                    full_url = urljoin(base_url, link['href'])
                    # Only include URLs from the same domain
                    if urlparse(full_url).netloc == urlparse(base_url).netloc:
                        priority = 3 if has_law_keyword else 2
                        # Keep highest priority if URL already exists
                        if full_url not in contact_urls or contact_urls[full_url] < priority:
                            contact_urls[full_url] = priority

        # Sort by priority (highest first), then limit
        sorted_urls = sorted(contact_urls.items(), key=lambda x: x[1], reverse=True)
        return sorted_urls[:CONFIG['max_pages_per_institution']]

    def extract_emails(self, soup: BeautifulSoup) -> List[str]:
        """Extract email addresses from page"""
        emails = set()

        # Method 1: Find mailto links
        for link in soup.find_all('a', href=True):
            if link['href'].startswith('mailto:'):
                email = link['href'].replace('mailto:', '').split('?')[0]
                emails.add(email)

        # Method 2: Regex pattern for email addresses
        text = soup.get_text()
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        found_emails = re.findall(email_pattern, text)
        emails.update(found_emails)

        # Method 3: Look for obfuscated emails (e.g., "user [at] domain [dot] edu")
        obfuscated_pattern = r'(\w+)\s*\[at\]\s*(\w+(?:\.\w+)*)\s*\[dot\]\s*(\w+)'
        obfuscated = re.findall(obfuscated_pattern, text, re.IGNORECASE)
        for user, domain, tld in obfuscated:
            emails.add(f"{user}@{domain}.{tld}")

        return list(emails)

    def extract_phone_numbers(self, text: str) -> List[str]:
        """Extract phone numbers from text"""
        # Pattern for common US phone formats
        patterns = [
            r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',  # (123) 456-7890 or 123-456-7890
            r'\d{3}[-.\s]\d{4}',  # 456-7890 (extension format)
        ]

        phones = set()
        for pattern in patterns:
            found = re.findall(pattern, text)
            phones.update(found)

        return list(phones)

    def extract_contacts_from_page(self, soup: BeautifulSoup, url: str) -> List[Dict]:
        """Extract structured contact information from a page"""
        contacts = []

        # Detect page context (Law School, Paralegal Program, or General)
        page_context = self.detect_page_context(url, soup)

        # Extract all emails first
        emails = self.extract_emails(soup)

        # Strategy 1: Look for structured contact listings
        # Common patterns: divs/sections with class containing 'staff', 'person', 'contact', 'team-member'
        contact_containers = soup.find_all(['div', 'section', 'article'],
            class_=re.compile(r'(staff|person|contact|team|member|faculty|employee|profile)', re.I))

        for container in contact_containers:
            contact = self.parse_contact_container(container, emails, url, page_context)
            if contact:
                contacts.append(contact)

        # Strategy 2: Look for table-based directories
        tables = soup.find_all('table')
        for table in tables:
            table_contacts = self.parse_contact_table(table, emails, url, page_context)
            contacts.extend(table_contacts)

        # Strategy 3: If no structured contacts found, create generic contacts for emails
        if not contacts and emails:
            for email in emails:
                contacts.append({
                    'name': None,
                    'title': None,
                    'email': email,
                    'phone': None,
                    'department': None,
                    'page_context': page_context,
                    'source_url': url
                })

        return contacts

    def parse_contact_container(self, container, available_emails: List[str], url: str, page_context: str = 'General') -> Optional[Dict]:
        """Parse a contact from a container element"""
        contact = {
            'name': None,
            'title': None,
            'email': None,
            'phone': None,
            'department': None,
            'page_context': page_context,
            'source_url': url
        }

        # Extract name (usually in h2, h3, h4, or span.name, div.name)
        name_elem = container.find(['h2', 'h3', 'h4', 'h5'])
        if not name_elem:
            name_elem = container.find(class_=re.compile(r'name', re.I))
        if name_elem:
            contact['name'] = name_elem.get_text(strip=True)

        # Extract title
        title_elem = container.find(class_=re.compile(r'(title|position|role)', re.I))
        if title_elem:
            contact['title'] = title_elem.get_text(strip=True)

        # Extract email
        email_link = container.find('a', href=re.compile(r'^mailto:', re.I))
        if email_link:
            contact['email'] = email_link['href'].replace('mailto:', '').split('?')[0]
        else:
            # Try to find email in text
            text = container.get_text()
            email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
            if email_match:
                contact['email'] = email_match.group(0)

        # Extract phone
        text = container.get_text()
        phones = self.extract_phone_numbers(text)
        if phones:
            contact['phone'] = phones[0]

        # Extract department
        dept_elem = container.find(class_=re.compile(r'(department|dept|division)', re.I))
        if dept_elem:
            contact['department'] = dept_elem.get_text(strip=True)

        # Only return if we have at least a name or email
        if contact['name'] or contact['email']:
            return contact

        return None

    def parse_contact_table(self, table, available_emails: List[str], url: str, page_context: str = 'General') -> List[Dict]:
        """Parse contacts from a table structure"""
        contacts = []

        # Look for header row to identify columns
        headers = []
        header_row = table.find('thead')
        if header_row:
            headers = [th.get_text(strip=True).lower() for th in header_row.find_all(['th', 'td'])]

        # Process data rows
        rows = table.find_all('tr')
        for row in rows[1:]:  # Skip header row
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue

            contact = {
                'name': None,
                'title': None,
                'email': None,
                'phone': None,
                'department': None,
                'page_context': page_context,
                'source_url': url
            }

            # If we have headers, map by column name
            if headers and len(cells) == len(headers):
                for i, cell in enumerate(cells):
                    header = headers[i]
                    text = cell.get_text(strip=True)

                    if 'name' in header:
                        contact['name'] = text
                    elif 'title' in header or 'position' in header:
                        contact['title'] = text
                    elif 'email' in header or 'e-mail' in header:
                        contact['email'] = text
                    elif 'phone' in header or 'tel' in header:
                        contact['phone'] = text
                    elif 'department' in header or 'dept' in header:
                        contact['department'] = text
            else:
                # No headers, try to infer from content
                for cell in cells:
                    text = cell.get_text(strip=True)

                    # Check for email
                    if '@' in text and not contact['email']:
                        contact['email'] = text
                    # Check for phone
                    elif re.search(r'\d{3}[-.\s]\d{3}[-.\s]\d{4}', text) and not contact['phone']:
                        contact['phone'] = text
                    # First text field is likely name
                    elif not contact['name'] and len(text) > 0:
                        contact['name'] = text
                    # Second text field is likely title
                    elif not contact['title'] and len(text) > 0:
                        contact['title'] = text

            if contact['name'] or contact['email']:
                contacts.append(contact)

        return contacts

    def scrape_institution(self, institution: Dict) -> List[Dict]:
        """Scrape contacts for a single institution"""
        unitid = institution['UNITID']
        name = institution['INSTNM']
        base_url = self.normalize_url(institution.get('WEBADDR'))
        client_types = institution.get('CLIENT_TYPE', 'Unclassified')

        logger.info(f"Scraping {name} ({unitid}) - {client_types}")

        if not base_url:
            logger.warning(f"No valid URL for {name}, skipping")
            return []

        all_contacts = []
        pages_checked = 0
        law_pages_found = 0
        paralegal_pages_found = 0

        # Fetch homepage
        time.sleep(CONFIG['request_delay'])
        homepage_soup = self.fetch_page(base_url)

        if not homepage_soup:
            logger.warning(f"Could not fetch homepage for {name}")
            return []

        # Find contact pages (now returns list of tuples: (url, priority))
        contact_urls_with_priority = self.find_contact_pages(base_url, homepage_soup)
        logger.info(f"Found {len(contact_urls_with_priority)} potential contact pages for {name}")

        # Check homepage first
        homepage_contacts = self.extract_contacts_from_page(homepage_soup, base_url)
        all_contacts.extend(homepage_contacts)
        pages_checked += 1

        # Check contact pages (prioritized by law/paralegal relevance)
        for contact_url, priority in contact_urls_with_priority:
            if pages_checked >= CONFIG['max_pages_per_institution']:
                break

            time.sleep(CONFIG['request_delay'])
            soup = self.fetch_page(contact_url)

            if soup:
                contacts = self.extract_contacts_from_page(soup, contact_url)
                all_contacts.extend(contacts)
                pages_checked += 1

                # Track law school and paralegal pages found
                if contacts:
                    page_context = contacts[0].get('page_context', 'General')
                    if page_context == 'Law School':
                        law_pages_found += 1
                    elif page_context == 'Paralegal Program':
                        paralegal_pages_found += 1

                logger.info(f"Extracted {len(contacts)} contacts from {contact_url}")

        # Log if we found law/paralegal specific content
        if law_pages_found > 0:
            logger.info(f"*** Found {law_pages_found} Law School pages at {name} ***")
        if paralegal_pages_found > 0:
            logger.info(f"*** Found {paralegal_pages_found} Paralegal Program pages at {name} ***")

        # Add institution metadata to each contact
        for contact in all_contacts:
            contact['UNITID'] = unitid
            contact['INSTNM'] = name
            contact['STABBR'] = institution.get('STABBR', '')
            contact['CLIENT_TYPE'] = client_types
            contact['scraped_date'] = datetime.now().isoformat()

        logger.info(f"Total contacts found for {name}: {len(all_contacts)}")
        return all_contacts

    def calculate_priority_scores(self, contacts: List[Dict]) -> List[Dict]:
        """Calculate priority scores for all contacts"""
        scored_contacts = []

        for contact in contacts:
            title = contact.get('title', '')
            client_types = contact.get('CLIENT_TYPE', '').split(', ')

            # Calculate score for each client type and use the highest
            max_score = 0
            for client_type in client_types:
                if client_type and client_type != 'Unclassified':
                    score = get_priority_score(title, client_type)
                    max_score = max(max_score, score)

            contact['priority_score'] = max_score

            # Only include contacts meeting minimum score
            if max_score >= CONFIG['min_priority_score']:
                scored_contacts.append(contact)

        return scored_contacts

    def run(self, input_file: str = 'institutions.csv', output_file: str = 'raw_contacts.csv'):
        """Main scraping workflow"""
        logger.info("="*80)
        logger.info("Starting Contact Scraper")
        logger.info("="*80)

        # Load institutions
        try:
            df = pd.read_csv(input_file, encoding='utf-8-sig')
            # Strip BOM from column names if present
            df.columns = df.columns.str.replace('ï»¿', '', regex=False)
            logger.info(f"Loaded {len(df)} institutions from {input_file}")
        except Exception as e:
            logger.error(f"Failed to load {input_file}: {e}")
            return

        self.stats['total_institutions'] = len(df)

        # Filter out already processed institutions if resuming
        if self.resume and 'processed_unitids' in self.progress:
            processed = set(self.progress['processed_unitids'])
            df = df[~df['UNITID'].isin(processed)]
            logger.info(f"Resuming: {len(df)} institutions remaining")

        # Process each institution
        for idx, row in df.iterrows():
            try:
                contacts = self.scrape_institution(row.to_dict())
                self.contacts.extend(contacts)
                self.stats['contacts_found'] += len(contacts)
                self.stats['successful'] += 1

            except Exception as e:
                logger.error(f"Error processing {row['INSTNM']}: {str(e)[:200]}")
                self.stats['failed'] += 1

            finally:
                self.stats['processed'] += 1

                # Update progress
                if 'processed_unitids' not in self.progress:
                    self.progress['processed_unitids'] = []
                self.progress['processed_unitids'].append(int(row['UNITID']))

                # Save progress every 10 institutions
                if self.stats['processed'] % 10 == 0:
                    self.save_progress()
                    self.export_contacts(output_file)
                    self.print_stats()

        # Calculate priority scores
        logger.info("Calculating priority scores...")
        self.contacts = self.calculate_priority_scores(self.contacts)

        # Final export
        self.export_contacts(output_file)
        self.save_progress()
        self.print_stats()

        logger.info("="*80)
        logger.info("Scraping Complete!")
        logger.info("="*80)

    def export_contacts(self, output_file: str):
        """Export contacts to CSV"""
        if not self.contacts:
            logger.warning("No contacts to export")
            return

        df = pd.DataFrame(self.contacts)

        # Reorder columns for better readability
        column_order = [
            'UNITID', 'INSTNM', 'STABBR', 'CLIENT_TYPE',
            'name', 'title', 'email', 'phone', 'department',
            'page_context', 'priority_score', 'source_url', 'scraped_date'
        ]

        # Only include columns that exist
        columns = [col for col in column_order if col in df.columns]
        df = df[columns]

        # Sort by priority score descending
        if 'priority_score' in df.columns:
            df = df.sort_values('priority_score', ascending=False)

        df.to_csv(output_file, index=False)
        logger.info(f"Exported {len(df)} contacts to {output_file}")

    def print_stats(self):
        """Print scraping statistics"""
        elapsed = datetime.now() - self.stats['start_time']

        logger.info("-"*80)
        logger.info(f"Progress: {self.stats['processed']}/{self.stats['total_institutions']} "
                   f"({self.stats['processed']/self.stats['total_institutions']*100:.1f}%)")
        logger.info(f"Successful: {self.stats['successful']}")
        logger.info(f"Failed: {self.stats['failed']}")
        logger.info(f"Contacts found: {self.stats['contacts_found']}")
        logger.info(f"Avg contacts/institution: "
                   f"{self.stats['contacts_found']/max(self.stats['successful'],1):.1f}")
        logger.info(f"Elapsed time: {elapsed}")
        logger.info("-"*80)

def main():
    """CLI entry point"""
    print("Contact Scraper for IPEDS Institutions")
    print("="*80)

    resume = input("Resume from previous run? (y/n): ").strip().lower() == 'y'

    scraper = ContactScraper(resume=resume)
    scraper.run()

if __name__ == "__main__":
    main()
