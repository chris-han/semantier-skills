from __future__ import annotations

import argparse
import json
import os

from .tools import inspect_target, score_target, list_candidates
from contracts.investment_opportunity import RuntimeContextDTO

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="vc-github-opportunity-radar")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("repository")
    score_parser = subparsers.add_parser("score")
    score_parser.add_argument("observation_json")
    subparsers.add_parser("candidates")
    universe_parser = subparsers.add_parser("universe")
    universe_parser.add_argument("name")
    universe_parser.add_argument("--topic", action="append", default=[])
    subparsers.add_parser("replay").add_argument("candidate_id")
    args = parser.parse_args(argv)
    if args.command == "inspect": result = inspect_target({"repository": args.repository})
    elif args.command == "score": result = score_target({"observation": json.loads(args.observation_json)})
    elif args.command == "candidates": result = list_candidates({}, runtime_context={"organization_id": os.environ.get("SEMANTIER_ORGANIZATION_ID", ""), "actor_id": os.environ.get("SEMANTIER_ACTOR_ID", "")})
    elif args.command == "universe": result = json.dumps({"status": "DRAFT", "name": args.name, "topics": args.topic})
    else:
        from services.investment_opportunity_candidate_service import StoreBackedInvestmentOpportunityCandidateService
        organization_id = os.environ.get("SEMANTIER_ORGANIZATION_ID", "")
        actor_id = os.environ.get("SEMANTIER_ACTOR_ID", "")
        result = json.dumps({"status": "ERROR", "error_code": "TRUSTED_RUNTIME_CONTEXT_REQUIRED"}) if not organization_id or not actor_id else json.dumps(StoreBackedInvestmentOpportunityCandidateService().build_replay_envelope(args.candidate_id, RuntimeContextDTO(organization_id=organization_id, workspace_id=os.environ.get("SEMANTIER_WORKSPACE_ID"), actor_id=actor_id)).__dict__, default=str)
    print(result)
    return 0
