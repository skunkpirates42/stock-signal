# Stock-signal project instructions

Read `CLAUDE.md` for application constraints and `docs/experiments/roadmap.md` for research
sequence. The application is paper-only; deterministic rules decide trades. Preserve
existing changes, provenance, frozen experiment definitions and saved run artifacts.
For web changes, also follow `web/AGENTS.md`.

## Automatic research-task delegation

When the user asks to implement, execute, continue or review T01–T07, or clearly requests
the work described by one of those packets, automatically use subagents with the models
below. This is standing project authorization to delegate those tasks; do not ask again
merely to select a worker or reviewer. Ordinary questions, documentation lookups, model
assignment edits and configuration work do not start experiment tasks.

Read the corresponding packet in `docs/experiments/tasks/README.md` before dispatch.
Check prerequisites and the current working tree; a file's presence alone does not prove
a dependency is complete. Do not silently execute an entire dependency chain beyond the
user's requested scope. Complete available independent work and report concrete gaps.

| Task | Implementation agent | Review agent(s), in order |
|---|---|---|
| T01 | research_astra_high | research_astra_review |
| T02 | research_luna_high | research_terra_review |
| T03 | research_terra_high | research_astra_review |
| T04 | research_luna_medium | research_astra_review |
| T05 | research_terra_high | research_astra_review |
| T06 | research_luna_medium | research_astra_review |
| T07 | research_luna_high | research_terra_review, research_astra_review |

Custom agents are defined in `.codex/agents/`. Their exact settings are:

| Agent | Model ID | Reasoning |
|---|---|---|
| research_luna_high | gpt-5.6-luna | high |
| research_luna_medium | gpt-5.6-luna | medium |
| research_terra_high | gpt-5.6-terra | high |
| research_astra_high | gpt-6-astra | high |
| research_terra_review | gpt-5.6-terra | high |
| research_astra_review | gpt-6-astra | high |

Use named custom agents when the runtime supports them. If its spawn tool exposes only
explicit model/reasoning parameters, use the exact settings above and pass the selected
agent's developer instructions in the assignment. With `collaboration.spawn_agent`, use
`fork_turns="none"` plus explicit `model` and `reasoning_effort`; do not use a full-history
fork for a model override. Give the worker the packet path, its bounded objective, file
ownership, relevant context, constraints and acceptance checks. Fresh context avoids
inheriting unrelated conversation and secrets.

Delegate concrete bounded work when useful independent coordinator work can run alongside
it (dependency checks, integration planning, other non-overlapping verification or report
preparation). Respect runtime delegation restrictions. If the runtime cannot honor the
assigned model/delegation, report the limitation instead of claiming it ran that model.
These instructions never change the coordinating session's own model.

The coordinator owns integration, task state and final reporting. Keep at most one writer
per file at a time; run dependent work sequentially. After implementation, give a fresh
review agent the contract, patch scope and evidence. Reviewers report findings without
editing code. Have the owner fix material findings and repeat relevant verification;
do not count self-review as the assigned review. For review-only requests, dispatch only
the reviewers. Do not create recursive agent trees.

Escalate Luna implementation failures to Terra high after one focused repair attempt;
escalate unresolved Terra integration/reconciliation failures to Astra high. Send unsettled
financial rules, leakage and statistical-design issues directly to Astra. Do not escalate
missing credentials, unavailable data or unset user risk limits into guessed answers.
Report the models actually used, checks run, review findings resolved and outstanding gaps.

## Verification and credentials

Keep tests offline using `tests/conftest.py` isolation. Never print `.env`, credentials,
request headers or HTTP exception locals. Never submit broker orders as part of a test or
shadow experiment. Runtime network and filesystem approval rules still apply to agents.
Run focused backend tests using `.venv/bin/python -m pytest <files> -q --tb=short`;
shared accounting/storage/replay changes require the full backend suite. Use
`git diff --check`. Documentation/configuration-only work needs relevant static validation.
Do not activate a paper configuration, start unattended collection or claim strategy
promotion merely because a coding task or review completed.
