from __future__ import annotations

TOOLSET_NAME = "resilient-public-data-collection"

PROBE_PUBLIC_URL_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "Public HTTP(S) URL to probe."},
        "referer": {
            "type": "string",
            "description": "Optional public page URL that legitimately links to the target.",
        },
        "timeout_seconds": {
            "type": "number",
            "default": 20,
            "minimum": 1,
            "maximum": 60,
        },
        "sample_bytes": {
            "type": "integer",
            "default": 65536,
            "minimum": 1,
            "maximum": 262144,
        },
    },
    "required": ["url"],
}

INSPECT_PUBLIC_PAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "Public HTML page to inspect."},
        "referer": {"type": "string"},
        "timeout_seconds": {
            "type": "number",
            "default": 20,
            "minimum": 1,
            "maximum": 60,
        },
        "max_html_bytes": {
            "type": "integer",
            "default": 2097152,
            "minimum": 1024,
            "maximum": 5242880,
        },
        "max_links": {
            "type": "integer",
            "default": 200,
            "minimum": 1,
            "maximum": 1000,
        },
    },
    "required": ["url"],
}

FREEZE_PUBLIC_MEMBERSHIP_SCHEMA = {
    "type": "object",
    "properties": {
        "collection_id": {"type": "string"},
        "members": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "url": {"type": "string"},
                    "referer": {"type": "string"},
                    "source_stratum": {"type": "string"},
                    "metadata": {"type": "object"},
                },
                "required": ["source_id", "url"],
            },
        },
    },
    "required": ["collection_id", "members"],
}

CAPTURE_PUBLIC_OBJECT_SCHEMA = {
    "type": "object",
    "properties": {
        "collection_id": {
            "type": "string",
            "description": "Workspace-scoped collection identifier.",
        },
        "url": {"type": "string", "description": "Public HTTP(S) object URL."},
        "referer": {
            "type": "string",
            "description": "Optional legitimate public parent/detail page.",
        },
        "attempt": {
            "type": "string",
            "default": "initial",
            "description": "Append-oriented attempt label, e.g. initial or recovery-1.",
        },
        "timeout_seconds": {
            "type": "number",
            "default": 30,
            "minimum": 1,
            "maximum": 60,
        },
        "max_bytes": {
            "type": "integer",
            "default": 52428800,
            "minimum": 1024,
            "maximum": 104857600,
        },
    },
    "required": ["collection_id", "url"],
}

FREEZE_PUBLIC_COLLECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "collection_id": {"type": "string"},
    },
    "required": ["collection_id"],
}

VERIFY_PUBLIC_COLLECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "collection_id": {"type": "string"},
    },
    "required": ["collection_id"],
}


def function_schema(parameters: dict) -> dict:
    return {"parameters": parameters}
