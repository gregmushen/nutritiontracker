# Printing Press API-to-Agent Workflow

## Purpose

This playbook describes how to turn an OpenAPI-backed service into an agent-native operating surface:

OpenAPI API -> Printing Press-style CLI -> installed binary -> Hermes skill -> verified natural-language workflow.

The goal is not to generate a thin endpoint wrapper. The goal is to design a small operational interface that an agent can use safely, predictably, and repeatedly.

Core instruction:

> Do not merely wrap endpoints. Design an agent-native operational interface. Commands should map to real user workflows, return JSON by default, be safe for automation, and have a companion skill that teaches Hermes when and how to use the CLI.

This applies to APIs like Nutrition Tracker, Hostfully, or any future service where an agent receives:

- An OpenAPI URL
- An optional API token
- A desired CLI name
- A set of desired workflow commands
- A request to make the API agent-friendly

## Deliverables

Each API-to-agent bridge should produce:

- A small CLI installed at `~/.local/bin/<cli>`
- Config stored at `~/.config/<cli>/config.json` with permissions `0600`
- Environment variable overrides for base URL, token, config path, and timeout
- A companion Hermes skill with exact commands and safety guidance
- Verification evidence for CLI help, health, read-only live access, and one representative workflow

Suggested names:

- Umbrella workflow: `printing-press-api-to-agent-workflow`
- CLI authoring section: `printing-press-openapi-cli-authoring`
- Skill authoring section: `printing-press-companion-skill-authoring`

## Playbook 1: Create a Printing Press-Style CLI from OpenAPI

### 1. Inspect the API Contract

Start by fetching the schema and reading it as a product surface, not as raw routes.

```bash
curl -fsSL "$OPENAPI_URL" -o /tmp/openapi.json
jq '.info, (.paths | keys)' /tmp/openapi.json
```

Inspect:

- Authentication scheme
- Tags and path groups
- Read endpoints versus write endpoints
- Required request bodies and query parameters
- Response schemas and error shapes
- Existing health, status, or version endpoints
- Workflows implied by the API

If the OpenAPI schema is missing important descriptions, infer from routes, model names, and live responses, then document the assumptions.

### 2. Group Endpoints into Human Domains

Do not mirror route names directly unless they are already workflow-shaped. Group endpoints into domains a person would recognize.

Examples:

| Raw Surface | Agent-Native Domain |
|---|---|
| `/kitchen/inventory`, `/kitchen/matches` | `kitchen` |
| `/diary/{date}/entries`, `/stats/daily/{date}` | `diary` |
| `/reservations`, `/guests`, `/properties` | `stays` or `bookings` |
| `/imports/activity/steps` | `activity` |

Prefer commands that answer user intent:

```bash
nt kitchen have eggs
nt kitchen matches --effort low --json
nt diary add --date today --meal lunch --food "Greek yogurt" --amount 1 --unit serving
hostfully today --json
```

Avoid generated-SDK command shapes:

```bash
nt post-kitchen-inventory
nt get-diary-date-entries
hostfully get-reservations-id
```

### 3. Choose the CLI Stack

Use the Printing Press standard for the environment. If no stricter standard exists, default to Go with Cobra because it produces a single portable binary and has predictable command ergonomics.

Recommended implementation shape:

- `cmd/<cli>/main.go` for CLI entrypoint
- `internal/api` for HTTP client and typed requests
- `internal/config` for config file, env vars, and permissions
- `internal/output` for JSON, compact, quiet, and agent formatting
- `internal/commands` for domain commands

Keep the first version small. Implement read commands first, then safe creates, then destructive actions only after explicit user request.

### 4. Standard Root Flags

Every generated CLI should include these root flags:

```text
--json       Emit machine-readable JSON output
--compact    Emit compact JSON or compact text for agent context
--quiet      Suppress nonessential output
--agent      Optimize output and errors for agent use
--base-url   API base URL override
--token      API bearer token override
--config     Config file path override
--timeout    HTTP timeout, for example 10s
```

Default output should be useful to a person. `--json` must be stable enough for automation. `--agent` should reduce decorative text and include actionable error details without leaking secrets.

### 5. Configuration and Secret Handling

Store persistent config at:

```text
~/.config/<cli>/config.json
```

The file must be created with permissions `0600`. Parent directories should be `0700` where possible.

Example config:

```json
{
  "base_url": "https://nutrition.example.com",
  "token": "<redacted>",
  "timeout": "10s"
}
```

Support environment variable overrides:

```text
<CLI>_BASE_URL
<CLI>_TOKEN
<CLI>_CONFIG
<CLI>_TIMEOUT
```

For a CLI named `nt`, use:

```text
NT_BASE_URL
NT_TOKEN
NT_CONFIG
NT_TIMEOUT
```

Precedence:

1. Explicit flags
2. Environment variables
3. Config file
4. Built-in defaults

Never print tokens in normal output, debug output, errors, or `config show`. Use `config show --revealed` only if the user explicitly asks for it.

### 6. Command Design Rules

Implement commands in this order:

1. `health` or `doctor`
2. Read-only list/get/search commands
3. Idempotent or low-risk creates
4. Updates
5. Deletes and other destructive writes

Avoid destructive writes unless the user explicitly asks for them. For delete, archive, cancel, bulk update, or overwrite commands:

- Require a clear command name
- Require an ID or exact selector
- Require confirmation unless `--yes` is provided
- Make dry-run available for bulk operations
- In agent mode, prefer returning a refusal-style error that explains the missing confirmation

### 7. Output Design

JSON output should be the contract agents depend on. Human text can evolve, but JSON field names should remain stable.

For successful commands:

```json
{
  "ok": true,
  "data": {},
  "warnings": [],
  "meta": {
    "base_url": "https://example.com",
    "duration_ms": 123
  }
}
```

For errors:

```json
{
  "ok": false,
  "error": {
    "code": "unauthorized",
    "message": "Invalid or missing bearer token",
    "hint": "Run '<cli> config set token <token>' or set <CLI>_TOKEN."
  }
}
```

Use compact mode when responses may be large. It should preserve IDs, names, statuses, dates, and next actions while dropping verbose descriptions.

### 8. Installation

Install the compiled CLI to:

```text
~/.local/bin/<cli>
```

Verify the install location is on `PATH`:

```bash
command -v <cli>
<cli> --help
```

If `~/.local/bin` is missing from `PATH`, document the required shell update instead of silently installing elsewhere.

### 9. CLI Verification

Before calling the CLI done, run:

```bash
command -v <cli>
<cli> --help
<cli> health --json
<cli> <read-command> --json
<cli> <representative-workflow> --json
```

For Nutrition Tracker, representative checks might be:

```bash
nt health --json
nt foods search "banana" --json
nt kitchen matches --effort low --json
```

For Hostfully, representative checks might be:

```bash
hostfully health --json
hostfully today --json
hostfully booking get <reservation-id> --json
```

Record any limitation plainly, such as missing token, unavailable live service, or an endpoint that exists in OpenAPI but fails live validation.

## Playbook 2: Create the Companion Hermes Skill

### 1. Why the Skill Matters

The CLI alone is not enough. The skill is what tells Hermes:

- When to use the CLI
- Which command maps to which user request
- Which operations are safe without asking
- Which outputs are reliable
- Which quirks or data hazards need care

The skill should be operational, not promotional. It should include exact commands the agent can run.

### 2. Required Frontmatter

Every companion skill must include frontmatter:

```yaml
---
name: <skill-name>
description: Use <cli> to work with <service/domain> when users ask to <primary jobs>.
version: 0.1.0
author: Printing Press
license: MIT
tags:
  - printing-press
  - openapi
  - cli
related:
  - printing-press-api-to-agent-workflow
---
```

### 3. Trigger Phrases and When to Use

Document natural-language triggers. Use concrete examples.

Nutrition Tracker examples:

- "What can I make?"
- "What do I have in the kitchen?"
- "Add eggs to my kitchen inventory"
- "Log this meal"
- "How much protein did I eat today?"
- "Find nutrition for Greek yogurt"

Hostfully examples:

- "Who's checking in today?"
- "Show upcoming reservations"
- "Find this guest"
- "What properties have arrivals tomorrow?"

Also document when not to use the skill:

- When the user asks a general nutrition question that does not need their data
- When the user asks for medical advice
- When a destructive API action would be required and the user has not explicitly requested it

### 4. Prerequisite Commands

Each skill should start with quick checks:

```bash
command -v <cli>
<cli> health --json
<cli> config show --json
```

If the CLI supports it, prefer:

```bash
<cli> doctor --json
```

The skill should tell Hermes to stop and report a concise blocker if:

- The CLI is not installed
- The API is unreachable
- Authentication fails
- Required config is missing

### 5. Common Workflows

Use exact commands. Include the mapping from user phrase to CLI command.

Nutrition Tracker examples:

```text
"what can I make?"
nt kitchen matches --agent --json

"what can I make that's easy?"
nt kitchen matches --effort low --agent --json

"I have eggs"
nt kitchen have eggs --agent --json

"add spinach to use soon"
nt kitchen inventory set spinach --status use_soon --agent --json

"log this meal"
nt diary add --date today --meal dinner --food "<food>" --amount <n> --unit "<unit>" --agent --json

"how did I do today?"
nt stats daily today --agent --json
```

Hostfully examples:

```text
"who's checking in today?"
hostfully today --agent --json

"show tomorrow's arrivals"
hostfully arrivals --date tomorrow --agent --json

"find this guest"
hostfully guests search "<name or email>" --agent --json
```

### 6. Safety and Pitfall Notes

Every skill should identify operations that need care:

- Destructive writes need explicit user request and confirmation
- Bulk changes should use dry-run first
- Tokens must never be printed
- Masked PII should not be treated as complete data
- Cached data may need sync before use
- Health checks only prove reachability, not data freshness

Current known quirks to document when relevant:

- Masked phone numbers may be incomplete and should not be used as sole identifiers
- Apple Health steps can be stale if the local cache has not synced
- Open Food Facts imports may contain zero-nutrient rows
- Local cache sync may be needed before reads reflect latest remote state
- Generated OpenAPI descriptions may be sparse, so command semantics may rely on live checks

### 7. Skill Verification Checklist

Before marking a skill ready:

- `command -v <cli>` succeeds
- `<cli> --help` includes the expected root flags
- `<cli> health --json` succeeds or reports an understood auth/connectivity blocker
- At least one read-only command succeeds live
- At least one representative workflow is verified
- Natural-language mappings use exact commands
- Safety notes cover destructive operations
- Known quirks are current
- The skill does not contain real secrets

## End-to-End Acceptance Criteria

The full API-to-agent bridge is complete when:

- The OpenAPI schema has been inspected and summarized
- Endpoints are grouped into human domains
- CLI commands map to user workflows
- Standard root flags are implemented
- Config and secret handling are safe
- Read commands exist before destructive writes
- CLI is installed to `~/.local/bin`
- CLI verification passes
- Hermes skill exists with frontmatter, triggers, commands, safety notes, quirks, and verification checklist
- A natural-language request can be translated into a successful CLI command without guessing

## Anti-Patterns

Avoid:

- One command per raw endpoint
- Hiding every operation behind a generic `request` command
- Returning table-only output with no JSON mode
- Requiring secrets in command history
- Printing bearer tokens in `config show`
- Making delete/cancel/archive easy to trigger accidentally
- Skipping live verification because generated code compiles
- Shipping a CLI without a companion skill
- Shipping a skill that says "use the CLI" but does not provide exact commands

## Nutrition Tracker Reference Mapping

This repo is a working example of the target API shape.

Useful OpenAPI source:

```text
https://nutrition.example.com/openapi.json
```

Useful domains:

- `foods`: search foods and barcode lookups
- `diary`: log meals and inspect entries
- `stats`: daily summaries
- `activity`: import or inspect steps
- `recipes`: create and inspect recipes
- `kitchen`: inventory, favorite meals, matches, shopping list

Representative natural-language mappings:

| User Says | CLI Command |
|---|---|
| "what can I make?" | `nt kitchen matches --agent --json` |
| "I have eggs" | `nt kitchen have eggs --agent --json` |
| "log this meal" | `nt diary add --date today --meal <meal> --food "<food>" --amount <n> --unit "<unit>" --agent --json` |
| "how did I do today?" | `nt stats daily today --agent --json` |
| "find Greek yogurt" | `nt foods search "Greek yogurt" --agent --json` |
