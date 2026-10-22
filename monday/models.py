from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import IntEnum
from typing import Any
import time

class Risk(IntEnum):
    READ_ONLY = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

@dataclass(frozen=True)
class Action:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)

@dataclass
class Decision:
    objective: str
    current_state: dict
    next_action: Action | None
    reason: str
    expected_observation: str
    completion_criteria: str
    risk: Risk = Risk.READ_ONLY
    confidence: float | None = None
    response: str = ""
    status: str = "RUNNING"

@dataclass
class Observation:
    tool: str
    ok: bool
    data: Any = None
    error: str = ""
    verified: bool = False
    simulated: bool = False
    inverse: Action | None = None

@dataclass
class TaskState:
    objective: str
    context: dict = field(default_factory=dict)
    observations: list[Observation] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    started: float = field(default_factory=time.monotonic)
    status: str = "RUNNING"
    response: str = ""

    def latest(self, tool):
        return next((o for o in reversed(self.observations) if o.tool == tool), None)

    def snapshot(self):
        return {"context": self.context, "observations": [asdict(o) for o in self.observations]}
