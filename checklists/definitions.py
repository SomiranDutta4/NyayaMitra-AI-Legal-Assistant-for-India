"""Issue checklists, per domain AND per type of problem (sub-issue).

Rule for what is "critical": its answer changes the forum, the time limit, which law applies,
eligibility for a remedy, or the person's safety. Everything else is "supporting" (picked up if
mentioned, never asked).

- applies_to: the sub-issues a field belongs to (None = every case in that domain).
- ONE QUESTION PER TURN: each turn asks about exactly one missing critical field.
- Order matters: fields are asked in list order (safety first, then what decides the law).

Questions: LLM 2 phrases the next question in context (in the extraction call, no extra API
call). The fixed FIELD_QUESTIONS below are the fallback and the text used for repeats.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel


class ChecklistField(BaseModel):
    field_id: str
    label: str
    category: str                      # "critical" | "supporting"
    description: str
    group: str
    applies_to: Optional[List[str]] = None


def F(fid, label, cat, desc, topic, applies_to=None) -> ChecklistField:
    # one question per turn: every field is its own "group" (the topic argument is kept only as documentation)
    return ChecklistField(field_id=fid, label=label, category=cat, description=desc, group=fid, applies_to=applies_to)


# ------------------------------------------------------------------ types of problem per domain
SUB_ISSUES: Dict[str, Dict[str, str]] = {
    "Consumer Law": {
        "defective_product": "goods that are broken, faulty or not as described",
        "deficient_service": "a service done badly or not at all (courier, airline, bank, repair, etc.)",
        "online_order": "bought online / e-commerce (non-delivery, refund or return refused)",
    },
    "Property Law": {
        "deposit": "security deposit not returned",
        "eviction": "being asked or forced to vacate / notice to leave",
        "lockout": "locked out, belongings kept, possession taken without court order",
        "builder_delay": "builder / developer delay or refund for a flat or plot",
        "other": "another property problem",
    },
    "Employment and Labour Law": {
        "unpaid_salary": "salary or wages not paid / delayed",
        "terminated": "fired, terminated or retrenched (with or without notice)",
        "gratuity": "gratuity or final settlement not paid after leaving",
        "other": "another employment problem",
    },
    "Contract Law": {
        "unpaid_work": "the other side has not paid for work or goods supplied",
        "non_performance": "the other side has not done / delivered what was promised",
        "cheque_bounce": "a cheque given to the user bounced",
        "other": "another contract problem",
    },
    "Criminal Law": {
        "fraud": "cheated / money taken by deception (offline)",
        "online_fraud": "UPI / OTP / online scam or cyber fraud",
        "threat": "threats or intimidation",
        "assault": "physical attack / hurt",
        "theft": "theft or property taken",
        "harassment_stalking": "being followed, stalked or harassed",
        "trespass": "someone entered or occupied the user's place",
        "cheque_bounce": "a cheque bounced",
        "other": "another criminal matter",
    },
    "Family Law": {
        "spouse_left": "spouse has left / living separately",
        "divorce": "wants a divorce or the spouse wants one",
        "maintenance": "financial support / maintenance (kharcha)",
        "domestic_violence": "abuse, cruelty or violence at home",
        "custody": "custody of or access to children",
        "dowry": "dowry demands or harassment",
        "other": "another family problem",
    },
}

DOMAIN_CHECKLISTS: Dict[str, List[ChecklistField]] = {
    "Consumer Law": [
        F("c_item", "What was bought and from whom", "critical",
          "The product or service, and the company / shop / website it was bought from.", "c_what"),
        F("c_problem", "What went wrong", "critical",
          "The specific defect or service failure.", "c_what"),
        F("c_amount", "Amount paid", "critical",
          "Price actually paid, in rupees (decides which consumer commission and the fee).", "c_money"),
        F("c_date", "Date of purchase / problem", "critical",
          "When it was bought or the problem started (2-year limit).", "c_money"),
        F("c_complained", "Complaint to seller / platform", "critical",
          "Whether the user already complained to the seller, company or platform, and their response.", "c_complaint"),
        F("c_order", "Platform and order ID", "supporting",
          "E-commerce platform name and order / ticket number.", "c_complaint", ["online_order"]),
        F("c_evidence", "Proof available", "supporting",
          "Invoice, order ID, emails, chats, photos, warranty card.", "c_complaint"),
    ],
    "Property Law": [
        F("p_role", "Your role", "critical",
          "Whether the user is the tenant, the landlord, or a buyer from a builder.", "p_role"),
        F("p_problem", "The dispute", "critical",
          "The main problem in one line (deposit, eviction, lock-out, builder delay...).", "p_role"),
        F("p_location", "City and state", "critical",
          "City and state of the property (tenancy and RERA rules differ by state).", "p_where"),
        F("p_deposit_amount", "Deposit amount", "critical",
          "Security deposit paid, in rupees.", "p_deposit", ["deposit"]),
        F("p_vacated", "Date vacated / keys returned", "critical",
          "When the user vacated and handed over the keys.", "p_deposit", ["deposit"]),
        F("p_deduction_reason", "Landlord's reason for keeping it", "critical",
          "Any reason the landlord gave (damage, unpaid rent, bills) or 'no reason'.", "p_deposit", ["deposit"]),
        F("p_notice", "Notice to vacate", "critical",
          "Whether a written notice was given, its date and how many days it allowed.", "p_eviction", ["eviction"]),
        F("p_rent_dues", "Rent dues", "critical",
          "Whether the user owes any rent.", "p_eviction", ["eviction"]),
        F("p_lockout_date", "Date locked out", "critical",
          "When the user was locked out / dispossessed (6-month limit for the possession suit).", "p_lockout", ["lockout"]),
        F("p_belongings", "Belongings kept", "critical",
          "Whether the user's belongings are still inside or kept by the other side.", "p_lockout", ["lockout"]),
        F("p_possession_due", "Promised possession date", "critical",
          "Possession date promised in the builder agreement.", "p_builder", ["builder_delay"]),
        F("p_paid_builder", "Amount paid to builder", "critical",
          "Total amount paid to the builder so far.", "p_builder", ["builder_delay"]),
        F("p_builder_goal", "Refund or possession", "critical",
          "Whether the user wants a refund (withdraw) or wants the flat with interest for delay.", "p_builder", ["builder_delay"]),
        F("p_agreement", "Written agreement", "supporting",
          "Rent agreement / builder-buyer agreement, registered or not; RERA registration.", "p_where"),
    ],
    "Employment and Labour Law": [
        F("l_status", "Employment status", "critical",
          "Still working, resigned, or fired — stated by the user, not assumed.", "l_status"),
        F("l_employer", "Type of employer", "critical",
          "Private company, shop/small business, government office, or household (government staff have different rules).", "l_status"),
        F("l_unpaid", "What is unpaid and how much", "critical",
          "Which months' salary / which dues, and the amount in rupees.", "l_dues", ["unpaid_salary", "gratuity"]),
        F("l_since", "Since when", "critical",
          "From which month the payment is pending.", "l_dues", ["unpaid_salary"]),
        F("l_left_date", "Date of leaving / termination", "critical",
          "When the user resigned or was fired.", "l_exit", ["terminated", "gratuity"]),
        F("l_service_years", "Years of service", "critical",
          "How long the user worked there (1 year matters for retrenchment, 5 years for gratuity).", "l_exit", ["terminated", "gratuity"]),
        F("l_notice_given", "Notice or reason given", "critical",
          "Whether a written notice / reason / notice pay was given before termination.", "l_exit", ["terminated"]),
        F("l_role", "Job role", "supporting", "Job title (worker, supervisor, manager) and monthly salary.", "l_status"),
        F("l_proof", "Proof of employment", "supporting", "Offer letter, salary slips, bank credits, ID card, emails.", "l_status"),
    ],
    "Contract Law": [
        F("k_deal", "Other party and what was agreed", "critical",
          "Who the other party is (person or company) and what was agreed.", "k_what"),
        F("k_breach", "What they failed to do", "critical",
          "The specific obligation that was not performed.", "k_what"),
        F("k_amount", "Amount involved", "critical",
          "Money owed or lost, in rupees.", "k_money"),
        F("k_date", "Date of breach", "critical",
          "When payment/performance was due and not done (3-year limit).", "k_money"),
        F("k_terms", "Written terms / arbitration clause", "critical",
          "Whether terms are in writing (contract, email, WhatsApp) and whether there is an arbitration clause.", "k_terms"),
        F("k_cheque", "Cheque return and notice", "critical",
          "When the bank returned the cheque and whether a demand notice has been sent (30-day deadlines).", "k_cheque", ["cheque_bounce"]),
        F("k_evidence", "Proof", "supporting", "Invoices, messages, bank records, delivery proof.", "k_terms"),
    ],
    "Criminal Law": [
        F("r_safe", "Safe right now", "critical",
          "Whether the user is safe now and whether the threat/harassment is ongoing.", "r_safety",
          ["threat", "assault", "harassment_stalking"]),
        F("r_incident", "What happened and who", "critical",
          "The incident and who did it (known or unknown person).", "r_what"),
        F("r_date", "Date of incident", "critical",
          "When it happened (before or after 1 July 2024 decides IPC vs BNS).", "r_what"),
        # money / injuries come before the police questions: for fraud, time decides whether money can be frozen
        F("r_money", "Money lost and how it was paid", "critical",
          "Amount lost, payment method (UPI, bank, card, cash) and exact time.", "r_fraud", ["fraud", "online_fraud"]),
        F("r_injuries", "Injuries / medical report", "critical",
          "Whether the user was injured and has a medical report.", "r_assault", ["assault"]),
        F("r_place", "City / place", "critical",
          "Where it happened (which police station area).", "r_police"),
        F("r_police", "Police complaint status", "critical",
          "Whether the user went to the police / filed an FIR and what happened.", "r_police"),
        F("r_evidence", "Evidence", "supporting", "Bank records, chats, call logs, recordings, CCTV, witnesses.", "r_police"),
    ],
    "Family Law": [
        F("f_safe", "Safe right now", "critical",
          "Whether the user is safe now and still living with the abuser.", "f_safety", ["domestic_violence", "dowry"]),
        F("f_relationship", "Relationship", "critical",
          "Who the user is and who the other party is (e.g. user is the husband, other party is his wife).", "f_who"),
        F("f_situation", "What is happening", "critical",
          "What has happened so far.", "f_who"),
        F("f_goal", "What you want", "critical",
          "Outcome wanted: reconcile, divorce, maintenance, custody, protection.", "f_goal"),
        F("f_case_filed", "Any case or notice already", "critical",
          "Whether either side has filed a case or sent a legal notice.", "f_goal"),
        F("f_marriage_law", "Marriage law / rites", "critical",
          "Hindu rites, Muslim law, Christian law or Special Marriage Act (only Hindu Marriage Act is covered).", "f_marriage"),
        F("f_marriage_date", "Marriage date and time apart", "critical",
          "When married and how long living separately (1-year rules for divorce).", "f_marriage"),
        F("f_children", "Children", "critical",
          "Children and their ages.", "f_money", ["custody", "maintenance"]),
        F("f_income", "Incomes", "critical",
          "Who earns what (user and spouse).", "f_money", ["maintenance"]),
        F("f_evidence", "Proof", "supporting", "Marriage certificate, messages, medical reports, police complaints.", "f_who"),
    ],
}

# ------------------------------------------------------------------ fallback questions (ONE fact each)
Q = lambda en, hi, hl: {"en": en, "hi": hi, "hinglish": hl}  # noqa: E731
FIELD_QUESTIONS: Dict[str, Dict[str, str]] = {
    # ---- Consumer
    "c_item": Q("What did you buy (or which service did you use), and from which company, shop or website?",
                "आपने क्या खरीदा था (या कौन सी सेवा ली थी), और किस कंपनी, दुकान या वेबसाइट से?",
                "Aapne kya kharida tha (ya kaunsi service li thi), aur kis company, shop ya website se?"),
    "c_problem": Q("What exactly went wrong with it?",
                   "उसमें ठीक-ठीक क्या गड़बड़ हुई?",
                   "Usme exactly kya galat hua?"),
    "c_amount": Q("How much did you pay for it? (The amount decides which consumer court you go to.)",
                  "आपने इसके लिए कितने पैसे दिए थे? (रकम से तय होता है कि कौन सी उपभोक्ता अदालत जाना है।)",
                  "Aapne iske liye kitne paise diye the? (Amount se decide hota hai kaunsa consumer court.)"),
    "c_date": Q("Roughly when did you buy it, or when did the problem start? (It sets your deadline — a rough month is fine.)",
                "आपने इसे लगभग कब खरीदा था, या समस्या कब शुरू हुई? (इससे आपकी समय-सीमा तय होती है — अंदाज़न महीना भी चलेगा।)",
                "Aapne ise lagbhag kab kharida tha, ya problem kab shuru hui? (Isse deadline tay hoti hai — rough month bhi chalega.)"),
    "c_complained": Q("Have you already complained to the seller or company (email, ticket or call)? What did they say?",
                      "क्या आपने विक्रेता या कंपनी से पहले ही शिकायत की है (ईमेल, टिकट या कॉल)? उन्होंने क्या कहा?",
                      "Kya aapne seller ya company ko pehle complain kiya hai (email, ticket ya call)? Unhone kya kaha?"),
    # ---- Property
    "p_role": Q("Are you the tenant, the landlord, or a buyer from a builder?",
                "क्या आप किरायेदार हैं, मकान मालिक हैं, या बिल्डर से खरीदार?",
                "Kya aap tenant hain, landlord hain, ya builder se buyer?"),
    "p_problem": Q("What is the main problem — for example deposit not returned, asked to vacate, locked out, or builder delay?",
                   "मुख्य समस्या क्या है — जैसे डिपॉजिट वापस नहीं मिला, घर खाली करने को कहा, ताला लगा दिया, या बिल्डर की देरी?",
                   "Main problem kya hai — jaise deposit wapas nahi mila, ghar khaali karne ko kaha, lock laga diya, ya builder delay?"),
    "p_location": Q("In which city and state is the property? (Tenancy rules differ from state to state.)",
                    "संपत्ति किस शहर और राज्य में है? (किरायेदारी के नियम हर राज्य में अलग होते हैं।)",
                    "Property kis city aur state mein hai? (Tenancy rules har state mein alag hote hain.)"),
    "p_deposit_amount": Q("How much was the security deposit?",
                          "सिक्योरिटी डिपॉजिट कितना था?",
                          "Security deposit kitna tha?"),
    "p_vacated": Q("When did you vacate and hand over the keys? (A rough date is fine.)",
                   "आपने घर कब खाली करके चाबी सौंपी? (अंदाज़न तारीख भी चलेगी।)",
                   "Aapne ghar kab khaali karke chaabi di? (Rough date bhi chalegi.)"),
    "p_deduction_reason": Q("Has the landlord given any reason for keeping the deposit, such as damage or unpaid rent?",
                            "क्या मकान मालिक ने डिपॉजिट रोकने का कोई कारण बताया है, जैसे नुकसान या बकाया किराया?",
                            "Kya landlord ne deposit rokne ka koi reason bataya hai, jaise damage ya baaki rent?"),
    "p_notice": Q("Did the landlord give you a written notice to vacate? If yes, on what date and how many days did it give you?",
                  "क्या मकान मालिक ने घर खाली करने का लिखित नोटिस दिया? अगर हाँ, तो किस तारीख को और कितने दिन का?",
                  "Kya landlord ne ghar khaali karne ka written notice diya? Agar haan, to kis date ko aur kitne din ka?"),
    "p_rent_dues": Q("Do you owe any rent to the landlord right now?",
                     "क्या अभी आपका मकान मालिक को कोई किराया देना बाकी है?",
                     "Kya abhi aapka landlord ko koi rent dena baaki hai?"),
    "p_lockout_date": Q("On what date were you locked out? (The date matters — a court case to get possession back has a 6-month limit.)",
                        "आपको किस तारीख को बाहर किया गया / ताला लगाया गया? (तारीख ज़रूरी है — कब्ज़ा वापस पाने के केस की 6 महीने की सीमा है।)",
                        "Aapko kis date ko lock out kiya gaya? (Date zaroori hai — possession wapas lene ke case ki 6 mahine ki limit hai.)"),
    "p_belongings": Q("Are any of your belongings still inside, or kept by them?",
                      "क्या आपका कोई सामान अभी भी अंदर है, या उनके पास है?",
                      "Kya aapka koi saamaan abhi bhi andar hai, ya unke paas hai?"),
    "p_possession_due": Q("What possession date did the builder promise in the agreement?",
                          "बिल्डर ने एग्रीमेंट में कब्ज़ा देने की कौन सी तारीख का वादा किया था?",
                          "Builder ne agreement mein possession ki kaunsi date promise ki thi?"),
    "p_paid_builder": Q("How much have you paid the builder so far?",
                        "आप अब तक बिल्डर को कितना भुगतान कर चुके हैं?",
                        "Aap ab tak builder ko kitna pay kar chuke hain?"),
    "p_builder_goal": Q("Do you want your money back, or the flat along with compensation for the delay?",
                        "क्या आप अपने पैसे वापस चाहते हैं, या देरी के मुआवज़े के साथ फ्लैट?",
                        "Kya aap apne paise wapas chahte hain, ya delay compensation ke saath flat?"),
    # ---- Labour
    "l_status": Q("Are you still working there, or did you resign or get fired?",
                  "क्या आप अभी भी वहाँ काम कर रहे हैं, या आपने इस्तीफा दिया या आपको निकाल दिया गया?",
                  "Kya aap abhi bhi wahan kaam kar rahe hain, ya resign kiya ya nikaal diye gaye?"),
    "l_employer": Q("Is the employer a private company, a shop or small business, a government office, or a household? (Government staff have different rules.)",
                    "नियोक्ता प्राइवेट कंपनी है, दुकान/छोटा व्यवसाय, सरकारी दफ्तर, या कोई घर? (सरकारी कर्मचारियों के नियम अलग होते हैं।)",
                    "Employer private company hai, shop/chhota business, government office, ya koi ghar? (Government staff ke rules alag hote hain.)"),
    "l_unpaid": Q("Which payment is pending (which months' salary, or which dues), and roughly how much?",
                  "कौन सा भुगतान बाकी है (किन महीनों का वेतन या कौन सा बकाया), और लगभग कितना?",
                  "Kaunsa payment pending hai (kin mahino ki salary ya kaunsa baaki), aur lagbhag kitna?"),
    "l_since": Q("Since when has the payment been pending? (A rough month is fine — it tells us your deadline.)",
                 "भुगतान कब से बाकी है? (अंदाज़न महीना भी चलेगा — इससे आपकी समय-सीमा पता चलती है।)",
                 "Payment kab se pending hai? (Rough month bhi chalega — isse deadline pata chalti hai.)"),
    "l_left_date": Q("When did you leave the job, or when were you fired? (A rough date is fine.)",
                     "आपने नौकरी कब छोड़ी, या आपको कब निकाला गया? (अंदाज़न तारीख भी चलेगी।)",
                     "Aapne job kab chhodi, ya aapko kab nikaala gaya? (Rough date bhi chalegi.)"),
    "l_service_years": Q("How many years did you work there? (It decides which benefits apply.)",
                         "आपने वहाँ कितने साल काम किया? (इससे तय होता है कि कौन से लाभ मिलेंगे।)",
                         "Aapne wahan kitne saal kaam kiya? (Isse benefits decide hote hain.)"),
    "l_notice_given": Q("Were you given any written notice, reason, or notice pay before being fired?",
                        "क्या निकाले जाने से पहले आपको कोई लिखित नोटिस, कारण या नोटिस-पे दिया गया?",
                        "Kya nikaale jaane se pehle aapko koi written notice, reason ya notice pay diya gaya?"),
    # ---- Contract
    "k_deal": Q("Who is the other party (a person or a company), and what did you agree?",
                "दूसरा पक्ष कौन है (कोई व्यक्ति या कंपनी), और आपके बीच क्या तय हुआ था?",
                "Doosri party kaun hai (koi vyakti ya company), aur aapke beech kya tay hua tha?"),
    "k_breach": Q("What exactly did they fail to do?",
                  "उन्होंने ठीक-ठीक क्या नहीं किया?",
                  "Unhone exactly kya nahi kiya?"),
    "k_amount": Q("How much money is involved?",
                  "कितने पैसे का मामला है?",
                  "Kitne paise ka maamla hai?"),
    "k_date": Q("Roughly when was the payment or work due? (It sets a 3-year deadline — a rough month is fine.)",
                "भुगतान या काम लगभग कब होना था? (इससे 3 साल की समय-सीमा तय होती है — अंदाज़न महीना भी चलेगा।)",
                "Payment ya kaam lagbhag kab hona tha? (Isse 3 saal ki deadline tay hoti hai — rough month bhi chalega.)"),
    "k_terms": Q("Was the agreement in writing — a signed contract, email or WhatsApp? If there is a contract, does it have an arbitration clause? (That changes where the dispute is decided.)",
                 "क्या समझौता लिखित में था — साइन किया कॉन्ट्रैक्ट, ईमेल या व्हाट्सऐप? अगर कॉन्ट्रैक्ट है, तो क्या उसमें आर्बिट्रेशन क्लॉज़ है? (इससे तय होता है विवाद कहाँ सुलझेगा।)",
                 "Kya agreement written mein tha — signed contract, email ya WhatsApp? Agar contract hai, to kya usme arbitration clause hai? (Isse decide hota hai dispute kahan suljhega.)"),
    "k_cheque": Q("When did the bank return the cheque? (Strict 30-day deadlines apply for cheque bounce.)",
                  "बैंक ने चेक कब लौटाया? (चेक बाउंस में 30 दिन की सख्त समय-सीमा होती है।)",
                  "Bank ne cheque kab lautaya? (Cheque bounce mein 30 din ki strict deadline hoti hai.)"),
    # ---- Criminal
    "r_safe": Q("First — are you safe right now? Is the person still threatening you or near you?",
                "सबसे पहले — क्या आप अभी सुरक्षित हैं? क्या वह व्यक्ति अभी भी आपको धमका रहा है या आपके आस-पास है?",
                "Sabse pehle — kya aap abhi safe hain? Kya woh vyakti abhi bhi aapko dhamka raha hai ya aapke aas-paas hai?"),
    "r_incident": Q("What exactly happened, and who did it — do you know the person?",
                    "ठीक-ठीक क्या हुआ, और यह किसने किया — क्या आप उस व्यक्ति को जानते हैं?",
                    "Exactly kya hua, aur yeh kisne kiya — kya aap us vyakti ko jaante hain?"),
    "r_date": Q("On what date did this happen? (The date decides which criminal law applies — a rough date is fine.)",
                "यह किस तारीख को हुआ? (तारीख से तय होता है कौन सा आपराधिक कानून लागू होगा — अंदाज़न तारीख भी चलेगी।)",
                "Yeh kis date ko hua? (Date se decide hota hai kaunsa criminal law lagega — rough date bhi chalegi.)"),
    "r_money": Q("How much money did you lose, and how did you pay — UPI, bank transfer, card or cash? (For online fraud, calling 1930 within hours can help freeze the money.)",
                 "आपके कितने पैसे गए, और आपने कैसे भुगतान किया — UPI, बैंक ट्रांसफर, कार्ड या नकद? (ऑनलाइन फ्रॉड में कुछ घंटों के अंदर 1930 पर कॉल करने से पैसे रुक सकते हैं।)",
                 "Aapke kitne paise gaye, aur aapne kaise pay kiya — UPI, bank transfer, card ya cash? (Online fraud mein kuch ghanton ke andar 1930 par call karne se paise ruk sakte hain.)"),
    "r_injuries": Q("Were you injured? Have you seen a doctor or got a medical report?",
                    "क्या आपको चोट लगी? क्या आपने डॉक्टर को दिखाया या मेडिकल रिपोर्ट ली है?",
                    "Kya aapko chot lagi? Kya aapne doctor ko dikhaya ya medical report li hai?"),
    "r_place": Q("In which city or area did this happen?",
                 "यह किस शहर या इलाके में हुआ?",
                 "Yeh kis city ya area mein hua?"),
    "r_police": Q("Have you gone to the police or filed a complaint/FIR yet? What happened there?",
                  "क्या आप पुलिस के पास गए हैं या शिकायत/FIR दर्ज की है? वहाँ क्या हुआ?",
                  "Kya aap police ke paas gaye hain ya complaint/FIR file ki hai? Wahan kya hua?"),
    # ---- Family
    "f_safe": Q("First — are you safe right now? Are you still living with the person who is hurting you?",
                "सबसे पहले — क्या आप अभी सुरक्षित हैं? क्या आप अभी भी उस व्यक्ति के साथ रह रहे हैं जो आपको चोट पहुँचा रहा है?",
                "Sabse pehle — kya aap abhi safe hain? Kya aap abhi bhi us vyakti ke saath reh rahe hain jo aapko hurt kar raha hai?"),
    "f_relationship": Q("Who is the other person to you — husband, wife, or in-laws?",
                        "दूसरा व्यक्ति आपका क्या लगता है — पति, पत्नी, या ससुराल वाले?",
                        "Doosra vyakti aapka kya lagta hai — pati, patni, ya sasural wale?"),
    "f_situation": Q("What has happened so far?",
                     "अब तक क्या हुआ है?",
                     "Ab tak kya hua hai?"),
    "f_goal": Q("I'm sorry you're going through this. What would you like to happen — try to save the marriage, separate or divorce, get financial support, or something about the children?",
                "मुझे दुख है कि आप इससे गुज़र रहे हैं। आप क्या चाहते हैं — शादी बचाने की कोशिश, अलग होना या तलाक, गुज़ारा भत्ता, या बच्चों से जुड़ी कोई बात?",
                "Mujhe afsos hai ki aap isse guzar rahe hain. Aap kya chahte hain — shaadi bachane ki koshish, alag hona ya divorce, kharcha (maintenance), ya bachchon se judi koi baat?"),
    "f_case_filed": Q("Has either of you already filed a case or sent a legal notice?",
                      "क्या आप में से किसी ने पहले ही कोई केस किया है या कानूनी नोटिस भेजा है?",
                      "Kya aap mein se kisi ne pehle hi koi case kiya hai ya legal notice bheja hai?"),
    "f_marriage_law": Q("Was your marriage under Hindu rites, Muslim law, Christian law, or the Special Marriage Act?",
                        "क्या आपकी शादी हिंदू रीति, मुस्लिम कानून, ईसाई कानून, या स्पेशल मैरिज एक्ट के तहत हुई थी?",
                        "Kya aapki shaadi Hindu rituals, Muslim law, Christian law, ya Special Marriage Act ke under hui thi?"),
    "f_marriage_date": Q("When did you get married, and how long have you been living apart? (These decide which options are open to you.)",
                         "आपकी शादी कब हुई थी, और आप कितने समय से अलग रह रहे हैं? (इनसे तय होता है कि आपके पास कौन से विकल्प हैं।)",
                         "Aapki shaadi kab hui thi, aur aap kitne time se alag reh rahe hain? (Isse decide hota hai aapke paas kaunse options hain.)"),
    "f_children": Q("Do you have children? How old are they?",
                    "क्या आपके बच्चे हैं? उनकी उम्र क्या है?",
                    "Kya aapke bachche hain? Unki umar kya hai?"),
    "f_income": Q("Who earns what — do you and your spouse have jobs or other income?",
                  "कौन कितना कमाता है — क्या आपकी और आपके जीवनसाथी की नौकरी या कोई और आय है?",
                  "Kaun kitna kamaata hai — kya aapki aur aapke spouse ki job ya koi aur income hai?"),
}

# ------------------------------------------------------------------ closing question per domain (collects proof)
CLOSING_QUESTIONS: Dict[str, Dict[str, str]] = {
    "Consumer Law": Q("Thank you. Do you have the invoice, order ID, emails or chats with the seller, or photos of the problem? Anything else I should know? (You can reply 'no'.)",
                      "धन्यवाद। क्या आपके पास बिल, ऑर्डर ID, विक्रेता के साथ ईमेल या चैट, या समस्या की फोटो हैं? कुछ और जो मुझे जानना चाहिए? (आप 'नहीं' लिख सकते हैं।)",
                      "Thank you. Kya aapke paas bill, order ID, seller ke saath emails ya chats, ya problem ki photos hain? Kuch aur jo mujhe jaanna chahiye? (Aap 'no' likh sakte hain.)"),
    "Property Law": Q("Thank you. Do you have a rent or sale agreement, rent or deposit payment receipts, or messages with the other side? Anything else I should know? (You can reply 'no'.)",
                      "धन्यवाद। क्या आपके पास रेंट या सेल एग्रीमेंट, किराया या डिपॉजिट की रसीदें, या दूसरे पक्ष के साथ मैसेज हैं? कुछ और जो मुझे जानना चाहिए? (आप 'नहीं' लिख सकते हैं।)",
                      "Thank you. Kya aapke paas rent ya sale agreement, rent ya deposit ki receipts, ya doosri party ke saath messages hain? Kuch aur jo mujhe jaanna chahiye? (Aap 'no' likh sakte hain.)"),
    "Employment and Labour Law": Q("Thank you. Do you have an offer or appointment letter, salary slips, or bank statements showing your salary? Anything else I should know? (You can reply 'no'.)",
                                   "धन्यवाद। क्या आपके पास ऑफर या नियुक्ति पत्र, सैलरी स्लिप, या वेतन दिखाने वाले बैंक स्टेटमेंट हैं? कुछ और जो मुझे जानना चाहिए? (आप 'नहीं' लिख सकते हैं।)",
                                   "Thank you. Kya aapke paas offer ya appointment letter, salary slips, ya salary dikhane wale bank statements hain? Kuch aur jo mujhe jaanna chahiye? (Aap 'no' likh sakte hain.)"),
    "Contract Law": Q("Thank you. Do you have the contract, invoices, emails or WhatsApp messages, or bank records of payments? Anything else I should know? (You can reply 'no'.)",
                      "धन्यवाद। क्या आपके पास कॉन्ट्रैक्ट, बिल, ईमेल या व्हाट्सऐप मैसेज, या भुगतान के बैंक रिकॉर्ड हैं? कुछ और जो मुझे जानना चाहिए? (आप 'नहीं' लिख सकते हैं।)",
                      "Thank you. Kya aapke paas contract, invoices, emails ya WhatsApp messages, ya payments ke bank records hain? Kuch aur jo mujhe jaanna chahiye? (Aap 'no' likh sakte hain.)"),
    "Criminal Law": Q("Thank you. Do you have any evidence — bank or UPI records, chats, call logs, recordings, CCTV, or witnesses? Anything else I should know? (You can reply 'no'.)",
                      "धन्यवाद। क्या आपके पास कोई सबूत है — बैंक या UPI रिकॉर्ड, चैट, कॉल लॉग, रिकॉर्डिंग, CCTV, या गवाह? कुछ और जो मुझे जानना चाहिए? (आप 'नहीं' लिख सकते हैं।)",
                      "Thank you. Kya aapke paas koi saboot hai — bank ya UPI records, chats, call logs, recordings, CCTV, ya witnesses? Kuch aur jo mujhe jaanna chahiye? (Aap 'no' likh sakte hain.)"),
    "Family Law": Q("Thank you. Do you have your marriage certificate or wedding photos, messages, or any medical or police records? Anything else I should know? (You can reply 'no'.)",
                    "धन्यवाद। क्या आपके पास विवाह प्रमाणपत्र या शादी की फोटो, मैसेज, या कोई मेडिकल या पुलिस रिकॉर्ड है? कुछ और जो मुझे जानना चाहिए? (आप 'नहीं' लिख सकते हैं।)",
                    "Thank you. Kya aapke paas marriage certificate ya shaadi ki photos, messages, ya koi medical ya police records hain? Kuch aur jo mujhe jaanna chahiye? (Aap 'no' likh sakte hain.)"),
}
ADDITIONAL_INFO_PROMPT = Q(
    "Thank you. Is there anything else about your situation that might be relevant — any documents, messages, or other details? (You can reply 'no'.)",
    "धन्यवाद। क्या आपकी स्थिति के बारे में कुछ और है जो ज़रूरी हो सकता है — कोई दस्तावेज़, मैसेज या अन्य जानकारी? (आप 'नहीं' लिख सकते हैं।)",
    "Thank you. Kya aapki situation ke baare mein kuch aur hai jo important ho sakta hai — koi documents, messages ya details? (Aap 'no' likh sakte hain.)",
)
# Used when a question is asked again. Two tones: the reply added something about the case (acknowledge it),
# or it didn't (gently re-ask). Never "sorry, I didn't get that" after someone shares something serious.
REPEAT_PREFIX = Q("Just so I can help you properly — ",
                  "आपकी सही मदद कर सकूँ, इसके लिए — ",
                  "Aapki sahi madad kar sakoon, iske liye — ")
NOTED_PREFIX = Q("Thank you for telling me — I've noted that. To help you properly, I still need one detail: ",
                 "बताने के लिए धन्यवाद — मैंने यह नोट कर लिया है। आपकी सही मदद के लिए मुझे एक बात और जाननी है: ",
                 "Batane ke liye thank you — maine yeh note kar liya hai. Aapki sahi madad ke liye mujhe ek baat aur jaanni hai: ")


def get_field(field_id: str) -> Optional[ChecklistField]:
    for fields in DOMAIN_CHECKLISTS.values():
        for f in fields:
            if f.field_id == field_id:
                return f
    return None


def group_question(field_id: str, lang: str) -> str:
    """Fixed one-fact question for a field (each field is its own group)."""
    return FIELD_QUESTIONS[field_id].get(lang) or FIELD_QUESTIONS[field_id]["en"]


def closing_question(domains: List[str], lang: str) -> str:
    for d in domains:
        if d in CLOSING_QUESTIONS:
            return CLOSING_QUESTIONS[d][lang]
    return ADDITIONAL_INFO_PROMPT[lang]
