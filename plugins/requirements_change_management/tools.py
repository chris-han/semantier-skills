from __future__ import annotations
import json
from contracts.requirements_plugin_domain import RequirementReviewObligationV1

_OWNER_SERVICE = None

def bind_owner_service(service) -> None:
    global _OWNER_SERVICE
    _OWNER_SERVICE = service

def requirements_change_compare(args, **kwargs):
    return json.dumps({"ok":True,"requirement_id":args["requirement_id"],"before":args["before"],"after":args["after"],"changed":args["before"] != args["after"]},ensure_ascii=False)

def requirements_change_impact(args, **kwargs):
    obligations=[RequirementReviewObligationV1.model_validate(x).model_dump(mode="json") for x in args.get("obligations",[])]
    return json.dumps({"ok":True,"requirement_id":args["requirement_id"],"coverage":"BOUNDED","obligations":obligations},ensure_ascii=False)

def requirements_change_baseline(args, **kwargs):
    if _OWNER_SERVICE is None:
        return json.dumps({"ok":False,"code":"OWNER_SERVICE_CONTEXT_REQUIRED"})
    baseline=_OWNER_SERVICE.current_baseline()
    return json.dumps({"ok":True,"baseline":baseline.model_dump(mode="json")})

def requirements_change_propose(args, **kwargs):
    if _OWNER_SERVICE is None:
        return json.dumps({"ok":False,"code":"OWNER_SERVICE_CONTEXT_REQUIRED"})
    return json.dumps({"ok":False,"code":"TYPED_DELTA_REQUIRED","message":"Use the owner-bound typed proposal adapter; plugin does not fabricate deltas."})

def requirements_change_submit_review(args, **kwargs):
    return json.dumps({"ok":True,"review_receipt_ref":f'plugin-review:{args["idempotency_key"]}',"candidate_ref":args["candidate_ref"],"reviewer_ref":args["reviewer_ref"],"disposition":args["disposition"],"basis_refs":args["basis_refs"],"next_action":"OWNER_ADMISSION_REQUIRED","admitted":False,"activated":False})

def requirements_change_publish(args, **kwargs):
    if _OWNER_SERVICE is None:
        return json.dumps({"ok":False,"code":"OWNER_SERVICE_CONTEXT_REQUIRED"})
    return json.dumps({"ok":False,"code":"TYPED_OWNER_PUBLICATION_REQUEST_REQUIRED","message":"Publication requires exact typed candidate, qualification and expected-head pins through core owner service."})
