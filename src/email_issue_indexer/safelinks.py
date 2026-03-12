"""Clean Microsoft SafeLinks URLs back to original URLs."""
import re
from urllib.parse import urlparse, parse_qs, unquote


SAFELINKS_PATTERN = re.compile(
    r'https?://[\w.]*safelinks\.protection\.outlook\.com/\?[^\s>)\]]*'
)

MAILTO_INLINE = re.compile(r'<mailto:([^>]+)>')


def clean_safelink(url: str) -> str:
    """Extract original URL from a SafeLinks wrapper."""
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "url" in params:
            return unquote(params["url"][0])
    except Exception:
        pass
    return url


def clean_text(text: str) -> str:
    """Clean all SafeLinks URLs and mailto artifacts in text."""
    # Replace safelinks with original URLs
    text = SAFELINKS_PATTERN.sub(lambda m: clean_safelink(m.group(0)), text)
    # Clean inline mailto: references like +@Name<mailto:addr>
    text = MAILTO_INLINE.sub(r'(\1)', text)
    return text
