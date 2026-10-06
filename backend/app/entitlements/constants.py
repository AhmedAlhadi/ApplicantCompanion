"""Stable entitlement meters, features, and seeded plan definitions."""
from __future__ import annotations

METER_FIT_CHECK = "fit_check"
METER_APPLICATION_PACK = "application_pack"
METER_SECTION_REGENERATION = "section_regeneration"
METER_CAREER_DOCUMENTS = "career_documents"
METER_STORAGE_BYTES = "storage_bytes"
METER_CONCURRENT_WORKFLOWS = "concurrent_workflows"
METER_ACTIVE_APPLICATIONS = "active_applications"

PERIODIC_METERS = (
    METER_FIT_CHECK,
    METER_APPLICATION_PACK,
    METER_SECTION_REGENERATION,
)
STATE_METERS = (
    METER_CAREER_DOCUMENTS,
    METER_STORAGE_BYTES,
    METER_CONCURRENT_WORKFLOWS,
    METER_ACTIVE_APPLICATIONS,
)
ALL_METERS = PERIODIC_METERS + STATE_METERS

FEATURE_ORGANIZATION_RESEARCH = "organization_research"
FEATURE_HIRING_CONTEXT = "hiring_context_research"
FEATURE_DOCX_EXPORT = "docx_export"
FEATURE_CUSTOM_SCORING = "custom_scoring"
FEATURE_ADVANCED_ANALYTICS = "advanced_analytics"
FEATURE_API_ACCESS = "api_access"
FEATURE_BULK_FIT_CHECK = "bulk_fit_check"
FEATURE_PRIORITY_PROCESSING = "priority_processing"

ALL_FEATURES = (
    FEATURE_ORGANIZATION_RESEARCH,
    FEATURE_HIRING_CONTEXT,
    FEATURE_DOCX_EXPORT,
    FEATURE_CUSTOM_SCORING,
    FEATURE_ADVANCED_ANALYTICS,
    FEATURE_API_ACCESS,
    FEATURE_BULK_FIT_CHECK,
    FEATURE_PRIORITY_PROCESSING,
)

ALL_TEMPLATE_KEYS = (
    "traditional-executive",
    "modern-professional",
    "international-un",
    "consulting",
    "technology-ai",
    "minimal-ats",
    "academic-research",
)
EXPLORER_TEMPLATES = ("minimal-ats", "modern-professional")
ESSENTIAL_TEMPLATES = EXPLORER_TEMPLATES + ("traditional-executive", "international-un")

MB = 1024 * 1024
GB = 1024 * MB

ACTIVE_SUBSCRIPTION_STATUSES = ("trialing", "active", "past_due", "cancelled")
USABLE_STATUSES = ("trialing", "active")

DEFAULT_PLAN_CODE = "explorer"


def _features(**overrides: bool) -> dict[str, bool]:
    base = {key: False for key in ALL_FEATURES}
    base.update(overrides)
    return base


SEEDED_PLANS: list[dict] = [
    {
        "code": "explorer",
        "display_name": "Explorer",
        "priority": 0,
        "limits": {
            METER_FIT_CHECK: 2,
            METER_APPLICATION_PACK: 1,
            METER_SECTION_REGENERATION: 2,
            METER_CAREER_DOCUMENTS: 2,
            METER_STORAGE_BYTES: 50 * MB,
            METER_CONCURRENT_WORKFLOWS: 1,
            METER_ACTIVE_APPLICATIONS: 10,
        },
        "rollover_caps": {meter: 0 for meter in PERIODIC_METERS},
        "features": _features(
            organization_research=True,
            hiring_context_research=True,
            docx_export=True,
        ),
        "template_keys": list(EXPLORER_TEMPLATES),
    },
    {
        "code": "essential",
        "display_name": "Essential",
        "priority": 1,
        "limits": {
            METER_FIT_CHECK: 15,
            METER_APPLICATION_PACK: 5,
            METER_SECTION_REGENERATION: 15,
            METER_CAREER_DOCUMENTS: 20,
            METER_STORAGE_BYTES: 250 * MB,
            METER_CONCURRENT_WORKFLOWS: 1,
            METER_ACTIVE_APPLICATIONS: 100,
        },
        "rollover_caps": {
            METER_FIT_CHECK: 15,
            METER_APPLICATION_PACK: 5,
            METER_SECTION_REGENERATION: 15,
        },
        "features": _features(
            organization_research=True,
            hiring_context_research=True,
            docx_export=True,
        ),
        "template_keys": list(ESSENTIAL_TEMPLATES),
    },
    {
        "code": "professional",
        "display_name": "Professional",
        "priority": 2,
        "limits": {
            METER_FIT_CHECK: 50,
            METER_APPLICATION_PACK: 15,
            METER_SECTION_REGENERATION: 60,
            METER_CAREER_DOCUMENTS: 100,
            METER_STORAGE_BYTES: 1 * GB,
            METER_CONCURRENT_WORKFLOWS: 2,
            METER_ACTIVE_APPLICATIONS: 500,
        },
        "rollover_caps": {
            METER_FIT_CHECK: 50,
            METER_APPLICATION_PACK: 15,
            METER_SECTION_REGENERATION: 60,
        },
        "features": _features(
            organization_research=True,
            hiring_context_research=True,
            docx_export=True,
            custom_scoring=True,
            advanced_analytics=True,
            priority_processing=True,
        ),
        "template_keys": list(ALL_TEMPLATE_KEYS),
    },
    {
        "code": "power",
        "display_name": "Power",
        "priority": 3,
        "limits": {
            METER_FIT_CHECK: 150,
            METER_APPLICATION_PACK: 40,
            METER_SECTION_REGENERATION: 200,
            METER_CAREER_DOCUMENTS: 250,
            METER_STORAGE_BYTES: 5 * GB,
            METER_CONCURRENT_WORKFLOWS: 5,
            METER_ACTIVE_APPLICATIONS: 2000,
        },
        "rollover_caps": {
            METER_FIT_CHECK: 150,
            METER_APPLICATION_PACK: 40,
            METER_SECTION_REGENERATION: 200,
        },
        "features": _features(
            organization_research=True,
            hiring_context_research=True,
            docx_export=True,
            custom_scoring=True,
            advanced_analytics=True,
            priority_processing=True,
            api_access=True,
            bulk_fit_check=True,
        ),
        "template_keys": list(ALL_TEMPLATE_KEYS),
    },
]
