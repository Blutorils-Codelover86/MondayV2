# MondayV2 conversation and Hyprland fixes

Cloud work on 2026-10-22, based on `main` commit
`0c9e8d39126a20791e7e77d57c863a8b332f0d3d`. All 48 fetched text files matched their
published blob hashes. This work targets **MondayV2**, preserving its pet, bridge, REPL and
one-line CLI. The original Monday repository was not modified in this task.

## Root cause and changes

The V2 interpreter had no conversational identity route. `who are you?` became a web query,
and `hi, who are you?` fell through to generic research. Broad metric keyword matching ran
before explanatory questions and app/window commands. The pet created a fresh Agent per
request, losing contextual observations even though its frontend looked like a conversation.

Supported greetings, identity/capability questions and guidance now produce deterministic text
with no tools, web search or model calls. Follow-ups reuse the selected in-memory task's verified
observations, with optional output-only local synthesis and the existing evidence/citation checks.
Missing, failed, timed-out or malformed model responses fall back honestly to PARTIAL excerpts.
Greetings/follow-ups do not replace the selected task. The pet carries that context across workers.
Conversational `yes`/`do it`/`open it` cannot authorize execution or supply an action target.
Unknown model proposals now ask for an explicit structured request; model confidence does not
authorize execution. Structured tools and existing deterministic command recipes keep their gateway.

Failures, cancellations and policy blocks include the number of earlier verified actions and state
that the goal remains incomplete. PermissionError is explicitly BLOCKED. File listings show names;
window listings/focus/close have natural commands, and focus/close require a unique observed target.
Closing still requires the normal action-bound approval. Model text is never executed.

## Hyprland behavior

Qt's ordinary Wayland window-position hints do not provide reliable pet placement. The new
`PetPlacement` adapter finds the exact companion title **and owned frontend PID**, validates its
observed address, and uses argv-only `hyprctl` dispatches to float/pin/resize/place only that window.
It handles logical monitor coordinates, fractional scaling, rotation and reserved areas. A collapse
shrinks the transparent input surface and preserves the bot's bottom/right edge, including when Qt
has already resized the client. Cached geometry avoids idle IPC polling; retries and calls are bounded.
Read-back must confirm floating/pinning/size/position before support is reported as configured.
The authenticated bridge accepts only bounded integer dimensions, not arbitrary window IDs or commands.

No Hyprland config, keybind, service, global rule or other application's placement is changed.
The existing Qt/native path remains for non-Hyprland desktops. Hyprland uses the native Wayland Qt
platform by default, respecting an explicitly chosen Qt platform. `monday pet status` exposes degraded
placement rather than claiming it worked. Unsupported/broken IPC leaves normal Qt behavior available.

References used for API compatibility:
- https://wiki.hypr.land/0.54.0/Configuring/Dispatchers/
- https://wiki.hypr.land/0.54.0/Configuring/Using-hyprctl/
- https://doc.qt.io/qt-6.8/qml-qtquick-window.html

## Tests and environment

Python 3.12.14, isolated `.venv`, `pip install -e '.[test]'`. No models or desktop dependencies
were downloaded. Tests use temporary data roots; external socket connections are blocked, while the
pet's authenticated loopback bridge tests remain enabled. No personal runtime history/config/logs
were read. Laya/Ollama behavior is covered with offline doubles, not live inference.

The unmodified imported suite in this cloud initially returned **235 passed, 15 failed, 1 skipped**:
14 CLI failures assumed pytest itself was a non-root user, and one child-process integration could
not observe its native child in this cloud's virtualized process table. The CLI fixture now explicitly
models a normal user, while its separate root-refusal test still checks production refusal. The
owned-child integration skips only when the proc table does not expose this process as its parent;
the production termination verifier was not relaxed. On a normal native host it still runs.

The other skip is the native Qt/QML smoke test: no QML runtime is installed in this cloud. The
compositor tests use recorded/mock IPC observations; they are not a claim of live Hyprland rendering.
Run the full suite on the laptop to exercise its native Qt and process tests.

Validation command: `.venv/bin/python -m pytest -q -rs`.
Current result: **312 passed, 2 skipped**. New behavioral coverage includes the exact reported
greetings, combined greeting/identity, pet context, fact/tool question separation, malformed citations,
unavailable/timed-out synthesis, approval/ambiguous action boundaries, window matching and close
approval, scaled/negative-monitor placement, collapse/expand geometry, wrong PID/address injection,
IPC timeout/retry limits and verification failure. Dependency, compile and whitespace checks also pass.

## Files changed and limits

- `monday/conversation.py`, `engine.py`, `pet.py`: text-only routing, contextual explanations, worker continuity.
- `monday/hyprland.py`, `desktop.py`, `ui/Pet.qml`: scoped native placement, geometry bridge, window commands.
- `monday/providers.py`, `safety.py`: malformed citation handling, local-only inference transport, explicit blocks.
- `monday-launch`: resolves its checkout through symlinks, without a hardcoded laptop path.
- `tests/test_conversation_hyprland.py`, `conftest.py`, `test_cli.py`, `test_adapters.py`: regressions and portable test environment.
- `README.md`, `docs/PET.md`, this report: usage, validation and handoff.

This remains a bounded grammar. Independent CLI invocations do not silently load unrelated history;
follow-up context lasts in the REPL/pet session. Factual reasoning needs verified source evidence;
generated summaries and excerpts remain PARTIAL. Lexical checks are not semantic proof, and injection
filtering is heuristic; the execution gateway remains the architectural boundary. No live model or
Hyprland/Qt quality benchmark was possible here. Screen hotplug and special compositor rules may
require restarting the pet. No merge, deployment, release or paid infrastructure was performed.
