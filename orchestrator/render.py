"""Turns the audited structured answer into the final Markdown a person reads.
Rendering is deterministic: the model never writes the citation list or the lawyer-referral block."""

from typing import Dict, List

from kb.retriever import LegalDocument
from rules.safety import LEGAL_AID

DISCLAIMER = ("_NyayaMitra gives general legal information based on the Bare Act provisions listed above. "
              "It is not legal advice and does not create a lawyer–client relationship. Laws and state rules change; "
              "confirm with an advocate or your District Legal Services Authority before filing._")


def render_answer(ans: Dict, evidence: Dict[str, LegalDocument], referral: List[str],
                  helplines: str = "", removed_note: str = "", general: bool = False) -> str:
    h = ({"summary": "Your question", "position": "What the law says", "options": "What this means in practice"}
         if general else
         {"summary": "Understanding your situation", "position": "Where you stand legally", "options": "Your options"})
    order: List[str] = []

    def refs(cites) -> str:
        out = []
        for c in cites or []:
            if c in evidence:
                if c not in order:
                    order.append(c)
                out.append(f"[{order.index(c) + 1}]")
        return " " + "".join(dict.fromkeys(out)) if out else ""

    md: List[str] = []
    if helplines:
        md += [helplines, ""]
    if ans.get("summary"):
        md += [f"### {h['summary']}", str(ans["summary"]), ""]
    if ans.get("legal_position"):
        md.append(f"### {h['position']}")
        md += [f"- {x.get('text', '')}{refs(x.get('cites'))}" for x in ans["legal_position"]]
        md.append("")
    if ans.get("options"):
        md.append(f"### {h['options']}")
        for i, x in enumerate(ans["options"], 1):
            md.append(f"{i}. **{x.get('title', '')}** — {x.get('detail', '')}{refs(x.get('cites'))}")
        md.append("")
    if ans.get("deadlines"):
        md.append("### Time limits")
        md += [f"- {x.get('text', '')}{refs(x.get('cites'))}" for x in ans["deadlines"]]
        md.append("")
    if ans.get("next_steps"):
        md.append("### What to do next")
        md += [f"{i}. {s}" for i, s in enumerate(ans["next_steps"], 1)]
        md.append("")
    if ans.get("evidence_to_collect"):
        md.append("### Keep these ready")
        md += [f"- {s}" for s in ans["evidence_to_collect"]]
        md.append("")
    doc = ans.get("draft_document") or {}
    if isinstance(doc, dict) and doc.get("text") and str(doc.get("type", "None")).lower() != "none":
        md.append(f"### Draft: {doc.get('type')} (edit before using)")
        md += ["> " + line if line.strip() else ">" for line in str(doc["text"]).splitlines()]
        md.append("")
    md.append("### When to involve a lawyer")
    if referral:
        md += [f"- {r}" for r in referral]
    else:
        md.append("- You can usually start this yourself. If the other side does not respond, or you are unsure about any step, consult a lawyer.")
    md += [f"- {LEGAL_AID['en']}", ""]
    if ans.get("assumptions"):
        md.append("### Assumptions and gaps")
        md += [f"- {s}" for s in ans["assumptions"]]
        md.append("")
    if removed_note:
        md += [f"_{removed_note}_", ""]
    if order:
        md.append("---")
        md.append("**Sources (Bare Act provisions)**")
        for i, c in enumerate(order, 1):
            d = evidence[c]
            md.append(f"{i}. {d.section}, *{d.act}* — {d.title}")
        md.append("")
    md.append(DISCLAIMER)
    return "\n".join(md).strip()


ABSTAIN_TEXT = {
    "en": ("I could not verify a reliable answer for your situation from the legal provisions I have, so I would rather not guess.\n\n"
           "**Please consult a lawyer** with your documents. If you cannot afford one, you can get free legal aid: "
           "call the NALSA helpline **15100** or visit your District Legal Services Authority (DLSA)."),
    "hi": ("मेरे पास उपलब्ध कानूनी प्रावधानों से मैं आपकी स्थिति का भरोसेमंद जवाब सत्यापित नहीं कर पाया, इसलिए मैं अनुमान नहीं लगाना चाहता।\n\n"
           "**कृपया अपने दस्तावेज़ों के साथ किसी वकील से सलाह लें।** अगर आप वकील का खर्च नहीं उठा सकते, तो निःशुल्क कानूनी सहायता के लिए "
           "NALSA हेल्पलाइन **15100** पर कॉल करें या अपने जिला विधिक सेवा प्राधिकरण (DLSA) जाएँ।"),
    "hinglish": ("Mere paas jo legal provisions hain unse main aapki situation ka reliable answer verify nahi kar paaya, isliye main guess nahi karunga.\n\n"
                 "**Please apne documents ke saath kisi lawyer se milein.** Agar lawyer ka kharcha nahi utha sakte, to free legal aid ke liye "
                 "NALSA helpline **15100** par call karein ya apne District Legal Services Authority (DLSA) jaayein."),
}
ERROR_TEXT = {
    "en": "Sorry — the AI service is not responding right now (it may be a rate limit). Please try again in a minute. Your conversation is saved.",
    "hi": "क्षमा करें — AI सेवा अभी जवाब नहीं दे रही है (शायद सीमा पूरी हो गई है)। कृपया एक मिनट बाद फिर से कोशिश करें। आपकी बातचीत सुरक्षित है।",
    "hinglish": "Sorry — AI service abhi respond nahi kar rahi (shayad rate limit). Please ek minute baad dobara try karein. Aapki baatcheet saved hai.",
}
