#!/usr/bin/env python3
"""Run one sealed paired qualification episode per fresh subprocess."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse

ARMS = {
    "B0": "97b2861a6d18984675dd3fb9946463b1c74d23b6",
    "B1": "f449fe14b6a8b6b3a247ff703a9d7c5fdceb8203",
}
SKILL = "semantier--semantier-thinking"
TOOLS = {"skills_list", "skill_view", "read_file"}
CASES = Path(__file__).with_name("native_multiturn_cases.json")


def run(args, work, case):
    from dotenv import dotenv_values
    import httpx

    conf = dotenv_values(args.route)
    base = conf["DASHSCOPE_BASE_URL"]
    model = conf["DASHSCOPE_MAIN_MODEL"]
    host = urlparse(base).hostname
    assert model == "qwen3.5-plus" and host
    assert hashlib.sha256(host.encode()).hexdigest() == "23b690e1c43d9c71fc3089be590a305b963fed55a8843320d19d588c0c7562d6"
    calls = []
    events = []
    denied = []
    send = httpx.Client.send

    def bounded_send(client, request, *pos, **kw):
        if args.preflight or request.url != httpx.URL(base + "/chat/completions"):
            raise RuntimeError("Qualification blocked network request")
        body = json.loads(request.content)
        if (len(calls) >= 3 or body.get("model") != model
                or len(request.content) > 128_000
                or not 0 < body.get("max_tokens", body.get("max_completion_tokens", 0)) <= 1200):
            raise RuntimeError("Qualification model budget exceeded")
        entry = {"model": model, "request_bytes": len(request.content)}
        calls.append(entry)
        started = time.monotonic()
        response = send(client, request, *pos, **kw)
        entry.update(status=response.status_code, seconds=round(time.monotonic() - started, 3))
        if not body.get("stream"):
            data = response.json()
            entry.update(usage=data.get("usage"), response_model=data.get("model"),
                         fingerprint=data.get("system_fingerprint"),
                         error_code=data.get("error", {}).get("code"))
        return response

    httpx.Client.send = bounded_send
    from run_agent import AIAgent
    from agent.prompt_builder import build_skills_system_prompt
    from hermes_cli.plugins import get_plugin_manager
    from model_tools import get_tool_definitions, handle_function_call
    from tools.registry import registry

    # Initialize the native registry, then remove all effectful/auxiliary tools.
    get_tool_definitions(enabled_toolsets=["skills", "file"], quiet_mode=True)
    for name in set(registry.get_all_tool_names()) - TOOLS:
        registry.deregister(name)

    fixture = case.get("file")
    if fixture:
        (work / fixture).write_text(case["content"])
        (work / fixture).chmod(0o444)

    def gate(tool_name, args=None, **_):
        args = args or {}
        allowed = (
            tool_name == "skills_list"
            or (tool_name == "skill_view" and args.get("name") in (SKILL, "semantier-thinking")
                and args.get("file_path") in (None, "", "SKILL.md", *references))
            or (tool_name == "read_file" and fixture is not None and args.get("path") in (fixture, f"./{fixture}", str(work / fixture)))
        )
        if not allowed:
            denied.append({"tool": tool_name, "args": args})
            return {"action": "block", "message": "Qualification fixture allowlist"}
        return None

    skill_dir = work / "home/skills/semantier-thinking"
    references = {path.relative_to(skill_dir).as_posix()
                  for path in (skill_dir / "references").glob("*.md")}
    agent = AIAgent(
        provider="openai", base_url=base, api_key="offline" if args.preflight else conf["DASHSCOPE_API_KEY"],
        model=model, enabled_toolsets=["skills", "file"], max_iterations=3,
        max_tokens=1200, quiet_mode=True, skip_memory=True, skip_background_review=True,
        skip_context_files=True, save_trajectories=False,
        request_overrides={"temperature": 0, "extra_body": {"enable_thinking": False}},
        tool_start_callback=lambda call, tool, params: events.append(
            {"event": "start", "id": call, "tool": tool, "args": params}),
        tool_complete_callback=lambda call, tool, params, result: events.append(
            {"event": "complete", "id": call, "tool": tool, "args": params, "result": result}),
    )
    get_plugin_manager()._hooks.setdefault("pre_tool_call", []).append(gate)
    try:
        index = build_skills_system_prompt(available_tools=set(agent.valid_tool_names),
                                         available_toolsets={"skills", "file"},
                                         skills_dir_override=work / "home/skills")
        assert SKILL in index, index
        assert set(agent.valid_tool_names) == TOOLS, agent.valid_tool_names
        if args.preflight:
            def invoke(name, params):
                return json.loads(handle_function_call(name, params, "preflight"))
            assert invoke("skill_view", {"name": SKILL})["success"]
            assert "KESTREL-17" in str(invoke("read_file", {"path": fixture}))
            for name, params in [
                ("read_file", {"path": "../outside.txt"}),
                ("write_file", {"path": fixture, "content": "overwrite"}),
                ("patch", {}), ("terminal", {}), ("web_search", {}),
            ]:
                reply = invoke(name, params)
                assert not reply.get("success") and reply.get("error"), reply
            assert (work / fixture).read_text() == case["content"]
            return {"arm": args.arm, "tools": sorted(TOOLS), "denied": denied, "preflight": "PASS"}
        history = None
        turns = []
        for prompt in case["turns"]:
            calls.clear()
            events.clear()
            denied.clear()
            start = time.monotonic()
            response = agent.run_conversation(prompt, conversation_history=history)
            history = response.get("messages")
            turns.append({"prompt": prompt, "response": response, "transport": list(calls),
                          "events": list(events), "denied": list(denied),
                          "seconds": round(time.monotonic() - start, 3)})
            if any(row.get("status") != 200 for row in calls):
                break
        return {"arm": args.arm, "case": case["id"], "model": model, "tools": sorted(TOOLS),
                "produced_at": datetime.now(timezone.utc).isoformat(), "turns": turns}
    finally:
        agent.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("hermes", "route", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--arm", choices=ARMS, required=True)
    parser.add_argument("--case", default="pilot")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    bundle = json.loads(CASES.read_text())
    cases = {case["id"]: case for case in [bundle["pilot"], *bundle["cases"]]}
    with tempfile.TemporaryDirectory(prefix="thinking-episode-") as directory:
        work = Path(directory)
        home = work / "home"
        skills = home / "skills"
        skills.mkdir(parents=True)
        package = "skills/semantier-thinking"
        repo = Path(__file__).resolve().parents[3]
        archive = subprocess.check_output(["/usr/bin/git", "-C", str(repo), "archive", ARMS[args.arm], package])
        subprocess.run(["tar", "xf", "-", "--strip-components=1", "-C", str(skills)],
                       input=archive, check=True)
        os.chdir(work)
        os.environ.update(HERMES_HOME=str(home), TERMINAL_CWD=str(work), TERMINAL_ENV="local")
        sys.path.insert(0, str(args.hermes.resolve()))
        result = run(args, work, cases[args.case])
        with args.output.open("x") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2, default=str)
            handle.write("\n")


if __name__ == "__main__":
    main()
