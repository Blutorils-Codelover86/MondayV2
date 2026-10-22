# Web access and desktop-control repair

Based on published `main` commit `15db51ca32583569f56bb8b0219aa4810ad9742a`.
This follow-up targets **main directly**, so it does not need the earlier stacked-PR merge order.

## Reproduced causes

The supplied screenshot showed `open visual studio` rejected because the local model's
proposal did not exactly match the already parsed action. That was an orchestration regression,
not an OS permission denial. Repeating a complete action through Gemma also added inference
latency before an ordinary app launch.

`explain python` could return only an echo. Other questions stopped at “local model unavailable”
instead of using the existing internet tools. The HTTP client already permits public HTTP(S)
URLs across domains; there was no public-site allowlist preventing internet use. The language
route, JSON-constrained conversational generation and lack of fallback were the problems.

## Changes

- Complete commands now go directly from deterministic interpretation to Laya's structured
  selection and the existing action gateway. Gemma cannot veto, substitute or delay the
  requested operation by restating different arguments. Unknown or ambiguous actionable
  requests still need clarification; a model cannot invent a new action target.
- Conversation uses Ollama's `/api/chat` with bounded role-based history and ordinary prose,
  rather than forcing conversation into JSON through `/api/generate`. Decision proposals and
  cited research synthesis keep their separate JSON contracts. Inference stays local; no model
  weights are downloaded and no cloud inference service is called.
- Echoes, unusable replies, underspecified explanations and trivial project-idea answers are
  rejected. General public questions then use `web.search` and `web.read`, with real evidence
  IDs and citations. Successful useful conversation does not need a web call.
- Current/latest/news questions and explicit read/summarize URLs route to the web immediately.
  `MONDAY_WEB_FALLBACK=0` disables automatic chat fallback; explicit searches still work.
  Fallback does not upload chat history, file bodies, clipboard content or local tool output.
  Obvious personal/local queries are excluded from automatic fallback; this is a conservative
  heuristic, not a general personal-data classifier. Explicit searches remain user initiated.
- Installed-app lookup handles punctuation/spaces and common names such as `visual studio`
  and `vscode`, matching actual XDG desktop entries. Several matching editors still require
  clarification. No model-generated executable name or shell command is run.
- `open youtube`, `open google`, `open github` and `open python.org` use the browser URL
  handoff. Handoffs remain PARTIAL when the displayed result cannot be verified.
- Three additional native Hyprland layout actions observe an exact window address, dispatch
  a fixed command, and verify compositor state: move to workspace, set floating/tiling and
  resize. Resizing requires an already floating window; layout tools protect the companion.
- Explicit clipboard read/write commands use the existing Wayland adapter. Writes preview
  the text for approval, verify by reading it back and omit text from audit records. They do
  not type into applications or send messages.

All existing path policy, tool-denial settings, action-bound confirmations, redaction,
STOP handling and the floating expressive pet remain in place. Public web content never
enters the local-action interpreter. Search results and read pages are untrusted evidence,
not new instructions or authority to access the desktop. Tests continue to block external
connections by default and use isolated state directories.

## Commands

```text
open visual studio
open youtube
open python.org
explain python
what can i make using python
what is the latest Python release
read https://www.python.org/about/
move window Code to workspace 2
float window Code
resize window Code to 1000x700
tile window Code
read clipboard
set clipboard to "a note I want to review"
```

Window names must uniquely match observed titles/classes or exact inventory IDs. Raw typed
APIs are also available:

```text
tool desktop.move_window_to_workspace {"window_id":"0x123","workspace":2}
tool desktop.set_floating {"window_id":"0x123","floating":true}
tool desktop.resize_window {"window_id":"0x123","width":1000,"height":700}
```

The adapter uses the existing `hyprctl` IPC backend, five-second bounded argv calls, no shell,
workspace integers 1–999 and sizes 100–7680 by 100–4320. Unsupported compositor/dispatcher
versions return failures rather than simulated success. Existing launch, focus, close, file,
project, service and package APIs remain available; their sensitive changes still require
approval. `monday tools` lists actual registered capabilities.

## Sentient inspiration and actual scope

Revisited the public [Sentient native-computer-use architecture](https://github.com/Sentient-OS-Labs/sentient-os/blob/main/Sentient%20OS%20macOS/Driver/Documentation%20-%20Native%20Computer%20Use.md).
Its relevant pattern is user-initiated task ownership, fresh observations, scoped actions,
visible progress, a shared STOP mechanism and verified completion. MONDAY uses its own
Python/QML implementation of those patterns. No Sentient code or assets were copied.

Sentient's signed macOS computer-use helper cannot be installed as a Linux/Wayland backend.
This change restores and expands native PC control; it does **not** provide arbitrary in-app
clicking, typing, login flows, screenshot vision, or full interactive browser automation.
Those require a supported Linux accessibility/portal or browser backend, target binding,
visible permissions and dedicated end-to-end verification. A raw input injector with an exit
code would not establish that a message, file change or application operation succeeded.
Existing approvals were not removed to create the appearance of unrestricted control.

## Verification

Isolated Python 3.12 environment; editable install with `.[test,test-ui]` succeeded.
Final `.venv/bin/python -m pytest -q -rs`: **414 passed, 2 skipped in 20.88s**.
The skips are the cloud virtualized-process integration and missing system `qml6` executable;
real Qt tests did run through PySide6. `pip check` and `git diff --check` passed.
The previous published implementation had 373 passing tests; 41 new regression cases cover
this repair. Existing model-expansion tests now assert that the exact user-requested safe
action runs while model substitutions never do; they no longer encode the broken veto. The screenshot scenarios are covered
by offline model/IPC fixtures, real temporary XDG-entry matching and mocked Ollama transport
responses. The full suite includes real offscreen Qt layout, input, approvals, action timeline,
STOP and expressive-state tests.

A live request through MONDAY's HTTP adapter to `https://www.python.org/about/` was attempted
in the isolated cloud environment. It failed with `gaierror: Temporary failure in name
resolution`. This is a cloud DNS/network limitation; live public-web retrieval is therefore
**not verified** here. No live Gemma/Laya inference or native Hyprland desktop is available
for this cloud check. Actual model quality, native app/window operations and web retrieval
on the user's laptop remain integration checks, not claimed successes.


Changed files: `monday/engine.py`, `monday/companion.py`, `monday/providers.py`,
`monday/desktop.py`, `monday/config.py`, `tests/conftest.py`,
`tests/test_local_companion.py`, `tests/test_web_desktop_repair.py`, `README.md`,
`docs/LOCAL_COMPANION.md`, and this report. No production dependencies were added.

API references: [Ollama chat](https://docs.ollama.com/api/chat) and
[Hyprland dispatchers](https://wiki.hypr.land/0.54.0/Configuring/Dispatchers/).
