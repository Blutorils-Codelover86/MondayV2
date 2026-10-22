# MONDAY desktop companion

```bash
monday pet on
monday pet off
monday pet status
```

`pet on` starts a native Qt QML companion using the already-installed Qt runtime. The
minimal mascot has a circular dark steel body and two rounded rectangular, softly
blue eyes, inspired by Gipsy Danger's restrained industrial styling. It blinks and breathes gently;
its eyes track pointer movement over the bot, widen for attentive input, scan asymmetrically while
thinking, curve into green crescents after success, turn amber for approval/partial outcomes, and
slant pink for errors. A lost local connection dims the face and polling continues to recover.
No microphone or voice activation is involved. No antenna,
ears, mouth or extra body parts. The command box sits above it.

Click the circle to collapse or reveal the command box. Drag the header, or press and
hold the circle to move it using the compositor's supported system-move API. The window
requests always-on-top behavior; placement and stacking ultimately depend on Wayland's
compositor. On Hyprland, it finds the window by the owned frontend PID and exact companion
title, then floats, pins and places that window using scoped IPC dispatchers. It reads monitor
scale, rotation and reserved panel areas. Opening/collapsing the bubble preserves the bot's
lower right corner after dragging. The expanded window is 400 pixels wide and content-height;
the collapsed surface is 116 by 104 logical pixels. Fixed size constraints and independently
requested dimensions prevent the stretched tile feedback seen in the reported screenshot. A
two-second scoped check restores floating/pinning/geometry if needed, without resetting a
correctly sized window's dragged position. IPC requests
are bounded and observations must confirm floating/pinning/geometry; failures are exposed by
`monday pet status`. No config files or global window rules are changed. Other compositors keep
their existing Qt/native behavior.

Type a command and press Enter or the arrow. While working, the arrow becomes Stop.
Risky actions display their concrete proposal and **Approve / Deny** buttons; only the
pending action's approval ID is accepted. Closing the pet or stopping the task cancels
pending approval. Requests are processed one at a time. The `explain` link shows the
previous task's result and decision reasons. Quick buttons inspect RAM, CPU, storage
and GPU. Responses and approvals are rendered as plain text.
You can also type `hi`, `who are you?`, `hi, who are you?`, `what does that mean?`, or
`why did it fail?`. The pet retains its last task across worker instances; greetings do not
erase that context. Questions about MONDAY do not search the web, and follow-ups never retry
an action or grant approval. Ordinary questions can use local Gemma with bounded conversation history and no tools. Explicit research still requires source evidence. The task panel shows each action and verification outcome; STOP also works while awaiting local inference.

## More useful commands

```bash
monday "python offical documentation"
monday "search python offical documentation"
monday "system ram usage"
monday "system cpu usage"
monday "system storage usage"
monday "system gpu usage"
monday "system usage"
```

The misspelled documentation objective is understood, relevant documentation hosts are
ranked ahead of marketing landing pages, and the selected page is actually read before
MONDAY returns its link. JavaScript fallback notices are excluded from answer excerpts.
When a discovered page fails, research tries up to three candidates. Neutral topic phrases
can be researched; unspecified mutating requests still ask for clarification. Structured
paths, contents and action verbs are not spell-corrected.

Storage usage inspects the filesystem rather than guessing a cleanup. GPU inspection uses
existing read-only sysfs/DRM counters; on this Intel i915 machine it samples render/copy/video
engines for accessible user clients, deduplicating shared client IDs. This is not a whole-GPU
measurement for inaccessible processes. NVIDIA/AMD telemetry is supported when their existing
interfaces are available; those paths are not claimed live-tested here.

## Proactive behavior

Health hints are **off by default**. Enable them with the circle button in the header.
While enabled, a separate read-only watcher checks RAM, root-disk usage and battery
once every 30 seconds. Two consecutive samples are needed before warning about RAM above
90%, disk above 95%, or unplugged battery at or below 15%. Warnings are suppressed for
10 minutes after display. The circle button in the header pauses/resumes these hints.
An actionable hint can open the bubble; **Check it** submits a normal diagnostic objective
through the same agent and ActionGateway. The watcher does not terminate apps, delete files,
change settings or download anything. It does not watch your screen or record keystrokes.

## Implementation and verification

`monday/pet.py`: companion lifecycle, authenticated loopback HTTP bridge, agent worker,
GUI approval synchronization, cancellation and read-only health watcher.

`monday/ui/Pet.qml`: native transparent window, command box, compact results, approval
buttons, diagnostic shortcuts and blinking vector character.

The bridge binds only to `127.0.0.1` on a random port. Every request needs a random bearer
token; browser origins and unexpected Host headers are rejected. The token stays in private
session/wrapper files, not process arguments. State lives under `~/.local/state/monday-v2/pet/`,
separate from task-history JSON files. Logs omit HTTP bodies and authorization headers.
The UI/backend stop when you close the companion; nothing is installed as a login service.

The owned QML process, rather than a polling-heartbeat deadline, determines whether the pet
is alive. This avoids shutting it down when timers pause or the laptop suspends.

The final test suite includes native QML TextField submission, real displayed RAM result,
headless rendering, bridge authentication/origin checks, approval acceptance/denial/stale-ID
rejection, cancellation, shutdown, sustained-health thresholds/cooldowns, source ranking,
GPU counter math, and the originally reported CLI examples. Existing safety tests remain.

Measured baseline for the Qt companion: approximately 180 MiB summed backend+QML RSS;
shared pages can be counted twice. The CLI remains around 25 MiB when idle. Raw measurements
are in [pet-measurements.json](pet-measurements.json); no resident model or browser is needed.
