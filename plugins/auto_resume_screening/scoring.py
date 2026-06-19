from __future__ import annotations

import hashlib
import re
from typing import Any


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _contains(text: str, keyword: str) -> bool:
    return keyword.lower() in text.lower()


def _experience_years(text: str) -> float:
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*(?:years?|年)", text, flags=re.IGNORECASE)
    values = [float(item) for item in matches]
    return max(values) if values else 0.0


def _text_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def rank_resumes(job_profile: dict[str, Any], resumes: list[dict[str, Any]]) -> dict[str, Any]:
    required = _as_list(job_profile.get("required_keywords"))
    preferred = _as_list(job_profile.get("preferred_keywords"))
    negative = _as_list(job_profile.get("negative_keywords"))
    min_years = float(job_profile.get("min_years_experience") or 0)

    rankings: list[dict[str, Any]] = []
    for index, resume in enumerate(resumes):
        text = str(resume.get("text") or "")
        required_hits = [keyword for keyword in required if _contains(text, keyword)]
        preferred_hits = [keyword for keyword in preferred if _contains(text, keyword)]
        negative_hits = [keyword for keyword in negative if _contains(text, keyword)]
        years = _experience_years(text)

        score = 0
        score += 50 if required and len(required_hits) == len(required) else len(required_hits) * 20
        score += len(preferred_hits) * 10
        score += 15 if min_years and years >= min_years else 0
        score -= len(negative_hits) * 30
        score = max(0, min(100, score))

        if score >= 70:
            recommendation = "shortlist"
        elif score >= 40:
            recommendation = "review"
        else:
            recommendation = "reject"

        candidate_id = str(resume.get("candidate_id") or f"candidate_{index + 1}")
        rankings.append(
            {
                "candidate_id": candidate_id,
                "display_name_zh": str(
                    resume.get("display_name_zh") or candidate_id or f"候选人{index + 1}"
                ),
                "source_path": str(resume.get("source_path") or ""),
                "score": score,
                "recommendation": recommendation,
                "evidence": {
                    "required_hits": required_hits,
                    "preferred_hits": preferred_hits,
                    "negative_hits": negative_hits,
                    "experience_years": years,
                    "text_sha256": _text_hash(text),
                },
            }
        )

    rankings.sort(key=lambda item: (-int(item["score"]), item["candidate_id"]))
    return {
        "status": "ok",
        "job_title": str(job_profile.get("title") or ""),
        "ranking_count": len(rankings),
        "rankings": rankings,
    }
