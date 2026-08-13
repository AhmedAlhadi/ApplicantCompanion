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
}

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
    "english", "french", "spanish", "arabic", "german", "portuguese", "russian",
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
}

# Related-term groups for TRANSFERABLE matching (§17)
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
]

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.\-]*")


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

_DATE_RANGE_RE = re.compile(
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{4}|\d{4}(?:[-/]\d{1,2})?)"
    r"\s*(?:–|-|—|to)\s*"
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{4}|\d{4}(?:[-/]\d{1,2})?|present|current|now)",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"^\s*[-•*–▪◦]\s+")
_ACHIEVEMENT_WORDS = re.compile(
    r"\b(led|achieved|increased|reduced|delivered|launched|improved|saved|grew|"
    r"won|secured|cut|boosted|doubled|tripled|spearheaded)\b|%|\$|\d+x",
    re.IGNORECASE,
)
_SECTION_HEADS = {
    "experience": re.compile(r"(experience|employment|work history|professional history)", re.I),
    "education": re.compile(r"^education|academic", re.I),
    "skills": re.compile(r"skills|competencies|technical proficiencies", re.I),
    "certifications": re.compile(r"certification|licenses|credentials", re.I),
    "languages": re.compile(r"languages", re.I),
    "publications": re.compile(r"publications", re.I),
    "projects": re.compile(r"projects", re.I),
}


def _is_heading(line: str) -> str | None:
    stripped = line.strip().strip(":").strip()
    if not stripped or len(stripped) > 60:
        return None
    for section, rx in _SECTION_HEADS.items():
        if rx.search(stripped):
            return section
    return None


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
        for sep in (" at ", " | ", " — ", " – ", " - ", ", "):
            if sep in header:
                left, right = header.split(sep, 1)
                if sep == " at ":
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
                    cat = "technical"
                    low = item.lower()
                    if low in METHODOLOGIES:
                        cat = "methodologies"
                    elif low in BEHAVIORAL:
                        cat = "behavioral"
                    elif low in LANGUAGES:
                        cat = "language"
                    skills.append({"name": item, "category": cat})
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
        categories.setdefault(key, item.get("category", "technical"))
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
    (re.compile(r"^(organization|organisation|company|employer)\s*[:\-]\s*(.+)$", re.I), "organization"),
    (re.compile(r"^(job\s*title|position(?:\s*title)?|title|role)\s*[:\-]\s*(.+)$", re.I), "job_title"),
    (re.compile(r"^(location|duty\s*station|based\s*in)\s*[:\-]\s*(.+)$", re.I), "location"),
    (re.compile(r"^(department|division|unit)\s*[:\-]\s*(.+)$", re.I), "department"),
    (re.compile(r"^(team)\s*[:\-]\s*(.+)$", re.I), "team"),
    (re.compile(r"^(contract(?:\s*type)?|employment\s*type)\s*[:\-]\s*(.+)$", re.I), "contract_type"),
    (re.compile(r"^(duration|contract\s*duration)\s*[:\-]\s*(.+)$", re.I), "duration"),
    (re.compile(r"^(deadline|closing\s*date|apply\s*by)\s*[:\-]\s*(.+)$", re.I), "deadline"),
    (re.compile(r"^(grade|level|seniority)\s*[:\-]\s*(.+)$", re.I), "grade_level"),
    (re.compile(r"^(reports?\s*to|reporting\s*line)\s*[:\-]\s*(.+)$", re.I), "reporting_line"),
]

_JD_SECTIONS = {
    "responsibilities": re.compile(r"responsibilit|duties|what you('| wi)ll do|key (functions|tasks)|role overview|your role", re.I),
    "requirements": re.compile(r"requirement|qualification|what we('re| are) looking for|who you are|your profile|skills (and|&) experience|experience (and|&) skills|must.have", re.I),
    "preferred": re.compile(r"preferred|desirable|nice.to.have|an asset|a plus|advantageous|bonus", re.I),
    "education": re.compile(r"^education", re.I),
    "about": re.compile(r"about (us|the|our)|who we are", re.I),
    "benefits": re.compile(r"we offer|benefits|compensation|what we provide", re.I),
}

_PREFERRED_HINTS = re.compile(r"preferred|desirable|nice.to.have|an asset|a plus|advantageous|would be|ideally", re.I)
_MANDATORY_HINTS = re.compile(r"\bmust\b|required|essential|minimum|at least|mandatory", re.I)


def _classify_requirement(text: str) -> str:
    low = text.lower()
    if re.search(r"degree|bachelor|master'?s|phd|doctorate|diploma|university|academic", low):
        return "education"
    if re.search(r"\d+\s*\+?\s*years?|years? of", low):
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
    found = [t for t in sorted(TECH_LEXICON | METHODOLOGIES | CERT_TERMS) if t in low]
    return found[:8]


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
            requirements.append({
                "text": bullet,
                "category": "responsibility",
                "requirement_type": "responsibility",
                "importance": "MEDIUM",
                "keywords": _req_keywords(bullet),
            })
        elif section in ("requirements", "preferred") and (is_bullet or len(stripped) > 30):
            req_type = "preferred" if (section == "preferred" or _PREFERRED_HINTS.search(bullet)) else "mandatory"
            requirements.append({
                "text": bullet,
                "category": _classify_requirement(bullet),
                "requirement_type": req_type,
                "importance": "",  # filled below once title is known
                "keywords": _req_keywords(bullet),
            })
        elif section == "education" and (is_bullet or len(stripped) > 20):
            requirements.append({
                "text": bullet,
                "category": "education",
                "requirement_type": "preferred" if _PREFERRED_HINTS.search(bullet) else "mandatory",
                "importance": "",
                "keywords": [],
            })

    if not position["job_title"] and first_text_line:
        position["job_title"] = first_text_line.strip()
    if not position["organization"]:
        m = re.search(r"\b(?:at|with|join)\s+([A-Z][A-Za-z0-9&.,' ]{2,60})", jd)
        if m:
            position["organization"] = m.group(1).strip().rstrip(".,;")

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
            keyword_map[term] = "tools" if " " not in term and "." in term else "technical"
    for term in sorted(METHODOLOGIES):
        if term in low_jd:
            keyword_map[term] = "methodologies"
    for term in sorted(CERT_TERMS):
        if term in low_jd:
            keyword_map[term] = "certifications"
    for term in competencies:
        keyword_map.setdefault(term, "behavioral")
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


def mock_candidate_matching(user_message: str) -> dict:
    payload = _extract_json_block(user_message)
    requirements = payload.get("requirements", [])
    evidence = payload.get("evidence", [])
    ev_tokens = [(ev, content_tokens(ev.get("text", ""))) for ev in evidence]

    matches = []
    for req in requirements:
        req_toks = content_tokens(req.get("text", ""))
        if not evidence:
            matches.append({
                "requirement_id": req.get("id", ""),
                "status": "UNKNOWN",
                "evidence": [],
                "explanation": "No career evidence available to evaluate this requirement.",
                "confidence": 0.0,
                "match_kind": "direct",
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
            expl = f"Direct evidence found in {best_ev.get('entity_type', 'record')}."
        elif best >= 0.30:
            status, kind = "PARTIALLY_MATCHED", "direct"
            conf = 0.4 + best / 2
            expl = "Partial coverage: related evidence exists but does not fully cover the requirement."
        elif transferable:
            status, kind = "TRANSFERABLE", "transferable"
            conf = 0.45
            expl = "No direct evidence; closely related transferable experience identified."
        else:
            status, kind = "NOT_MATCHED", "direct"
            conf = 0.7
            expl = "No supporting evidence found in the career knowledge base."
        matches.append({
            "requirement_id": req.get("id", ""),
            "status": status,
            "evidence": supporting if status != "NOT_MATCHED" else [],
            "explanation": expl,
            "confidence": round(conf, 2),
            "match_kind": kind,
        })
    return {"matches": matches}


# ── scoring narrative ────────────────────────────────────────────────────────


def mock_scoring(user_message: str) -> dict:
    payload = _extract_json_block(user_message)
    matches = payload.get("matches", [])
    overall = payload.get("overall_score", 0.0)

    strong, partial, gaps, transferable = [], [], [], []
    for m in matches:
        text = m.get("requirement_text", "")
        status = m.get("status", "UNKNOWN")
        if status == "MATCHED":
            strong.append(text)
        elif status == "PARTIALLY_MATCHED":
            partial.append(text)
        elif status == "TRANSFERABLE":
            transferable.append(text)
        elif status == "NOT_MATCHED":
            gaps.append(text)

    risks = []
    if gaps:
        risks.append(f"{len(gaps)} requirement(s) have no supporting evidence.")
    unknowns = [m for m in matches if m.get("status") == "UNKNOWN"]
    if unknowns:
        risks.append(f"{len(unknowns)} requirement(s) could not be evaluated (insufficient data).")
    advantages = strong[:3]

    explanation = (
        f"Overall fit is {overall:.0%}. "
        f"{len(strong)} requirement(s) are directly matched by evidence, "
        f"{len(partial)} partially matched, {len(transferable)} covered by transferable "
        f"experience, and {len(gaps)} gap(s) identified."
    )
    return {
        "strong_matches": strong,
        "partial_matches": partial,
        "gaps": gaps,
        "transferable": transferable,
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
            concerns.append(f"Gap in important requirement: {m.get('requirement_text', '')[:120]}")
        for kw in m.get("keywords", []):
            if m.get("status") == "MATCHED" and kw not in matched_skills:
                matched_skills.append(kw)

    priority_experience = [eid for eid, _ in exp_counter.most_common(5)]
    title = position.get("job_title", "this role")
    org = position.get("organization", "the organization")
    positioning = (
        f"Position the candidate as a results-oriented professional for {title} at {org}, "
        f"leading with directly evidenced experience and quantified achievements."
    )
    messaging = (
        f"Open with the strongest evidence-backed alignment to {title}; "
        f"connect the candidate's measurable results to {org}'s priorities; "
        f"address transferable areas honestly without overstating them."
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

    priority_ids = strategy.get("priority_experience", [])
    priority_skills = [s.lower() for s in strategy.get("priority_skills", [])]

    def exp_rank(e):
        return (0 if e.get("id") in priority_ids else 1, -(priority_ids.index(e["id"]) if e.get("id") in priority_ids else 0), e.get("start_date") or "")

    ordered_exp = sorted(experiences, key=exp_rank, reverse=True)

    exp_entries = []
    for e in ordered_exp:
        bullets = []
        for ach in e.get("achievements", []):
            if isinstance(ach, dict):
                text = ach.get("description", "")
                eid = ach.get("id", e.get("id", ""))
            else:
                text, eid = str(ach), e.get("id", "")
            if text:
                bullets.append({"text": text, "evidence_ids": [eid]})
        for resp in e.get("responsibilities", [])[:6]:
            bullets.append({"text": resp, "evidence_ids": [e.get("id", "")]})
        exp_entries.append({
            "organization": e.get("organization", ""),
            "job_title": e.get("job_title", ""),
            "start_date": e.get("start_date", "") or "",
            "end_date": e.get("end_date", "") or "Present",
            "location": e.get("location", ""),
            "bullets": bullets[:8],
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
        f"Professional with evidenced experience aligned to {job.get('position_title', 'the role')} "
        f"at {job.get('organization_name', 'the organization')}. "
        f"Key strengths: {top_skills}." if top_skills else
        f"Professional applying for {job.get('position_title', 'the role')}."
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
        salutation = f"Dear {hm['name']},"
    else:
        salutation = "Dear Hiring Manager,"

    paragraphs = []
    paragraphs.append({
        "text": (
            f"I am writing to apply for the role of {title} at {org}. "
            f"{strategy.get('positioning', '')}".strip()
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
        "subject": f"Application for {title} — {org}",
        "salutation": salutation,
        "paragraphs": paragraphs,
        "closing": f"Sincerely,\n{name}".strip(),
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
}


def dispatch(prompt_name: str, user_message: str) -> dict:
    handler = _DISPATCH.get(prompt_name)
    if handler is None:
        return {"note": f"mock provider: no deterministic handler for {prompt_name}"}
    return handler(user_message)
