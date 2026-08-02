from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Request

from agents.webapi.deps import require_route_authorization
from . import plugin_api

router = APIRouter(tags=["vc-github-opportunity-radar"])
BASE = "/api/plugins/vc-github-opportunity-radar/v1"
ROUTES = (
    ("GET", f"{BASE}/capabilities", "authenticated_tenant_member"),
    ("GET", f"{BASE}/candidates", "authenticated_tenant_member"),
    ("POST", f"{BASE}/universes", "authenticated_tenant_member"),
    ("POST", f"{BASE}/scan", "authenticated_tenant_member"),
    ("POST", f"{BASE}/inspect", "authenticated_tenant_member"),
    ("POST", f"{BASE}/score", "authenticated_tenant_member"),
    ("POST", f"{BASE}/candidates", "authenticated_tenant_member"),
    ("GET", f"{BASE}/candidates/{{candidate_id}}", "authenticated_tenant_member"),
    ("POST", f"{BASE}/candidates/{{candidate_id}}/review", "governed_reviewer_capability"),
    ("POST", f"{BASE}/candidates/{{candidate_id}}/actions", "authenticated_tenant_member"),
    ("GET", f"{BASE}/candidates/{{candidate_id}}/replay", "authenticated_tenant_member"),
)
ROUTE_POLICY_MAP = {(method, path): "authenticated" for method, path, _ in ROUTES}
ROUTE_AUTHZ_CLASS_MAP = {(method, path): ("tenant-admin" if authorization == "governed_reviewer_capability" else "tenant-member") for method, path, authorization in ROUTES}

def _ctx(request: Request, method: str, path: str):
    from agents.route_policy import RouteAuthorizationClass
    return require_route_authorization(request, authorization_class=RouteAuthorizationClass(ROUTE_AUTHZ_CLASS_MAP[(method, path)]), route_hint=f"{method} {path}")
async def _body(request: Request) -> dict[str, Any]:
    try: value = await request.json()
    except Exception: return {}
    return value if isinstance(value, dict) else {}

@router.get(f"{BASE}/capabilities")
async def capabilities(request: Request): _ctx(request, "GET", f"{BASE}/capabilities"); return plugin_api.capabilities()
@router.get(f"{BASE}/candidates")
async def list_candidates(request: Request): return plugin_api.list_candidates(ctx=_ctx(request, "GET", f"{BASE}/candidates"), filters=dict(request.query_params))
@router.post(f"{BASE}/universes")
async def propose_universe(request: Request): return plugin_api.propose_universe(ctx=_ctx(request, "POST", f"{BASE}/universes"), payload=await _body(request))
@router.post(f"{BASE}/inspect")
async def inspect_target(request: Request): _ctx(request, "POST", f"{BASE}/inspect"); return plugin_api.inspect_target(payload=await _body(request))
@router.post(f"{BASE}/score")
async def score_target(request: Request): _ctx(request, "POST", f"{BASE}/score"); return plugin_api.score_target(payload=await _body(request))
@router.post(f"{BASE}/scan")
async def scan(request: Request):
    ctx = _ctx(request, "POST", f"{BASE}/scan")
    payload = await _body(request)
    targets = list(payload.get("repositories") or [])[: int(payload.get("max_targets") or 25)]
    observations = [plugin_api.inspect_target(payload={"repository": target}) for target in targets]
    if not observations:
        observations = [plugin_api.fixture_observation()]
    return {"status": "ok", "scan": {"status": "COMPLETED", "partial": len(targets) < len(payload.get("repositories") or [])}, "observations": observations, "organization_id": getattr(ctx, "organization_id", None)}
@router.post(f"{BASE}/candidates")
async def submit_candidate(request: Request): return plugin_api.submit_candidate(ctx=_ctx(request, "POST", f"{BASE}/candidates"), payload=await _body(request))
@router.get(f"{BASE}/candidates/{{candidate_id}}")
async def candidate_state(candidate_id: str, request: Request): return plugin_api.candidate_state(ctx=_ctx(request, "GET", f"{BASE}/candidates/{{candidate_id}}"), candidate_id=candidate_id)
@router.post(f"{BASE}/candidates/{{candidate_id}}/review")
async def review_candidate(candidate_id: str, request: Request): return plugin_api.review_candidate(ctx=_ctx(request, "POST", f"{BASE}/candidates/{{candidate_id}}/review"), candidate_id=candidate_id, payload=await _body(request))
@router.post(f"{BASE}/candidates/{{candidate_id}}/actions")
async def propose_action(candidate_id: str, request: Request): return plugin_api.propose_action(ctx=_ctx(request, "POST", f"{BASE}/candidates/{{candidate_id}}/actions"), candidate_id=candidate_id, payload=await _body(request))
@router.get(f"{BASE}/candidates/{{candidate_id}}/replay")
async def replay(candidate_id: str, request: Request): return plugin_api.replay(ctx=_ctx(request, "GET", f"{BASE}/candidates/{{candidate_id}}/replay"), candidate_id=candidate_id)
