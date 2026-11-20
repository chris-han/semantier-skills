#!/usr/bin/env python3
"""Bilingual route probes: default is fixture validation, never a model call.

An optional driver reads one UTF-8 JSON input on stdin:
{case_id, locale, condition, messages}. It emits one JSON object:
{lead, depth, mode, specialists, ask_user, answer}.
Route fields are SELF-REPORTED; this is not native Hermes skill activation.
"""
import argparse
import json
import re
import shlex
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = Path(__file__).with_name("bilingual_pairs.json")
LANGUAGES = ("en", "zh", "mixed")
LEADS = {"none", "inquiry", "decision", "writing"}
DEPTHS = {"L0", "L1", "L2", "L3"}
MODES = {"deliver", "coach"}
SPECIALISTS = {"ethical", "organizational"}
HAN = re.compile(r"[\u3400-\u9fff]")


def route_tuple(pred):
    if not isinstance(pred, dict) or pred.get("lead") not in LEADS or pred.get("depth") not in DEPTHS:
        return None
    if pred.get("mode") not in MODES or type(pred.get("ask_user")) is not bool:
        return None
    specs = pred.get("specialists")
    if not isinstance(specs, list) or len(specs) != len(set(map(str, specs))) or any(s not in SPECIALISTS for s in specs):
        return None
    if not isinstance(pred.get("answer"), str) or not pred["answer"].strip():
        return None
    return pred["lead"], pred["depth"], pred["mode"], tuple(sorted(specs)), pred["ask_user"]


def expected_tuple(exp):
    return exp["lead"], exp["depth"], exp["mode"], tuple(sorted(exp["specialists"])), exp["ask_user"]


def load_pairs(path=DATASET, limit=6):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be 1..100")
    pairs = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= 100:
        raise ValueError("expected a bounded nonempty list of bilingual pairs")
    ids = set()
    for i, case in enumerate(pairs):
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"].strip() or case["id"] in ids:
            raise ValueError(f"case {i}: missing or duplicate id")
        ids.add(case["id"])
        exp, req, output_lang = (case.get(key) for key in ("expected", "requests", "response_language"))
        if not isinstance(exp, dict) or not isinstance(req, dict) or not isinstance(output_lang, dict):
            raise ValueError(f"case {i}: missing route/locale fields")
        if exp.get("lead") not in LEADS or exp.get("depth") not in DEPTHS or exp.get("mode") not in MODES:
            raise ValueError(f"case {i}: invalid route")
        specs = exp.get("specialists")
        if not isinstance(specs, list) or len(specs) != len(set(map(str, specs))) or any(s not in SPECIALISTS for s in specs):
            raise ValueError(f"case {i}: invalid specialists")
        if type(exp.get("ask_user")) is not bool or (exp["lead"] == "none") != (exp["depth"] == "L0"):
            raise ValueError(f"case {i}: incompatible route")
        if exp["depth"] == "L0" and (specs or exp["mode"] == "coach"):
            raise ValueError(f"case {i}: spurious L0 coach or specialist")
        if set(req) != set(LANGUAGES) or set(output_lang) != set(LANGUAGES):
            raise ValueError(f"case {i}: missing language variant")
        if any(not isinstance(req[locale], str) or not req[locale].strip() or output_lang[locale] not in {"en", "zh"}
               for locale in LANGUAGES):
            raise ValueError(f"case {i}: invalid request/response locale")
        if HAN.search(req["en"]) or not HAN.search(req["zh"]) or not HAN.search(req["mixed"]) or not re.search("[A-Za-z]", req["mixed"]):
            raise ValueError(f"case {i}: inappropriate locale fixture")
        quote = case.get("preserve_quote")
        if quote is not None and (not isinstance(quote, str) or not quote or any(quote not in req[locale] for locale in LANGUAGES)):
            raise ValueError(f"case {i}: missing verbatim quote")
    return pairs[:limit]


INSTRUMENT = (
    "For this controlled prompt-level probe, complete the user request and return only a JSON object: "
    '{"lead":"none|inquiry|decision|writing","depth":"L0|L1|L2|L3",'
    '"mode":"deliver|coach","specialists":[],"ask_user":false,"answer":"..."}'
    ". Route fields should describe the action you chose, not a known oracle. "
    "Use specialists only for material reasoning gaps; ask_user means your answer contains a needed user question. "
    "Keep the user-facing answer in the requested language and do not invent evidence."
)


def make_messages(case, locale, condition):
    if locale not in LANGUAGES or condition not in {"baseline", "skill"}:
        raise ValueError("invalid locale/condition")
    system = "You are a careful assistant. Solve the user request without inventing facts or citations."
    if condition == "skill":
        system = (ROOT / "SKILL.md").read_text(encoding="utf-8") + "\n\n" + (
            ROOT / "references/language-and-terminology.md").read_text(encoding="utf-8")
    return [{"role": "system", "content": system},
            {"role": "system", "content": INSTRUMENT},
            {"role": "user", "content": case["requests"][locale]}]


def script_heuristic(answer):
    """Weak script check; short Chinese answers and quoted Chinese may fool it."""
    return "zh" if len(HAN.findall(answer)) >= 3 else "en"


def score_condition(rows):
    total = len(rows)
    valid = sum(route_tuple(r.get("prediction")) is not None for r in rows)
    route_ok = sum(route_tuple(r.get("prediction")) == expected_tuple(r["expected"]) for r in rows)
    script_ok = sum(route_tuple(r.get("prediction")) is not None and
                    script_heuristic(r["prediction"]["answer"]) == r["response_language"] for r in rows)
    quotes = sum(bool(r.get("preserve_quote")) for r in rows)
    quote_ok = sum(bool(r.get("preserve_quote")) and route_tuple(r.get("prediction")) is not None and
                   r["preserve_quote"] in r["prediction"]["answer"] for r in rows)
    return {"total": total, "valid": valid, "invalid": total - valid,
            "route_correct": route_ok, "route_accuracy_total": round(route_ok / total, 4) if total else None,
            "language_script_matched": script_ok,
            "language_script_heuristic_rate_total": round(script_ok / total, 4) if total else None,
            "quote_eligible": quotes, "quote_preserved": quote_ok}


def cross_locale_consistency(rows):
    by_id = defaultdict(dict)
    for row in rows:
        by_id[row["case_id"]][row["locale"]] = route_tuple(row.get("prediction"))
    complete = sum(set(v) == set(LANGUAGES) and all(v[k] is not None for k in LANGUAGES)
                   for v in by_id.values())
    consistent = sum(set(v) == set(LANGUAGES) and all(v[k] is not None for k in LANGUAGES) and
                     len({v[k] for k in LANGUAGES}) == 1 for v in by_id.values())
    return {"triples": len(by_id), "complete": complete, "consistent": consistent,
            "consistency_rate_total": round(consistent / len(by_id), 4) if by_id else None}


def invoke_driver(argv, case, locale, condition, timeout):
    data = {"case_id": case["id"], "locale": locale, "condition": condition,
            "messages": make_messages(case, locale, condition)}
    p = subprocess.run(argv, input=json.dumps(data, ensure_ascii=False), text=True,
                       encoding="utf-8", capture_output=True, timeout=timeout, check=False)
    if p.returncode:
        raise RuntimeError("driver exited nonzero")
    try:
        result = json.loads(p.stdout.strip())
    except (TypeError, ValueError) as e:
        raise ValueError("driver output is not JSON") from e
    if route_tuple(result) is None:
        raise ValueError("driver output has an invalid route or empty answer")
    return result


def run(path=DATASET, limit=6, driver=None, timeout=30):
    cases = load_pairs(path, limit)
    report = {"benchmark": "Semantier Thinking bilingual synthetic route probes",
              "fixture": str(path), "selected_pairs": len(cases),
              "prompt_variants": len(cases) * len(LANGUAGES),
              "languages": list(LANGUAGES), "model_calls_attempted": 0,
              "eval_type": "PROMPT_LEVEL_SELF_REPORTED_ROUTE_ABLATION" if driver else "ORACLE_SCHEMA_SMOKE_ONLY"}
    if driver is None:
        report["caveat"] = "Oracle schema only; model calls = 0. No performance or language-parity claim."
        return report
    if not isinstance(driver, (list, tuple)) or not driver or type(timeout) is not int or not 1 <= timeout <= 600:
        raise ValueError("invalid driver or timeout")
    output = {"baseline": [], "skill": []}
    for idx, case in enumerate(cases):
        for locale_idx, locale in enumerate(LANGUAGES):
            order = ("baseline", "skill") if (idx + locale_idx) % 2 == 0 else ("skill", "baseline")
            for condition in order:
                row = {"case_id": case["id"], "locale": locale, "expected": case["expected"],
                       "response_language": case["response_language"][locale],
                       "preserve_quote": case.get("preserve_quote")}
                report["model_calls_attempted"] += 1
                try:
                    row["prediction"] = invoke_driver(driver, case, locale, condition, timeout)
                except (RuntimeError, ValueError, subprocess.TimeoutExpired, OSError) as e:
                    row["prediction"], row["error_type"] = None, type(e).__name__
                output[condition].append(row)
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report["conditions"] = {
        condition: {"metrics": score_condition(rows),
                    "cross_language": cross_locale_consistency(rows), "cases": rows}
        for condition, rows in output.items()
    }
    base = report["conditions"]["baseline"]["metrics"]["route_accuracy_total"]
    skill = report["conditions"]["skill"]["metrics"]["route_accuracy_total"]
    report["delta_self_reported_route_accuracy"] = round(skill - base, 4)
    report["caveat"] = (
        "Self-reported prompt-level routes and a script heuristic, not independently observed Hermes activation, "
        "language fluency, factual correctness or user learning. Synthetic labels are not independent benchmark gold."
    )
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, default=DATASET)
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--driver", default=None, help="Explicit model driver; external calls and billing may apply")
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    if not 1 <= args.timeout <= 600:
        ap.error("timeout must be 1..600")
    driver = shlex.split(args.driver) if args.driver else None
    result = json.dumps(run(args.dataset, args.limit, driver, args.timeout), ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.write_text(result, encoding="utf-8")
    print(result)


if __name__ == "__main__":
    main()
