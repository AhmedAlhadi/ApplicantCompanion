"""Professional knowledge CRUD, ingestion, retrieval, and role linking."""


def test_knowledge_crud_and_role_link(client, auth_headers):
    exp = client.post(
        "/api/career/experiences",
        headers=auth_headers,
        json={"organization": "ShipFast", "job_title": "Software Developer", "domains": ["logistics"]},
    )
    assert exp.status_code == 201, exp.text
    exp_id = exp.json()["id"]

    created = client.post(
        "/api/career/knowledge",
        headers=auth_headers,
        json={
            "name": "warehousing",
            "kind": "process",
            "depth": "applied",
            "summary": "WMS and inbound/outbound flows",
            "contexts": [
                {
                    "experience_id": exp_id,
                    "acquisition_mode": "acquired_through_role",
                    "how_applied": "Integrated warehouse events into the TMS",
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["canonical_name"] == "warehousing"
    assert body["kind"] == "process"
    assert body["contexts"]
    knowledge_id = body["id"]

    listing = client.get("/api/career/knowledge", headers=auth_headers)
    assert listing.status_code == 200
    names = {row["canonical_name"].lower() for row in listing.json()}
    assert "warehousing" in names
    assert "logistics" in names

    verified = client.post(
        f"/api/career/knowledge/{knowledge_id}/verify?status_value=verified",
        headers=auth_headers,
    )
    assert verified.status_code == 200
    assert verified.json()["verification_status"] == "verified"

    deleted = client.delete(f"/api/career/knowledge/{knowledge_id}", headers=auth_headers)
    assert deleted.status_code == 200
    remaining = {row["id"] for row in client.get("/api/career/knowledge", headers=auth_headers).json()}
    assert knowledge_id not in remaining


def test_experience_domains_create_knowledge(client, auth_headers):
    resp = client.post(
        "/api/career/experiences",
        headers=auth_headers,
        json={
            "organization": "Acme SaaS",
            "job_title": "Finance Analyst",
            "domains": ["subscription billing", "revenue operations"],
        },
    )
    assert resp.status_code == 201, resp.text
    knowledge = client.get("/api/career/knowledge", headers=auth_headers).json()
    names = {row["canonical_name"].lower() for row in knowledge}
    assert "subscription billing" in names
    assert "revenue operations" in names


def test_logistics_developer_ingestion_captures_domain_knowledge(client, auth_headers):
    text = """
PROFESSIONAL EXPERIENCE
Software Developer at Northwind Logistics
January 2020 - December 2023
- Built Python services for the warehouse management and freight booking platforms
- Mapped last-mile delivery exceptions into the TMS
- Worked with customs documentation SLAs and supply chain planners

SKILLS
Python, SQL
"""
    resp = client.post("/api/career/ingest-text", headers=auth_headers, json={"text": text, "doc_type": "cv"})
    assert resp.status_code == 200, resp.text
    auto = resp.json().get("auto_applied") or {}
    assert auto.get("professional_knowledge", 0) >= 1

    pending_id = resp.json().get("pending_ingestion_id")
    if pending_id:
        pending = client.get(f"/api/career/pending-ingestions/{pending_id}", headers=auth_headers).json()
        client.post(
            f"/api/career/pending-ingestions/{pending_id}/confirm",
            headers=auth_headers,
            json={
                "decisions": [
                    {"proposal_id": p["proposal_id"], "action": p.get("action") or "create", "target_id": p.get("target_id")}
                    for p in pending["proposals"]
                ]
            },
        )

    knowledge = client.get("/api/career/knowledge", headers=auth_headers).json()
    blob = " ".join(
        " ".join([row.get("canonical_name") or "", row.get("summary") or "", row.get("kind") or ""])
        for row in knowledge
    ).lower()
    assert any(term in blob for term in ("logistics", "warehouse", "freight", "supply chain", "customs", "last-mile", "last mile", "tms"))

    search = client.get("/api/career/search?q=logistics warehousing", headers=auth_headers)
    assert search.status_code == 200
    types = {item["entity_type"] for item in search.json()}
    assert "professional_knowledge" in types or any("logistics" in (item.get("text") or "").lower() for item in search.json())


def test_saas_finance_ingestion_captures_cross_functional_knowledge(client, auth_headers):
    text = """
PROFESSIONAL EXPERIENCE
Finance Manager at CloudBill SaaS
March 2018 - Present
- Owned accounts receivable and subscription billing operations
- Partnered with product on revenue recognition and customer success reporting
- Administered Salesforce and billing workflows for the SaaS catalog

SKILLS
Excel, financial analysis
"""
    resp = client.post("/api/career/ingest-text", headers=auth_headers, json={"text": text, "doc_type": "cv"})
    assert resp.status_code == 200, resp.text
    pending_id = resp.json().get("pending_ingestion_id")
    if pending_id:
        pending = client.get(f"/api/career/pending-ingestions/{pending_id}", headers=auth_headers).json()
        client.post(
            f"/api/career/pending-ingestions/{pending_id}/confirm",
            headers=auth_headers,
            json={
                "decisions": [
                    {"proposal_id": p["proposal_id"], "action": "create", "target_id": None}
                    for p in pending["proposals"]
                ]
            },
        )
    knowledge = client.get("/api/career/knowledge", headers=auth_headers).json()
    blob = " ".join(row.get("canonical_name", "") for row in knowledge).lower()
    assert any(term in blob for term in ("saas", "billing", "subscription", "revenue", "accounts receivable"))


def test_knowledge_invalid_parent_rejected(client, auth_headers):
    resp = client.post(
        "/api/career/knowledge",
        headers=auth_headers,
        json={
            "name": "clinical protocols",
            "kind": "process",
            "contexts": [{"experience_id": "00000000-0000-0000-0000-000000000000"}],
        },
    )
    assert resp.status_code == 422
