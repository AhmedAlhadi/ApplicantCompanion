# Serah — Website Brief

Copy and structure for adding **Serah** to the Shortlisted website. Written for marketing pages, not for engineers.

**Product name:** Serah
**Brand line:** Job-seeker workspace from Shortlisted
**Languages:** English and Arabic (interface and generated documents can be set independently)

---

## 1. Positioning

Serah is a personal job-application workspace. You give it your career history once. For every new vacancy it analyzes the job, researches the organization, matches your real evidence, scores the fit honestly, and writes a targeted CV and cover letter — without inventing anything.

It is not a chatbot that “writes a resume.” It is a career intelligence workspace: structured knowledge, explainable matching, and human-in-the-loop documents.

### One-liners (pick one)

- Give Serah your career once. For every job, get an honest fit score and a CV that only uses what you have actually done.
- Tailored applications without fabricated experience.
- Job intelligence, evidence-based matching, and ATS-ready documents — still under your control.
- Upload your career. Paste a job ad. Review the fit. Export a targeted CV and cover letter.

### Short paragraph (hero / product card)

Serah turns your career history into a living knowledge base, then uses it to analyze each vacancy. It parses the job description, researches the organization, maps your evidence to every requirement, and shows an explainable fit score. When you decide to apply, it generates a job-specific CV and cover letter — truthful, ATS-aware, and fully editable.

### Longer paragraph (product page)

Most AI resume tools rewrite your CV in the voice of the job ad and quietly upgrade your experience. Serah does the opposite. It first extracts a structured Career Knowledge Base from your documents — roles, projects, achievements, skills, education, certifications, languages, publications, and the domain, industry, and process knowledge you picked up on the job. Then, for each new job, specialized AI agents parse the vacancy, research the employer from public sources, retrieve only the relevant evidence, and score the match programmatically. Documents are generated from that evidence, validated against it, and versioned so you can edit, regenerate a section, or restore an earlier draft. You stay the decision maker.

---

## 2. Suggested page outline

Use this as a product page or a “Products → Serah” section.

1. **Hero** — name, one-liner, two CTAs (e.g. Try Serah / See how it works)
2. **Problem** — generic AI CVs invent; generic templates don’t match the job
3. **How it works** — 5 steps
4. **Features** — career knowledge, job intelligence, scoring, documents, tracking
5. **AI capabilities** — the specialized agents (without sounding like a model list)
6. **Trust** — evidence first, no hallucination, you stay in control, privacy
7. **Who it is for**
8. **FAQ**

---

## 3. Problem / promise

**Problem**

- Generic CVs lose to tailored ones, but rewriting for every vacancy is slow.
- Chat-style tools invent metrics, titles, and skills you cannot defend in an interview.
- Fit is a feeling, not a score you can explain.
- ATS systems need clean structure and real keywords — not stuffing, not graphics-as-text.

**Promise**

Serah customizes every application from *your* evidence. If you have not done it, it will not claim it. If the fit is weak, it tells you — and still lets you decide.

---

## 4. How it works

1. **Build your career knowledge**
   Upload a CV (PDF, DOCX, or text) or paste your history. Serah extracts roles, projects, achievements, skills, education, and more. You review and confirm before anything is treated as verified.

2. **Paste a job description**
   Add a vacancy. Serah parses position details, mandatory vs preferred requirements, responsibilities, competencies, and keywords.

3. **See the intelligence**
   It researches the organization from public sources, tries to identify the hiring context, and maps your evidence to each requirement.

4. **Read an honest score**
   A transparent job-fit score is calculated from structured matches — not guessed by a language model. You see strong matches, gaps, transferable experience, risks, and advantages.

5. **Generate, edit, export**
   Approve the strategy, generate a targeted CV and cover letter, edit anything, regenerate a section, restore a version, and export PDF or DOCX.

---

## 5. Product features

Use these as feature cards or accordion sections.

### Career Knowledge Base

A persistent, structured record of your professional life — not a single uploaded file.

- Profile, employment history, projects, achievements
- Skills (technical, functional, clinical, domain, behavioral, tools, methodologies — uncategorized until evidenced)
- Professional knowledge gained on the job: industry, processes, terminology, regulations, products, and stakeholder environments — kept distinct from skills
- Education, certifications, languages, publications
- Leadership, management, and consulting experience
- Previous applications, outcomes, and lessons learned
- Visual knowledge graph and career timeline
- Duplicate detection (e.g. “Power BI” / “Microsoft Power BI” → one canonical skill)
- Every extracted fact keeps **provenance**: where it came from (document, page, section)

Extracted items start as *needs review*. You confirm, merge, or edit them so generated documents only rely on what you accept.

### Job analysis

Paste a job description. Serah normalizes it into:

- Position information (organization, title, grade, location, contract, deadline, reporting line)
- Mandatory vs preferred requirements (education, experience, skills, languages, certifications, management, domain)
- Responsibilities and competencies
- Keywords classified by type (technical, functional, clinical, domain, organizational, behavioral, tools, methodologies, certifications, or uncategorized)
- Requirement importance: Critical / High / Medium / Low — not every sentence in a JD is equal

### Organization and hiring-team intelligence

For each vacancy, Serah researches publicly available information:

- Mission, strategy, programs, structure, recent announcements
- Digital / data / AI initiatives where relevant
- Culture and leadership priorities from authoritative sources
- Publicly identifiable hiring manager, recruiter, or team lead — only with sufficient confidence

Research prefers official sites and reports over rumor. Every claim is sourced. Private or sensitive personal data is never sought. If a hiring manager cannot be identified confidently, Serah says so instead of inventing a name.

### Evidence-based matching

Each JD requirement is compared with your knowledge base and labeled:

| Status | Meaning |
|---|---|
| Matched | Direct evidence in your career record |
| Partially matched | Some but not full coverage |
| Transferable | Related experience, not claimed as the same role |
| Not matched | A real gap |
| Unknown | Not enough information — never treated as a fail |

Every match cites evidence. Transferable skills stay transferable; the CV will not upgrade them into direct experience.

### Transparent job-fit score

The score is calculated programmatically from those matches. The AI writes the explanation; it does not invent the number.

Default categories (weights are configurable):

| Category | Default weight |
|---|---|
| Mandatory qualifications | 25% |
| Relevant experience | 20% |
| Technical / functional skills | 15% |
| Responsibilities match | 15% |
| Domain knowledge | 10% |
| Leadership / management | 5% |
| Education / certifications | 5% |
| Language / other | 5% |

You also get:

- Overall fit percentage and recommendation (Strong Fit vs Moderate/Weak Fit)
- Per-category breakdown
- Strong matches, partial matches, gaps, transferable experience
- Risks and competitive advantages
- A configurable threshold (default 80%). Below it, Serah asks before generating documents — it never hard-rejects an application. You always decide.

### Application strategy

Before writing documents, Serah proposes:

- How to position you for this specific role
- Which experiences and achievements should get the most space
- Which skills and keywords to use naturally
- What to de-emphasize
- Concerns to address
- What the cover letter should emphasize

You review the strategy, then generate.

### Targeted CV generation

Each CV is built for that vacancy from retrieved evidence, the strategy, and (when available) organization research.

- Truthful and evidence-cited
- Relevant experience prioritized
- ATS-compatible structure and terminology
- No keyword stuffing, hidden text, or unsupported claims
- Optional “View Evidence” on generated bullets — see the source claim, original wording, and document

### Targeted cover letters

The letter is not a CV summary. It explains why this role, why this organization, why you, with the strongest evidence and a professional close. If a hiring manager is confidently identified, tone may align with public team priorities — never with private social activity.

### ATS analysis

ATS analysis is optional. Hide ATS scores in Settings when the profession does not use applicant-tracking systems.


- ATS compatibility score
- Keyword coverage and missing important keywords
- Overuse warnings
- Formatting risks
- Requirement coverage

Optimization uses standard headings, clean text, truthful title alignment, and natural keyword frequency. No tables-as-content tricks, no graphics-as-text, no fake qualifications.

### Career Coach

Ask career questions from a dedicated Coach page (and from a job or application). Answers use only your retrieved evidence, cite the supporting records, and stay in your account. The coach does not invent experience and does not replace the structured workspace.

### Document editor, versions, and export

- Full edit of generated content
- Change template / theme
- Regenerate a single section (summary, experience, skills, cover letter) without rewriting the rest
- Immutable versions for every generate, edit, section regen, and restore
- Export **PDF** and **DOCX**

### Professional themes (CV + matching cover letter)

1. Traditional Executive
2. Modern Professional
3. International Organization / UN
4. Consulting
5. Technology / AI
6. Minimal ATS
7. Academic / Research

Default themes live in Settings; you can still switch theme on a document.

### Application workspace and dashboard

Track each application from draft through submitted, interview, offer, rejected, or withdrawn.

Dashboard at a glance:

- Total applications and pipeline by status
- Average job fit and average ATS score
- Applications this month
- Highest-fit opportunities
- Recent applications

Notes, outcomes, and lessons learned stay on the application and inform later ones.

### Guided first run

Onboarding walks a new user through: upload a CV → confirm profile → paste a job ad → analyze and generate the first strategy, resume, and cover letter.

### Bilingual workspace

- Interface: English or Arabic (RTL)
- Document / content language independent of the UI — used for summaries, matching explanations, strategy, CVs, and cover letters

### Accounts and privacy

- Each account has isolated career, jobs, and applications
- Sign-in with email/password or Google
- Admin manages accounts only — not another person’s career data
- Light / dark appearance, configurable scoring weights and fit threshold

---

## 6. AI capabilities (for a “How the AI works” section)

Serah does not use one giant prompt. Specialized agents run in a coordinated pipeline. You can present this as “eleven specialists, one workspace.”

### Agents

| Agent | What it does for the user |
|---|---|
| **Career Knowledge** | Turns CVs, notes, and past applications into structured, sourced career records |
| **Career Normalization** | Deduplicates skills and entities without merging things that should stay distinct |
| **Job Analysis** | Parses the vacancy into position data, prioritized requirements, responsibilities, and keywords |
| **Organization Research** | Collects sourced public facts about the employer |
| **Hiring Team Research** | Identifies public hiring-context people only when confidence is high |
| **Candidate Matching** | Verdict per requirement, with cited evidence and transferable-skill honesty |
| **Scoring Engine** | Weighted, explainable fit score — calculated, not guessed |
| **Scoring Narrative** | Writes strengths, gaps, risks, and advantages around that score |
| **Application Strategy** | Positioning, emphasis, keywords, and messaging plan |
| **CV Agent** | Job-specific CV from retrieved evidence only |
| **Cover Letter Agent** | Role- and organization-specific letter, not a CV paraphrase |
| **ATS Analysis** | Compatibility, coverage, and formatting risk report |

### Two pipelines users actually see

**Job analysis**
Parse JD → research organization → research hiring context → retrieve your evidence → match requirements → calculate score

**Document generation**
Application strategy → your go/no-go if below threshold → generate CV → validate → generate cover letter → validate → ready for review

Progress is visible while it runs. If research fails, matching and generation can still continue.

### Guardrails worth advertising

These are product claims you can stand behind:

1. **Evidence first** — no invented jobs, skills, metrics, titles, certifications, or education.
2. **Retrieval before generation** — only relevant evidence is sent to the model, not your entire history dumped into a prompt.
3. **Scores are calculated** — the language model does not pick the percentage.
4. **Human in the loop** — below-threshold fit asks before generating; every document is editable and restorable.
5. **Anti-hallucination validation** — claims must cite evidence that exists in your knowledge base; failures are flagged for review.
6. **Source traceability** — “View Evidence” on generated content.
7. **Transferable ≠ direct** — related experience is labeled honestly.
8. **You are never auto-rejected** — the score advises; you decide.
9. **Untrusted content is data** — job ads and web pages cannot override the system’s rules.
10. **Research stays public and sourced** — no scraping of private contact or personal data.

### What the AI will not do

Useful for trust copy and FAQ:

- Will not invent or inflate your experience
- Will not treat a previous job description as proof of your skills
- Will not invent a hiring manager
- Will not personalize letters from private social activity
- Will not hide keywords or stuff them
- Will not lock you out of editing the result

---

## 7. Who it is for

- Professionals who apply to several roles and need each package tailored
- Nurses, teachers, skilled trades, sales, operations, finance, public-sector, and technology candidates — Serah is not a tech-only product
- Candidates targeting UN, NGO, government, consulting, healthcare, education, or academic tracks (dedicated themes)
- People who want an honest gap analysis before spending time on an application
- Bilingual EN/AR job seekers
- Anyone who has been burned by AI CVs that they could not defend in an interview

**Not positioned as:** a job board, an auto-apply bot, or a replacement for the candidate’s judgment.

---

## 8. Ready-to-paste website copy

### Hero headline options

- Career intelligence for every application
- Tailored CVs. Real evidence. No invented experience.
- Know the fit before you write the CV
- From one career history to every job-specific application

### Hero subheads

- Serah analyzes the vacancy, matches your evidence, and drafts an ATS-ready CV and cover letter you can trust in the interview.
- Built by Shortlisted. You stay in control of every claim.

### Feature-grid blurbs (short)

- **Career knowledge, not a file.** Roles, skills, and achievements stay structured and reusable.
- **Job intelligence.** Requirements, employer research, and hiring context in one place.
- **Explainable fit.** A calculated score with matches, gaps, and risks — not a black-box percentage.
- **Documents that cite you.** Targeted CV and cover letter, with evidence behind each claim.
- **ATS without tricks.** Clean structure, honest keywords, compatibility report.
- **You edit last.** Versions, section regen, PDF and DOCX export.

### Trust strip

Evidence first · Retrieval before generation · Explainable scoring · Human in the loop · Privacy-first accounts

### CTA ideas

- Open Serah
- Analyze your first job
- See a sample fit report
- Start with your CV

---

## 9. FAQ (website)

**Does Serah make up experience to fit the job?**
No. Every generated claim has to come from your Career Knowledge Base. If the evidence is not there, the claim is not written. Gaps are shown, not covered up.

**Is the fit score just the AI’s opinion?**
No. Matching is structured; the score is calculated from those matches with configurable weights. The AI only writes the narrative around the number.

**What if my score is below 80%?**
Serah asks whether you want to continue. It will not block you. The threshold is yours to change.

**Can I edit the CV?**
Yes. Edit text, change theme, regenerate one section, or restore an earlier version. Nothing is locked.

**What files can I export?**
PDF and DOCX.

**Does it work in Arabic?**
Yes. The interface is English or Arabic. Generated document language can be set separately.

**Is my career data shared with other users?**
No. Each account only sees its own career, jobs, and applications. Admins manage accounts, not other people’s files.

**Does it apply to jobs for me?**
No. Serah prepares intelligence and documents. You submit the application.

---

## 10. Arabic copy (for a bilingual site)

### اسم المنتج

سرا (Serah) — مساحة الباحث عن عمل من Shortlisted

### جملة واحدة

أدخل مسيرتك المهنية مرة واحدة. لكل شاغر جديد تحصل على تحليل صادق لمدى التطابق، وسيرة ذاتية وخطاب تقديم مبنيين على خبرتك الحقيقية فقط.

### فقرة قصيرة

تحوّل سرا تاريخك المهني إلى قاعدة معرفة قابلة لإعادة الاستخدام، ثم تحلل كل وظيفة: تفكيك الإعلان، بحث المؤسسة، مطابقة الأدلة، ودرجة توافق واضحة. عند المتابعة تُنشئ سيرة ذاتية وخطاب تقديم مخصصين للشاغر — دون اختلاق خبرات — مع إمكانية المراجعة والتعديل والتصدير.

### خطوات العمل

1. ارفع سيرتك أو الصق خبراتك لبناء قاعدة المعرفة المهنية
2. الصق إعلان الوظيفة
3. راجع تحليل المتطلبات وبحث الجهة ودرجة التوافق
4. اعتمد استراتيجية التقديم
5. ولّد السيرة وخطاب التقديم، عدّل، ثم صدّر PDF أو DOCX

### مزايا مختصرة

- قاعدة معرفة مهنية (خبرات، مشاريع، مهارات، تعليم، شهادات)
- تحليل إعلان الوظيفة وترتيب المتطلبات حسب الأهمية
- بحث علني عن المؤسسة وسياق التوظيف مع ذكر المصادر
- مطابقة بالأدلة وتمييز الخبرة القابلة للنقل عن الخبرة المباشرة
- درجة توافق محسوبة وقابلة للشرح — ليست رقماً يخمنه النموذج
- سيرة وخطاب تقديم مخصصان، متوافقان مع أنظمة التتبع (ATS)
- سبعة قوالب مهنية (تنفيذي، حديث، منظمات دولية / الأمم المتحدة، استشارات، تقنية، ATS مبسّط، أكاديمي)
- تعديل كامل، إعادة توليد قسم واحد، إصدارات، وتصدير
- واجهة عربية وإنجليزية، ولغة المستندات مستقلة عن لغة الواجهة
- أنت صاحب القرار دائماً

### ضمانات

لا اختلاق خبرات · كل ادعاء قابل للتتبع إلى دليلك · الدرجة استشارية وليست رفضاً تلقائياً · بيانات كل حساب معزولة

---

## 11. Screenshot / visual suggestions

If the site needs visuals, prioritize in this order:

1. Dashboard — pipeline, average fit, highest-fit jobs
2. Job fit view — score breakdown + requirements matrix
3. Career knowledge graph / timeline
4. Application strategy + document editor with “View Evidence”
5. Onboarding: paste JD → working → first CV ready

Avoid chatbot screenshots; the product is a workspace.

---

## 12. Claims to avoid on the website

Do not say:

- “Guaranteed interviews / offers”
- “Auto-applies to jobs”
- “The AI decides if you should apply” (you decide)
- “Scrapes LinkedIn private data” or “finds the hiring manager’s personal contact”
- Provider-specific branding as the product (models are interchangeable)

Safe alternatives: honest fit analysis, targeted documents from your evidence, interview-defendable claims, ATS-aware formatting.
