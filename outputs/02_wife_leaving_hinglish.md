# 02_wife_leaving_hinglish
_Relationship must not be asked again; Hinglish_

**User:** meri wife mujhe chhod ke ja rahi hai

**NyayaMitra:**

Aapne bataya ki aapki wife aapko chhod kar ja rahi hain, thoda batayenge ki kya hua hai aur abhi aap log alag reh rahe hain kya?

---

**User:** woh apne maayke chali gayi hai aur wapas nahi aana chahti

**NyayaMitra:**

Aapki wife ghar chali gayi hain, toh ab aap kya chahte hain - reconciliation, divorce, ya kuch aur?

---

**User:** main chahta hoon ki woh wapas aa jaye, divorce nahi chahiye

**NyayaMitra:**

Aapki wife ne abhi tak koi police complaint, court case ya legal notice bheja hai kya?

---

**User:** nahi, koi case ya notice nahi hai

**NyayaMitra:**

Aapki shaadi kis riti-riwaz ya dharm ke anusaar hui thi?

---

**User:** Hindu rituals se shaadi hui thi

**NyayaMitra:**

Aapki shaadi kab hui thi aur kitne samay se aap dono alag reh rahe hain? (Approximate month ya saal bata sakte hain)

---

**User:** 2021 mein shaadi hui thi, 2 mahine se alag reh rahe hain

**NyayaMitra:**

Thank you. Kya aapke paas marriage certificate ya shaadi ki photos, messages, ya koi medical ya police records hain? Kuch aur jo mujhe jaanna chahiye? (Aap 'no' likh sakte hain.)

---

**User:** nahi

**NyayaMitra:**

### Aapki situation ko samajhna
Aapki shaadi 2021 mein Hindu rituals ke mutabiq hui thi, aur aapki wife apne parents ke ghar chali gayi hain aur wapas aana nahi chahti hain. Aap log September 2026 se lagbhag 2 months se alag reh rahe hain, aur aap divorce lene ke bajaye chahte hain ki woh wapas aa jayein.

### Aapka legal stand kya hai
- Kyunki aapki wife ne bina kisi reasonable excuse ke aapka sath chhod diya hai, aap district court mein restitution of conjugal rights (pati-patni ke sath rehne ke adhikar ki bahali) ke liye petition daal sakte hain taaki woh wapas aa sakein. [1]
- Agar aap restitution of conjugal rights ke liye file karte hain, toh chhod kar jaane ka koi reasonable excuse saabit karne ki zimmedari aapki wife ki hogi. [1]
- Divorce ki petition file karne ke liye desertion (alag rehna) kam se kam continuous 2 years tak hona chahiye, aur aapko alag rehte hue abhi sirf lagbhag 2 months hi hue hain. [2]

### Aapke paas kya options hain
1. **Restitution of Conjugal Rights** — District court (ya Family Court agar bani ho) mein petition file karein jisme court se request ki jaye ki aapki wife ko wapas aane ka order diya jaye. [1][3]
2. **Reconciliation and Counseling** — Family Court ya community/family mediators ki madad lein taaki aapke differences solve ho sakein aur aapki wife khushi-khushi wapas aane ke liye maan jaye, kyunki abhi tak koi formal case ya notice file nahi kiya gaya hai. [3]

### Aage kya karein
1. Reconciliation (sulah) ke baare mein baat karne ke liye apni wife ya unke family members se aaram se contact karein.
2. Agar baatchit kaam na aaye, toh restitution of conjugal rights ke liye ek formal request ya petition draft karne ke liye kisi local advocate se consult karein.
3. Apna marriage certificate ya wedding photographs taiyar rakhein.
4. Separation (alag rehne) ki dates aur communications ka record banakar rakhein.

### Yeh cheezein ready rakhein
- Marriage certificate ya wedding photographs
- Unke jaane ya alag rehne ke baare mein hue koi bhi messages ya written communication

### Lawyer ko kab involve karein
- Family disputes (divorce, maintenance, custody) poori tarah facts aur evidence par depend karte hain; court filing kisi family lawyer ya DLSA ke through karwayi honi chahiye.
- Free legal aid ke liye: NALSA helpline **15100**, ya apne District Legal Services Authority (DLSA) se contact karein.

### Assumptions aur gaps
- Aaj ki date yani November 9, 2026 tak dono taraf se koi bhi formal case ya notice file nahi kiya gaya hai.

---
**Sources (Bare Act provisions)**
1. Section 9, *Hindu Marriage Act, 1955* — Restitution of conjugal rights (spouse has left)
2. Section 13, *Hindu Marriage Act, 1955* — Grounds for divorce
3. Section 7, *Family Courts Act, 1984* — Family Court jurisdiction

_NyayaMitra upar diye gaye Bare Act provisions ke aadhar par general legal information deta hai. Yeh legal advice nahi hai aur isse koi lawyer-client relationship nahi banti. Laws aur state rules badalte rehte hain; kuch bhi file karne se pehle kisi advocate ya apne District Legal Services Authority se confirm zaroor karein._

---

## Pipeline record
- final status: `COMPLETED`
- language: `hinglish`
- domains: ['Family Law']
- problem types: {'Family Law': ['spouse_left']}
- questions asked: 5
- retrieval calls: 1
- evidence: ['HMA1955_S9', 'HMA1955_S13', 'HMA1955_S14', 'HMA1955_S13B', 'FCA1984_S7', 'BNSS2023_S144', 'HMA1955_S25']
- model calls: 17, tokens in/out: 22726/4014
- wall time: 53s

### Checklist
- Relationship: COLLECTED — User is the husband; the other party is his wife
- What is happening: COLLECTED — Wife has gone to her parents' house and does not want to come back
- What you want: COLLECTED — User wants her to come back and does not want a divorce
- Any case or notice already: COLLECTED — No case or notice has been filed
- Marriage law / rites: COLLECTED — Hindu rituals
- Marriage date and time apart: COLLECTED — Married in 2021; living apart for 2 months
- Proof: MISSING

### Audit attempt 1: PASS
- L2 [S] SUPPORTED: Accurately reflects the user's stated facts and system-computed timeline.
- L2 [L1] SUPPORTED: Correctly applies Section 9 HMA 1955; the wife has withdrawn from society, and the user is the aggrieved spouse.
- L2 [L2] SUPPORTED: Correctly states the burden of proof as per Section 9 HMA 1955.
- L2 [L3] SUPPORTED: Correctly cites the 2-year desertion requirement under Section 13 HMA 1955 and accurately notes the user has only been apart for 2 months.
- L2 [O1] SUPPORTED: Correctly identifies the forum (District Court or Family Court) for a restitution petition based on HMA S9 and FCA S7.
- L2 [O2] SUPPORTED: Practical advice consistent with the Family Court's jurisdiction and the user's goal of reconciliation.
- L2 [N1] SUPPORTED: Practical advice with no specific legal claim.
- L2 [N2] SUPPORTED: Practical advice to seek legal representation.
- L2 [N3] SUPPORTED: Practical advice to keep documents ready.
- L2 [N4] SUPPORTED: Practical advice to maintain records.