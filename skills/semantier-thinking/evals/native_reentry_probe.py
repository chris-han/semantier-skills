#!/usr/bin/env python3
"""Optional bounded Hermes-native skill routing probe (not CI; network/model cost).

Compare current skill source to one pinned prior Git revision. The probe is a
diagnostic for actual skill_view events and short multi-turn behavior, NOT an
independent efficacy experiment or generalized learning proof.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]  # semantier-skills repo
RUNTIME = REPO.parent
HERMES = RUNTIME / "hermes-agent"
PIN = "97b2861a6d18984675dd3fb9946463b1c74d23b6"
CONVERSATION = (
    "An experiment's proposed agent workflow scored 1/4 while a deterministic repair scored 4/4. "
    "The report now says this rules out the whole agentic workflow learning method. "
    "What does the result actually establish? Which single evidence check matters next?",
    "We inspected source: the graph references evidence_complete_false, while the supplied inputs only have "
    "evidence_complete. Is that reference a native fallback? Update the attribution, preserving the original scores.",
    "Computing NOT evidence_complete avoids missing input, but a review condition is true at the same time, "
    "so the controller has two eligible outgoing branches and stops. What should we check next, "
    "and what can we NOT claim from the already-exposed holdout?"
)
CONTROL = "The diagnosed typo is already fixed. Confirm that the existing unit test passes; no reasoning dispute remains."


def previous_file(relative):
    return subprocess.check_output(
        ["git", "show", f"{PIN}:{relative}"], cwd=REPO
    ).decode("utf-8")


def install(tmp: Path, arm: str):
    dest = tmp / "skills" / "semantier-thinking"
    shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if arm == "before":
        for relative in (
            "SKILL.md", "references/critical-inquiry.md", "references/evidence-handoff.md"
        ):
            (dest / relative).write_text(
                previous_file(f"skills/semantier-thinking/{relative}"), encoding="utf-8"
            )
        (dest / "references/diagnostic-revision.md").unlink(missing_ok=True)
    return dest


def probe(arm, *, model, base, key, max_turns, scenario):
    with tempfile.TemporaryDirectory(prefix=f"thinking-{arm}-") as home:
        home = Path(home)
        install(home, arm)
        # Set before importing Hermes and constructing the session.
        os.environ["HERMES_HOME"] = str(home)
        if str(HERMES) not in sys.path:
            sys.path.insert(0, str(HERMES))
        from run_agent import AIAgent
        from agent.prompt_builder import build_skills_system_prompt
        events = []
        def on_start(call_id, tool, args):
            if tool in {"skill_view", "skills_list"}:
                events.append({"tool": tool, "name": args.get("name") if isinstance(args, dict) else None,
                               "file": args.get("file_path") if isinstance(args, dict) else None})
        agent = AIAgent(
            provider="openai", base_url=base, api_key=key, model=model,
            enabled_toolsets=["skills"], max_iterations=9, max_tokens=1200,
            quiet_mode=True, skip_context_files=False, skip_memory=True,
            skip_background_review=True, save_trajectories=False,
            request_overrides={"temperature": 0, "extra_body": {"enable_thinking": False}},
            tool_start_callback=on_start, run_budget_seconds=65,
        )
        try:
            actual_tools = sorted(agent.valid_tool_names)
            index = build_skills_system_prompt(
                available_tools=set(agent.valid_tool_names),
                available_toolsets={"skills"},
                skills_dir_override=home / "skills",
            )
            ready = ("semantier--semantier-thinking" in index and "skill_view" in actual_tools)
            if not ready:
                return {"arm": arm, "error": "SKILL_NOT_DISCOVERABLE", "tools": actual_tools,
                        "index_contains": "semantier--semantier-thinking" in index}
            results = []
            for turn in ((CONTROL,) if scenario == "control" else CONVERSATION[:max_turns]):
                try:
                    response = agent.run_conversation(turn)
                    results.append({
                        "completed": response.get("completed"), "failed": response.get("failed"),
                        "final_response": (response.get("final_response") or "")[:2200],
                        "api_calls": response.get("api_calls"),
                        "skill_events_so_far": len(events),
                    })
                except Exception as exc:
                    results.append({"error_type": type(exc).__name__,
                                    "error": str(exc)[:250]})
                    break
            return {"arm": arm, "tools": actual_tools, "skill_discoverable": ready,
                    "events": events, "turns": results}
        finally:
            agent.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turns", type=int, default=2, choices=(1, 2, 3))
    parser.add_argument("--arm", choices=("before", "after", "both"), default="both")
    parser.add_argument("--scenario", choices=("recovery", "control"), default="recovery")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    from dotenv import dotenv_values
    conf = dotenv_values(RUNTIME / ".semantier-home" / ".env")
    model = conf.get("DASHSCOPE_MAIN_MODEL")
    base = conf.get("DASHSCOPE_BASE_URL")
    key = conf.get("DASHSCOPE_API_KEY")
    if not (model and base and key):
        raise SystemExit("NO_CONFIGURED_DEVELOPMENT_MODEL_ROUTE — no calls were made")
    rows = []
    for arm in (("before", "after") if args.arm == "both" else (args.arm,)):
        rows.append(probe(arm, model=model, base=base, key=key, max_turns=args.turns, scenario=args.scenario))
    result = {
        "type": "HERMES_NATIVE_SKILL_DISCOVERY_DIAGNOSTIC",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_alias": model, "model_revision": "UNKNOWN", "cost": "UNKNOWN",
        "reference_ref": PIN, "candidate": "working-tree source v0.1.2",
        "scenario": args.scenario,
        "status": "OBSERVED_IF_COMPLETED_NOT_GENERALIZED",
        "records": rows,
    }
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
