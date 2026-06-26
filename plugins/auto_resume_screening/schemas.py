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

LIST_SESSION_UPLOADS_SCHEMA = {
    "description": "List supported and unsupported uploaded files for the active workspace session.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

RESOLVE_UPLOADED_RESUME_SCHEMA = {
    "description": (
        "Resolve a resume filename, uploads path, or upload_id against the active session upload manifest."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Resume filename, uploads/<filename> path, or upload_id.",
            },
            "resume_path": {
                "type": "string",
                "description": "Backward-compatible alias for query.",
            },
        },
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

EXTRACT_ROLE_TERMS_SCHEMA = {
    "description": (
        "Fetch configured occupation index pages and return extracted role terms missing "
        "from the plugin role-term heuristic."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "source_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional source URLs. Defaults to Zhaopin job categories and O*NET all occupations."
                ),
            },
            "timeout_seconds": {"type": "number", "default": 15},
            "max_terms_per_source": {"type": "integer", "default": 200, "minimum": 1},
        },
    },
}
