# Semantier Skills

Standalone GitHub-backed plugin catalog for Semantier and Hermes installation flows.

Plugin authoring guidance lives in [docs/derived/semantier-marketplace-plugin-creation-guideline.md](../docs/derived/semantier-marketplace-plugin-creation-guideline.md).

## Included Packages

- `feishu_meeting_coordinator`

## Plugin Layout

The Feishu meeting coordinator is distributed as one plugin package. The plugin
bundles its skill metadata and helper scripts so install/uninstall does not leave
behind a separate skill source tree.

```text
plugins/
└── feishu_meeting_coordinator/
    ├── SKILL.md
    ├── plugin.yaml
    ├── scripts/
    │   └── feishu_bot_api.py
    └── ...
```

## Install Identifiers

The current Feishu meeting coordinator plugin is installable from this repository with:

```text
chris-han/semantier-skills/plugins/feishu_meeting_coordinator
```

## Marketplace URL

Use this repository URL directly in the Skills screen marketplace URL setting:

```text
https://github.com/chris-han/semantier-skills
```

The workspace marketplace search treats that GitHub repo URL as a package catalog and searches both plugin packages and skill packages.
