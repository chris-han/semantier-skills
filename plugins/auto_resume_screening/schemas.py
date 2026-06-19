from __future__ import annotations

TOOLSET_NAME = "auto_resume_screening"

JOB_PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "required_keywords": {"type": "array", "items": {"type": "string"}, "default": []},
        "preferred_keywords": {"type": "array", "items": {"type": "string"}, "default": []},
        "negative_keywords": {"type": "array", "items": {"type": "string"}, "default": []},
        "min_years_experience": {"type": "number", "default": 0},
    },
    "required": ["title"],
}

EXTRACT_RESUME_TEXT_SCHEMA = {
    "description": "Extract normalized text from one uploaded resume file.",
    "parameters": {
        "type": "object",
        "properties": {
            "resume_path": {
                "type": "string",
                "description": "Path or uploaded filename for a resume document.",
            },
        },
        "required": ["resume_path"],
    },
}

RANK_RESUME_CANDIDATES_SCHEMA = {
    "description": "Rank extracted resume texts against a deterministic job profile.",
    "parameters": {
        "type": "object",
        "properties": {
            "job_profile": JOB_PROFILE_SCHEMA,
            "resumes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "candidate_id": {"type": "string"},
                        "source_path": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["candidate_id", "source_path", "text"],
                },
            },
        },
        "required": ["job_profile", "resumes"],
    },
}

SCREEN_RESUMES_SCHEMA = {
    "description": (
        "Extract and rank uploaded resumes, then persist a workspace-scoped screening artifact."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "job_profile": JOB_PROFILE_SCHEMA,
            "resume_paths": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "run_label": {"type": "string", "default": "resume-screening"},
        },
        "required": ["job_profile", "resume_paths"],
    },
}
