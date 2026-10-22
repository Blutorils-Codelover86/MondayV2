# Floating window and expressive pet follow-up

Based on review commit `8552b0e002193d6e33d0603cd86788de68e6ee9f`, 2026-10-22.

## Reported failure

The supplied screenshot showed a large tiled transparent surface, with the command panel at its
upper edge and the pet far below. The first implementation forwarded the Qt Window's **actual**
width/height to `/geometry`. A compositor-imposed tile could therefore become the requested size,
creating a feedback loop even after the adapter attempted to float it. It also stopped checking once
geometry was cached, so later compositor changes could go undetected.

## Fix

- `Pet.qml` now uses a normal focusable Qt window, 400 logical pixels wide when expanded and
  116 by 104 when collapsed. Requested height comes from the bounded content layout. Minimum and
  maximum constraints match those independent requested dimensions. Compositor-assigned width/height
  never become geometry requests. The panel and bot share the same compact content coordinates.
- Existing scoped Hyprland IPC still floats and pins only the observed frontend PID/title/address.
  Every two seconds it rechecks the owned surface and restores floating/pinning/size if it was tiled
  or changed. A correctly sized, user-dragged position is preserved; offscreen positions are clamped
  to the observed monitor. No compositor config or global tiling rules are changed.
- Results are selectable and scrollable rather than cut off after five lines. Clicking the bot
  expands/collapses the panel and requests normal input focus. Enter/send, Stop, approval and denial,
  health controls and close retain the authenticated backend. Approval controls cannot be hidden by
  collapsing the panel while approval is pending. Geometry acknowledgements cannot overwrite newer
  task state with an older snapshot. Connection loss shows a dim pet and keeps polling for recovery.
- `PetFace.qml` adds restrained vector animation: breathing/blinking idle, attentive wider eyes,
  pointer-following curiosity, scanning asymmetric thinking, green success crescents, amber approval
  and warning, pink error eyes, and a dim offline state. Outcome status comes from the actual backend;
  CANCELLED/BLOCKED/PARTIAL do not receive success expressions. There is no new microphone, model or
  inference dependency. The existing mascot shape and control structure remain.

## Verification

`python -m pytest -q -rs`: **318 passed, 2 skipped in 18.92s**.
`pip check`, `compileall`, and `git diff --check` also pass.

Three new integration scenarios load the **real QML** with PySide6/Qt 6.12.0 using its offscreen
software renderer and the real authenticated loopback PetHTTP/PetService backend:

1. Layout: fixed constraints, externally imposed 917x1020 tile dimensions do not contaminate desired
   geometry, collapse/expand through controls, and long full results remain available in a bounded view.
2. Input: real mouse/keyboard events type `hi`, submit it, display the backend response, deny and approve
   owned temporary file operations, and cancel a pending operation with Stop. Actual test files are
   checked for presence/absence. No personal files or runtime state are accessed.
3. Expressions: render idle, thinking, success, approval, warning, error, attentive and offline states.
   Success, approval and error renders were visually inspected.

Three additional compositor regressions verify re-tiling recovery despite cached geometry, preservation
of a user-dragged position without dispatching commands, and recovery of an offscreen pet. These are
mock IPC tests, separate from the real Qt integration above.

The two remaining skips are the older qml6-executable smoke test (that standalone executable is absent)
and the native owned-child process integration (the cloud's virtual proc table does not expose it).
The QML component itself was rendered and interacted with using PySide6. No live Hyprland session is
available here, so actual compositor input routing/dragging still requires the laptop smoke test.
Offscreen Qt's `propagateSizeHints` warnings reflect that platform plugin, not a passed Hyprland test.

For developer UI checks only, install `pip install -e '.[test-ui]'`, then run
`python -m pytest -q tests/test_pet_window.py`. The optional extra uses PySide6-Essentials and is not
needed by the normal existing qml6/qml launcher. No model weights or paid services are used.

Changed implementation files: `monday/ui/Pet.qml`, new `PetFace.qml`, `monday/hyprland.py`,
`monday/pet.py`; tests: `test_conversation_hyprland.py`, new `test_pet_window.py` and
`scripts/qt_window_check.py`; developer extra and documentation: `pyproject.toml`, README, PET.md,
and this report. No merge or deployment is performed.
