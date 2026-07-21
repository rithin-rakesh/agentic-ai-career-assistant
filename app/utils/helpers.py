import re
from datetime import datetime, timezone
from typing import Optional

def clean_text(text: Optional[str]) -> str:
    """
    Cleans raw HTML text by removing excessive whitespace, tabs, and newlines.
    """
    if not text:
        return ""
    cleaned = re.sub(r'\s+', ' ', text)
    return cleaned.strip()

def parse_date(date_str: Optional[str]) -> datetime:
    """
    Parses a date string into a timezone-aware datetime object.
    If the parsing fails or date is empty, returns the current UTC time.
    """
    if not date_str:
        return datetime.now(timezone.utc)
    
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%b %d, %Y",
        "%d %b %Y"
    ]
    
    for fmt in formats:
        try:
            parsed = datetime.strptime(date_str.strip(), fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            continue
            
    return datetime.now(timezone.utc)

def extract_experience(description: str) -> Optional[int]:
    """
    Extracts years of experience requirements from a job description.
    Uses regex patterns to identify experience ranges (e.g. '2-5 years')
    and single limits (e.g. '3+ years', '1 year').
    Returns the minimum required years of experience found, or None if not specified.
    """
    if not description:
        return None
        
    text = description.lower()
    
    # Standard terminology indicating zero experience requirement
    zero_experience_keywords = ["no experience", "entry level", "fresher", "no prior experience"]
    if any(keyword in text for keyword in zero_experience_keywords):
        return 0
        
    # 1. Match ranges e.g. "2 to 5 years", "2-5 years", "2 - 5 years", "2-5 yrs"
    range_pattern = r'(\d+)\s*(?:-|to)\s*(\d+)\s*(?:yrs?|years?)'
    ranges = re.findall(range_pattern, text)
    if ranges:
        # Return the lowest range minimum found
        return min(int(r[0]) for r in ranges)
        
    # 2. Match single limit mentions e.g. "3+ years", "3 years", "3 yrs", "at least 3 years"
    # Ensure we look for keywords in close proximity to numbers to avoid matching random figures
    single_pattern = r'(?:requires?|needs?|minimum|at least)?\s*(\d+)\+?\s*(?:yrs?|years?)\s*(?:of)?\s*(?:experience|exp)?'
    singles = re.findall(single_pattern, text)
    if singles:
        return min(int(s) for s in singles)
        
    return None
