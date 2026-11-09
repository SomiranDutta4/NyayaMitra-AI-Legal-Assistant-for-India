"""Layer 1 of the auditor: deterministic checks, plain Python, same input -> same verdict.

1. Citation check   - every cited doc_id must be in the retrieved evidence; legal statements must cite.
2. Section check    - every "Section/Article/Rule N" mentioned must exist in the evidence.
3. Act check        - every statute named must be one present in the evidence (catches IPC vs BNS,
                      Consumer Protection Act 1986 vs 2019, etc.).
4. Number check     - every amount / time period / percentage in a statement must appear in the
                      provisions it cites, in the user's own facts, or in system-computed facts.
"""

import re
from typing import Dict, Iterable, List, Set, Tuple

# ---------------------------------------------------------------- numbers
_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
_NUMWORD = "(?:" + "|".join(list(_UNITS) + list(_TENS) + ["hundred"]) + ")"
_WORDNUM = re.compile(rf"\b{_NUMWORD}(?:[\s-]+(?:and[\s-]+)?{_NUMWORD})*\b", re.I)
_ORD = {"first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th", "fifth": "5th", "sixth": "6th",
        "seventh": "7th", "eighth": "8th", "ninth": "9th", "tenth": "10th", "fifteenth": "15th", "thirtieth": "30th"}
_ORD_RE = re.compile(r"\b(" + "|".join(_ORD) + r")\b", re.I)


def words_to_digits(text: str) -> str:
    text = _ORD_RE.sub(lambda m: _ORD[m.group(1).lower()], text)

    def parse(m):
        cur = 0
        for w in re.split(r"[\s-]+", m.group(0).lower()):
            if w in _UNITS:
                cur += _UNITS[w]
            elif w in _TENS:
                cur += _TENS[w]
            elif w == "hundred":
                cur = (cur or 1) * 100
        return str(cur)
    return _WORDNUM.sub(parse, text)


_SCALE = {"thousand": 1e3, "lakh": 1e5, "lakhs": 1e5, "crore": 1e7, "crores": 1e7}
_NUM = r"(\d[\d,]*(?:\.\d+)?)"
_AMT = re.compile(
    rf"(?:₹|\brs\.?|\binr)\s*{_NUM}\s*(thousand|lakhs?|crores?)?"
    rf"|{_NUM}\s*(lakhs?|crores?)\b"
    rf"|{_NUM}\s*(thousand)?\s*rupees", re.I)
_DUR = re.compile(rf"{_NUM}[\s-]*(?:working[\s-]+|calendar[\s-]+|clear[\s-]+)?(hours?|days?|weeks?|months?|years?)\b", re.I)
_PCT = re.compile(rf"{_NUM}\s*(?:%|per\s*cent|percent)", re.I)
_NTH = re.compile(r"\b(\d+)(?:st|nd|rd|th)\s+day\b", re.I)
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def _f(s: str) -> float:
    return float(s.replace(",", ""))


def extract_numbers(text: str) -> Set[Tuple[str, float]]:
    """Normalised numeric facts, e.g. {('inr', 5000000.0), ('month', 24.0), ('day', 30.0)}."""
    t = words_to_digits((text or "").translate(_DEVANAGARI_DIGITS))
    out: Set[Tuple[str, float]] = set()
    for m in _AMT.finditer(t):
        if m.group(1):
            n, sc = m.group(1), m.group(2)
        elif m.group(3):
            n, sc = m.group(3), m.group(4)
        else:
            n, sc = m.group(5), m.group(6)
        try:
            out.add(("inr", _f(n) * _SCALE.get((sc or "").lower(), 1)))
        except ValueError:
            pass
    for m in _DUR.finditer(t):
        n, u = _f(m.group(1)), m.group(2).lower().rstrip("s")
        if u == "year":
            out.add(("month", n * 12))
        elif u == "week":
            out.add(("day", n * 7))
        else:
            out.add((u, n))
    for m in _PCT.finditer(t):
        out.add(("pct", _f(m.group(1))))
    for m in _NTH.finditer(t):
        out.add(("nth_day", float(m.group(1))))
    return out


def fmt_number(k: Tuple[str, float]) -> str:
    unit, n = k
    n_s = str(int(n)) if float(n).is_integer() else str(n)
    return {"inr": f"₹{n_s}", "pct": f"{n_s}%", "nth_day": f"{n_s}th day"}.get(unit, f"{n_s} {unit}(s)")


# ---------------------------------------------------------------- sections
_SEC_RE = re.compile(
    r"\b(?:Sections?|Secs?\.?|S\.|Articles?|Arts?\.|Rules?|Order)\s+"
    r"((?:\d+[A-Z]{0,2}(?:\(\d+[a-z]?\))*(?:\s*(?:,|and|to|or|&|/)\s*)?)+)", re.I)
_SEC_TOKEN = re.compile(r"(\d+)([A-Z]{0,2})")


def _section_tokens(text: str, expand_ranges: bool = False) -> Set[str]:
    toks: Set[str] = set()
    for m in _SEC_RE.finditer(text or ""):
        chunk = m.group(1)
        # drop sub-section brackets for matching: 2(11) -> base 2 and full 2(11)
        found = [(int(a), b.upper()) for a, b in _SEC_TOKEN.findall(re.sub(r"\(\d+[a-z]?\)", " ", chunk))]
        for n, suf in found:
            toks.add(f"{n}{suf}")
        for full in re.findall(r"\d+[A-Z]{0,2}\(\d+[a-z]?\)", chunk):
            toks.add(full.upper())
        if expand_ranges:
            for a, b in re.findall(r"(\d+)\s*to\s*(\d+)", chunk):
                for k in range(int(a), int(b) + 1):
                    toks.add(str(k))
    return toks


# ---------------------------------------------------------------- acts
ACT_ALIASES = [
    ("IPC", r"\bIPC\b|Indian Penal Code"),
    ("CRPC", r"\bCr\.?\s?P\.?\s?C\b|Code of Criminal Procedure"),
    ("BNS", r"\bBNS\b(?!S)|Bharatiya Nyaya Sanhita"),
    ("BNSS", r"\bBNSS\b|Bharatiya Nagarik Suraksha Sanhita"),
    ("BSA", r"Bharatiya Sakshya"),
    ("EVIDENCE", r"Evidence Act"),
    ("CPA1986", r"Consumer Protection Act,?\s*1986"),
    ("CPA2019", r"Consumer Protection Act(?!,?\s*1986)"),
    ("TPA", r"Transfer of Property Act"),
    ("MTA", r"Model Tenancy Act"),
    ("RENT_CONTROL", r"Rent Control Act"),
    ("SRA", r"Specific Relief Act"),
    ("LIMITATION", r"Limitation Act"),
    ("RERA", r"\bRERA\b|Real Estate \(Regulation"),
    ("COW", r"Code on Wages"),
    ("PWA", r"Payment of Wages Act"),
    ("GRATUITY", r"Gratuity Act"),
    ("IRC", r"Industrial Relations Code"),
    ("IDA", r"Industrial Disputes Act"),
    ("SSC", r"Code on Social Security"),
    ("MWA", r"Minimum Wages Act"),
    ("SHOPS", r"Shops? (?:and|&) Establishments?"),
    ("ICA", r"Indian Contract Act|\bContract Act\b"),
    ("ARBITRATION", r"Arbitration (?:and Conciliation )?Act"),
    ("NIA", r"Negotiable Instruments Act|\bNI Act\b"),
    ("ITA", r"Information Technology Act|\bIT Act\b"),
    ("HMA", r"Hindu Marriage Act"),
    ("SMA", r"Special Marriage Act"),
    ("PWDVA", r"Domestic Violence Act|\bPWDVA\b|\bDV Act\b"),
    ("FCA", r"Family Courts Act"),
    ("LSAA", r"Legal Services Authorities Act"),
    ("DOWRY", r"Dowry Prohibition Act"),
    ("HMGA", r"Hindu Minority and Guardianship Act"),
    ("GWA", r"Guardians and Wards Act"),
]
_ACT_RE = [(k, re.compile(p, re.I)) for k, p in ACT_ALIASES]


def act_keys(text: str) -> Set[str]:
    return {k for k, rx in _ACT_RE if rx.search(text or "")}


# ---------------------------------------------------------------- the check
CITED_KINDS = {"legal_position", "option", "deadline"}


def run_deterministic_checks(items: List[Dict], evidence: Dict[str, Dict], facts_text: str,
                             computed_text: str) -> List[Dict]:
    """items: [{'id','kind','text','cites'}]; evidence: {doc_id: {'act','section','text'}}.
    Returns a list of issues; empty list == pass."""
    issues: List[Dict] = []
    ev_text = {i: f"{d['section']} {d['act']}. {d['text']}" for i, d in evidence.items()}
    all_ev = " ".join(ev_text.values())
    allowed_sections = _section_tokens(all_ev, expand_ranges=True)
    allowed_acts = act_keys(all_ev)
    user_nums = extract_numbers(facts_text) | extract_numbers(computed_text)
    all_ev_nums = extract_numbers(all_ev)
    # A section/Act the USER named may be repeated in the summary or assumptions (e.g. "we could not
    # verify the 'Section 420B' you mentioned"), but never inside a cited legal statement.
    user_sections = _section_tokens(facts_text)
    user_acts = act_keys(facts_text)

    for it in items:
        text, kind, cites = it.get("text", ""), it.get("kind"), it.get("cites") or []

        if kind in CITED_KINDS:
            if not cites:
                issues.append({"item": it["id"], "check": "citation",
                               "detail": "Legal statement has no citation; cite a provided doc_id or remove it."})
            bad = [c for c in cites if c not in evidence]
            if bad:
                issues.append({"item": it["id"], "check": "citation",
                               "detail": f"Cites doc_id(s) not in the evidence: {bad}."})

        echo_ok = kind in ("summary", "assumption")
        ok_sections = allowed_sections | (user_sections if echo_ok else set())
        mentioned = _section_tokens(text)
        unknown = sorted(t for t in mentioned if t not in ok_sections and re.sub(r"\(.*", "", t) not in ok_sections)
        if unknown:
            issues.append({"item": it["id"], "check": "section",
                           "detail": f"Mentions section/article/rule {unknown} which is not in the evidence."})

        foreign = sorted(act_keys(text) - allowed_acts - (user_acts if echo_ok else set()))
        if foreign:
            issues.append({"item": it["id"], "check": "act",
                           "detail": f"Names a law not in the evidence ({', '.join(foreign)}). Use only the provided Acts."})

        if kind == "draft_document":
            continue
        if kind in CITED_KINDS:
            src = extract_numbers(" ".join(ev_text.get(c, "") for c in cites))
        elif kind in ("next_step", "assumption"):
            src = all_ev_nums
        else:  # summary: only the user's facts and computed facts
            src = set()
        extra = extract_numbers(text) - src - user_nums
        if extra:
            issues.append({"item": it["id"], "check": "number",
                           "detail": f"Number(s) {', '.join(fmt_number(x) for x in sorted(extra))} do not appear in the cited provisions or the user's facts."})
    return issues


def translation_preserves(english: str, translated: str) -> List[str]:
    """After translation, every digit-run and every [n] citation marker must survive."""
    en_digits = re.findall(r"\d+", re.sub(r"[,]", "", english))
    tr = re.sub(r"[,]", "", (translated or "").translate(_DEVANAGARI_DIGITS))
    tr_digits = set(re.findall(r"\d+", tr))
    missing = sorted({d for d in en_digits if d not in tr_digits}, key=len)
    return missing
