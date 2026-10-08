# CLAUDE.md

## Shared memory (read first)
@docs/agent-memory/PROJECT_CONTEXT.md
@docs/agent-memory/DECISIONS.md
@docs/agent-memory/HANDOFF.md

## Ground truth order
1. Actual repo state (git status/log, `outputs/experiment/*/continual-report.json`) is
   always authoritative.
2. HANDOFF.md is a pointer, not a fact. If it disagrees with what you observe (e.g. a
   `continual-report.json` newer than HANDOFF.md, as the SessionStart hook may flag),
   trust the observation and say the doc looks stale.
3. PROJECT_CONTEXT.md / DECISIONS.md change rarely; treat as reliable unless code/git
   contradicts them.

## When to update shared memory (judgment call, not mechanical)
- HANDOFF.md: after work that changes what the next session needs to know. Prune
  resolved entries; don't let it become a chronological log or complete experiment
  ledger — push settled conclusions to DECISIONS.md instead of leaving raw numbers here.
- DECISIONS.md: only when a real research/architecture decision is made, changed, or
  superseded.
- PROJECT_CONTEXT.md: only when stable architecture/methodology actually changes.
- Do not touch all three mechanically after every small edit — this is a judgment call,
  not something a hook can decide for you.

## Language
`docs/agent-memory/*.md`: Chinese prose, English for identifiers/paths/commands/model
names/config keys/technical terms. This file (CLAUDE.md) stays English.

## Notes
- The `## Live repo state` block a SessionStart hook may print into context is
  generated fresh each session (git status/log + a staleness check against HANDOFF.md)
  — it is not part of shared memory and is not saved anywhere.
- Do not create a Claude-specific copy of project knowledge outside
  `docs/agent-memory/`; these three files are the single shared-memory layer used by
  both Claude Code and Codex.
