"""
ACFC-Safe Calibration Suite — trigger.py

CalibrationTrigger fires when directional evaluator blindness persists across
a sliding window of turns.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .metrics import RiskPair


@dataclass
class CalibrationTrigger:
    window_size: int = 5
    required_hits: int = 3
    history: list[RiskPair] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.window_size < 1:
            raise ValueError("window_size must be >= 1")
        if self.required_hits < 1:
            raise ValueError("required_hits must be >= 1")
        if self.required_hits > self.window_size:
            raise ValueError(
                f"required_hits ({self.required_hits}) cannot exceed "
                f"window_size ({self.window_size})"
            )

    def process_turn(self, pair: RiskPair) -> bool:
        self.history.append(pair)

        if len(self.history) < self.window_size:
            return False

        recent = self.history[-self.window_size:]
        hits = sum(1 for item in recent if item.is_blindness_detected)
        return hits >= self.required_hits

    @property
    def current_window(self) -> list[RiskPair]:
        return self.history[-self.window_size:]

    @property
    def hit_count(self) -> int:
        return sum(1 for p in self.current_window if p.is_blindness_detected)

    @property
    def is_armed(self) -> bool:
        return len(self.history) >= self.window_size and self.hit_count >= self.required_hits

    def reset(self) -> None:
        """
        Clear history and disarm the trigger.

        Call only after a MemorySnapshot has been frozen.
        """
        self.history.clear()
