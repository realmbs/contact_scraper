#!/usr/bin/env python3
"""
Link Extraction Module

Intelligently extracts and scores profile/bio links from directory pages.
Enables deep crawling to individual profile pages.

Author: Claude Code
Date: 2025-12-29
"""

import re
from typing import List, Dict, Tuple, Set
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from loguru import logger


class ProfileLink:
    """Represents a link to an individual profile page."""

    def __init__(self, url: str, text: str, score: int, context: str = ''):
        """
        Initialize profile link.

        Args:
            url: Full URL to profile page
            text: Link anchor text
            score: Priority score (0-100, higher = more likely to be a profile)
            context: Surrounding HTML context
        """
        self.url = url
        self.text = text
        self.score = score
        self.context = context

    def __repr__(self):
        return f"ProfileLink(url={self.url[:50]}, text={self.text[:30]}, score={self.score})"


class LinkExtractor:
    """
    Intelligent link extraction for profile pages.

    Analyzes directory listings to find links to individual profiles.
    Scores and prioritizes links based on multiple signals.
    """

    # URL pattern scores (higher = more likely to be a profile)
    URL_PATTERNS = {
        r'/profile/[^/]+$': 90,
        r'/profiles/[^/]+$': 90,
        r'/bio/[^/]+$': 85,
        r'/bios/[^/]+$': 85,
        r'/faculty/[^/]+/[^/]+$': 80,  # /faculty/john-doe
        r'/staff/[^/]+/[^/]+$': 80,  # /staff/jane-smith
        r'/people/[^/]+/[^/]+$': 75,  # /people/john-doe
        r'/directory/[^/]+$': 70,     # Multi-Tier Phase 5.1: /directory/person-name
        r'/directory\?.*person': 65,  # Multi-Tier Phase 5.1: /directory?id=123&person=true
        r'/team/[^/]+$': 70,
        r'\?id=\d+': 50,              # Multi-Tier Phase 5.1: Query parameters with ID (common for CMS)
        r'/\d+$': -20,                # Numeric IDs less reliable
    }

    # Exclude patterns (should NOT follow these links)
    EXCLUDE_PATTERNS = [
        r'/student',
        r'/admissions',
        r'/apply',
        r'/events',
        r'/news',
        r'/blog',
        r'/publications',
        r'/press',
        r'/calendar',
        r'/courses',
        r'/programs',
        r'\.pdf$',
        r'\.doc$',
        r'\.jpg$',
        r'\.png$',
        r'mailto:',
        r'^#',  # Anchor links
        r'javascript:',
    ]

    # Social media domains to exclude
    SOCIAL_MEDIA_DOMAINS = [
        'linkedin.com', 'twitter.com', 'facebook.com', 'instagram.com',
        'youtube.com', 'vimeo.com', 'researchgate.net', 'academia.edu'
    ]

    def __init__(self, max_links_per_page: int = 30, min_score: int = 40):
        """
        Initialize link extractor.

        Args:
            max_links_per_page: Maximum profile links to extract per directory page
            min_score: Minimum score threshold (0-100) for including a link
        """
        self.max_links = max_links_per_page
        self.min_score = min_score
        self.stats = {
            'pages_processed': 0,
            'total_links_found': 0,
            'links_filtered': 0
        }

    def extract_profile_links(self, directory_url: str, html: str) -> List[ProfileLink]:
        """
        Extract profile/bio links from a directory page.

        Args:
            directory_url: URL of the directory page (for resolving relative links)
            html: HTML content of directory page

        Returns:
            List of ProfileLink objects, sorted by score (highest first)
        """
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        links = []
        seen_urls = set()

        # Find all links
        all_links = soup.find_all('a', href=True)
        logger.debug(f"Found {len(all_links)} total links on directory page")

        for link in all_links:
            href = link.get('href', '').strip()
            text = link.get_text().strip()

            # Skip empty or anchor links
            if not href or href.startswith('#'):
                continue

            # Resolve relative URLs
            full_url = urljoin(directory_url, href)

            # Skip duplicates
            if full_url in seen_urls:
                continue

            # Check if this looks like a profile link
            score = self._score_profile_link(full_url, text, link)

            # Filter by score
            if score >= self.min_score:
                # Get surrounding context
                context = self._get_link_context(link)

                profile_link = ProfileLink(
                    url=full_url,
                    text=text,
                    score=score,
                    context=context
                )
                links.append(profile_link)
                seen_urls.add(full_url)

        # Sort by score (highest first)
        links.sort(key=lambda x: x.score, reverse=True)

        # Limit to max_links
        links = links[:self.max_links]

        # Update stats
        self.stats['pages_processed'] += 1
        self.stats['total_links_found'] += len(seen_urls)
        self.stats['links_filtered'] += len(links)

        logger.info(f"Extracted {len(links)} profile links from directory page (from {len(all_links)} total links)")

        return links

    def _score_profile_link(self, url: str, text: str, link_element) -> int:
        """
        Score a link based on how likely it is to be a profile page.

        Args:
            url: Full URL
            text: Link anchor text
            link_element: BeautifulSoup link element

        Returns:
            Score 0-100 (higher = more likely to be profile)
        """
        score = 0

        # 1. URL pattern analysis
        url_lower = url.lower()

        # Check exclude patterns first
        for pattern in self.EXCLUDE_PATTERNS:
            if re.search(pattern, url_lower):
                return 0  # Excluded

        # Check social media
        parsed = urlparse(url)
        if any(domain in parsed.netloc.lower() for domain in self.SOCIAL_MEDIA_DOMAINS):
            return 0  # Excluded

        # Check profile URL patterns
        for pattern, pattern_score in self.URL_PATTERNS.items():
            if re.search(pattern, url_lower):
                score += pattern_score
                break

        # 2. Anchor text analysis
        if text:
            # Name-like text (2-4 words, capitalized)
            words = text.split()
            if 2 <= len(words) <= 4:
                # Check if words are capitalized (likely a name)
                if all(w[0].isupper() for w in words if w and len(w) > 1):
                    score += 40
                elif any(w[0].isupper() for w in words):
                    score += 20

            # Contains job title keywords (less reliable, but can help)
            title_keywords = ['director', 'dean', 'professor', 'librarian', 'administrator']
            if any(keyword in text.lower() for keyword in title_keywords):
                score += 10

            # "View profile", "Read bio", etc.
            action_phrases = ['view profile', 'read bio', 'learn more', 'see bio']
            if any(phrase in text.lower() for phrase in action_phrases):
                score += 15

        # 3. HTML structure/context analysis
        parent = link_element.parent
        if parent:
            parent_classes = parent.get('class', [])
            parent_class_str = ' '.join(parent_classes).lower()

            # Check parent element classes
            profile_indicators = ['profile', 'person', 'faculty', 'staff', 'bio', 'member', 'card']
            if any(indicator in parent_class_str for indicator in profile_indicators):
                score += 25

            # Check if link is inside a repeating structure (directory listing)
            # Look for multiple siblings with same class
            siblings = parent.find_parent(['div', 'ul', 'section'])
            if siblings:
                similar_siblings = siblings.find_all(parent.name, class_=parent.get('class'))
                if len(similar_siblings) >= 3:  # Part of a list
                    score += 15

        # 4. Image proximity (profiles often have headshot + link)
        prev_sibling = link_element.find_previous_sibling(['img', 'picture'])
        if prev_sibling:
            score += 10

        return min(score, 100)  # Cap at 100

    def _get_link_context(self, link_element) -> str:
        """Extract surrounding context for a link (for debugging)."""
        parent = link_element.parent
        if parent:
            # Get parent's text (up to 200 chars)
            context = parent.get_text().strip()[:200]
            return context
        return ''

    def filter_by_domain(self, links: List[ProfileLink], base_domain: str) -> List[ProfileLink]:
        """
        Filter links to only include same-domain links.

        Args:
            links: List of ProfileLink objects
            base_domain: Base domain to match (e.g., 'law.stanford.edu')

        Returns:
            Filtered list of ProfileLink objects
        """
        base_parsed = urlparse(f"https://{base_domain}")
        base_netloc = base_parsed.netloc.lower()

        filtered = []
        for link in links:
            parsed = urlparse(link.url)
            link_netloc = parsed.netloc.lower()

            # Allow exact match or subdomain
            if link_netloc == base_netloc or link_netloc.endswith(f'.{base_netloc}'):
                filtered.append(link)

        logger.debug(f"Filtered links to same domain: {len(links)} → {len(filtered)}")
        return filtered

    def deduplicate_links(self, links: List[ProfileLink]) -> List[ProfileLink]:
        """
        Remove duplicate links (same URL with different anchors).

        Args:
            links: List of ProfileLink objects

        Returns:
            Deduplicated list
        """
        seen = {}
        for link in links:
            # Normalize URL (remove fragment)
            url_normalized = link.url.split('#')[0]

            # Keep highest scoring version
            if url_normalized not in seen or link.score > seen[url_normalized].score:
                seen[url_normalized] = link

        deduped = list(seen.values())
        deduped.sort(key=lambda x: x.score, reverse=True)

        logger.debug(f"Deduplicated links: {len(links)} → {len(deduped)}")
        return deduped

    def get_stats(self) -> Dict:
        """Get extraction statistics."""
        avg_links = 0
        if self.stats['pages_processed'] > 0:
            avg_links = self.stats['links_filtered'] / self.stats['pages_processed']

        return {
            'pages_processed': self.stats['pages_processed'],
            'total_links_found': self.stats['total_links_found'],
            'links_filtered': self.stats['links_filtered'],
            'avg_links_per_page': round(avg_links, 1)
        }


# Singleton instance
_link_extractor = None


def get_link_extractor(max_links: int = 30, min_score: int = 40) -> LinkExtractor:
    """
    Get or create singleton LinkExtractor instance.

    Args:
        max_links: Maximum links to extract per page
        min_score: Minimum score threshold

    Returns:
        LinkExtractor instance
    """
    global _link_extractor
    if _link_extractor is None:
        _link_extractor = LinkExtractor(max_links_per_page=max_links, min_score=min_score)
    return _link_extractor
