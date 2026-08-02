from __future__ import annotations

def resolve_repository(observation: dict) -> dict:
    data = observation.get("github_observation", observation)
    repo = data.get("repository", {})
    owner = repo.get("owner_login")
    return {"repository_ref": data.get("source_ref"), "company_ref": None, "organization_ref": f"github:org:{owner}" if owner else None, "confidence": 0.5 if owner else 0.0, "status": "HYPOTHESIS", "evidence_refs": [data.get("provenance", {}).get("selected_field_hash")], "resolution_version": "vc_github_entity_resolution_v1"}
