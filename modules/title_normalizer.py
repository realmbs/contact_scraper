"""
Title Normalization Module

Provides intelligent title preprocessing and normalization for improved matching.
Focuses on data quality by:
- Extracting modifiers (Interim, Acting, Senior, etc.)
- Expanding abbreviations
- Filtering exclusions (student, emeritus, etc.)
- Preserving metadata for confidence adjustments

Author: Claude Code
Date: 2025-12-24
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


# ============================================================================
# Abbreviation Mappings
# ============================================================================

ABBREVIATION_MAP = {
    # Titles
    r'\bdir\.?\b': 'Director',
    r'\bassoc\.?\b': 'Associate',
    r'\basst\.?\b': 'Assistant',
    r'\bdept\.?\b': 'Department',
    r'\bcoord\.?\b': 'Coordinator',
    r'\bprog\.?\b': 'Program',
    r'\bmgr\.?\b': 'Manager',
    r'\badmin\.?\b': 'Administrator',
    r'\blibn\.?\b': 'Librarian',

    # Academic
    r'\bprof\.?\b': 'Professor',
    r'\badj\.?\b': 'Adjunct',
    r'\bsr\.?\b': 'Senior',
    r'\bjr\.?\b': 'Junior',

    # Departments
    r'\binfo\.?\b': 'Information',
    r'\btech\.?\b': 'Technology',
    r'\bacad\.?\b': 'Academic',
    r'\bstud\.?\b': 'Student',
    r'\bsvcs\.?\b': 'Services',
}


# ============================================================================
# Modifier Patterns
# ============================================================================

# Temporary/Interim modifiers (reduce confidence)
TEMPORARY_MODIFIERS = [
    'interim', 'acting', 'temporary', 'temp', 'provisional',
    'ad interim', 'pro tem', 'pro tempore'
]

# Seniority modifiers (preserve but don't penalize)
SENIORITY_MODIFIERS = [
    'senior', 'sr', 'junior', 'jr', 'chief', 'lead', 'principal'
]

# Co-leadership modifiers (positive signal)
# Note: These are special - they replace the base role, not just modify it
SHARED_ROLE_PREFIXES = [
    'co-director', 'co-chair', 'co-coordinator',
    'co director', 'co chair', 'co coordinator',  # Space variants
    'joint'
]

# Emeritus/Retired (exclusion)
EMERITUS_PATTERNS = [
    'emeritus', 'emerita', 'retired', 'former', 'ex-'
]

# Student roles (exclusion)
STUDENT_PATTERNS = [
    r'\bstudent\s+(?:director|coordinator|assistant)',
    r'graduate\s+assistant',
    r'student\s+worker',
    r'work[\s-]?study'
]

# Visiting/Temporary affiliations (exclusion)
VISITING_PATTERNS = [
    'visiting', 'adjunct', 'affiliate', 'courtesy', 'lecturer'
]

# Assistant-to roles (exclusion - these are support staff, not decision-makers)
ASSISTANT_TO_PATTERNS = [
    r'assistant\s+to\s+the',
    r'aide\s+to',
    r'executive\s+assistant\s+to'
]


# ============================================================================
# Normalization Result Dataclass
# ============================================================================

@dataclass
class NormalizedTitle:
    """
    Result of title normalization process.

    Attributes:
        original: Original raw title
        normalized: Cleaned and normalized title
        modifiers: List of extracted modifiers (interim, acting, senior, etc.)
        is_temporary: True if interim/acting role
        is_student: True if student position
        is_emeritus: True if retired/emeritus
        is_visiting: True if visiting/adjunct
        is_support_staff: True if assistant-to role
        is_shared_role: True if co-director/joint role
        should_exclude: True if title should be excluded from matching
        abbreviations_expanded: List of abbreviations that were expanded
        confidence_modifier: Adjustment to confidence score (-10 to +5)
    """
    original: str
    normalized: str
    modifiers: List[str]
    is_temporary: bool = False
    is_student: bool = False
    is_emeritus: bool = False
    is_visiting: bool = False
    is_support_staff: bool = False
    is_shared_role: bool = False
    should_exclude: bool = False
    abbreviations_expanded: List[str] = None
    confidence_modifier: int = 0

    def __post_init__(self):
        if self.abbreviations_expanded is None:
            self.abbreviations_expanded = []


# ============================================================================
# Core Normalization Functions
# ============================================================================

def expand_abbreviations(title: str) -> Tuple[str, List[str]]:
    """
    Expand common title abbreviations.

    Args:
        title: Raw title string

    Returns:
        Tuple of (expanded_title, list_of_expansions)

    Examples:
        "Dir. of Legal Writing" → "Director of Legal Writing", ["Dir."]
        "Assoc. Dean" → "Associate Dean", ["Assoc."]
    """
    expanded = title
    expansions = []

    for abbrev_pattern, full_form in ABBREVIATION_MAP.items():
        if re.search(abbrev_pattern, expanded, re.IGNORECASE):
            # Track what was expanded
            match = re.search(abbrev_pattern, expanded, re.IGNORECASE)
            if match:
                expansions.append(match.group(0))

            # Replace abbreviation
            expanded = re.sub(abbrev_pattern, full_form, expanded, flags=re.IGNORECASE)

    # Clean up any double periods or spaces
    expanded = re.sub(r'\.\.+', '.', expanded)  # Multiple periods → single period
    expanded = re.sub(r'\s+\.', '.', expanded)  # Space before period → just period
    expanded = re.sub(r'\.\s+of', ' of', expanded)  # "Director. of" → "Director of"

    return expanded, expansions


def extract_modifiers(title: str) -> Tuple[str, List[str]]:
    """
    Extract and remove modifiers from title while preserving core role.

    Args:
        title: Title string (ideally after abbreviation expansion)

    Returns:
        Tuple of (title_without_modifiers, list_of_modifiers)

    Examples:
        "Interim Library Director" → "Library Director", ["Interim"]
        "Senior Associate Dean" → "Associate Dean", ["Senior"]
        "Co-Director of Programs" → "Co-Director of Programs", []  # Co-Director is the role itself
    """
    modifiers = []
    clean_title = title

    # Check for co-director/co-chair roles (DON'T remove these - they are the role itself)
    has_shared_role_prefix = any(
        re.search(rf'\b{re.escape(prefix)}\b', clean_title, re.IGNORECASE)
        for prefix in SHARED_ROLE_PREFIXES
    )

    # Extract removable modifiers (temporary and seniority)
    removable_modifiers = TEMPORARY_MODIFIERS + SENIORITY_MODIFIERS

    for modifier in removable_modifiers:
        pattern = rf'\b{re.escape(modifier)}\b'
        if re.search(pattern, clean_title, re.IGNORECASE):
            match = re.search(pattern, clean_title, re.IGNORECASE)
            if match:
                modifiers.append(match.group(0))
                clean_title = re.sub(pattern, '', clean_title, flags=re.IGNORECASE)

    # Clean up extra whitespace
    clean_title = re.sub(r'\s+', ' ', clean_title).strip()

    return clean_title, modifiers


def strip_qualifiers(title: str) -> str:
    """
    Remove parenthetical and suffix qualifiers.

    Args:
        title: Title string

    Returns:
        Title without qualifiers

    Examples:
        "Director (Adjunct)" → "Director"
        "Library Director - Law School" → "Library Director"
        "Dean, J.D. Program" → "Dean"
        "Co-Director of Programs" → "Co-Director of Programs"  # Preserve compound words
    """
    # Remove parenthetical content
    title = re.sub(r'\([^)]*\)', '', title)

    # Remove dash/hyphen suffixes ONLY if preceded by whitespace
    # This preserves compound words like "Co-Director" while removing " - Law School"
    title = re.sub(r'\s+[-–—]\s*.*$', '', title)

    # Remove comma suffixes (but preserve "Dean, Academic Affairs" structure)
    # Only remove if comma is followed by non-role words
    non_role_suffixes = r',\s+(J\.D\.|LL\.M\.|Ph\.D\.|Esq\.|Law School|School of Law)'
    title = re.sub(non_role_suffixes, '', title, flags=re.IGNORECASE)

    # Clean up extra whitespace
    title = re.sub(r'\s+', ' ', title).strip()

    return title


def check_exclusions(title: str) -> Dict[str, bool]:
    """
    Check if title matches exclusion patterns.

    Args:
        title: Title string (lowercase recommended)

    Returns:
        Dictionary with exclusion flags:
        {
            'is_emeritus': bool,
            'is_student': bool,
            'is_visiting': bool,
            'is_support_staff': bool
        }
    """
    title_lower = title.lower()

    # Remove parenthetical qualifiers for exclusion checking
    # (Adjunct), (Part-time) etc. shouldn't trigger exclusion if the core role is legitimate
    title_for_exclusion = re.sub(r'\([^)]*\)', '', title_lower).strip()

    # Check emeritus
    is_emeritus = any(pattern in title_for_exclusion for pattern in EMERITUS_PATTERNS)

    # Check student roles
    is_student = any(re.search(pattern, title_for_exclusion) for pattern in STUDENT_PATTERNS)

    # Check visiting/adjunct (only if NOT in parentheses)
    is_visiting = any(pattern in title_for_exclusion for pattern in VISITING_PATTERNS)

    # Check assistant-to roles
    is_support_staff = any(re.search(pattern, title_for_exclusion) for pattern in ASSISTANT_TO_PATTERNS)

    return {
        'is_emeritus': is_emeritus,
        'is_student': is_student,
        'is_visiting': is_visiting,
        'is_support_staff': is_support_staff
    }


def calculate_confidence_modifier(normalized_title: NormalizedTitle) -> int:
    """
    Calculate confidence score adjustment based on title characteristics.

    Args:
        normalized_title: NormalizedTitle object

    Returns:
        Integer adjustment to confidence score (-10 to +5)

    Logic:
        Penalties:
        - Temporary role (interim/acting): -3 points
        - Abbreviated title: -2 points
        - Visiting/adjunct: -3 points

        Bonuses:
        - Shared role (co-director): +2 points
        - No abbreviations (clean data): +1 point
    """
    modifier = 0

    # Penalties
    if normalized_title.is_temporary:
        modifier -= 3  # Temporary appointments less reliable

    if normalized_title.abbreviations_expanded:
        modifier -= 2  # Abbreviated titles less certain

    if normalized_title.is_visiting:
        modifier -= 3  # Visiting roles may not be target audience

    # Bonuses
    if normalized_title.is_shared_role:
        modifier += 2  # Co-directors are high-value contacts

    if not normalized_title.abbreviations_expanded:
        modifier += 1  # Clean, unabbreviated data more reliable

    return modifier


def normalize_title(title: str) -> NormalizedTitle:
    """
    Main normalization pipeline - orchestrates all preprocessing steps.

    Args:
        title: Raw title string from extraction

    Returns:
        NormalizedTitle object with all metadata

    Example:
        Input: "Interim Dir. of Library Services (Adjunct)"
        Output: NormalizedTitle(
            original="Interim Dir. of Library Services (Adjunct)",
            normalized="Director of Library Services",
            modifiers=["Interim"],
            is_temporary=True,
            abbreviations_expanded=["Dir."],
            confidence_modifier=-5  # -3 for interim, -2 for abbreviation
        )
    """
    if not title or not isinstance(title, str):
        return NormalizedTitle(
            original=title or "",
            normalized="",
            modifiers=[],
            should_exclude=True
        )

    original = title.strip()

    # Step 1: Expand abbreviations
    expanded, abbreviations = expand_abbreviations(original)

    # Step 2: Strip qualifiers (parenthetical, suffixes)
    cleaned = strip_qualifiers(expanded)

    # Step 3: Extract modifiers
    normalized, modifiers = extract_modifiers(cleaned)

    # Step 4: Check exclusion patterns
    exclusions = check_exclusions(original)

    # Step 5: Determine flags
    is_temporary = any(mod.lower() in TEMPORARY_MODIFIERS for mod in modifiers)
    # Check if the normalized title contains co-director/co-chair patterns
    is_shared_role = any(
        re.search(rf'\b{re.escape(prefix)}\b', normalized, re.IGNORECASE)
        for prefix in SHARED_ROLE_PREFIXES
    )

    # Should exclude if any exclusion flag is True
    should_exclude = any(exclusions.values())

    # Step 6: Create normalized title object
    normalized_title = NormalizedTitle(
        original=original,
        normalized=normalized.strip(),
        modifiers=modifiers,
        is_temporary=is_temporary,
        is_student=exclusions['is_student'],
        is_emeritus=exclusions['is_emeritus'],
        is_visiting=exclusions['is_visiting'],
        is_support_staff=exclusions['is_support_staff'],
        is_shared_role=is_shared_role,
        should_exclude=should_exclude,
        abbreviations_expanded=abbreviations
    )

    # Step 7: Calculate confidence modifier
    normalized_title.confidence_modifier = calculate_confidence_modifier(normalized_title)

    return normalized_title


# ============================================================================
# Batch Processing
# ============================================================================

def normalize_titles_batch(titles: List[str]) -> List[NormalizedTitle]:
    """
    Normalize multiple titles in batch.

    Args:
        titles: List of raw title strings

    Returns:
        List of NormalizedTitle objects
    """
    return [normalize_title(title) for title in titles]


# ============================================================================
# Utility Functions
# ============================================================================

def should_exclude_title(title: str) -> bool:
    """
    Quick check if title should be excluded (without full normalization).

    Args:
        title: Raw title string

    Returns:
        True if title should be excluded, False otherwise

    Usage:
        Use this for fast pre-filtering before expensive normalization.
    """
    exclusions = check_exclusions(title)
    return any(exclusions.values())


def get_title_summary(normalized_title: NormalizedTitle) -> str:
    """
    Get human-readable summary of normalization result.

    Args:
        normalized_title: NormalizedTitle object

    Returns:
        Formatted summary string
    """
    summary_parts = [
        f"Original: {normalized_title.original}",
        f"Normalized: {normalized_title.normalized}",
    ]

    if normalized_title.modifiers:
        summary_parts.append(f"Modifiers: {', '.join(normalized_title.modifiers)}")

    if normalized_title.abbreviations_expanded:
        summary_parts.append(f"Abbreviations: {', '.join(normalized_title.abbreviations_expanded)}")

    flags = []
    if normalized_title.is_temporary:
        flags.append("Temporary")
    if normalized_title.is_student:
        flags.append("Student")
    if normalized_title.is_emeritus:
        flags.append("Emeritus")
    if normalized_title.is_visiting:
        flags.append("Visiting")
    if normalized_title.is_shared_role:
        flags.append("Shared Role")

    if flags:
        summary_parts.append(f"Flags: {', '.join(flags)}")

    summary_parts.append(f"Confidence Modifier: {normalized_title.confidence_modifier:+d}")
    summary_parts.append(f"Should Exclude: {normalized_title.should_exclude}")

    return " | ".join(summary_parts)
