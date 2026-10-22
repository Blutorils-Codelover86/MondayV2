# MONDAY V2 build report

Built and exercised on 2026-10-05 (Asia/Kolkata), under `/home/blu/Projects/MondayV2`.
The original `/home/blu/Projects/Monday` source and environment were left in place.
V2 has its own virtual environment and console script; no global command, desktop
configuration, service, package, or model was installed or replaced.

## Desktop companion and usefulness update (2026-10-05)

MONDAY now includes `monday pet on/off/status`, a native Qt QML companion with a circular
body, two rounded rectangular blinking eyes, and a command box above it. It has action-bound
GUI approvals, cancellation, diagnostic shortcuts and opt-in proactive read-only health
hints. The documentation queries and storage/GPU examples reported by the user are fixed.
Research ranks relevant documentation pages, suppresses JavaScript notices, and retries
failed sources. There are now **52 tools** (30 READ_ONLY). New modules: `gpu.py`, `research.py`,
`pet.py`, `ui/Pet.qml`; regressions: `test_usefulness.py`, `test_pet.py`. The final suite has
**251 passing tests**; native QML command entry/result rendering was exercised.
See [PET.md](PET.md) and [pet-measurements.json](pet-measurements.json) for current details.
Later sections describe the original build snapshot where explicitly dated.

## Internet-access update (2026-10-05)

General web search is now enabled by default using DuckDuckGo Lite without an API key
or local service. The original Wikipedia-only default described later in this report is
historical. SearXNG configuration still takes precedence; auto mode falls back to Wikipedia
with an explicit degraded-provider label if general search is unavailable. Public HTTP(S)
services may now use any valid port; private/local addresses, credential-bearing URLs,
local action approvals and page-instruction isolation remain protected.

Added `search web for …`, `search internet for …` and `look up …` objectives with precedence
over local diagnostic keywords. Search titles/links remain discovery data, not read evidence.
The HTTP reader handles bounded gzip/deflate decompression, compressed bodies without a
header, and refuses binary/oversized decoded content. This was needed for a real Python.org
response. No firewall, proxy, global network policy, model or installed system package changed.

Follow-up verification: **218 tests passed**, including provider parsing/redirect decoding,
private links, challenge fallback, nonstandard public ports, query routing, SearXNG override,
compression and expansion limits. Live default search returned 8 general web results for
“Python official documentation”; direct retrieval of `https://docs.python.org/3/` extracted
readable official documentation. The Python.org documentation landing page includes a
JavaScript-fallback notice, which an extractive research response may quote; V2 cannot render
JavaScript and does not guarantee an ideal answer from every discovered page.

Provider reference: [DuckDuckGo non-JavaScript search](https://duckduckgo.com/duckduckgo-help-pages/features/non-javascript/).

## Implemented architecture

`objective → interpretation → TaskState → DecisionEngine.next → ActionGateway →
ToolRegistry → execute → observe/verify → update TaskState → decide again → one-line result`.

The engine executes one next action at a time using observations, not an unvalidated list
of model shell commands. A bounded set of domain workflows supplies evidence dependencies;
structured tool calls expose the remaining capabilities. Optional Laya and Ollama providers
supply advice, while risk/approval stays deterministic. `explain` retains the decision and
verification record. Errors, unsupported interfaces, denied approval and dry runs have
separate truthful outcomes. Research summaries remain PARTIAL because lexical support is
not semantic proof. Full architecture and safety contracts are in [README.md](../README.md).

## Inspection and reuse of old MONDAY

Inspected old README/pyproject, interpreter, controller/planner references, application/file
execution design, URL validation, Laya adapter, redaction and existing test patterns.

* **Directly reused:** `monday/redact.py`, copied into V2, with its secret-pattern rules.
* **Reused lessons:** separate safety authority from model advice; fail closed on missing
  approval; cached-only model use; observation required before success; evidence carries
  source URLs; malformed/failed models fall back; redact persisted records.
* **Reimplemented:** registry, gateway, task/decision records, loop, tools, CLI and providers.
* **Discarded:** fixed old GoalType/TaskSpec pipeline as the foundation for PC control;
  app whitelist; browser-required retrieval; model-centric routing; multi-paragraph default
  result formatting; old package/module coupling and browser/framework dependencies.
* **Laya change:** the old thread timeout cannot stop an underlying inference and may leave
  interpreter shutdown waiting; V2 uses an offline, killable subprocess with no implicit
  checkpoint fetching. This costs repeated load latency when enabled.

The new interpreter has a small grammar for common objectives, rather than hundreds of
phrase-to-command mappings. It is not a general natural-language planner without an
optional reasoner. The core multi-step state loop remains independent of that grammar.

## Tools and safety

**51 registered tools:** 29 READ_ONLY, 5 LOW, 13 MEDIUM, 3 HIGH, 1 CRITICAL.
The complete names, descriptions, JSON schemas and risk levels are in [tools.json](tools.json).

Groups: system/sensors/network/audio/Bluetooth/logs; process and service operations;
filesystem and real inverses; discovered XDG applications; desktop windows/clipboard/
notifications; controlled diagnostic argv; Arch packages; project/build/test/Git/editor/
terminal; web search/retrieval/browser.

MEDIUM/HIGH/CRITICAL actions require explicit terminal approval. No TTY or silence means
no approval. All engine calls use ActionGateway; model confidence cannot bypass it. Files
stay inside configured roots, credential/configuration/generated paths and symlinks are
blocked, and deletion is nonrecursive. Commands use validated argv, never `shell=True`.
Builds execute arbitrary project code and therefore always ask. Privileged operations use
`pkexec` for only that operation; MONDAY refuses permanent root execution. Package changes
show resolved versions before approval and verify installed versions or removal. Upgrades
use current pacman databases and do not refresh them. No AUR support is claimed.

`Ctrl-C`, a persistent `monday stop` flag, finite step/time budgets, subprocess timeouts and
process-group cleanup constrain active execution. `resume` explicitly clears the stop flag.
Dry-run validates the next action and shows the conditional workflow without executing it.
Undo checks recorded hashes/path state and refuses changed files, occupied destinations
or nonempty created directories. Irreversible operations have no invented inverse.

## Test results

Final run: `.venv/bin/python -m pytest -q` → **201 passed in 2.13 seconds; 0 failures**.

Coverage includes interpretation, observation order, conditional planning, loop guards,
step/time budgets, tool schemas, approvals/non-TTY/silence, confidence isolation, path
boundaries/traversal/symlinks/private locations, process identity and protected PIDs,
application discovery/ambiguity/launch verification, unsupported desktop APIs, package
previews/change/version checks, OS authentication failure, filesystem hashing/no-clobber/
undo, HTTP content limits/private destinations/redirects/rate limits/offline/malformed data,
page extraction, prompt-injection separation, optional model failures, subprocess output/
timeouts/cancellation, CLI, secret redaction and audit permissions/content omission.

Destructive system/package/service actions were mocked. Process termination used only an
owned, disposable sleeping test child. File changes were confined to pytest temporary
roots. No existing user file was deleted or overwritten by tests.

During development, a new privacy test exposed supplied file content in the original
objective and read content in terminal decision responses saved to task records. Both
persistence paths were corrected; the final regression checks every state-directory file.
There are no remaining failing tests.

## Live checks actually performed

The reproducible [live-results.json](live-results.json) contains **18 successful checks**:
CPU, RAM, disk, temperatures, battery, network interfaces, uptime, audio, Bluetooth,
process listing, Bluetooth service state, XDG app discovery, desktop capabilities,
installed pacman inspection, real `https://example.com` extraction, a successful Make build
in an owned temporary project, temporary file creation, and its guarded undo.

Additional CLI probes performed:

* `check my ram`, slow-PC diagnosis and its no-execution conditional plan.
* Firefox package lookup: correctly reported not installed.
* Bluetooth: software-blocked adapter observed; service was active. No unblock/restart was
  performed, since this build task did not authorize changing the user's connectivity.
* `open Dolphin`: launched a real desktop application and observed its process. The window
  was not claimed verified; the application may remain open from this probe.
* Current project type detection: Python project recognized.
* Wikipedia search and page retrieval for Unix, microkernel and monolithic kernel. Readable
  source paragraphs were extracted; no search snippet was substituted for reading a page.
* KDE window inspection: correctly returned unsupported because `kdotool` is not installed.
* Wayland clipboard read: completed; clipboard text was not retained as a build artifact.
* Existing Ollama `qwen2.5-coder:0.5b` summary attempt: fell back to a labelled source excerpt;
  no generated summary was accepted. No model was downloaded.
* Existing old-environment Laya: installed version **0.3.22**, module location and public
  `load` signature inspected. Real inference not attempted given RAM pressure; optional
  provider behavior was tested with mocked worker results.

No live service restart, software install/remove/upgrade, arbitrary user-process termination,
window closing/focusing, clipboard write, or real project-code rewrite was performed.
These are not reported as live validated.

## Measured resource use

Measurements are actual fresh-process readings from this machine, not estimates.
See [benchmarks.json](benchmarks.json), produced by `scripts/benchmark.py`.

| Measurement | Result |
|---|---|
| Host physical RAM | 7,987,093,504 bytes (nominal 8 GB) |
| Python | 3.14.7 |
| Idle REPL RSS, median of 5 fresh processes | **25.06 MiB** |
| Startup to first REPL prompt, median of 5 | **0.241 s** |
| RAM objective including startup, median of 5 | **0.327 s** |
| Idle child processes / resident models | **0 / 0** |

Startup samples: 0.246, 0.239, 0.241, 0.251, 0.235 seconds. RAM-task samples:
0.327, 0.321, 0.316, 0.347, 0.331 seconds. Runs include Python startup, imports and audit
setup; RSS is sampled at the REPL prompt. Filesystem cache/load affects timing; these are
five samples on an already active desktop, not cold-boot benchmarks. No always-on model,
browser, agent framework, vector database or background service is needed.

## Files created

Source/runtime files:

```text
MondayV2/
  .gitignore
  README.md
  pyproject.toml
  monday-launch
  monday/
    __init__.py   __main__.py   models.py     config.py
    registry.py   safety.py     runtime.py    audit.py
    bootstrap.py  engine.py     cli.py        redact.py
    system.py     filesystem.py desktop.py    projects.py
    packages.py   web.py        providers.py  laya_worker.py
  tests/
    conftest.py        test_safety.py      test_filesystem.py
    test_engine.py     test_runtime.py     test_web.py
    test_adapters.py   test_cli.py
  scripts/
    live_checks.py
    benchmark.py
  docs/
    BUILD_REPORT.md
    tools.json
    live-results.json
    benchmarks.json
    live-check-output.txt
    benchmark-output.txt
```

Also generated: `.venv/`, editable-install metadata, pytest/Python caches, and private runtime
records under `~/.local/state/monday-v2/`. They are not old MONDAY data or source changes.

## Known limitations

1. **Natural-language breadth:** common workflows and all structured tools work without an
   LLM. Unusual objectives ask for clarification; no universal autonomous PC planning is
   claimed. Clarifications start a new objective rather than resuming a persisted plan.
2. **Current KDE desktop:** launch/clipboard/notification/XDG APIs work. Window inventory,
   focus/close require a supported backend; Hyprland IPC and optional KDE `kdotool` paths
   have offline tests, but no live validation on those backends. No security boundary is
   bypassed and no desktop configuration was changed.
3. **Visible app/browser state:** a live process proves process launch, not visible window
   state or document readiness. Browser/file handoff remains PARTIAL. No coordinate GUI
   automation or arbitrary application accessibility control is implemented.
4. **Research:** default search covers Wikipedia; general search needs SearXNG. The SearXNG
   path is implemented but no live instance was used. HTTP cannot render JavaScript or
   bypass blocked pages. DNS resolution depends on the OS resolver; public-IP preflight
   is not a sandbox against DNS rebinding. Summaries are conservatively PARTIAL.
5. **Models:** optional Laya inference is not live measured; V2's default environment does
   not contain the old venv's private Laya installation. Ollama's tested small model did
   not produce an accepted generated summary. Default operations load neither model.
6. **Projects:** builds/tests are real, approved code execution, not an OS sandbox. CMake
   requires an existing configured `build/`; Python build requires the `build` module;
   Node/Rust require their existing toolchains. User-process restart is deliberately
   supported through observed service restart rather than guessing arbitrary command lines.
7. **Filesystem:** no recursive deletion, cross-device move, huge-file transfer, broad
   credential access, or safe inverse for arbitrary overwrites. Path checks cannot defend
   against a hostile same-user process racing directory replacement during execution.
8. **Cancellation:** subprocess work polls the stop flag; synchronous DNS/HTTP/model calls
   can remain blocked until their configured timeout. An interactive approval prompt must
   return before the flag is checked again. Killing MONDAY with SIGKILL is not an undo.
9. **System data:** process CPU figures are cumulative CPU seconds, not an instantaneous
   per-process sample; temperature/battery may be unavailable. Network checks observe
   host interfaces, not gateway latency, Internet reachability or Wi-Fi signal quality.
10. **Deployment:** a separate local implementation is installed in its own environment,
    not a system daemon or global replacement. The venv reuses system site packages on
    this machine; independent installation should install declared dependencies normally.

## Exact start commands

```bash
cd /home/blu/Projects/MondayV2
source .venv/bin/activate
monday "check my ram"
monday "my computer is slow"
monday plan "restart bluetooth"
monday tools
monday doctor
monday                        # lightweight interactive mode
```

Or: `/home/blu/Projects/MondayV2/monday-launch "check my ram"`.
Tests: `/home/blu/Projects/MondayV2/.venv/bin/python -m pytest /home/blu/Projects/MondayV2/tests`
should be run with the working directory set to MondayV2 so the intended package is selected.

## Primary API references checked

* [Laya public API and quickstart](https://github.com/NandhaKishorM/laya): typed prediction,
  bounded choices and loader behavior, cross-checked against the installed 0.3.22 signature.
* [Hyprland dispatchers](https://wiki.hypr.land/0.41.0/Configuring/Dispatchers/): address-based
  window targeting; the backend is optional and version-dependent.
* [KWin scripting API](https://develop.kde.org/docs/plasma/kwin/api/) and
  [KWin scripting tutorial](https://develop.kde.org/docs/plasma/kwin/): compositor-specific
  supported desktop APIs; X11 tools were not assumed to work under Wayland.
