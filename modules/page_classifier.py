#!/usr/bin/env python3
"""
Page Classification Module

Intelligently classifies web pages to determine optimal extraction strategy.
Detects: homepage, directory listing, individual profile, search results, contact forms, etc.

Author: Claude Code
Date: 2025-12-29
"""

import re
from typing import Dict, Tuple, Optional
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
from loguru import logger


class PageType:
    """Page type constants"""
    HOMEPAGE = 'homepage'
    DIRECTORY_LISTING = 'directory_listing'
    INDIVIDUAL_PROFILE = 'individual_profile'
    SEARCH_RESULTS = 'search_results'
    CONTACT_FORM = 'contact_form'
    STUDENT_DIRECTORY = 'student_directory'  # Should be excluded
    PORTAL = 'portal'  # Should be excluded
    SOCIAL_MEDIA = 'social_media'  # Should be excluded
    IRRELEVANT = 'irrelevant'


class PageClassifier:
    """
    Intelligent page type classifier for web scraping optimization.

    Uses multiple signals:
    - URL patterns
    - HTML structure
    - Heading text
    - Link density
    - Meta tags
    """

    # URL pattern scores (negative = exclude, positive = include)
    URL_PATTERNS = {
        # High confidence directory listings
        r'/directory\b': (PageType.DIRECTORY_LISTING, 80),
        r'/staff-directory': (PageType.DIRECTORY_LISTING, 90),
        r'/faculty-directory': (PageType.DIRECTORY_LISTING, 90),
        r'/faculty-profiles$': (PageType.DIRECTORY_LISTING, 85),  # Multi-Tier Phase 5.3: /faculty-profiles (no subpath)
        r'/staff-profiles$': (PageType.DIRECTORY_LISTING, 85),    # Multi-Tier Phase 5.3: /staff-profiles (no subpath)
        r'/our-faculty/[^/]+$': (PageType.DIRECTORY_LISTING, 80), # Multi-Tier Phase 5.3: /our-faculty/faculty-profiles
        r'/our-staff/[^/]+$': (PageType.DIRECTORY_LISTING, 80),   # Multi-Tier Phase 5.3: /our-staff/staff-directory
        r'/personnel': (PageType.DIRECTORY_LISTING, 85),
        r'/people\b': (PageType.DIRECTORY_LISTING, 75),
        r'/our-people': (PageType.DIRECTORY_LISTING, 80),
        r'/team\b': (PageType.DIRECTORY_LISTING, 70),

        # Individual profiles
        r'/profile/[^/]+$': (PageType.INDIVIDUAL_PROFILE, 85),
        r'/bio/[^/]+$': (PageType.INDIVIDUAL_PROFILE, 85),
        r'/faculty/[^/]+$': (PageType.INDIVIDUAL_PROFILE, 75),
        r'/staff/[^/]+$': (PageType.INDIVIDUAL_PROFILE, 75),
        r'/people/[^/]+$': (PageType.INDIVIDUAL_PROFILE, 70),

        # Search results
        r'/search\?': (PageType.SEARCH_RESULTS, 80),
        r'[\?&]q=': (PageType.SEARCH_RESULTS, 75),
        r'[\?&]search=': (PageType.SEARCH_RESULTS, 75),

        # Contact forms
        r'/contact-us': (PageType.CONTACT_FORM, 80),
        r'/contact\b': (PageType.CONTACT_FORM, 70),

        # EXCLUDE: Student directories
        r'/student-directory': (PageType.STUDENT_DIRECTORY, -100),
        r'/student-profiles': (PageType.STUDENT_DIRECTORY, -100),
        r'/students/directory': (PageType.STUDENT_DIRECTORY, -100),

        # EXCLUDE: Portals
        r'/grades\b': (PageType.PORTAL, -100),
        r'/portal\b': (PageType.PORTAL, -100),
        r'/login\b': (PageType.PORTAL, -100),
        r'apps\.': (PageType.PORTAL, -80),
        r'outlook\.office': (PageType.SOCIAL_MEDIA, -100),

        # EXCLUDE: Social media
        r'instagram\.com': (PageType.SOCIAL_MEDIA, -100),
        r'twitter\.com': (PageType.SOCIAL_MEDIA, -100),
        r'facebook\.com': (PageType.SOCIAL_MEDIA, -100),
        r'linkedin\.com': (PageType.SOCIAL_MEDIA, -100),
        r'youtube\.com': (PageType.SOCIAL_MEDIA, -100),
        r'bluesky\.': (PageType.SOCIAL_MEDIA, -100),
    }

    # HTML structure patterns
    DIRECTORY_INDICATORS = [
        'profile-card', 'person-card', 'staff-card', 'faculty-card',
        'directory-item', 'people-list', 'staff-list', 'faculty-list',
        'personnel-item', 'team-member', 'employee-item',
    ]

    PROFILE_INDICATORS = [
        'profile-detail', 'bio-content', 'person-detail', 'faculty-bio',
        'contact-info', 'profile-header', 'biography', 'cv-content'
    ]

    STUDENT_INDICATORS = [
        'student-profile', 'student-card', 'student-directory',
        'class-of-', 'graduation-year', 'jd-candidate', 'llm-student'
    ]

    def __init__(self):
        """Initialize page classifier."""
        self.stats = {
            'total_classified': 0,
            'by_type': {}
        }

    def classify_page(self, url: str, html: str, heading_text: Optional[str] = None) -> Tuple[str, int]:
        """
        Classify a web page based on URL, HTML structure, and content.

        Args:
            url: Page URL
            html: HTML content
            heading_text: Optional main heading text (h1)

        Returns:
            Tuple of (page_type, confidence_score)
            confidence_score: 0-100 (negative scores = should exclude)
        """
        scores = {}

        # 1. URL pattern analysis
        url_type, url_score = self._classify_url(url)
        if url_type:
            scores[url_type] = url_score

        # 2. HTML structure analysis
        if html:
            soup = BeautifulSoup(html, 'html.parser')

            # Check for directory indicators
            dir_score = self._score_directory_indicators(soup)
            if dir_score > 0:
                scores[PageType.DIRECTORY_LISTING] = scores.get(PageType.DIRECTORY_LISTING, 0) + dir_score

            # Check for profile indicators
            profile_score = self._score_profile_indicators(soup)
            if profile_score > 0:
                scores[PageType.INDIVIDUAL_PROFILE] = scores.get(PageType.INDIVIDUAL_PROFILE, 0) + profile_score

            # Check for student indicators (negative score)
            student_score = self._score_student_indicators(soup)
            if student_score > 0:
                scores[PageType.STUDENT_DIRECTORY] = -100  # Strong exclusion

            # Check link density (high = listing, low = individual)
            link_density = self._calculate_link_density(soup)
            if link_density > 20:  # Many links = likely a listing
                scores[PageType.DIRECTORY_LISTING] = scores.get(PageType.DIRECTORY_LISTING, 0) + 20
            elif link_density < 5:  # Few links = likely individual profile
                scores[PageType.INDIVIDUAL_PROFILE] = scores.get(PageType.INDIVIDUAL_PROFILE, 0) + 15

        # 3. Heading text analysis
        if heading_text:
            heading_type, heading_score = self._classify_heading(heading_text)
            if heading_type:
                scores[heading_type] = scores.get(heading_type, 0) + heading_score

        # 4. Determine final classification
        if not scores:
            page_type = PageType.IRRELEVANT
            confidence = 50
        else:
            # Get highest scoring type
            page_type = max(scores, key=scores.get)
            confidence = scores[page_type]

        # Update statistics
        self.stats['total_classified'] += 1
        self.stats['by_type'][page_type] = self.stats['by_type'].get(page_type, 0) + 1

        logger.debug(f"Classified page: {url[:60]} → {page_type} (confidence: {confidence})")

        return (page_type, confidence)

    def _classify_url(self, url: str) -> Tuple[Optional[str], int]:
        """Classify based on URL patterns."""
        parsed = urlparse(url)
        full_url = url.lower()
        path = parsed.path.lower()

        # Check each pattern
        for pattern, (page_type, score) in self.URL_PATTERNS.items():
            if re.search(pattern, full_url):
                return (page_type, score)

        # Default: check if it's a homepage
        if path in ['/', '', '/index.html', '/index.php']:
            return (PageType.HOMEPAGE, 70)

        return (None, 0)

    def _score_directory_indicators(self, soup: BeautifulSoup) -> int:
        """Score directory listing indicators in HTML."""
        score = 0
        html_text = str(soup).lower()

        # Check for directory-specific classes
        for indicator in self.DIRECTORY_INDICATORS:
            if indicator in html_text:
                score += 15

        # Check for repeating person structures (strong signal)
        person_divs = soup.find_all(['div', 'article', 'section'],
                                     class_=re.compile(r'(person|profile|staff|faculty|member)', re.I))
        if len(person_divs) >= 3:  # 3+ person cards = likely a directory
            score += 30

        # Check for common directory headings
        headings = soup.find_all(['h1', 'h2', 'h3'])
        for h in headings:
            h_text = h.get_text().lower()
            if any(word in h_text for word in ['directory', 'our team', 'our people', 'staff', 'faculty']):
                score += 20
                break

        return min(score, 70)  # Cap at 70

    def _score_profile_indicators(self, soup: BeautifulSoup) -> int:
        """Score individual profile indicators in HTML."""
        score = 0
        html_text = str(soup).lower()

        # Check for profile-specific classes
        for indicator in self.PROFILE_INDICATORS:
            if indicator in html_text:
                score += 15

        # Check for biographical content (long text blocks)
        bio_sections = soup.find_all(['div', 'section'],
                                     class_=re.compile(r'(bio|about|profile|cv)', re.I))
        for section in bio_sections:
            text = section.get_text()
            if len(text) > 200:  # Long bio text = likely individual profile
                score += 25
                break

        # Check for single person's name in h1
        h1 = soup.find('h1')
        if h1:
            h1_text = h1.get_text()
            # Simple heuristic: if h1 has 2-4 words, might be a person's name
            words = h1_text.split()
            if 2 <= len(words) <= 4:
                score += 15

        return min(score, 70)  # Cap at 70

    def _score_student_indicators(self, soup: BeautifulSoup) -> int:
        """Score student directory indicators (for exclusion)."""
        score = 0
        html_text = str(soup).lower()

        # Check for student-specific indicators
        for indicator in self.STUDENT_INDICATORS:
            if indicator in html_text:
                score += 30

        # Check headings for "student"
        headings = soup.find_all(['h1', 'h2', 'h3'])
        for h in headings:
            h_text = h.get_text().lower()
            if 'student' in h_text and any(word in h_text for word in ['directory', 'profiles', 'roster']):
                score += 50
                break

        return score

    def _calculate_link_density(self, soup: BeautifulSoup) -> int:
        """Calculate number of person-related links on page."""
        # Count links that look like person profiles
        links = soup.find_all('a', href=True)
        person_links = 0

        for link in links:
            href = link.get('href', '').lower()
            text = link.get_text().lower()

            # Check if link looks like a person profile
            if any(pattern in href for pattern in ['/profile/', '/bio/', '/faculty/', '/staff/', '/people/']):
                person_links += 1
            # Or if link text looks like a name (2-4 words, capitalized)
            elif text and 2 <= len(text.split()) <= 4:
                person_links += 1

        return person_links

    def _classify_heading(self, heading_text: str) -> Tuple[Optional[str], int]:
        """Classify based on main heading text."""
        heading_lower = heading_text.lower()

        # Directory indicators
        if any(word in heading_lower for word in ['directory', 'our team', 'our people', 'staff', 'faculty']):
            return (PageType.DIRECTORY_LISTING, 25)

        # Individual profile (looks like a name)
        words = heading_text.split()
        if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
            return (PageType.INDIVIDUAL_PROFILE, 20)

        return (None, 0)

    def should_exclude(self, url: str, html: str = '') -> bool:
        """
        Quick check: should this page be excluded from scraping?

        Returns:
            True if page should be excluded (student directory, portal, social media)
        """
        page_type, confidence = self.classify_page(url, html)

        # Exclude these types
        exclude_types = [
            PageType.STUDENT_DIRECTORY,
            PageType.PORTAL,
            PageType.SOCIAL_MEDIA,
        ]

        return page_type in exclude_types or confidence < 0

    def is_directory_listing(self, url: str, html: str = '') -> bool:
        """Check if page is a directory listing (good for link extraction)."""
        page_type, confidence = self.classify_page(url, html)
        return page_type == PageType.DIRECTORY_LISTING and confidence > 50

    def is_individual_profile(self, url: str, html: str = '') -> bool:
        """Check if page is an individual profile (good for direct extraction)."""
        page_type, confidence = self.classify_page(url, html)
        return page_type == PageType.INDIVIDUAL_PROFILE and confidence > 50

    def get_stats(self) -> Dict:
        """Get classification statistics."""
        return {
            'total_classified': self.stats['total_classified'],
            'by_type': self.stats['by_type'].copy()
        }


# Singleton instance
_page_classifier = None


def get_page_classifier() -> PageClassifier:
    """Get or create singleton PageClassifier instance."""
    global _page_classifier
    if _page_classifier is None:
        _page_classifier = PageClassifier()
    return _page_classifier
