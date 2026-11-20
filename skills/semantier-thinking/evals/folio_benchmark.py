#!/usr/bin/env python3
"""FOLIO natural-language entailment adapter and bounded model-command ablation.

No model is invoked without explicit --driver. Dataset bytes are never bundled.
Input to driver: JSON object {messages:[{role,content},...],case_id,condition} on stdin.
Output from driver: one JSON object {label:True|False|Uncertain} on stdout.
"""
import argparse
import json
import shlex
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = {"True", "False", "Uncertain"}
PINNED_REPO = "Yale-LILY/FOLIO"
PINNED_COMMIT = "5d7bb84c7edab3fb358e057d2807f19cf5cf5e2d"
PINNED_PATH = "data/v0.0/folio-validation.jsonl"


def parse_examples(path, limit):
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be 1..1000")
    examples = []
    with Path(path).open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row.get("premises"), list) or not row["premises"] or not all(isinstance(x, str) and x.strip() for x in row["premises"]):
                raise ValueError(f"line {lineno}: invalid premises")
            if not isinstance(row.get("conclusion"), str) or not row["conclusion"].strip() or row.get("label") not in LABELS:
                raise ValueError(f"line {lineno}: invalid conclusion/label")
            examples.append({"case_id": f"line-{lineno}", "premises": row["premises"], "conclusion": row["conclusion"], "label": row["label"]})
            if len(examples) >= limit:
                break
    if not examples:
        raise ValueError("no cases in selected dataset")
    return examples


def make_messages(ex, condition):
    user = "Given only these premises, is the conclusion entailed (True), contradicted (False), or neither (Uncertain)?\n" + \
           "Premises:\n" + "\n".join(f"{i}. {p}" for i, p in enumerate(ex["premises"], 1)) + \
           "\nConclusion: " + ex["conclusion"] + \
           '\nReturn JSON only: {"label":"True|False|Uncertain"}. Do not use outside world knowledge as an extra premise.'
    system = "You are an entailment evaluator. Use the provided premises only. Return one of True, False, Uncertain as JSON."
    if condition == "skill":
        system = (ROOT / "SKILL.md").read_text(encoding="utf-8") + "\n\n" + (ROOT / "references/critical-inquiry.md").read_text(encoding="utf-8") + \
                 "\n\nEvaluation mode: deliver, inquiry, L2. Follow the supplied-premises boundary. Return only the asked JSON label."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def invoke_driver(argv, ex, condition, timeout):
    payload = {"case_id": ex["case_id"], "condition": condition, "messages": make_messages(ex, condition)}
    proc = subprocess.run(argv, input=json.dumps(payload, ensure_ascii=False), capture_output=True, text=True, encoding="utf-8", timeout=timeout, check=False)
    if proc.returncode:
        raise RuntimeError(f"driver exited nonzero: {proc.returncode}")
    try:
        prediction = json.loads(proc.stdout.strip())["label"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("driver output must be JSON object containing label") from exc
    if prediction not in LABELS:
        raise ValueError(f"unsupported prediction label: {prediction!r}")
    return prediction


def score(results):
    valid = [r for r in results if r.get("prediction") in LABELS]
    correct = sum(r["prediction"] == r["gold"] for r in valid)
    return {"total": len(results), "valid": len(valid), "invalid": len(results) - len(valid), "correct": correct,
            "accuracy_total": round(correct / len(results), 4) if results else None}


def run(path, limit, driver=None, timeout=30):
    cases = parse_examples(path, limit)
    output = {"benchmark": "FOLIO v0.0 validation (natural-language labels)", "dataset_repo": PINNED_REPO, "dataset_commit": PINNED_COMMIT,
              "dataset_path": PINNED_PATH, "local_dataset": str(path), "selected": len(cases), "gold_counts": dict(Counter(x["label"] for x in cases)),
              "eval_type": "PROMPT_LEVEL_ABLATION" if driver else "DATASET_SCHEMA_SMOKE_ONLY", "conditions": {}}
    if driver is None:
        output["model_runs"] = 0
        output["caveat"] = "Dataset parser check only. No model was invoked and no accuracy/improvement can be claimed."
        return output
    for condition in ("baseline", "skill"):
        results = []
        for ex in cases:
            try:
                predicted = invoke_driver(driver, ex, condition, timeout)
                results.append({"id": ex["case_id"], "gold": ex["label"], "prediction": predicted})
            except (RuntimeError, ValueError, subprocess.TimeoutExpired, OSError) as e:
                results.append({"id": ex["case_id"], "gold": ex["label"], "prediction": None, "error": type(e).__name__})
        output["conditions"][condition] = {"metrics": score(results), "cases": results}
    output["model_runs"] = 2 * len(cases)
    output["paired_delta_total_accuracy"] = round(output["conditions"]["skill"]["metrics"]["accuracy_total"] - output["conditions"]["baseline"]["metrics"]["accuracy_total"], 4)
    output["caveat"] = "Same dataset cases, two prompts. Prompt-level ablation is not installed-skill end-to-end qualification or evidence of generalized reasoning improvement."
    return output


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True, type=Path, help="Local FOLIO JSONL; never downloaded automatically")
    ap.add_argument("--limit", type=int, default=20, help="Bounded cases; default 20")
    ap.add_argument("--driver", default=None, help="Explicit command implementing stdin JSON -> stdout JSON; model cost/network may apply")
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--out", type=Path, default=None, help="Optional local output; no automatic upload")
    args = ap.parse_args()
    if args.timeout < 1 or args.timeout > 600:
        ap.error("timeout must be 1..600")
    driver = shlex.split(args.driver) if args.driver else None
    if driver == []:
        ap.error("empty driver")
    report = run(args.dataset, args.limit, driver=driver, timeout=args.timeout)
    serialized = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.write_text(serialized, encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
