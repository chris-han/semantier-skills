# Feishu Bot Meeting Coordinator

Standalone Hermes/Semantier skill repository for Feishu contact lookup, attendee negotiation, and calendar meeting creation.

## Repository Layout

- `skills/feishu-bot-meeting-coordinator/SKILL.md`
- `skills/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py`
- `marketplace/index.json`

## Install From Skills Screen

After publishing the parent `publishable-skills` folder as a Git repository, the Skills screen can install this skill in two ways.

### 1. Direct install identifier

Use this identifier in the marketplace install input:

```text
chris-han/publishable-skills/feishu-bot-meeting-coordinator/skills/feishu-bot-meeting-coordinator
```

### 2. Raw SKILL URL

Use this URL in the marketplace install input:

```text
https://raw.githubusercontent.com/chris-han/publishable-skills/main/feishu-bot-meeting-coordinator/skills/feishu-bot-meeting-coordinator/SKILL.md
```

## Custom Marketplace URL

The Semantier workspace now supports a user-editable marketplace URL in the Skills screen.

If you host `marketplace/index.json` at a stable public URL, paste that URL into the Skills screen marketplace settings. The workspace search wrapper will fetch the JSON index and locally filter results.

Expected hosted URL after publish:

```text
https://raw.githubusercontent.com/chris-han/publishable-skills/main/feishu-bot-meeting-coordinator/marketplace/index.json
```

The bundled marketplace index in this workspace is already pinned to `chris-han/publishable-skills`.

## Runtime Notes

- The helper expects Feishu credentials from the active Hermes/Semantier runtime environment.
- The helper also attempts to load `.env` from `$HERMES_HOME` or `$SEMANTIER_LOCAL_STATE_DIR` when those are present.
- The skill defaults user-facing timezone behavior to `Asia/Shanghai`.

## Publish Checklist

1. Publish the parent `publishable-skills` directory as the GitHub repository root.
2. Push to GitHub.
3. Install from the Skills screen using either the direct identifier or the raw SKILL URL.
4. Optionally set the marketplace URL to the hosted `marketplace/index.json` file for search-based discovery.