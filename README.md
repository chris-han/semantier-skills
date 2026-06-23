# Semantier Skills

Standalone GitHub-backed plugin catalog for Semantier and Hermes installation flows.

Plugin authoring guidance lives in [docs/derived/semantier-marketplace-plugin-creation-guideline.md](../docs/derived/semantier-marketplace-plugin-creation-guideline.md).

## Included Packages

- `feishu_meeting_coordinator`
- `auto_resume_screening`

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

The auto resume screening plugin is installable from this repository with:

```text
chris-han/semantier-skills/plugins/auto_resume_screening
```

`real_company_onboarding` is a built-in shared Semantier runtime plugin. Its
source is tracked in the Semantier runtime repository at
`src/plugins/real_company_onboarding`, installed by launcher bootstrap into the
shared runtime, and is not advertised as a marketplace-installable package.

`automate_excel` is a built-in Semantier runtime plugin. Its source remains at
`plugins/automate_excel`, but it is installed by launcher bootstrap and is not
advertised as a marketplace-installable package.

## Marketplace URL

Use this repository URL directly in the Skills screen marketplace URL setting:

```text
https://github.com/chris-han/semantier-skills
```

The workspace marketplace search treats that GitHub repo URL as a package catalog and searches both plugin packages and skill packages.
