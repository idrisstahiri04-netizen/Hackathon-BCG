"""Date parsing. Only explicit dates are returned; otherwise None."""
import re
from datetime import datetime
from email.utils import parsedate_to_datetime

MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
MON3 = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"

_PATTERNS = [
    # 22nd October 2024 / 22 October, 2024
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({MONTHS}|{MON3})\.?,?\s+(20\d\d)\b", re.I), "dmy"),
    # October 22, 2024 / October 22nd 2024
    (re.compile(rf"\b({MONTHS}|{MON3})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", re.I), "mdy"),
    # 22.11.2024 / 22/11/2024 (Kenya uses day-first)
    (re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](20\d\d)\b"), "dmy_num"),
]


def _month(s: str) -> int:
    s = s.lower()[:3]
    return [m[:3] for m in MONTHS.split("|")].index(s) + 1


def find_date_in_text(text: str, max_chars: int = 2500) -> str | None:
    """First explicit calendar date in the opening part of a document (ISO date) or None."""
    head = (text or "")[:max_chars]
    best = None
    for rx, kind in _PATTERNS:
        m = rx.search(head)
        if not m:
            continue
        try:
            if kind == "dmy":
                d = datetime(int(m.group(3)), _month(m.group(2)), int(m.group(1)))
            elif kind == "mdy":
                d = datetime(int(m.group(3)), _month(m.group(1)), int(m.group(2)))
            else:
                d = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        if d.date() > datetime.now().date():
            continue  # a future date is an event/deadline date, not the publication date
        if best is None or m.start() < best[0]:
            best = (m.start(), d.date().isoformat())
    return best[1] if best else None


def rfc822_to_iso(s: str) -> str | None:
    try:
        return parsedate_to_datetime(s).isoformat()
    except (TypeError, ValueError):
        return None


def wp_local_to_iso(s: str | None) -> str | None:
    """WordPress `date` is site-local time; all four sites are Africa/Nairobi (UTC+3)."""
    if not s:
        return None
    return s + "+03:00" if re.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$", s) else s


def drupal_created_to_iso(s: str) -> str | None:
    """'Tue, 09/22/2026 - 23:08' (GAA, US month/day order) -> ISO, Nairobi time."""
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})\s*-\s*(\d{2}):(\d{2})", s or "")
    if not m:
        return None
    mo, d, y, hh, mm = map(int, m.groups())
    try:
        return datetime(y, mo, d, hh, mm).isoformat() + "+03:00"
    except ValueError:
        return None


def upload_month_hint(url: str) -> str | None:
    """'/wp-content/uploads/2024/11/x.pdf' or '/files/2026-10/x.pdf' -> '2024-11' (upload month, NOT publication date)."""
    m = re.search(r"/(20\d\d)[/-](\d\d)/", url)
    return f"{m.group(1)}-{m.group(2)}" if m else None
