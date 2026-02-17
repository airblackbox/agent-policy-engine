"""
PE-4: Kill switches.

Runtime limits that halt, pause, or downgrade agents when thresholds
are exceeded. Tracks spend, tokens, duration, tool calls, errors, and
step counts per episode.
"""

from __future__ import annotations

from typing import Any

from pkg.models.policy import (
    Action,
    AutonTier,
    KillSwitch,
    KillSwitchType,
    LimitType,
    PolicyDecision,
)


class KillSwitchMonitor:
    """Monitors runtime metrics and triggers kill switches."""

    def __init__(self, switches: list[KillSwitch] | None = None) -> None:
        self.switches: list[KillSwitch] = switches or []
        self._counters: dict[str, float] = {}
    def add_switch(self, switch: KillSwitch) -> None:
        self.switches.append(switch)

    def reset(self) -> None:
        """Reset all counters (e.g. at start of new episode)."""
        self._counters = {}

    def update(self, metrics: dict[str, float]) -> None:
        """Update counters with new metric values.

        metrics keys should match LimitType values:
          spend_usd, total_tokens, duration_seconds,
          tool_calls, error_count, step_count
        """
        for key, value in metrics.items():
            self._counters[key] = self._counters.get(key, 0.0) + value

    def set_absolute(self, metrics: dict[str, float]) -> None:
        """Set absolute counter values (not incremental)."""
        self._counters.update(metrics)

    def check(self) -> list[PolicyDecision]:
        """Check all kill switches against current counters.

        Returns a list of triggered decisions. Empty list = all clear.
        """
        triggered: list[PolicyDecision] = []

        for switch in self.switches:
            if not switch.enabled:
                continue

            current = self._counters.get(switch.limit_type.value, 0.0)
            if current >= switch.threshold:
                decision = self._trigger(switch, current)
                triggered.append(decision)

        return triggered
    def check_single(self, limit_type: LimitType, value: float) -> PolicyDecision | None:
        """Check a specific limit type against a value."""
        for switch in self.switches:
            if not switch.enabled:
                continue
            if switch.limit_type == limit_type and value >= switch.threshold:
                return self._trigger(switch, value)
        return None

    def get_headroom(self) -> dict[str, dict[str, float]]:
        """Get remaining headroom for each limit.

        Returns dict of limit_type -> {threshold, current, remaining, pct_used}.
        """
        headroom: dict[str, dict[str, float]] = {}
        for switch in self.switches:
            if not switch.enabled:
                continue
            current = self._counters.get(switch.limit_type.value, 0.0)
            remaining = max(0.0, switch.threshold - current)
            pct_used = (current / switch.threshold * 100) if switch.threshold > 0 else 0
            headroom[switch.limit_type.value] = {
                "threshold": switch.threshold,
                "current": round(current, 4),
                "remaining": round(remaining, 4),
                "pct_used": round(pct_used, 2),
            }
        return headroom
    def _trigger(self, switch: KillSwitch, current: float) -> PolicyDecision:
        """Create a policy decision for a triggered kill switch."""
        action_map = {
            KillSwitchType.HALT: Action.DENY,
            KillSwitchType.PAUSE: Action.ESCALATE,
            KillSwitchType.DOWNGRADE: Action.LOG,
            KillSwitchType.ALERT: Action.LOG,
        }

        return PolicyDecision(
            action=action_map.get(switch.action, Action.DENY),
            reason=f"Kill switch triggered: {switch.limit_type.value} = {current:.2f} (threshold: {switch.threshold:.2f}). {switch.description}",
            policy_id="kill-switch",
            policy_name=f"kill-switch:{switch.limit_type.value}",
            kill_switch_triggered=switch.switch_id,
        )