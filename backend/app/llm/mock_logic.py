"""Deterministic, offline implementations of every agent task.

Used by MockProvider. These are rule-based heuristics — not random stubs — so
the entire pipeline runs with zero external dependencies and produces stable,
testable results (§56 deterministic fixtures). When a real LLM provider is
configured, the same payloads go to the model instead.
"""
from __future__ import annotations

import json
import re
from collections import Counter

from ..qualification import degree_level, evaluate_qualification_paths, resolve_match_status
from ..services.deadlines import extract_application_deadline, normalize_application_deadline
from ..services.document_postprocess import (
    _date_sort_key,
    relevance_terms,
    relevant_bullets_for_experience,
)

# ── shared helpers ───────────────────────────────────────────────────────────

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "in", "is", "it", "its", "of", "on", "or", "that", "the", "to",
    "with", "you", "your", "we", "our", "will", "this", "these", "those",
    "their", "they", "them", "his", "her", "he", "she", "who", "whom", "which",
    "including", "include", "includes", "such", "other", "others", "etc",
    "ability", "strong", "proven", "excellent", "demonstrated", "experience",
    "experiences", "work", "working", "knowledge", "skills", "skill", "years",
    "year", "minimum", "least", "related", "field", "fields", "within", "across",
    "في", "من", "على", "إلى", "عن", "مع", "هذا", "هذه", "ذلك", "التي", "الذي",
    "كان", "يكون", "هو", "هي", "أو", "أن", "إن", "لا", "ما", "قد", "كل",
    "بعض", "بين", "بعد", "قبل", "خلال", "لدى", "كما", "حيث", "يجب", "الخبرة",
    "العمل", "المهارات", "سنوات", "سنة",
}

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.\-]*|[\u0600-\u06FF]{2,}", re.I)


def output_language(text: str) -> str:
    match = re.search(r"OUTPUT_LANGUAGE:\s*(ar|en)\b", text or "", re.I)
    return match.group(1).lower() if match else "en"


def _loc(user_message: str, en: str, ar: str) -> str:
    return ar if output_language(user_message) == "ar" else en

TECH_LEXICON = {
    "python", "java", "javascript", "typescript", "c#", "c++", "go", "rust",
    "ruby", "php", "swift", "kotlin", "r", "matlab", "scala", "sql", "nosql",
    "postgresql", "mysql", "sqlite", "oracle", "sql server", "mongodb", "redis",
    "elasticsearch", "cassandra", "dynamodb", "power bi", "powerbi", "tableau",
    "excel", "looker", "qlik", "spss", "stata", "sas", "gis", "arcgis", "qgis",
    "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "terraform",
    "jenkins", "git", "github", "gitlab", "jira", "confluence", "sharepoint",
    "office 365", "microsoft 365", "sap", "salesforce", "oracle erp", "workday",
    "react", "angular", "vue", "django", "flask", "fastapi", "spring", "node",
    "node.js", "express", "graphql", "rest", "rest api", "microservices",
    "machine learning", "deep learning", "nlp", "computer vision", "ai",
    "artificial intelligence", "data analysis", "data engineering",
    "data architecture", "data warehouse", "data platform", "etl", "airflow",
    "spark", "hadoop", "kafka", "dbt", "snowflake", "databricks", "pandas",
    "numpy", "tensorflow", "pytorch", "scikit-learn", "llm", "openai",
    "mis", "erp", "crm", "dhis2", "kobo", "odk", "commcare",
}

METHODOLOGIES = {
    "agile", "scrum", "kanban", "lean", "prince2", "pmp", "itil", "devops",
    "ci/cd", "tdd", "waterfall", "saf e", "safe", "design thinking", "okr",
    "results-based management", "logical framework", "theory of change",
    "monitoring and evaluation", "m&e",
}

CERT_TERMS = {
    "pmp", "prince2", "cissp", "cfa", "cpa", "aws certified", "azure certified",
    "scrum master", "csm", "itil foundation", "six sigma", "toefl", "ielts",
}

LANGUAGES = {
    "english", "french", "spanish", "arabic", "العربية", "عربي", "german", "portuguese", "russian",
    "chinese", "mandarin", "turkish", "kurdish", "hindi", "urdu", "swahili",
    "italian", "dutch", "japanese", "korean", "persian", "farsi", "dari", "pashto",
}

BEHAVIORAL = {
    "leadership", "communication", "analytical", "strategic thinking",
    "stakeholder management", "teamwork", "collaboration", "innovation",
    "problem solving", "adaptability", "negotiation", "facilitation",
    "mentoring", "coaching", "project management", "time management",
}

DOMAIN_TERMS = {
    "humanitarian", "development", "ngo", "un", "undp", "unicef", "wfp",
    "health", "education", "finance", "fintech", "banking", "government",
    "public sector", "climate", "protection", "logistics", "supply chain",
    "procurement", "grant management", "digital transformation",
    "warehousing", "freight", "last-mile", "last mile", "tms", "wms",
    "customs", "saas", "subscription", "billing", "revenue operations",
    "revops", "accounts payable", "accounts receivable", "revenue recognition",
    "customer success", "clinical", "pedagogy", "apprenticeship",
    "nursing", "patient care", "acute care", "primary care", "curriculum",
    "classroom", "safeguarding", "electrical", "construction", "hvac",
    "sales", "operations", "retail", "hospitality", "manufacturing",
}

CLINICAL_TERMS = {
    "patient care", "vital signs", "medication administration", "wound care",
    "triage", "electronic health record", "ehr", "emr", "charting", "icu",
    "nursing", "clinical assessment", "infection control", "iv therapy",
}

EDUCATION_TERMS = {
    "lesson planning", "classroom management", "curriculum", "formative assessment",
    "summative assessment", "iep", "differentiated instruction", "pedagogy",
    "safeguarding", "parent communication",
}

TRADE_TERMS = {
    "conduit", "panel", "lockout", "tagout", "nec", "wiring", "troubleshooting",
    "blueprint", "schematic", "voltage", "grounding", "apprenticeship",
}

SALES_OPS_TERMS = {
    "pipeline", "quota", "account management", "crm", "forecasting",
    "territory", "order management", "inventory", "kpis", "customer onboarding",
}

FUNCTIONAL_TERMS = {
    "budgeting", "scheduling", "reporting", "quality assurance", "training",
    "policy", "compliance", "operations", "coordination",
}


def _skill_category(name: str) -> str:
    low = (name or "").strip().lower()
    if not low:
        return "uncategorized"
    if low in LANGUAGES:
        return "language"
    if low in CERT_TERMS:
        return "certifications"
    if low in METHODOLOGIES:
        return "methodology"
    if low in BEHAVIORAL or "leadership" in low:
        return "leadership" if "lead" in low or "mentor" in low else "behavioral"
    if low in TECH_LEXICON:
        return "technical"
    if any(term in low for term in CLINICAL_TERMS) or low in CLINICAL_TERMS:
        return "clinical"
    if any(term in low for term in EDUCATION_TERMS) or low in EDUCATION_TERMS:
        return "functional"
    if any(term in low for term in TRADE_TERMS) or low in TRADE_TERMS:
        return "tools"
    if any(term in low for term in SALES_OPS_TERMS) or low in SALES_OPS_TERMS:
        return "functional"
    if low in FUNCTIONAL_TERMS:
        return "functional"
    if low in DOMAIN_TERMS or any(term in low for term in DOMAIN_TERMS if " " in term or len(term) > 4):
        return "domain"
    return "uncategorized"


RELATED_GROUPS = [
    {"data architecture", "data platform", "data engineering", "database",
     "information architecture", "data warehouse", "etl", "data modeling"},
    {"ai", "artificial intelligence", "machine learning", "ml", "nlp", "llm",
     "data science", "analytics", "predictive"},
    {"power bi", "tableau", "dashboard", "data visualization", "reporting",
     "business intelligence", "bi"},
    {"project management", "programme management", "program management",
     "portfolio management", "pmp", "prince2"},
    {"monitoring and evaluation", "m&e", "results-based management",
     "impact measurement", "logical framework"},
    {"digital transformation", "digitalization", "digitization", "ict",
     "information systems", "mis"},
    {"logistics", "supply chain", "warehousing", "freight", "last mile",
     "last-mile", "tms", "wms"},
    {"saas", "subscription", "billing", "revenue operations", "revops",
     "accounts payable", "accounts receivable", "finance"},
    {"nursing", "patient care", "clinical", "vital signs", "triage",
     "infection control"},
    {"teaching", "curriculum", "lesson planning", "classroom management",
     "pedagogy", "formative assessment"},
    {"electrical", "wiring", "conduit", "lockout", "nec", "troubleshooting"},
    {"sales", "pipeline", "account management", "quota", "crm", "forecasting"},
]


def tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def content_tokens(text: str) -> set[str]:
    toks = {t for t in tokens(text) if t not in STOPWORDS and len(t) > 2}
    lowered = text.lower()
    for term in TECH_LEXICON | METHODOLOGIES | CERT_TERMS | LANGUAGES | BEHAVIORAL | DOMAIN_TERMS:
        if " " in term and term in lowered:
            toks.add(term)
    return toks


def _extract_json_block(user_message: str) -> dict:
    m = re.search(r"```json\s*(.*?)```", user_message, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            return {}
    start, end = user_message.find("{"), user_message.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(user_message[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return {}


def _extract_tag(user_message: str, tag: str) -> str:
    m = re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", user_message, re.DOTALL)
    return m.group(1) if m else ""


def _overlap(a: set[str], b: set[str]) -> float:
    if not a:
        return 0.0
    return len(a & b) / len(a)


def _related_hit(req_text: str, ev_text: str) -> bool:
    rl, el = req_text.lower(), ev_text.lower()
    for group in RELATED_GROUPS:
        if any(term in rl for term in group) and any(term in el for term in group):
            return True
    return False


# ── career extraction ────────────────────────────────────────────────────────

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+\d{1,3}[\s.\-]?)?(?:\(?\d{2,4}\)?[\s.\-]?)?\d{3}[\s.\-]?\d{4}"
)
_LINKEDIN_RE = re.compile(r"https?://(?:www\.)?linkedin\.com/\S+", re.I)
_NAME_LINE_RE = re.compile(
    r"^(?:[A-Z][A-Za-z'`.\-]+(?:\s+[A-Z][A-Za-z'`.\-]+){1,3}"
    r"|[\u0600-\u06FF]{2,}(?:\s+[\u0600-\u06FF]{2,}){0,4})$"
)

_AR_MONTHS = (
    r"يناير|فبراير|مارس|أبريل|ابريل|مايو|يونيو|يوليو|أغسطس|اغسطس|سبتمبر|"
    r"أكتوبر|اكتوبر|نوفمبر|ديسمبر|كانون الثاني|شباط|آذار|نيسان|أيار|ايار|"
    r"حزيران|تموز|آب|أيلول|ايلول|تشرين الأول|تشرين الثاني|كانون الأول"
)
_DATE_RANGE_RE = re.compile(
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{4}"
    r"|\d{4}(?:[-/]\d{1,2})?"
    r"|(?:" + _AR_MONTHS + r")\s*\d{4})"
    r"\s*(?:–|-|—|to|إلى|حتى)\s*"
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{4}"
    r"|\d{4}(?:[-/]\d{1,2})?"
    r"|present|current|now|حتى الآن|الحالي"
    r"|(?:" + _AR_MONTHS + r")\s*\d{4})",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"^\s*[-•*–▪◦]\s+")
_ACHIEVEMENT_WORDS = re.compile(
    r"\b(led|achieved|increased|reduced|delivered|launched|improved|saved|grew|"
    r"won|secured|cut|boosted|doubled|tripled|spearheaded)\b|%|\$|\d+x",
    re.IGNORECASE,
)
_SECTION_HEADS = {
    "experience": re.compile(
        r"(experience|employment|work history|professional history|الخبرة(?:\s*العملية)?|الخبرات)",
        re.I,
    ),
    "education": re.compile(r"^education|academic|التعليم|المؤهلات العلمية", re.I),
    "skills": re.compile(r"skills|competencies|technical proficiencies|المهارات|الكفاءات", re.I),
    "certifications": re.compile(r"certification|licenses|credentials|الشهادات|الاعتمادات", re.I),
    "languages": re.compile(r"languages|اللغات", re.I),
    "publications": re.compile(r"publications|المنشورات|الأبحاث", re.I),
    "projects": re.compile(r"projects|المشاريع", re.I),
}


def _is_heading(line: str) -> str | None:
    stripped = line.strip().strip(":").strip()
    if not stripped or len(stripped) > 60:
        return None
    for section, rx in _SECTION_HEADS.items():
        if rx.search(stripped):
            return section
    return None


def _extract_profile_block(text: str) -> dict:
    """Pull contact/name lines from the top of a CV when present."""
    email_m = _EMAIL_RE.search(text)
    linkedin_m = _LINKEDIN_RE.search(text)
    phone = ""
    for match in _PHONE_RE.finditer(text):
        candidate = match.group(0).strip()
        if email_m and candidate in (email_m.group(0) or ""):
            continue
        digits = re.sub(r"\D", "", candidate)
        if 8 <= len(digits) <= 15:
            phone = candidate
            break

    full_name = ""
    headline = ""
    location = ""
    for raw in text.splitlines()[:12]:
        stripped = raw.strip().strip("|").strip()
        if not stripped or _is_heading(stripped):
            if _is_heading(stripped):
                break
            continue
        if email_m and email_m.group(0) in stripped:
            continue
        if linkedin_m and linkedin_m.group(0) in stripped:
            continue
        if phone and phone in stripped:
            continue
        low = stripped.lower()
        if low.startswith(("tel:", "phone:", "email:", "linkedin:", "location:")):
            if low.startswith("location:"):
                location = stripped.split(":", 1)[1].strip()
            continue
        if not full_name and (_NAME_LINE_RE.match(stripped) or (len(stripped.split()) in (2, 3) and stripped[0].isupper())):
            full_name = stripped
            continue
        if full_name and not headline and 8 < len(stripped) < 90 and not _DATE_RANGE_RE.search(stripped):
            headline = stripped
            continue

    loc_m = re.search(r"(?im)^location:\s*(.+)$", text)
    if loc_m:
        location = loc_m.group(1).strip()

    return {
        "full_name": full_name,
        "headline": headline,
        "summary": "",
        "email": email_m.group(0) if email_m else "",
        "phone": phone,
        "location": location,
        "linkedin": linkedin_m.group(0).rstrip(").,") if linkedin_m else "",
    }


def mock_career_extraction(user_message: str) -> dict:
    text = _extract_tag(user_message, "document") or user_message
    lines = [ln.rstrip() for ln in text.splitlines()]

    experiences: list[dict] = []
    skills: list[dict] = []
    education: list[dict] = []
    certifications: list[dict] = []
    languages: list[dict] = []
    achievements_top: list[str] = []

    section = None
    current_exp: dict | None = None
    pending_header: str | None = None

    def flush_exp():
        nonlocal current_exp
        if current_exp and (current_exp.get("organization") or current_exp.get("job_title")):
            experiences.append(current_exp)
        current_exp = None

    def _start_exp(header: str, start: str, end: str):
        nonlocal current_exp
        flush_exp()
        org, title = header, ""
        for sep in (" at ", " | ", " — ", " – ", " - ", "، ", ", "):
            if sep in header:
                left, right = header.split(sep, 1)
                if sep in (" at ", "، "):
                    title, org = left.strip(), right.strip()
                else:
                    org, title = left.strip(), right.strip()
                break
        current_exp = {
            "organization": org.strip(),
            "job_title": title.strip(),
            "start_date": start,
            "end_date": end,
            "employment_type": "",
            "location": "",
            "responsibilities": [],
            "achievements": [],
            "projects": [],
            "technologies": [],
            "skills": [],
            "domains": [],
            "leadership": [],
            "stakeholders": [],
            "quantified_results": [],
            "confidence": 0.9,
        }

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        head = _is_heading(stripped)
        if head:
            flush_exp()
            pending_header = None
            section = head
            continue

        if section == "experience" or (section is None and _DATE_RANGE_RE.search(stripped)):
            m = _DATE_RANGE_RE.search(stripped)
            if m and not _BULLET_RE.match(stripped):
                header = _DATE_RANGE_RE.sub("", stripped).strip(" |–—-") or (pending_header or "")
                pending_header = None
                _start_exp(header, m.group(1), m.group(2))
                continue
            if _BULLET_RE.match(stripped):
                if current_exp is not None:
                    bullet = _BULLET_RE.sub("", stripped)
                    if _ACHIEVEMENT_WORDS.search(bullet):
                        current_exp["achievements"].append(bullet)
                        if re.search(r"\d", bullet):
                            current_exp["quantified_results"].append(bullet)
                    else:
                        current_exp["responsibilities"].append(bullet)
                    for term in sorted(TECH_LEXICON):
                        if term in bullet.lower() and term not in current_exp["technologies"]:
                            current_exp["technologies"].append(term)
                    for term in sorted(DOMAIN_TERMS, key=len, reverse=True):
                        if term in bullet.lower() and term not in current_exp["domains"]:
                            current_exp["domains"].append(term)
                continue
            # Non-bullet line: long lines continue the current role, short
            # lines are the header of the next role (dates on following line).
            if current_exp is not None and len(stripped) > 60:
                if _ACHIEVEMENT_WORDS.search(stripped):
                    current_exp["achievements"].append(stripped)
                else:
                    current_exp["responsibilities"].append(stripped)
            else:
                if current_exp is not None:
                    flush_exp()
                pending_header = stripped
            continue

        if section == "skills":
            for item in re.split(r"[,;•\n]", stripped):
                item = item.strip(" -•*")
                if item and len(item) < 60:
                    skills.append({"name": item, "category": _skill_category(item)})
            continue

        if section == "education":
            education.append({
                "institution": stripped.strip(" -•*"),
                "degree": "",
                "field_of_study": "",
                "start_date": "",
                "end_date": "",
            })
            continue

        if section == "certifications":
            certifications.append({"name": stripped.strip(" -•*"), "issuer": "", "issue_date": ""})
            continue

        if section == "languages":
            parts = re.split(r"[,;]", stripped)
            for part in parts:
                part = part.strip(" -•*")
                if not part:
                    continue
                m = re.match(r"([A-Za-z]+)\s*[:\-(]?\s*(.*)", part)
                if m:
                    languages.append({"language": m.group(1), "proficiency": m.group(2).strip(")")})
            continue

        if section == "projects" and current_exp is not None:
            current_exp["projects"].append(stripped.strip(" -•*"))
            continue

    flush_exp()

    professional_knowledge: list[dict] = []
    seen_knowledge: set[str] = set()
    KIND_HINTS = {
        "logistics": "industry",
        "supply chain": "industry",
        "warehousing": "process",
        "freight": "process",
        "last-mile": "process",
        "last mile": "process",
        "customs": "regulation",
        "saas": "industry",
        "subscription": "process",
        "billing": "process",
        "revenue operations": "business_function",
        "revops": "business_function",
        "accounts payable": "process",
        "accounts receivable": "process",
        "revenue recognition": "regulation",
        "customer success": "business_function",
        "humanitarian": "industry",
        "digital transformation": "domain",
    }
    for exp in experiences:
        for domain in exp.get("domains") or []:
            key = domain.lower()
            if key in seen_knowledge:
                continue
            seen_knowledge.add(key)
            professional_knowledge.append(
                {
                    "name": domain,
                    "kind": KIND_HINTS.get(key, "domain"),
                    "summary": f"Acquired while working as {exp.get('job_title') or 'a professional'} at {exp.get('organization') or 'the organization'}.",
                    "depth": "applied",
                    "organization_hint": exp.get("organization") or "",
                    "job_title_hint": exp.get("job_title") or "",
                    "how_acquired": f"Role exposure in {exp.get('job_title') or 'this role'}",
                    "how_applied": "",
                    "acquisition_mode": "acquired_through_role",
                    "confidence": 0.7,
                }
            )
            exp.setdefault("professional_knowledge", []).append(
                {"name": domain, "kind": KIND_HINTS.get(key, "domain"), "depth": "applied"}
            )
        # Also scan the whole role text for domain terms not already captured
        blob = " ".join(
            [exp.get("job_title") or "", exp.get("organization") or ""]
            + (exp.get("responsibilities") or [])
            + (exp.get("achievements") or [])
        ).lower()
        for term in DOMAIN_TERMS:
            if term in blob and term not in (d.lower() for d in exp.get("domains") or []):
                exp.setdefault("domains", []).append(term)
                if term not in seen_knowledge:
                    seen_knowledge.add(term)
                    professional_knowledge.append(
                        {
                            "name": term,
                            "kind": KIND_HINTS.get(term, "domain"),
                            "summary": f"Exposed to {term} at {exp.get('organization') or 'this employer'}.",
                            "depth": "awareness" if term not in blob[:80] else "applied",
                            "organization_hint": exp.get("organization") or "",
                            "job_title_hint": exp.get("job_title") or "",
                            "how_acquired": "Inferred from role description",
                            "how_applied": "",
                            "acquisition_mode": "adjacent_exposure",
                            "confidence": 0.6,
                        }
                    )

    # de-duplicate skills preserving order
    seen = set()
    unique_skills = []
    for s in skills:
        key = s["name"].lower()
        if key not in seen:
            seen.add(key)
            unique_skills.append(s)

    return {
        "experiences": experiences,
        "skills": unique_skills,
        "education": education,
        "certifications": certifications,
        "languages": languages,
        "achievements": achievements_top,
        "publications": [],
        "professional_knowledge": professional_knowledge,
        "profile": _extract_profile_block(text),
        "summary": "",
        "notes": ["Extracted by deterministic offline parser; review before marking verified."],
    }


# ── career normalization ─────────────────────────────────────────────────────

_GENERIC_SUFFIXES = ("programming", "development", "language", "software", "tool", "tools")


def _norm_key(name: str) -> str:
    key = re.sub(r"[^a-z0-9+#]", "", name.lower())
    for suffix in _GENERIC_SUFFIXES:
        if key.endswith(suffix) and len(key) > len(suffix) + 2:
            key = key[: -len(suffix)]
    for prefix in ("microsoft", "ms"):
        if key.startswith(prefix) and len(key) > len(prefix) + 2:
            key = key[len(prefix):]
    return key


def mock_career_normalization(user_message: str) -> dict:
    payload = _extract_json_block(user_message)
    items = payload.get("items", [])
    groups: dict[str, list[str]] = {}
    categories: dict[str, str] = {}
    for item in items:
        name = item.get("name", "").strip()
        if not name:
            continue
        key = _norm_key(name)
        groups.setdefault(key, []).append(name)
        categories.setdefault(key, item.get("category") or _skill_category(name) or "uncategorized")
    canonical = []
    for key, names in sorted(groups.items()):
        # canonical = the most frequent, then the shortest clean form
        counts = Counter(names)
        best = sorted(counts.items(), key=lambda kv: (-kv[1], len(kv[0])))[0][0]
        canonical.append({
            "canonical_name": best,
            "aliases": sorted(set(names) - {best}),
            "category": categories[key],
        })
    return {"canonical": canonical}


# ── career reconciliation ────────────────────────────────────────────────────


def _extract_all_json_blocks(user_message: str) -> list:
    blocks = []
    for m in re.finditer(r"```json\s*(.*?)```", user_message, re.DOTALL):
        try:
            blocks.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            continue
    return blocks


def _org_key(name: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    for alias, canon in (
        ("msft", "microsoft"),
        ("goog", "google"),
        ("fb", "meta"),
        ("amazonwebservices", "aws"),
    ):
        if key == alias:
            return canon
    return key


def _best_experience_match(extracted: dict, existing: list[dict]) -> dict | None:
    org = _org_key(extracted.get("organization") or extracted.get("payload", {}).get("organization", ""))
    title = (extracted.get("job_title") or extracted.get("payload", {}).get("job_title", "")).lower()
    if not org:
        return None
    candidates = [e for e in existing if e.get("entity_type") == "experience" and _org_key(e.get("organization", "")) == org]
    if not candidates:
        return None
    if title:
        titled = [c for c in candidates if title and (title in (c.get("job_title") or "").lower() or (c.get("job_title") or "").lower() in title)]
        if titled:
            return titled[0]
    return candidates[0]


def _best_name_match(name: str, existing: list[dict], entity_type: str) -> dict | None:
    key = _norm_key(name)
    if not key:
        return None
    best = None
    best_score = 0
    for e in existing:
        if e.get("entity_type") != entity_type:
            continue
        other = _norm_key(e.get("name") or e.get("label") or e.get("description") or "")
        if not other:
            continue
        if key == other or key in other or other in key:
            score = min(len(key), len(other)) / max(len(key), len(other))
            if score > best_score:
                best_score = score
                best = e
    return best if best_score >= 0.5 else None


def mock_career_reconciliation(user_message: str) -> dict:
    blocks = _extract_all_json_blocks(user_message)
    existing: list[dict] = []
    extracted: list[dict] = []
    if len(blocks) >= 2:
        existing = blocks[0] if isinstance(blocks[0], list) else blocks[0].get("existing", [])
        extracted = blocks[1] if isinstance(blocks[1], list) else blocks[1].get("extracted", [])
    elif len(blocks) == 1 and isinstance(blocks[0], dict):
        existing = blocks[0].get("existing", [])
        extracted = blocks[0].get("extracted", [])

    proposals: list[dict] = []
    for item in extracted:
        entity_type = item.get("entity_type", "experience")
        payload = item.get("payload") or item
        action = "create"
        target_id = None
        target_label = ""
        confidence = 0.55
        reasoning = "No clear match in existing knowledge base."

        if entity_type == "experience":
            match = _best_experience_match({"organization": payload.get("organization", ""), "job_title": payload.get("job_title", "")}, existing)
            if match:
                action = "merge"
                target_id = match.get("id")
                target_label = match.get("label") or f"{match.get('job_title', '')} at {match.get('organization', '')}"
                confidence = 0.85
                reasoning = f"Same organization ({match.get('organization')}); treating as additional detail for existing role."
        elif entity_type == "project":
            match = _best_name_match(payload.get("name") or payload.get("description") or "", existing, "project")
            if match:
                action = "merge"
                target_id = match.get("id")
                target_label = match.get("label") or match.get("name") or ""
                confidence = 0.8
                reasoning = "Project name closely matches an existing project."
        elif entity_type == "achievement":
            text = payload.get("description") or payload.get("text") or ""
            match = _best_name_match(text, existing, "achievement")
            if match:
                action = "merge"
                target_id = match.get("id")
                target_label = match.get("label") or (match.get("description") or "")[:80]
                confidence = 0.75
                reasoning = "Achievement text overlaps an existing achievement."

        proposals.append({
            "proposal_id": "",
            "entity_type": entity_type,
            "action": action,
            "target_id": target_id,
            "target_label": target_label,
            "confidence": confidence,
            "reasoning": reasoning,
            "payload": payload,
        })
    return {"proposals": proposals}


# ── JD analysis ──────────────────────────────────────────────────────────────

_FIELD_RES = [
    (re.compile(r"^(organization|organisation|company|employer|الجهة|الشركة|المنظمة)\s*[:\-]\s*(.+)$", re.I), "organization"),
    (re.compile(r"^(job\s*title|position(?:\s*title)?|title|role|المسمى(?:\s*الوظيفي)?|الوظيفة)\s*[:\-]\s*(.+)$", re.I), "job_title"),
    (re.compile(r"^(location|duty\s*station|based\s*in|الموقع|مكان\s*العمل)\s*[:\-]\s*(.+)$", re.I), "location"),
    (re.compile(r"^(department|division|unit|القسم|الدائرة)\s*[:\-]\s*(.+)$", re.I), "department"),
    (re.compile(r"^(team|الفريق)\s*[:\-]\s*(.+)$", re.I), "team"),
    (re.compile(r"^(contract(?:\s*type)?|employment\s*type|نوع\s*العقد)\s*[:\-]\s*(.+)$", re.I), "contract_type"),
    (re.compile(r"^(duration|contract\s*duration|المدة)\s*[:\-]\s*(.+)$", re.I), "duration"),
    (re.compile(
        r"^(?:application\s+)?(deadline|closing(?:\s*date)?|close\s*date|"
        r"last\s*date(?:\s*to\s*apply)?|due\s*date|apply\s*(?:by|before|until)|"
        r"آخر\s*موعد(?:\s*للتقديم)?|تاريخ\s*الإغلاق)"
        r"\s*[:\-]\s*(.+)$",
        re.I,
    ), "deadline"),
    (re.compile(r"^(grade|level|seniority|الدرجة|المستوى)\s*[:\-]\s*(.+)$", re.I), "grade_level"),
    (re.compile(r"^(reports?\s*to|reporting\s*line|يرفع\s*إلى)\s*[:\-]\s*(.+)$", re.I), "reporting_line"),
]

_JD_SECTIONS = {
    "responsibilities": re.compile(
        r"responsibilit|duties|what you('| wi)ll do|key (functions|tasks)|role overview|your role|المسؤوليات|المهام",
        re.I,
    ),
    "requirements": re.compile(
        r"requirement|qualification|what we('re| are) looking for|who you are|your profile|skills (and|&) experience|experience (and|&) skills|must.have|المتطلبات|المؤهلات",
        re.I,
    ),
    "preferred": re.compile(r"preferred|desirable|nice.to.have|an asset|a plus|advantageous|bonus|المفضل|يفضل", re.I),
    "education": re.compile(r"^education|التعليم", re.I),
    "about": re.compile(r"about (us|the|our)|who we are|نبذة|عن\s*(الجهة|المنظمة)", re.I),
    "benefits": re.compile(r"we offer|benefits|compensation|what we provide|المزايا", re.I),
}

_PREFERRED_HINTS = re.compile(
    r"preferred|desirable|nice.to.have|an asset|a plus|advantageous|would be|ideally|يفضل|المفضل",
    re.I,
)
_MANDATORY_HINTS = re.compile(r"\bmust\b|required|essential|minimum|at least|mandatory|مطلوب|إلزامي|ضروري", re.I)


def _classify_requirement(text: str) -> str:
    low = text.lower()
    if re.search(r"degree|bachelor|master'?s|phd|doctorate|diploma|university|academic|بكالوريوس|ماجستير|دكتوراه|ثانوية|توجيهي", low):
        return "education"
    if re.search(r"\d+\s*\+?\s*years?|years? of|سنوات", low):
        return "experience"
    if any(lang in low for lang in LANGUAGES) and re.search(r"fluen|proficien|knowledge of|native|working", low):
        return "language"
    if re.search(r"certif|pmp|prince2|cissp|cfa\b|cpa\b", low):
        return "certification"
    if re.search(r"manage|supervis|lead(ing)? (a )?team|people management|staff management|mentor", low):
        return "management"
    if any(term in low for term in BEHAVIORAL):
        return "competency"
    if any(term in low for term in TECH_LEXICON):
        return "technical_skill"
    if any(term in low for term in DOMAIN_TERMS):
        return "domain"
    return "functional"


def _importance(text: str, req_type: str, title_tokens: set[str]) -> str:
    low = text.lower()
    if req_type == "mandatory":
        if _MANDATORY_HINTS.search(low):
            return "CRITICAL"
        if title_tokens and _overlap(set(tokens(low)) - STOPWORDS, title_tokens) > 0:
            return "CRITICAL"
        return "HIGH"
    if req_type == "preferred":
        return "MEDIUM"
    return "LOW"


def _req_keywords(text: str) -> list[str]:
    low = text.lower()
    found = [t for t in sorted(TECH_LEXICON | METHODOLOGIES | CERT_TERMS | CLINICAL_TERMS | EDUCATION_TERMS | TRADE_TERMS | SALES_OPS_TERMS) if t in low]
    return found[:8]


_YEAR_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
}

_DEGREE_RE = re.compile(
    r"\b("
    r"phd|doctor(?:al|ate)?|"
    r"master'?s?|mba|advanced(?:\s+university)?\s+degree|"
    r"bachelor'?s?|undergraduate|"
    r"first[- ]level\s+university(?:\s+degree)?|"
    r"first\s+university\s+degree|"
    r"university\s+degree|"
    r"associate|"
    r"high\s+school(?:\s+diploma)?|"
    r"secondary(?:\s+school)?(?:\s+(?:degree|diploma|education))?|"
    r"diploma"
    r")\b",
    re.I,
)

_YEAR_TOKEN = r"\d+(?:\.\d+)?|" + "|".join(_YEAR_WORDS)
_YEAR_RE = re.compile(
    rf"(?:(?:(?P<n1>{_YEAR_TOKEN})\s+)?additional\s+(?:(?P<n2>{_YEAR_TOKEN})\s+)?years?"
    rf"|(?:minimum\s+|at\s+least\s+)?(?P<n3>{_YEAR_TOKEN})\+?\s+years?)",
    re.I,
)

_ALT_MARKERS_RE = re.compile(
    r"\b(?:or|alternatively|in lieu of|may be accepted|equivalent combination)\b",
    re.I,
)
_ALT_SPLIT_RE = re.compile(
    r"\s*(?:,?\s*\bor\b|,?\s*\balternatively\b|(?<=\.)\s+|;\s*)\s*",
    re.I,
)
_EDU_TERM_STOP = {
    "relevant", "experience", "degree", "university", "bachelor", "master",
    "phd", "doctorate", "secondary", "school", "diploma", "education",
    "advanced", "equivalent",
}


def _parse_year_token(token: str | None) -> float | None:
    if not token:
        return None
    lowered = token.lower()
    if lowered in _YEAR_WORDS:
        return float(_YEAR_WORDS[lowered])
    try:
        return float(lowered)
    except ValueError:
        return None


def _canonical_degree_level(text: str) -> str:
    rank = degree_level(text)
    lowered = text.lower()
    if rank >= 5:
        return "phd"
    if rank == 4:
        return "master"
    if rank == 3:
        return "bachelor"
    if rank == 2:
        return "associate" if "associate" in lowered else "diploma"
    if rank == 1:
        return "secondary"
    return ""


def _clause_degree(text: str) -> str:
    match = _DEGREE_RE.search(text)
    return _canonical_degree_level(match.group(1)) if match else ""


def _clause_years(text: str) -> tuple[float | None, bool]:
    match = _YEAR_RE.search(text)
    if not match:
        return None, False
    additional = "additional" in match.group(0).lower()
    for key in ("n1", "n2", "n3"):
        parsed = _parse_year_token(match.group(key))
        if parsed is not None:
            return parsed, additional
    return None, False


def _experience_predicate(years: float, text: str) -> dict:
    terms = [term for term in _req_keywords(text) if term not in _EDU_TERM_STOP]
    return {
        "kind": "relevant_experience",
        "minimum_years": years,
        "value": "",
        "terms": terms,
    }


def _degree_predicate(level: str) -> dict:
    return {
        "kind": "degree_level",
        "minimum_level": level,
        "value": "",
        "terms": [],
    }


def _route_label(level: str, years: float | None) -> str:
    if level and years is not None:
        return f"{level.title()} plus experience route"
    if level:
        return f"{level.title()} route"
    return "Experience route"


def _qualification_paths(text: str) -> list[dict]:
    """Extract only explicit degree/years predicates from qualification prose."""
    protected = re.sub(r"\bor equivalent\b", " equivalent", text.replace("’", "'"), flags=re.I)
    has_alternative = bool(_ALT_MARKERS_RE.search(protected))
    stripped = re.sub(r"\bin lieu of\b.*", "", protected, flags=re.I)
    clauses = (
        [part.strip(" ,.") for part in _ALT_SPLIT_RE.split(stripped) if part.strip(" ,.")]
        if has_alternative
        else [stripped.strip(" ,.")]
    )

    parsed: list[dict] = []
    for clause in clauses:
        clause = re.sub(r"\bmay (?:also )?be accepted\b.*", "", clause, flags=re.I).strip(" ,.")
        if not clause:
            continue
        level = _clause_degree(clause)
        years, additional = _clause_years(clause)
        if not level and years is None:
            continue
        parsed.append({"level": level, "years": years, "additional": additional, "clause": clause})
    if not parsed:
        return []

    baseline = next(
        (item["years"] for item in parsed if item["years"] is not None and not item["additional"]),
        None,
    )
    routes: list[dict] = []
    seen_levels: set[str] = set()
    for item in parsed:
        years = item["years"]
        if years is not None and item["additional"]:
            years = (baseline or 0.0) + years
        if item["level"] and item["level"] in seen_levels:
            continue
        if item["level"]:
            seen_levels.add(item["level"])
        predicates = []
        if item["level"]:
            predicates.append(_degree_predicate(item["level"]))
        if years is not None:
            predicates.append(_experience_predicate(years, item["clause"]))
        if predicates:
            routes.append({"label": _route_label(item["level"], years), "predicates": predicates})
    return routes[:3] if has_alternative else routes[:1]


def mock_jd_analysis(user_message: str) -> dict:
    jd = _extract_tag(user_message, "job_description") or user_message
    lines = [ln.rstrip() for ln in jd.splitlines()]

    position = {
        "organization": "", "department": "", "team": "", "job_title": "",
        "grade_level": "", "location": "", "contract_type": "", "duration": "",
        "deadline": "", "remote_policy": "", "reporting_line": "",
    }
    requirements: list[dict] = []
    responsibilities: list[str] = []
    competencies: set[str] = set()
    keyword_map: dict[str, str] = {}

    section = None
    first_text_line = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        matched_field = False
        for rx, field in _FIELD_RES:
            m = rx.match(stripped)
            if m:
                position[field] = m.group(2).strip()
                matched_field = True
                break
        if matched_field:
            continue

        bullet = _BULLET_RE.sub("", stripped)
        is_bullet = bool(_BULLET_RE.match(stripped)) or bool(re.match(r"^\d+[.)]\s+", stripped))
        bullet = re.sub(r"^\d+[.)]\s+", "", bullet)

        head = None
        candidate = stripped.strip(":").strip()
        if not is_bullet and len(candidate) <= 70:
            for sec, rx in _JD_SECTIONS.items():
                if rx.search(candidate):
                    head = sec
                    break
        if head:
            section = head
            continue

        if not first_text_line and len(stripped) < 90 and not is_bullet:
            first_text_line = stripped

        if section == "responsibilities" and (is_bullet or len(stripped) > 30):
            responsibilities.append(bullet)
        elif section in ("requirements", "preferred") and (is_bullet or len(stripped) > 30):
            req_type = "preferred" if (section == "preferred" or _PREFERRED_HINTS.search(bullet)) else "mandatory"
            requirements.append({
                "text": bullet,
                "category": _classify_requirement(bullet),
                "requirement_type": req_type,
                "importance": "",  # filled below once title is known
                "keywords": _req_keywords(bullet),
                "qualification_paths": _qualification_paths(bullet),
            })
        elif section == "education" and (is_bullet or len(stripped) > 20):
            requirements.append({
                "text": bullet,
                "category": "education",
                "requirement_type": "preferred" if _PREFERRED_HINTS.search(bullet) else "mandatory",
                "importance": "",
                "keywords": [],
                "qualification_paths": _qualification_paths(bullet),
            })

    if not position["job_title"] and first_text_line:
        position["job_title"] = first_text_line.strip()
    if not position["organization"]:
        m = re.search(r"\b(?:at|with|join)\s+([A-Z][A-Za-z0-9&.,' ]{2,60})", jd)
        if m:
            position["organization"] = m.group(1).strip().rstrip(".,;")
    position["deadline"] = (
        normalize_application_deadline(position.get("deadline", ""))
        or extract_application_deadline(jd)
    )

    low_jd = jd.lower()
    if re.search(r"\bremote\b", low_jd):
        position["remote_policy"] = "hybrid" if "hybrid" in low_jd else "remote"
    elif "on-site" in low_jd or "onsite" in low_jd:
        position["remote_policy"] = "on-site"

    title_tokens = set(tokens(position["job_title"])) - STOPWORDS
    for req in requirements:
        if not req["importance"]:
            req["importance"] = _importance(req["text"], req["requirement_type"], title_tokens)

    # competencies
    for term in sorted(BEHAVIORAL):
        if term in low_jd:
            competencies.add(term)

    # classified keywords
    for term in sorted(TECH_LEXICON):
        if term in low_jd:
            keyword_map[term] = "technical"
    for term in sorted(METHODOLOGIES):
        if term in low_jd:
            keyword_map[term] = "methodologies"
    for term in sorted(CERT_TERMS):
        if term in low_jd:
            keyword_map[term] = "certifications"
    for term in competencies:
        keyword_map.setdefault(term, "behavioral")
    for term in sorted(CLINICAL_TERMS | EDUCATION_TERMS | TRADE_TERMS | SALES_OPS_TERMS):
        if term in low_jd:
            keyword_map.setdefault(term, _skill_category(term))
    for term in sorted(DOMAIN_TERMS):
        if re.search(rf"\b{re.escape(term)}\b", low_jd):
            keyword_map.setdefault(term, "domain")

    keywords = [{"term": t, "classification": c} for t, c in sorted(keyword_map.items())]

    summary_bits = []
    if position["job_title"]:
        summary_bits.append(f"Role: {position['job_title']}")
    if position["organization"]:
        summary_bits.append(f"at {position['organization']}")
    n_mand = sum(1 for r in requirements if r["requirement_type"] == "mandatory")
    summary_bits.append(f"{n_mand} mandatory requirements, {len(responsibilities)} responsibilities extracted")

    return {
        "position": position,
        "requirements": requirements,
        "responsibilities": responsibilities,
        "competencies": sorted(competencies),
        "keywords": keywords,
        "summary": " — ".join(summary_bits),
    }


# ── organization research ────────────────────────────────────────────────────

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def mock_organization_research(user_message: str) -> dict:
    payload = _extract_json_block(user_message)
    snippets = payload.get("snippets", [])
    organization = payload.get("organization", "")
    if not snippets:
        return {
            "organization": organization,
            "website": "",
            "claims": [],
            "unavailable": True,
            "note": "Research unavailable: no public sources retrieved.",
        }
    claims = []
    for snip in snippets:
        text = snip.get("text", "")
        source_type = snip.get("source_type", "other")
        confidence = {"official": "HIGH", "institutional": "MEDIUM", "news": "MEDIUM"}.get(source_type, "LOW")
        picked = 0
        for sent in _SENT_SPLIT.split(text):
            sent = sent.strip()
            if not sent or len(sent) < 40 or len(sent) > 400:
                continue
            low = sent.lower()
            if any(k in low for k in ("mission", "strategy", "strategic", "initiative", "program", "digital", "vision", "priority", "priorities", "announc", "launch")):
                claims.append({
                    "claim": sent,
                    "category": "strategy",
                    "source_url": snip.get("url", ""),
                    "source_type": source_type,
                    "publication_date": snip.get("published_at", ""),
                    "confidence": confidence,
                    "relevance_to_job": payload.get("job_title", ""),
                })
                picked += 1
            if picked >= 2:
                break
    return {
        "organization": organization,
        "website": snippets[0].get("url", "") if snippets else "",
        "claims": claims[:12],
        "unavailable": False,
        "note": "",
    }


# ── hiring manager research ──────────────────────────────────────────────────

_NAME_ROLE_RE = re.compile(
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*(?:,|—|-|–|is)\s+(?:the\s+)?"
    r"((?:Director|Head|Chief|Manager|Lead|Officer|Coordinator)[^.,;\n]{0,80})",
)


def mock_hiring_research(user_message: str) -> dict:
    payload = _extract_json_block(user_message)
    snippets = payload.get("snippets", [])
    people = []
    seen = set()
    for snip in snippets:
        for m in _NAME_ROLE_RE.finditer(snip.get("text", "")):
            name, role = m.group(1).strip(), m.group(2).strip()
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            people.append({
                "name": name,
                "role": role,
                "confidence": "MEDIUM",
                "evidence": [snip.get("url", "") or snip.get("title", "")],
                "profile_url": snip.get("url", ""),
            })
    if not people:
        return {
            "hiring_manager": None,
            "recruiter": None,
            "other_people": [],
            "team_insights": [],
            "identified": False,
            "note": "Hiring manager not identified with sufficient confidence.",
        }
    return {
        "hiring_manager": people[0],
        "recruiter": None,
        "other_people": people[1:],
        "team_insights": [],
        "identified": True,
        "note": "",
    }


# ── candidate matching ───────────────────────────────────────────────────────


def _structured_fact_items(structured_facts: dict, req_id: str) -> list[dict]:
    if not isinstance(structured_facts, dict):
        return []
    scoped = structured_facts.get(req_id, structured_facts)
    if not isinstance(scoped, dict):
        return []
    items: list[dict] = []
    for value in scoped.values():
        if isinstance(value, list):
            items.extend(item for item in value if isinstance(item, dict))
    return items


def _merge_evidence(*groups: list | None) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple] = set()
    for group in groups:
        for ev in group or []:
            if not isinstance(ev, dict):
                continue
            key = (ev.get("entity_type"), ev.get("entity_id") or ev.get("text"))
            if key in seen:
                continue
            seen.add(key)
            out.append(ev)
    return out


def mock_candidate_matching(user_message: str) -> dict:
    payload = _extract_json_block(user_message)
    requirements = payload.get("requirements", [])
    evidence = payload.get("evidence", [])
    evidence_by_requirement = payload.get("evidence_by_requirement", {})
    structured_facts = payload.get("structured_facts", {})

    matches = []
    for req in requirements:
        req_id = req.get("id", "")
        scoped = evidence_by_requirement.get(req_id)
        req_evidence = _merge_evidence(
            scoped if scoped else evidence,
            _structured_fact_items(structured_facts, req_id),
        )
        ev_tokens = [(ev, content_tokens(ev.get("text", ""))) for ev in req_evidence]
        evaluation = evaluate_qualification_paths(
            req.get("qualification_paths", []),
            structured_facts.get(req.get("id", ""), structured_facts),
        )
        if evaluation.get("status") == "MATCHED":
            evidence_by_id = {ev.get("entity_id"): ev for ev in req_evidence}
            supporting = [
                {
                    "entity_type": evidence_by_id[eid].get("entity_type", ""),
                    "entity_id": eid,
                    "evidence": evidence_by_id[eid].get("text", "")[:300],
                    "source": evidence_by_id[eid].get("verification_status", ""),
                }
                for eid in evaluation.get("evidence_ids", [])
                if eid in evidence_by_id
            ]
            matches.append({
                "requirement_id": req.get("id", ""),
                "status": "MATCHED",
                "evidence": supporting,
                "explanation": _loc(
                    user_message,
                    "Satisfied an alternative qualification path.",
                    "تم استيفاء مسار تأهيل بديل.",
                ),
                "confidence": 0.95,
                "match_kind": "direct",
                "qualification_evaluation": evaluation,
            })
            continue
        req_toks = content_tokens(req.get("text", ""))
        if not req_evidence:
            status = resolve_match_status(evaluation, "UNKNOWN")
            matches.append({
                "requirement_id": req.get("id", ""),
                "status": status,
                "evidence": [],
                "explanation": _loc(
                    user_message,
                    "No career evidence available to evaluate this requirement.",
                    "لا توجد أدلة مهنية لتقييم هذا المتطلب.",
                ),
                "confidence": 0.0,
                "match_kind": "direct",
                "qualification_evaluation": evaluation or {},
            })
            continue
        scored = sorted(
            ((ev, _overlap(req_toks, etoks)) for ev, etoks in ev_tokens),
            key=lambda x: x[1],
            reverse=True,
        )
        best_ev, best = scored[0]
        supporting = [
            {
                "entity_type": ev.get("entity_type", ""),
                "entity_id": ev.get("entity_id", ""),
                "evidence": ev.get("text", "")[:300],
                "source": ev.get("verification_status", ""),
            }
            for ev, sc in scored[:3]
            if sc >= 0.15
        ]
        transferable = any(_related_hit(req.get("text", ""), ev.get("text", "")) for ev, _ in scored[:5])

        if best >= 0.55:
            status, kind = "MATCHED", "direct"
            conf = min(0.99, 0.55 + best / 2)
            expl = _loc(
                user_message,
                f"Direct evidence found in {best_ev.get('entity_type', 'record')}.",
                f"وُجد دليل مباشر في {best_ev.get('entity_type', 'record')}.",
            )
        elif best >= 0.30:
            status, kind = "PARTIALLY_MATCHED", "direct"
            conf = 0.4 + best / 2
            expl = _loc(
                user_message,
                "Partial coverage: related evidence exists but does not fully cover the requirement.",
                "تغطية جزئية: توجد أدلة ذات صلة لكنها لا تغطي المتطلب بالكامل.",
            )
        elif transferable:
            status, kind = "TRANSFERABLE", "transferable"
            conf = 0.45
            expl = _loc(
                user_message,
                "No direct evidence; closely related transferable experience identified.",
                "لا دليل مباشر؛ وُجدت خبرة قريبة قابلة للنقل.",
            )
        else:
            status, kind = "NOT_MATCHED", "direct"
            conf = 0.7
            expl = _loc(
                user_message,
                "No supporting evidence found in the career knowledge base.",
                "لم يُعثر على دليل داعم في قاعدة المعرفة المهنية.",
            )
        status = resolve_match_status(evaluation, status)
        matches.append({
            "requirement_id": req.get("id", ""),
            "status": status,
            "evidence": supporting if status != "NOT_MATCHED" else [],
            "explanation": expl,
            "confidence": round(conf, 2),
            "match_kind": kind,
            "qualification_evaluation": evaluation or {},
        })
    return {"matches": matches}


# ── scoring narrative ────────────────────────────────────────────────────────


def mock_scoring(user_message: str) -> dict:
    payload = _extract_json_block(user_message)
    matches = payload.get("matches", [])
    overall = payload.get("overall_score", 0.0)

    # Strength/gap lists are derived programmatically by the scoring engine;
    # the narrative only supplies risks, advantages and the explanation.
    counts = {"MATCHED": 0, "PARTIALLY_MATCHED": 0, "TRANSFERABLE": 0, "NOT_MATCHED": 0, "UNKNOWN": 0}
    strong_texts = []
    for m in matches:
        status = m.get("status", "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1
        if status == "MATCHED":
            strong_texts.append(m.get("requirement_text", ""))

    risks = []
    if counts["NOT_MATCHED"]:
        risks.append(_loc(
            user_message,
            f"{counts['NOT_MATCHED']} requirement(s) have no supporting evidence.",
            f"{counts['NOT_MATCHED']} متطلب/متطلبات بلا دليل داعم.",
        ))
    if counts["UNKNOWN"]:
        risks.append(_loc(
            user_message,
            f"{counts['UNKNOWN']} requirement(s) could not be evaluated (insufficient data).",
            f"{counts['UNKNOWN']} متطلب/متطلبات تعذر تقييمها بسبب نقص البيانات.",
        ))
    advantages = strong_texts[:3]

    explanation = _loc(
        user_message,
        (
            f"Overall fit is {overall:.0%}. "
            f"{counts['MATCHED']} requirement(s) are directly matched by evidence, "
            f"{counts['PARTIALLY_MATCHED']} partially matched, {counts['TRANSFERABLE']} covered by transferable "
            f"experience, and {counts['NOT_MATCHED']} gap(s) identified. "
            "Domain and process knowledge is scored separately from skills and tools."
        ),
        (
            f"الملاءمة الإجمالية {overall:.0%}. "
            f"{counts['MATCHED']} متطلب مطابق مباشرة بالأدلة، "
            f"{counts['PARTIALLY_MATCHED']} مطابق جزئياً، {counts['TRANSFERABLE']} مغطى بخبرة قابلة للنقل، "
            f"و{counts['NOT_MATCHED']} فجوة/فجوات. "
            "تُقيَّم معرفة المجال والعمليات بشكل منفصل عن المهارات والأدوات."
        ),
    )
    return {
        "risks": risks,
        "advantages": advantages,
        "explanation": explanation,
    }


# ── application strategy ─────────────────────────────────────────────────────


def mock_strategy(user_message: str) -> dict:
    payload = _extract_json_block(user_message)
    job = payload.get("job_analysis", {})
    position = job.get("position", {})
    matches = payload.get("matches", [])
    keywords = [k.get("term", "") for k in job.get("keywords", [])]

    exp_counter: Counter = Counter()
    matched_skills: list[str] = []
    concerns: list[str] = []
    for m in matches:
        for ev in m.get("evidence", []):
            if ev.get("entity_type") == "experience":
                exp_counter[ev.get("entity_id", "")] += 1
        if m.get("status") in ("NOT_MATCHED",) and m.get("importance") in ("CRITICAL", "HIGH"):
            concerns.append(_loc(
                user_message,
                f"Gap in important requirement: {m.get('requirement_text', '')[:120]}",
                f"فجوة في متطلب مهم: {m.get('requirement_text', '')[:120]}",
            ))
        for kw in m.get("keywords", []):
            if m.get("status") == "MATCHED" and kw not in matched_skills:
                matched_skills.append(kw)

    priority_experience = [eid for eid, _ in exp_counter.most_common(5)]
    title = position.get("job_title", "this role")
    org = position.get("organization", "the organization")
    positioning = _loc(
        user_message,
        (
            f"Position the candidate as a results-oriented professional for {title} at {org}, "
            f"leading with directly evidenced experience and quantified achievements."
        ),
        (
            f"قدّم المرشح كمهني موجّه بالنتائج لوظيفة {title} في {org}، "
            f"مع إبراز الخبرة المدعومة بالأدلة والإنجازات المكمّمة."
        ),
    )
    messaging = _loc(
        user_message,
        (
            f"Open with the strongest evidence-backed alignment to {title}; "
            f"connect the candidate's measurable results to {org}'s priorities; "
            f"address transferable areas honestly without overstating them."
        ),
        (
            f"ابدأ بأقوى محاذاة مدعومة بالأدلة لوظيفة {title}؛ "
            f"اربط نتائج المرشح القابلة للقياس بأولويات {org}؛ "
            f"وعالج المجالات القابلة للنقل بصدق دون مبالغة."
        ),
    )
    return {
        "positioning": positioning,
        "priority_experience": priority_experience,
        "priority_skills": matched_skills[:12],
        "keywords": keywords[:20],
        "evidence_plan": [
            {"requirement": m.get("requirement_text", "")[:120], "evidence": m.get("evidence", [])[:2]}
            for m in matches
            if m.get("status") == "MATCHED"
        ][:8],
        "de_emphasis": [],
        "concerns": concerns[:6],
        "messaging_strategy": messaging,
    }


# ── CV generation ────────────────────────────────────────────────────────────


def mock_cv_generation(user_message: str) -> dict:
    payload = _extract_json_block(user_message)
    profile = payload.get("profile", {})
    job = payload.get("job", {})
    experiences = payload.get("experiences", [])
    skills = payload.get("skills", [])
    education = payload.get("education", [])
    certifications = payload.get("certifications", [])
    languages = payload.get("languages", [])
    strategy = payload.get("strategy", {})

    priority_ids = set(strategy.get("priority_experience") or [])
    de_emphasis = set(strategy.get("de_emphasis") or [])
    priority_skills = [s.lower() for s in strategy.get("priority_skills", [])]
    terms = relevance_terms(job, strategy, payload.get("matches") or [])

    ordered_exp = sorted(experiences, key=_date_sort_key, reverse=True)

    exp_entries = []
    for e in ordered_exp:
        exp_id = e.get("id", "")
        if exp_id in de_emphasis:
            limit = 2
        elif exp_id in priority_ids:
            limit = 6
        else:
            limit = 4
        if terms:
            bullets = relevant_bullets_for_experience(e, terms, max_bullets=limit)
        else:
            bullets = []
            for ach in e.get("achievements", []):
                if isinstance(ach, dict):
                    text = ach.get("description", "")
                    eid = ach.get("id", exp_id)
                else:
                    text, eid = str(ach), exp_id
                if text:
                    bullets.append({"text": text, "evidence_ids": [eid] if eid else []})
            for resp in e.get("responsibilities", [])[:limit]:
                bullets.append({"text": resp, "evidence_ids": [exp_id] if exp_id else []})
            bullets = bullets[:limit]
        exp_entries.append({
            "experience_id": exp_id,
            "organization": e.get("organization", ""),
            "job_title": e.get("job_title", ""),
            "start_date": e.get("start_date", "") or "",
            "end_date": e.get("end_date", "") or _loc(user_message, "Present", "حتى الآن"),
            "location": e.get("location", ""),
            "bullets": bullets,
        })

    def skill_rank(s):
        return 0 if s.get("canonical_name", "").lower() in priority_skills else 1

    ordered_skills = sorted(skills, key=skill_rank)
    skill_names = [s.get("canonical_name", s.get("name", "")) for s in ordered_skills]

    top_skills = ", ".join(skill_names[:3])
    headline = profile.get("headline") or (
        f"{job.get('position_title', 'Professional')} | {top_skills}" if top_skills else job.get("position_title", "")
    )
    summary = profile.get("summary") or (
        _loc(
            user_message,
            (
                f"Professional with evidenced experience aligned to {job.get('position_title', 'the role')} "
                f"at {job.get('organization_name', 'the organization')}. "
                f"Key strengths: {top_skills}." if top_skills else
                f"Professional applying for {job.get('position_title', 'the role')}."
            ),
            (
                f"مهني بخبرة موثّقة متوافقة مع {job.get('position_title', 'الدور')} "
                f"في {job.get('organization_name', 'الجهة')}. "
                f"نقاط القوة: {top_skills}." if top_skills else
                f"مهني يتقدم لوظيفة {job.get('position_title', 'الدور')}."
            ),
        )
    )
    summary_eids = [e.get("id", "") for e in ordered_exp[:2] if e.get("id")]

    return {
        "headline": headline,
        "summary": summary,
        "summary_evidence_ids": summary_eids,
        "experience": exp_entries,
        "skills": skill_names,
        "education": [
            {
                "institution": ed.get("institution", ""),
                "degree": ed.get("degree", ""),
                "field_of_study": ed.get("field_of_study", ""),
                "start_date": ed.get("start_date") or "",
                "end_date": ed.get("end_date") or "",
            }
            for ed in education
        ],
        "certifications": [c.get("name", "") for c in certifications if c.get("name")],
        "languages": [
            {"language": l.get("language", ""), "proficiency": l.get("proficiency", "")}
            for l in languages
        ],
        "additional_sections": [],
    }


# ── cover letter generation ──────────────────────────────────────────────────


def mock_cover_letter(user_message: str) -> dict:
    payload = _extract_json_block(user_message)
    profile = payload.get("profile", {})
    job = payload.get("job", {})
    research = payload.get("research", [])
    hiring = payload.get("hiring_context", {})
    matches = payload.get("matches", [])
    strategy = payload.get("strategy", {})

    title = job.get("position_title", "the position")
    org = job.get("organization_name", "your organization")

    hm = hiring.get("hiring_manager") if hiring else None
    if hm and hm.get("confidence") in ("HIGH", "MEDIUM") and hm.get("name"):
        salutation = f"Dear {hm['name']}," if output_language(user_message) == "en" else f"السيد/ة {hm['name']}،"
    else:
        salutation = _loc(user_message, "Dear Hiring Manager,", "السيد/ة مدير التوظيف،")

    paragraphs = []
    paragraphs.append({
        "text": (
            _loc(
                user_message,
                f"I am writing to apply for the role of {title} at {org}. {strategy.get('positioning', '')}".strip(),
                f"أتقدم بطلبي لوظيفة {title} في {org}. {strategy.get('positioning', '')}".strip(),
            )
        ),
        "evidence_ids": [],
    })

    if research:
        claim = research[0].get("claim", "")
        paragraphs.append({
            "text": (
                f"{org}'s work resonates strongly with my professional focus: {claim} "
                f"This alignment makes the opportunity to contribute to your team especially compelling."
            ),
            "evidence_ids": [],
        })

    strong = [m for m in matches if m.get("status") == "MATCHED"]
    ev_ids: list[str] = []
    ev_texts: list[str] = []
    for m in strong[:3]:
        for ev in m.get("evidence", [])[:1]:
            if ev.get("entity_id"):
                ev_ids.append(ev["entity_id"])
            snippet = ev.get("evidence", "").strip()
            if snippet:
                ev_texts.append(snippet.split("\n")[0][:200])
    if ev_texts:
        body = "In my recent work I " + ev_texts[0][0].lower() + ev_texts[0][1:] if ev_texts[0] else ""
        if len(ev_texts) > 1:
            body += f" I also {ev_texts[1][0].lower() + ev_texts[1][1:] if ev_texts[1] else ''}"
        paragraphs.append({
            "text": (
                f"My experience maps directly to your key requirements. {body.strip()} "
                f"These are documented, verifiable results that I would bring to {org}."
            ),
            "evidence_ids": ev_ids,
        })

    transferable = [m for m in matches if m.get("status") == "TRANSFERABLE"]
    if transferable:
        paragraphs.append({
            "text": (
                "Where my background is adjacent rather than direct — for example "
                f"\"{transferable[0].get('requirement_text', '')[:100]}\" — I bring closely "
                "related, demonstrable experience and a track record of transferring it quickly."
            ),
            "evidence_ids": [ev.get("entity_id", "") for ev in transferable[0].get("evidence", [])[:1]],
        })

    paragraphs.append({
        "text": (
            f"I would welcome the opportunity to discuss how my evidenced track record can "
            f"support {org}'s objectives as {title}. Thank you for your consideration."
        ),
        "evidence_ids": [],
    })

    name = profile.get("full_name", "")
    return {
        "subject": _loc(user_message, f"Application for {title} — {org}", f"طلب توظيف لوظيفة {title} — {org}"),
        "salutation": salutation,
        "paragraphs": paragraphs,
        "closing": _loc(user_message, f"Sincerely,\n{name}".strip(), f"مع فائق الاحترام،\n{name}".strip()),
    }


def mock_career_coach(user_message: str) -> dict:
    payload = _extract_json_block(user_message)
    question = (payload.get("question") or user_message or "").lower()
    evidence = payload.get("evidence") or []
    if "ignore previous" in question or "reveal the system" in question:
        return {
            "answer": _loc(
                user_message,
                "I can only discuss your career evidence. I will not follow instructions embedded in untrusted text.",
                "يمكنني مناقشة أدلة مسيرتك المهنية فقط. لن أتبع تعليمات مضمّنة في نص غير موثوق.",
            ),
            "citation_ids": [],
            "refused": True,
        }
    hits = []
    for item in evidence:
        text = (item.get("text") or "").lower()
        eid = item.get("entity_id") or ""
        if eid and any(tok in text for tok in tokens(question) if len(tok) > 3):
            hits.append(item)
    if not hits:
        return {
            "answer": _loc(
                user_message,
                "I do not have enough evidenced information in your career knowledge base to answer that.",
                "لا تتوفر أدلة كافية في قاعدة معرفتك المهنية للإجابة على ذلك.",
            ),
            "citation_ids": [],
            "refused": True,
        }
    snippets = "; ".join((h.get("text") or "")[:160] for h in hits[:3])
    return {
        "answer": _loc(
            user_message,
            f"Based on your evidenced records: {snippets}",
            f"استناداً إلى سجلاتك الموثقة: {snippets}",
        ),
        "citation_ids": [h.get("entity_id") for h in hits[:3] if h.get("entity_id")],
        "refused": False,
    }


# ── ATS analysis ─────────────────────────────────────────────────────────────


def mock_ats_analysis(user_message: str) -> dict:
    payload = _extract_json_block(user_message)
    doc_text = (payload.get("document_text", "") or "").lower()
    keywords = payload.get("keywords", [])
    requirements = payload.get("requirements", [])

    covered, missing, overuse = [], [], []
    for kw in keywords:
        term = kw.get("term", kw) if isinstance(kw, dict) else str(kw)
        if not term:
            continue
        count = len(re.findall(rf"\b{re.escape(term.lower())}\b", doc_text))
        if count > 0:
            covered.append(term)
        else:
            missing.append(term)
        if count > 6:
            overuse.append(f"'{term}' appears {count} times — possible keyword stuffing")

    formatting_risks = []
    if re.search(r"\|.*\|", doc_text):
        formatting_risks.append("Tables detected — some ATS systems parse them poorly")
    if re.search(r"[^\x00-\x7F]{3,}", doc_text):
        formatting_risks.append("Heavy non-ASCII/graphical characters detected")

    req_covered = 0
    for req in requirements:
        req_toks = content_tokens(req.get("text", "") if isinstance(req, dict) else str(req))
        if req_toks and _overlap(req_toks, set(tokens(doc_text))) >= 0.4:
            req_covered += 1
    req_total = len(requirements)

    kw_total = len(keywords)
    coverage = (len(covered) / kw_total) if kw_total else 1.0
    req_coverage = (req_covered / req_total) if req_total else 1.0
    score = round(0.6 * coverage + 0.4 * req_coverage, 3)
    if overuse:
        score = max(0.0, score - 0.05 * len(overuse))
    if formatting_risks:
        score = max(0.0, score - 0.05 * len(formatting_risks))

    notes = []
    if missing:
        notes.append(f"Consider naturally incorporating: {', '.join(missing[:5])}")
    return {
        "ats_score": score,
        "keyword_coverage": round(coverage, 3),
        "covered_keywords": covered,
        "missing_keywords": missing,
        "keyword_overuse_warnings": overuse,
        "formatting_risks": formatting_risks,
        "requirement_coverage": round(req_coverage, 3),
        "notes": notes,
    }


# ── dispatcher ───────────────────────────────────────────────────────────────

_DISPATCH = {
    "career_extraction": mock_career_extraction,
    "career_normalization": mock_career_normalization,
    "career_reconciliation": mock_career_reconciliation,
    "jd_analysis": mock_jd_analysis,
    "organization_research": mock_organization_research,
    "hiring_manager_research": mock_hiring_research,
    "candidate_matching": mock_candidate_matching,
    "scoring": mock_scoring,
    "application_strategy": mock_strategy,
    "cv_generation": mock_cv_generation,
    "cover_letter_generation": mock_cover_letter,
    "ats_analysis": mock_ats_analysis,
    "career_coach": mock_career_coach,
}


def dispatch(prompt_name: str, user_message: str) -> dict:
    handler = _DISPATCH.get(prompt_name)
    if handler is None:
        return {"note": f"mock provider: no deterministic handler for {prompt_name}"}
    return handler(user_message)
