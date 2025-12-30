#!/usr/bin/env python3
"""
Email De-obfuscation Module

Extracts and decodes obfuscated email addresses from web pages.
Handles: Cloudflare protection, text patterns, JavaScript encoding, etc.

Author: Claude Code
Date: 2025-12-29
"""

import re
from typing import List, Set, Optional
from bs4 import BeautifulSoup
from loguru import logger


class EmailDeobfuscator:
    """
    Intelligent email de-obfuscation for web scraping.

    Handles multiple obfuscation techniques:
    - Cloudflare email protection (data-cfemail)
    - Text patterns: "email [at] domain [dot] com"
    - JavaScript encoding
    - HTML entity encoding
    - <noscript> fallbacks
    """

    # Text pattern variations
    TEXT_PATTERNS = [
        # email [at] domain [dot] com
        (r'(\w+(?:\.\w+)*)\s*\[at\]\s*(\w+(?:\.\w+)*)', r'\1@\2'),
        # email (at) domain (dot) com
        (r'(\w+(?:\.\w+)*)\s*\(at\)\s*(\w+(?:\.\w+)*)', r'\1@\2'),
        # email AT domain DOT com
        (r'(\w+(?:\.\w+)*)\s+AT\s+(\w+(?:\.\w+)*)', r'\1@\2'),
        # Replace [dot] and (dot)
        (r'\[dot\]', '.'),
        (r'\(dot\)', '.'),
        (r'\s+DOT\s+', '.'),
    ]

    def __init__(self):
        """Initialize email de-obfuscator."""
        self.stats = {
            'cloudflare_decoded': 0,
            'text_pattern_decoded': 0,
            'javascript_extracted': 0,
            'noscript_extracted': 0,
            'total_deobfuscated': 0
        }

    def deobfuscate_all(self, html: str) -> Set[str]:
        """
        Extract all obfuscated emails from HTML.

        Args:
            html: HTML content

        Returns:
            Set of decoded email addresses
        """
        emails = set()

        if not html:
            return emails

        soup = BeautifulSoup(html, 'html.parser')

        # 1. Cloudflare protection
        cloudflare_emails = self._decode_cloudflare(soup)
        emails.update(cloudflare_emails)

        # 2. Text pattern deobfuscation
        text_emails = self._decode_text_patterns(html)
        emails.update(text_emails)

        # 3. JavaScript extraction
        js_emails = self._extract_from_javascript(soup)
        emails.update(js_emails)

        # 4. Noscript fallbacks
        noscript_emails = self._extract_from_noscript(soup)
        emails.update(noscript_emails)

        # 5. Data attributes (data-email, data-contact, etc.)
        attr_emails = self._extract_from_attributes(soup)
        emails.update(attr_emails)

        if emails:
            self.stats['total_deobfuscated'] += len(emails)
            logger.debug(f"De-obfuscated {len(emails)} email addresses")

        return emails

    def _decode_cloudflare(self, soup: BeautifulSoup) -> Set[str]:
        """
        Decode Cloudflare email protection.

        Cloudflare uses data-cfemail attribute with XOR encoding.
        Algorithm: First byte is key, XOR with subsequent bytes.
        """
        emails = set()

        # Find all elements with data-cfemail attribute
        cf_elements = soup.find_all(attrs={'data-cfemail': True})

        for element in cf_elements:
            encoded = element.get('data-cfemail', '')
            if not encoded:
                continue

            try:
                # Decode hex string
                encoded_bytes = bytes.fromhex(encoded)

                # First byte is the XOR key
                key = encoded_bytes[0]

                # XOR each subsequent byte with key
                decoded_chars = []
                for byte in encoded_bytes[1:]:
                    decoded_chars.append(chr(byte ^ key))

                email = ''.join(decoded_chars)

                # Validate it looks like an email
                if self._is_valid_email_format(email):
                    emails.add(email)
                    self.stats['cloudflare_decoded'] += 1
                    logger.debug(f"Decoded Cloudflare email: {email}")

            except Exception as e:
                logger.debug(f"Failed to decode Cloudflare email: {e}")

        return emails

    def _decode_text_patterns(self, text: str) -> Set[str]:
        """
        Decode text-based obfuscation patterns.

        Patterns:
        - email [at] domain [dot] com
        - email (at) domain (dot) com
        - email AT domain DOT com
        """
        emails = set()

        # Apply each pattern transformation
        decoded_text = text
        for pattern, replacement in self.TEXT_PATTERNS:
            decoded_text = re.sub(pattern, replacement, decoded_text, flags=re.IGNORECASE)

        # Find email addresses in decoded text
        email_regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        found_emails = re.findall(email_regex, decoded_text)

        for email in found_emails:
            if self._is_valid_email_format(email):
                # Check if this email was actually obfuscated (not in original text)
                if email not in text:
                    emails.add(email)
                    self.stats['text_pattern_decoded'] += 1
                    logger.debug(f"Decoded text pattern email: {email}")

        return emails

    def _extract_from_javascript(self, soup: BeautifulSoup) -> Set[str]:
        """
        Extract emails from JavaScript code.

        Looks for common patterns:
        - var email = "user@domain.com";
        - document.write("email@domain.com");
        - String concatenation: "user" + "@" + "domain.com"
        """
        emails = set()

        # Find all script tags
        scripts = soup.find_all('script')

        for script in scripts:
            script_text = script.get_text()
            if not script_text:
                continue

            # Pattern 1: Simple string literals containing @
            simple_pattern = r'["\']([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})["\']'
            found = re.findall(simple_pattern, script_text)
            for email in found:
                if self._is_valid_email_format(email):
                    emails.add(email)
                    self.stats['javascript_extracted'] += 1

            # Pattern 2: String concatenation (simplified)
            # Look for: "user" + "@" + "domain"
            concat_pattern = r'["\']([a-z0-9._-]+)["\']\s*\+\s*["\']@["\']\s*\+\s*["\']([a-z0-9._-]+\.[a-z]{2,})["\']'
            found = re.findall(concat_pattern, script_text, re.IGNORECASE)
            for user, domain in found:
                email = f"{user}@{domain}"
                if self._is_valid_email_format(email):
                    emails.add(email)
                    self.stats['javascript_extracted'] += 1

        return emails

    def _extract_from_noscript(self, soup: BeautifulSoup) -> Set[str]:
        """
        Extract emails from <noscript> fallback content.

        Many sites provide plain email in <noscript> for non-JS browsers.
        """
        emails = set()

        noscript_tags = soup.find_all('noscript')
        for tag in noscript_tags:
            text = tag.get_text()

            # Find emails in noscript content
            email_regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            found = re.findall(email_regex, text)

            for email in found:
                if self._is_valid_email_format(email):
                    emails.add(email)
                    self.stats['noscript_extracted'] += 1
                    logger.debug(f"Extracted email from noscript: {email}")

        return emails

    def _extract_from_attributes(self, soup: BeautifulSoup) -> Set[str]:
        """
        Extract emails from data attributes.

        Some sites store emails in custom data attributes:
        - data-email
        - data-contact
        - data-mail
        - data-user-email
        """
        emails = set()

        # Common attribute names
        attr_names = ['data-email', 'data-contact', 'data-mail', 'data-user-email']

        for attr in attr_names:
            elements = soup.find_all(attrs={attr: True})
            for element in elements:
                email = element.get(attr, '').strip()
                if email and self._is_valid_email_format(email):
                    emails.add(email)
                    logger.debug(f"Extracted email from {attr}: {email}")

        return emails

    def _is_valid_email_format(self, email: str) -> bool:
        """
        Validate email format.

        Args:
            email: Email address to validate

        Returns:
            True if valid format
        """
        if not email or len(email) < 5:
            return False

        # Basic email regex
        pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'
        if not re.match(pattern, email):
            return False

        # Exclude common false positives
        false_positives = [
            'email@example.com',
            'user@example.com',
            'admin@example.com',
            'info@example.com',
            'test@test.com',
            'example@example.com'
        ]
        if email.lower() in false_positives:
            return False

        return True

    def deobfuscate_single(self, text: str) -> Optional[str]:
        """
        Attempt to deobfuscate a single email string.

        Args:
            text: Potentially obfuscated email text

        Returns:
            Decoded email or None
        """
        if not text:
            return None

        # Try text pattern deobfuscation
        decoded = text
        for pattern, replacement in self.TEXT_PATTERNS:
            decoded = re.sub(pattern, replacement, decoded, flags=re.IGNORECASE)

        # Check if result is valid email
        if self._is_valid_email_format(decoded):
            return decoded

        return None

    def get_stats(self) -> dict:
        """Get de-obfuscation statistics."""
        return {
            'cloudflare_decoded': self.stats['cloudflare_decoded'],
            'text_pattern_decoded': self.stats['text_pattern_decoded'],
            'javascript_extracted': self.stats['javascript_extracted'],
            'noscript_extracted': self.stats['noscript_extracted'],
            'total_deobfuscated': self.stats['total_deobfuscated']
        }


# Singleton instance
_email_deobfuscator = None


def get_email_deobfuscator() -> EmailDeobfuscator:
    """Get or create singleton EmailDeobfuscator instance."""
    global _email_deobfuscator
    if _email_deobfuscator is None:
        _email_deobfuscator = EmailDeobfuscator()
    return _email_deobfuscator
