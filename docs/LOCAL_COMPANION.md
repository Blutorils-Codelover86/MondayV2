# Local language and desktop gateway

This is the initial PR #2 implementation report. Current behavior supersedes the Gemma
preflight gate and JSON chat described below; see [web/desktop repair](WEB_DESKTOP_REPAIR.md).

## Inspected baseline and root cause

This change is for **MondayV2**, based on published review head
`1d8d402574a89faa08e4ff88807e8ec0a132b42a` (`fix/conversation-hyprland`). The
original Monday repository and personal runtime data were not used.

The existing Python agent already had typed `Action`, `Decision`, `Observation` and
`TaskState` records, a schema registry, a deterministic approval gateway, bounded subprocesses,
redacted private audit files, and a native Qt Quick companion. The QML bridge is authenticated
and loopback-only. Existing Hyprland placement keeps the owned companion surface floating and
pinned; `PetFace.qml` already implements expressive states.

The missing connection was conversational language: Ollama was disabled by default and only
supported tool proposals and evidence summaries. General questions mostly went to web search.
Laya only ranked research candidates. There was no active-window/workspace API, no common
names for the requested gateway actions, and the UI showed only the most recent progress string.

## Current responsibilities

| Source | Responsibility |
| --- | --- |
| `config.py`, `providers.py` | Local Ollama configuration/transport; bounded, offline Laya worker |
| `companion.py`, `conversation.py` | Narrow native intent grammar, bounded chat context, text-only follow-ups and grounded explanation selection |
| `engine.py` | Explicit intent recipe, optional Gemma interpretation, Laya structured execute/clarify selection, observed-state task loop |
| `registry.py`, `models.py` | Typed actions, argument schemas and structured observations |
| `safety.py`, `runtime.py` | Final policy/permission/approval authority, cancellation and bounded argv execution |
| `desktop.py`, `filesystem.py` | Native compositor actions and scoped, bounded file search |
| `pet.py`, `ui/Pet.qml` | One active task, action timeline, status, approval preview, STOP and retained conversation |
| `audit.py` | Existing redacted task records and action/approval history in MONDAY's state directory |

For supported explicit actions, Gemma interprets against **one deterministic candidate's
schema**. A conflicting proposal asks for clarification. Laya selects only `execute` or
`clarify` for that candidate; its confidence does not authorize anything. The gateway then
validates permissions and arguments independently, requests action-bound approval where
required, executes, and verifies. Explicit `tool name {json}` remains compatible and bypasses
unnecessary language reinterpretation, but still uses Laya and the gateway.

Missing local models do not prevent deterministic explicit recipes. An unavailable Laya
checkpoint uses an audited deterministic fallback; malformed/failed configured Laya selection
asks for clarification without executing. Ollama transport failures use deterministic action
interpretation/result text; invalid or conflicting returned proposals cannot expand a request.
Unknown action requests still ask for a concrete target. Conversational “yes” never grants
approval. No model output is parsed as executable shell.

Ordinary questions go to Gemma with **no executor or tool schemas**. Answers are labelled as
not externally verified. The session retains four text turns (800 characters per user/assistant
field) in memory. Tool evidence and private file bodies are not copied into this chat history.
Greetings preserve prior task context. “What did you just do?” explains the prior recorded task
without retrying it. Explicit web searches, documentation lookups and existing comparison
recipes retain their separate citation/evidence checks and truthful PARTIAL summaries.

Tool outcomes always retain their deterministic evidence, status and limitations. Gemma can
select an exact explanatory sentence from that text, with an exact supporting quote. A malformed,
unsupported or unavailable result falls back to the original explanation. This deliberately
conservative extraction is not unrestricted generated reasoning over desktop data.

## Configuration

Requires Python 3.11+, Arch/Wayland, the existing Qt QML runtime and the normal user's session.
No new production Python dependency was added.

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
# Ollama must already be running and gemma3:1b must already be installed:
ollama list
.venv/bin/monday "Hey MONDAY, what can you do?"
.venv/bin/monday pet on
```

MONDAY never pulls model weights, starts a paid inference service, or silently changes models.
Provision a local checkpoint/model separately if desired.

| Setting | Default and behavior |
| --- | --- |
| `MONDAY_MODEL` | `gemma3:1b`; empty string disables inference |
| `MONDAY_OLLAMA_URL` | `http://127.0.0.1:11434`; only loopback HTTP(S), no credentials, redirects or environment proxies |
| `MONDAY_LAYA_PATH` | Empty; optional complete local checkpoint and separately installed `.[laya]` dependency |
| `MONDAY_ROOTS` | Colon-separated approved roots; existing defaults are Projects, Documents and Downloads |
| `MONDAY_DENY_TOOLS` | Comma-separated tool names to block independently of model output; equivalent old/new launch, focus and windows aliases share denial |
| `MONDAY_DATA_DIR` | Existing MONDAY state/audit location; tests use temporary isolated directories |

Ollama uses `/api/tags` before `/api/generate`, JSON output, 2048 context tokens,
256 predicted tokens, temperature 0, and `keep_alive: 0` to release model memory. Responses
and model inventory are capped at 64 KiB. The bridge polls cancellation every 50 ms during
an inference wait. A stopped HTTP worker may finish its bounded local request (up to the
2-second inventory and 25-second generation socket timeouts); its late result is discarded
and cannot execute actions. STOP does not kill a shared Ollama server. Repeated cold model
loads trade latency for lower retained RAM; real latency and 8 GB headroom are unmeasured.

## Action contract

All actions return the existing structured `Observation` (`ok`, `verified`, `data`, `error`),
with distinct failure, BLOCKED and CANCELLED outcomes. Read-only and low-risk actions are
allowed for explicit requests unless denied by configuration. Existing medium/high/critical
operations still require literal, action-bound approval and fail closed on denial/timeout.
There is no new keyboard/mouse automation, message sending or unrestricted desktop tool.

| Action | Arguments | Implementation / evidence |
| --- | --- | --- |
| `desktop.list_windows` | `{}` | Native Hyprland client inventory; existing optional KWin backend retained |
| `desktop.get_active_window` | `{}` | Hyprland active-window metadata only; no screenshots or contents |
| `desktop.focus_window` | `{"window_id":"0x123"}` | Observed inventory membership and validated address; focus read-back |
| `desktop.switch_workspace` | `{"workspace":2}` | Integer 1–999; fixed IPC dispatch and active-workspace read-back |
| `desktop.launch_app` | `{"app":"Dolphin"}` | Existing XDG desktop-entry resolution; shell/interpreter wrappers rejected; running-process verification |
| `system.get_status` | `{}` | CPU/RAM/disk sample via existing system adapter |
| `files.search` | `{"pattern":"python-projects"}` | Approved roots, metadata/name search; no file contents read |

Hyprland operations use its native IPC client `hyprctl` with fixed argv and 5-second
timeouts. They do not emulate X11 input or edit compositor configuration. Existing XDG
handoffs remain available where appropriate and stay PARTIAL when visible navigation cannot
be verified. No new portal/D-Bus dependency is required for this initial action set.

Python project candidates contain a Python file or `pyproject.toml`, `setup.py` or
`requirements.txt`; they are candidates, not proof of a complete/working project. Other
patterns match names. Search excludes protected paths and symlinks, caps at 100 matches,
20,000 entries or about 3 seconds, and reports PARTIAL when bounded or folders are unavailable.
Results include concrete paths instead of just a count. Existing `app.*`, `desktop.windows`,
`desktop.focus` and `fs.*` tools remain registered.

## User-visible behavior and examples

| Request | Before | After / validation |
| --- | --- | --- |
| Hey MONDAY, what can you do? | Basic deterministic help | Useful help, zero tools/model calls (offline regression) |
| Explain my RAM usage. | Broad “explain” could become research | Real system sample, available GiB and one-sample limitation |
| What window am I using? | Research | Active title/class from IPC (fixture tested) |
| Open Dolphin. | App recipe; sentence punctuation could contaminate target | Typed launch; exact XDG app resolution and process verification (fixture tested) |
| Switch to workspace 2. | Unspecified request | Typed switch with active-workspace read-back (fixture tested) |
| Find my Python projects. | Web research | Bounded approved-root search (real temporary files tested) |
| What did you just do? | New research | Prior task outcome and verified evidence, no action retry |
| Stop the current task. | Not connected as a phrase | STOP path; pending approval denied and no further actions |

The compact companion keeps its existing pet expressions and owned-window placement.
It adds a visible task status and scrollable per-action RUNNING/VERIFIED/failure timeline.
Approval previews remain visible until answered or stopped. The STOP button remains usable
while busy; the input also accepts a stop phrase. There is one active task. Audit records
remain local and redacted; the history/explain controls expose prior results. Health hints
are now off by default and can be explicitly enabled with the existing header control.
No background window-content collection, screen recording or personal-source indexing was added.

## Sentient architectural study

Inspected Sentient OS at `16e871ad43c19ca8b26ed36daf66baaa44e886e5`:

- [README](https://github.com/Sentient-OS-Labs/sentient-os/blob/16e871ad43c19ca8b26ed36daf66baaa44e886e5/README.md)
- [Native computer use](https://github.com/Sentient-OS-Labs/sentient-os/blob/16e871ad43c19ca8b26ed36daf66baaa44e886e5/Sentient%20OS%20macOS/Driver/Documentation%20-%20Native%20Computer%20Use.md)
- [Licensing](https://github.com/Sentient-OS-Labs/sentient-os/blob/16e871ad43c19ca8b26ed36daf66baaa44e886e5/LICENSING.md)

Useful patterns were one coordinator/task lock, streamed visible progress, a common STOP
path, user-initiated execution, fresh-state verification, and distinguishing cancellation
from completion. MONDAY implements these patterns using its own existing Python/QML gateway.
No Sentient source code or assets were copied. Its AGPL/macOS helper, cloud providers,
proactive personal-data analysis and native input automation were not incorporated.

## Verification and remaining limits

Cloud baseline: **318 passed, 2 skipped in 19.03s**. Python 3.12 isolated venv;
editable project installation with `.[test,test-ui]` succeeded. Production dependencies
remain unchanged. Final `.venv/bin/python -m pytest -q -rs`: **373 passed, 2 skipped in
21.03s**. `.venv/bin/python -m pip check`: **No broken requirements found**.
`git diff --check` passed. All 56 baseline text blobs were verified against the published
GitHub tree; the unchanged preview PNG is preserved in the review branch.

The regression suite uses offline model/IPC fixtures and real temporary file searches and
system metric sampling. Real Qt offscreen checks exercise layout/expressions, the bridge,
mouse/keyboard input, approval/denial, STOP button, typed STOP, status and the action timeline.
The owned-process integration skips on this cloud's virtualized process table; the separate
system `qml6` executable smoke test skips because that executable is absent. PySide6 provides
actual Qt checks despite that skip. No personal runtime database, logs, credentials or home
files were accessed for validation.

Live Ollama is unavailable (`ollama` executable absent, loopback API connection refused),
no Laya checkpoint was supplied, and native compositor behavior was not exercised here. Gemma answer quality,
real Laya decisions, native focus/workspace switching, Dolphin launch, actual compositor
placement and real 8 GB performance therefore remain **unverified**. An active-window query
reports what Hyprland says at request time; entering a request in the companion may itself
focus MONDAY. It does not silently track your previously active app. General model answers
can be wrong; action interpretation intentionally remains narrow and may ask for clarification.

## Changed files

- Language/configuration/orchestration: `monday/companion.py`, `monday/config.py`,
  `monday/providers.py`, `monday/bootstrap.py`, `monday/engine.py`, `monday/conversation.py`.
- Gateway/adapters: `monday/desktop.py`, `monday/filesystem.py`, `monday/safety.py`.
- Companion: `monday/pet.py`, `monday/ui/Pet.qml`.
- Verification: `tests/test_local_companion.py`, `scripts/qt_window_check.py`,
  `tests/test_adapters.py`, `tests/test_safety.py`. The existing confidence test now uses
  a valid Laya execute selection to prove approval is still denied; separate regressions
  reject malformed selections. The process fixture also handles a live child missing
  from the cloud's virtualized process table; production process verification is unchanged.
- Documentation: `README.md`, `docs/PET.md`, `docs/LOCAL_COMPANION.md`.
