# Automatic research-task delegation

Configured September 18, 2026. Root `AGENTS.md` routes requested T01–T07 work to the
assigned implementation and review agents. The coordinator keeps its own model.

## Use

Start a new Codex session in this repository so startup instructions and project agents
are loaded. Then use ordinary requests such as:

- `Implement T01.`
- `Continue T02 using the task plan.`
- `Review the T03 changes.`

The coordinator reads the packet, checks dependencies, delegates bounded work with the
assigned model/effort, arranges a separate review and reports validation. An unmet T01
contract blocks dependent T02 calculations, not unrelated fixture or inventory work.
A task request does not implicitly authorize all later tasks or a trading deployment.
Asking about a task or opening the README does not execute it.

## Files and routing

- `AGENTS.md`: automatically loaded project workflow, task routing and escalation rules.
- `.codex/config.toml`: enables agents and allows up to three concurrent child threads.
- `.codex/agents/research_luna_high.toml`: T02/T07 implementation, Luna high.
- `.codex/agents/research_luna_medium.toml`: T04/T06 implementation, Luna medium.
- `.codex/agents/research_terra_high.toml`: T03/T05 implementation, Terra high.
- `.codex/agents/research_astra_high.toml`: T01 design and complex escalations, Astra high.
- `.codex/agents/research_terra_review.toml`: T02/T07 implementation review, Terra high.
- `.codex/agents/research_astra_review.toml`: remaining reviews and T07 research review, Astra high.

The [task packets](tasks/README.md) contain the full model assignments and acceptance rules.
Review agents report findings without editing the implementation. One writer owns a file
at a time. Workers do not recursively spawn agents. A failed focused repair escalates
Luna to Terra, then unresolved integration issues to Astra. Missing data is not a reason
to guess inputs or upgrade models indefinitely.

## Runtime behavior and limits

The routing is an instruction-driven coordinator workflow, not a filesystem watcher or
an automatic switch of the parent model. The runtime must expose subagent tools and the
requested models. Project configuration must be trusted/enabled in the client. Higher
priority platform restrictions and permission settings still apply.

Named custom agents are used where supported. In runtimes exposing explicit spawn
parameters instead, AGENTS.md instructs the coordinator to pass the exact model and
reasoning settings, with fresh context and the selected agent's instructions. The
collaboration tool in the configuring session uses that explicit-parameter interface.
If the runtime cannot honor the assignment, report the limitation; do not silently run a
different model and label it as the assigned one. A user-specific model override takes
precedence over the default table.

## Validation performed

- Parsed all six agent TOML files and checked their model IDs, reasoning settings,
  descriptions and instructions.
- Codex CLI 0.154.0's local prompt renderer confirmed the root routing instructions load.
- The local app-server accepted strict configuration parsing; its read-only `config/read`
  returned agents enabled and the three-child concurrency setting.
- Prompt rendering does not expose custom-agent descriptions in this installation, so
  it was not used as proof of named-agent discovery. No inference session or experimental
  task was launched to validate this configuration. Actual model dispatch remains an
  execution-time check reported by the coordinator.

Sources: [AGENTS.md loading](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
and [custom agents and model settings](https://learn.chatgpt.com/docs/agent-configuration/subagents).
