from __future__ import annotations

import argparse
import json
from pathlib import Path

from .track_b import evaluate_bank_marketing_zip, evaluate_kdd_orange_small, evaluate_online_shoppers_zip
from .track_c import evaluate_criteo


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bank", type=Path, required=True)
    parser.add_argument("--online-shoppers", type=Path, required=True)
    parser.add_argument("--kdd", type=Path, required=True)
    parser.add_argument("--kdd-labels", type=Path, required=True)
    parser.add_argument("--criteo", type=Path, required=True)
    parser.add_argument("--criteo-limit", type=int, default=200000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = {
        "track_b": [
            evaluate_bank_marketing_zip(args.bank),
            evaluate_online_shoppers_zip(args.online_shoppers),
            evaluate_kdd_orange_small(args.kdd, args.kdd_labels),
        ],
        "track_c": evaluate_criteo(args.criteo, limit=args.criteo_limit),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
