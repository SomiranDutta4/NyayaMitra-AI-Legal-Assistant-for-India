"""Deterministic safety layer. Runs on every user message BEFORE any model call, so an
emergency never depends on an LLM classifying it correctly."""

import re
from typing import Dict, List

# category -> patterns (English, Hinglish, Hindi)
_PATTERNS: Dict[str, List[str]] = {
    "self_harm": [
        r"\bsuicid", r"\bkill myself\b", r"\bend my life\b", r"\bwant to die\b", r"\bkhudkushi\b",
        r"\bmar jaana chahta\b", r"\bmar jaana chahti\b", r"आत्महत्या", r"मर जाना चाहत",
    ],
    "danger": [
        r"\bin danger\b", r"\bkill me\b", r"\bkill us\b", r"\bgoing to kill\b", r"\bbeat(ing)? me\b",
        r"\bhit(ting)? me\b", r"\battack(ed|ing)? me\b", r"\bthreaten(ed|ing)? to (beat|kill|hurt)",
        r"\bunsafe\b", r"\bbachao\b", r"\bkhatra\b", r"\bjaan se maar", r"\bmaar (dalega|dalenge|denge|raha|rahe)",
        r"बचाओ", r"खतरा", r"जान से मार", r"मार डाल", r"मार रहा", r"मार रहे",
    ],
    "women": [
        r"\bdomestic violence\b", r"\bdowry\b", r"\bdahej\b", r"\bharass(ed|ment)\b.*\b(husband|in-?laws|sasural)\b",
        r"\b(husband|pati)\b.*\b(beat|hit|maar)", r"घरेलू हिंसा", r"दहेज",
    ],
    "cyber_fraud": [
        r"\bupi\b.*\b(fraud|scam)", r"\b(otp|kyc)\b.*\b(fraud|scam|call)", r"\bonline (fraud|scam)\b",
        r"\bcyber ?(fraud|crime)\b", r"\bmoney (was )?debited\b", r"\bpaise kat gaye\b", r"ऑनलाइन (धोखा|फ्रॉड)",
    ],
    "child": [r"\bchild (abuse|labour|labor)\b", r"\bminor\b.*\b(abuse|missing)", r"\bmissing child\b"],
}
_COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in _PATTERNS.items()}

HELPLINES = {
    "danger": ("112", {"en": "Emergency (Police / Ambulance)", "hi": "आपातकालीन सहायता (पुलिस / एम्बुलेंस)", "hinglish": "Emergency (Police / Ambulance)"}),
    "women": ("181", {"en": "Women Helpline", "hi": "महिला हेल्पलाइन", "hinglish": "Women Helpline"}),
    "self_harm": ("14416", {"en": "Tele-MANAS mental health helpline (24x7, free)", "hi": "टेली-मानस मानसिक स्वास्थ्य हेल्पलाइन (24x7, निःशुल्क)", "hinglish": "Tele-MANAS mental health helpline (24x7, free)"}),
    "cyber_fraud": ("1930", {"en": "Cyber Fraud Helpline (call quickly to try to freeze the money) / cybercrime.gov.in", "hi": "साइबर फ्रॉड हेल्पलाइन (पैसे रुकवाने के लिए तुरंत कॉल करें) / cybercrime.gov.in", "hinglish": "Cyber Fraud Helpline (paise freeze karwane ke liye turant call karein) / cybercrime.gov.in"}),
    "child": ("1098", {"en": "Childline", "hi": "चाइल्डलाइन", "hinglish": "Childline"}),
}
LEGAL_AID = {
    "en": "Free legal aid: NALSA helpline **15100**, or your District Legal Services Authority (DLSA).",
    "hi": "निःशुल्क कानूनी सहायता: NALSA हेल्पलाइन **15100**, या आपका जिला विधिक सेवा प्राधिकरण (DLSA)।",
    "hinglish": "Free legal aid: NALSA helpline **15100**, ya aapka District Legal Services Authority (DLSA).",
}


def detect_safety_flags(text: str) -> List[str]:
    flags = [cat for cat, pats in _COMPILED.items() if any(p.search(text or "") for p in pats)]
    if any(f in flags for f in ("self_harm", "women", "child")) and "danger" not in flags and re.search(r"\b(beat|hit|maar|attack)", text or "", re.I):
        flags.append("danger")
    return flags


def is_emergency(flags: List[str]) -> bool:
    return "danger" in flags or "self_harm" in flags


def helpline_block(flags: List[str], lang: str = "en") -> str:
    if not flags:
        return ""
    lang = lang if lang in ("en", "hi", "hinglish") else "en"
    header = {
        "en": "**If you are in immediate danger, call 112 now.** Your safety comes first.",
        "hi": "**अगर आप तुरंत खतरे में हैं, तो अभी 112 पर कॉल करें।** आपकी सुरक्षा सबसे पहले है।",
        "hinglish": "**Agar aap abhi khatre mein hain, to turant 112 par call karein.** Aapki safety sabse pehle hai.",
    }
    lines = []
    if is_emergency(flags):
        lines.append(header[lang])
    order = ["danger", "self_harm", "women", "child", "cyber_fraud"]
    for f in order:
        if f in flags:
            num, label = HELPLINES[f]
            lines.append(f"- **{num}** — {label[lang]}")
    return "\n".join(lines)


# --------- When to send the person to a real lawyer (rule-based, not model-decided) ---------
_COURT_PROCESS = re.compile(
    r"\b(summons|warrant|arrest(ed)?|bail|charge ?sheet|fir (against|on) me|case (filed )?against me|"
    r"court notice|legal notice (from|received)|police (called|came for) me|anticipatory)\b", re.I)


def referral_reasons(domains: List[str], case_text_en: str, amount_inr=None, limitation_note: str = "") -> List[str]:
    reasons = []
    if "Criminal Law" in domains:
        reasons.append("Criminal matters can affect your liberty and record; have a lawyer review the complaint or FIR before you file or respond.")
    if "Family Law" in domains:
        reasons.append("Family disputes (divorce, maintenance, custody) depend heavily on facts and evidence; a family lawyer or the DLSA should handle the court filing.")
    if _COURT_PROCESS.search(case_text_en or ""):
        reasons.append("You mention a court or police process against you. Do not ignore it - speak to a lawyer immediately.")
    if amount_inr and amount_inr > 5_000_000:
        reasons.append("The amount involved is large; professional drafting of the claim is worth it.")
    if limitation_note:
        reasons.append(limitation_note)
    return reasons
