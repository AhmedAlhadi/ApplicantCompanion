"""Seed data: default user, built-in templates, and a demo career knowledge
base so the example workflows (§57, §64) run end-to-end out of the box.

Seeding is idempotent: it only runs when the database has no users.
Set SEED_DEMO_DATA=false to seed only the user + templates.
"""
from __future__ import annotations

import logging
import os

from .database import SessionLocal
from .models import (
    Achievement,
    CareerProfile,
    Certification,
    Education,
    Experience,
    KnowledgeContext,
    Language,
    ProfessionalKnowledge,
    Skill,
    Template,
    User,
)
from .retrieval.pipeline import index_all_for_user
from .security.auth import hash_password
from .services.settings import set_user_setting
from .templates.engine import build_builtin_templates

logger = logging.getLogger(__name__)


def _seed_credentials() -> tuple[str, str]:
    return (
        os.environ.get("SEED_USER_EMAIL", "demo@example.com"),
        os.environ.get("SEED_USER_PASSWORD", "demo-password-123"),
    )


DEMO_EXPERIENCES = [
    {
        "organization": "UNDP",
        "job_title": "Digital Transformation Specialist",
        "start_date": "2022-03",
        "end_date": None,
        "employment_type": "full-time",
        "location": "Amman, Jordan",
        "responsibilities": [
            "Lead the design and delivery of digital transformation programmes across regional offices",
            "Manage a cross-functional team of 6 engineers and analysts building data platforms",
            "Advise senior management on technology strategy, AI adoption and data governance",
        ],
        "technologies": ["Power BI", "Python", "PostgreSQL", "Azure", "SharePoint"],
        "domains": ["digital transformation", "development", "public sector"],
        "knowledge": [
            {"name": "humanitarian programme operations", "kind": "industry", "depth": "practiced"},
            {"name": "results-based management", "kind": "methodology", "depth": "applied"},
        ],
        "leadership": ["Managed a cross-functional team of 6", "Chaired the regional data governance working group"],
        "stakeholders": ["Country Directors", "Government counterparts", "UN agencies"],
        "verification_status": "verified",
        "confidence": 0.95,
        "achievements": [
            {"description": "Led implementation of an AI-enabled MIS platform adopted by 12 country offices, cutting reporting time by 40%", "quantified_result": "12 country offices; 40% faster reporting"},
            {"description": "Delivered Power BI dashboards for programme monitoring used by 200+ staff", "quantified_result": "200+ staff users"},
        ],
    },
    {
        "organization": "TechForGood Consulting",
        "job_title": "Senior Data Consultant",
        "start_date": "2019-06",
        "end_date": "2022-02",
        "employment_type": "full-time",
        "location": "Remote",
        "responsibilities": [
            "Designed data architecture for NGO clients migrating legacy systems to cloud data warehouses",
            "Built ETL pipelines and data models for monitoring and evaluation programmes",
        ],
        "technologies": ["Python", "SQL", "dbt", "Snowflake", "Docker"],
        "domains": ["data architecture", "monitoring and evaluation", "ngo"],
        "leadership": ["Mentored 3 junior consultants"],
        "stakeholders": ["NGO programme leads"],
        "verification_status": "verified",
        "confidence": 0.95,
        "achievements": [
            {"description": "Architected a data warehouse consolidating 15 programme databases for a major INGO", "quantified_result": "15 databases consolidated"},
        ],
    },
]

DEMO_SKILLS = [
    ("Python", "technical", ["Python programming"]),
    ("SQL", "technical", []),
    ("Power BI", "technical", ["Microsoft Power BI", "PowerBI"]),
    ("Data architecture", "technical", ["information architecture"]),
    ("ETL", "technical", ["data pipelines"]),
    ("Docker", "technical", []),
    ("PostgreSQL", "technical", []),
    ("Machine learning", "technical", ["ML"]),
    ("Project management", "methodologies", []),
    ("Stakeholder management", "behavioral", []),
    ("Digital transformation", "domain", []),
    ("Monitoring and evaluation", "domain", ["M&E"]),
]

DEMO_EDUCATION = [
    {"institution": "University of Manchester", "degree": "MSc", "field_of_study": "Information Systems", "start_date": "2014-09", "end_date": "2015-09"},
    {"institution": "University of Jordan", "degree": "BSc", "field_of_study": "Computer Science", "start_date": "2009-09", "end_date": "2013-06"},
]

DEMO_CERTS = [
    {"name": "PRINCE2 Practitioner", "issuer": "AXELOS", "issue_date": "2021-04"},
    {"name": "Microsoft Certified: Azure Data Fundamentals", "issuer": "Microsoft", "issue_date": "2022-01"},
]

DEMO_LANGUAGES = [
    {"language": "Arabic", "proficiency": "Native", "is_native": True},
    {"language": "English", "proficiency": "Fluent", "is_native": False},
]


def seed_if_empty() -> None:
    db = SessionLocal()
    try:
        from .services.entitlements import EntitlementsService

        entitlements = EntitlementsService(db)
        entitlements.ensure_catalog()
        if db.query(User).count() > 0:
            entitlements.backfill_subscriptions()
            db.commit()
            return
        email, password = _seed_credentials()
        logger.info("Seeding initial data…")
        user = User(email=email, password_hash=hash_password(password), full_name="Demo User", is_admin=True)
        db.add(user)
        db.flush()

        for tpl in build_builtin_templates():
            db.add(Template(**tpl))

        db.add(
            CareerProfile(
                user_id=user.id,
                full_name="Demo User",
                headline="Digital Transformation & Data Platform Leader",
                summary="Technology leader with 7+ years delivering data platforms and digital transformation programmes across the development sector.",
                email=email,
                location="Amman, Jordan",
                preferred_positioning="Senior digital transformation / data platform roles in international organizations.",
            )
        )

        if os.environ.get("SEED_DEMO_DATA", "true").lower() == "true":
            for exp in DEMO_EXPERIENCES:
                payload = dict(exp)
                achievements = payload.pop("achievements")
                knowledge_items = payload.pop("knowledge", [])
                row = Experience(user_id=user.id, **payload)
                db.add(row)
                db.flush()
                for ach in achievements:
                    db.add(Achievement(user_id=user.id, experience_id=row.id, verification_status="verified", confidence=0.95, **ach))
                for item in knowledge_items + [{"name": name, "kind": "domain", "depth": "applied"} for name in payload.get("domains") or []]:
                    name = item["name"]
                    knowledge = (
                        db.query(ProfessionalKnowledge)
                        .filter(
                            ProfessionalKnowledge.user_id == user.id,
                            ProfessionalKnowledge.canonical_name == name,
                            ProfessionalKnowledge.is_deleted == False,  # noqa: E712
                        )
                        .first()
                    )
                    if knowledge is None:
                        knowledge = ProfessionalKnowledge(
                            user_id=user.id,
                            name=name,
                            canonical_name=name,
                            kind=item.get("kind", "domain"),
                            depth=item.get("depth", "applied"),
                            summary=item.get("summary", ""),
                            verification_status="verified",
                            confidence=0.9,
                            evidence_count=1,
                        )
                        db.add(knowledge)
                        db.flush()
                    db.add(
                        KnowledgeContext(
                            user_id=user.id,
                            knowledge_id=knowledge.id,
                            experience_id=row.id,
                            acquisition_mode="acquired_through_role",
                            verification_status="verified",
                            confidence=0.9,
                        )
                    )

            for name, category, synonyms in DEMO_SKILLS:
                db.add(Skill(user_id=user.id, name=name, canonical_name=name, category=category, synonyms=synonyms, verification_status="verified", confidence=0.9, evidence_count=2))
            for edu in DEMO_EDUCATION:
                db.add(Education(user_id=user.id, verification_status="verified", **edu))
            for cert in DEMO_CERTS:
                db.add(Certification(user_id=user.id, verification_status="verified", **cert))
            for lang in DEMO_LANGUAGES:
                db.add(Language(user_id=user.id, **lang))
            db.flush()
            index_all_for_user(db, user.id)
            set_user_setting(db, user.id, "onboarding_status", "completed")

        from .config import get_settings

        plan_code = "power" if get_settings().app_env == "test" else "explorer"
        EntitlementsService(db).assign(user.id, plan_code=plan_code, notes="Initial plan")
        db.commit()
        logger.info("Seed complete. Login: %s", email)
    finally:
        db.close()
