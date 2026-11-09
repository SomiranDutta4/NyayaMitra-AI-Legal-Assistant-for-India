"""Deterministic legal arithmetic. Dates, money limits and which criminal code applies are
computed in Python, never left to the model."""

import re
from datetime import date
from typing import Any, Dict, Optional

BNS_START = date(2024, 7, 1)


def parse_date(value: Any) -> Optional[date]:
    """Accepts 'YYYY-MM-DD' or 'YYYY-MM' (day defaults to 1)."""
    if not value or not isinstance(value, str):
        return None
    m = re.match(r"^\s*(\d{4})-(\d{1,2})(?:-(\d{1,2}))?\s*$", value)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3) or 1))
    except ValueError:
        return None


def months_between(d: date, today: date) -> int:
    return (today.year - d.year) * 12 + (today.month - d.month) - (1 if today.day < d.day else 0)


def consumer_forum(amount_inr: float) -> str:
    if amount_inr <= 5_000_000:
        return "District Consumer Disputes Redressal Commission"
    if amount_inr <= 20_000_000:
        return "State Consumer Disputes Redressal Commission"
    return "National Consumer Disputes Redressal Commission"


def fmt_inr(x: float) -> str:
    """Indian digit grouping: 4500000 -> ₹45,00,000."""
    n = int(round(x))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", head)
        s = f"{head},{tail}"
    return f"₹{s}"


def compute_case_facts(domains, key_date: Optional[str], amount_inr: Optional[float],
                       today: Optional[date] = None) -> Dict[str, Any]:
    """Facts the drafter must use as given. Their numbers are whitelisted in the number check."""
    today = today or date.today()
    out: Dict[str, Any] = {"today": today.isoformat()}
    d = parse_date(key_date)
    if d:
        if d > today:
            out["date_warning"] = f"The date given ({d.isoformat()}) is in the future; it may be wrong."
        else:
            m = months_between(d, today)
            approx = len(key_date.strip()) <= 7  # only year-month was known
            shown = d.strftime("%B %Y") if approx else d.isoformat()
            out["key_date"] = shown + (" (month only, approximate)" if approx else "")
            out["time_elapsed"] = (f"about {m} months since {shown}" if m >= 1 else f"less than 1 month since {shown}")
            out["months_elapsed"] = m
        if "Criminal Law" in domains:
            out["criminal_code"] = (
                "Bharatiya Nyaya Sanhita, 2023 / Bharatiya Nagarik Suraksha Sanhita, 2023 (incident on or after 1 July 2024)"
                if d >= BNS_START else
                "Indian Penal Code, 1860 / Code of Criminal Procedure, 1973 (incident before 1 July 2024)"
            )
    if amount_inr:
        out["amount"] = fmt_inr(amount_inr)
        if "Consumer Law" in domains:
            out["consumer_forum"] = f"{consumer_forum(amount_inr)} (amount {fmt_inr(amount_inr)})"
    return out


def limitation_warning(domains, months_elapsed: Optional[int]) -> str:
    """Conservative flag only: e.g. a consumer complaint older than 2 years (Section 69 CPA)."""
    if months_elapsed is None:
        return ""
    if "Consumer Law" in domains and months_elapsed > 24:
        return "More than two years have passed, so the consumer complaint may be time-barred unless the delay is condoned; a lawyer should assess this."
    if months_elapsed > 36:
        return "More than three years have passed; civil claims may be time-barred. A lawyer should check limitation before you file."
    return ""
