"""Tests for PE-4: Kill switches."""

from __future__ import annotations

import pytest

from pkg.limits.killswitch import KillSwitchMonitor
from pkg.models.policy import (
    Action,
    KillSwitch,
    KillSwitchType,
    LimitType,
)


class TestKillSwitchMonitor:
    def test_no_triggers_under_threshold(self):
        monitor = KillSwitchMonitor([
            KillSwitch(limit_type=LimitType.SPEND_USD, threshold=1.0),
        ])
        monitor.update({"spend_usd": 0.5})
        assert monitor.check() == []

    def test_triggers_at_threshold(self):
        monitor = KillSwitchMonitor([
            KillSwitch(limit_type=LimitType.SPEND_USD, threshold=1.0, action=KillSwitchType.HALT),
        ])
        monitor.update({"spend_usd": 1.0})
        decisions = monitor.check()
        assert len(decisions) == 1
        assert decisions[0].action == Action.DENY

    def test_pause_action(self):
        monitor = KillSwitchMonitor([
            KillSwitch(limit_type=LimitType.TOOL_CALLS, threshold=10, action=KillSwitchType.PAUSE),
        ])
        monitor.update({"tool_calls": 15})
        decisions = monitor.check()
        assert decisions[0].action == Action.ESCALATE

    def test_incremental_updates(self):
        monitor = KillSwitchMonitor([
            KillSwitch(limit_type=LimitType.TOTAL_TOKENS, threshold=1000),
        ])
        monitor.update({"total_tokens": 400})
        assert monitor.check() == []
        monitor.update({"total_tokens": 400})
        assert monitor.check() == []
        monitor.update({"total_tokens": 300})
        decisions = monitor.check()
        assert len(decisions) == 1

    def test_headroom_tracking(self):
        monitor = KillSwitchMonitor([
            KillSwitch(limit_type=LimitType.SPEND_USD, threshold=10.0),
        ])
        monitor.update({"spend_usd": 3.0})
        headroom = monitor.get_headroom()
        assert headroom["spend_usd"]["remaining"] == 7.0
        assert headroom["spend_usd"]["pct_used"] == 30.0

    def test_reset_clears_counters(self):
        monitor = KillSwitchMonitor([
            KillSwitch(limit_type=LimitType.SPEND_USD, threshold=1.0),
        ])
        monitor.update({"spend_usd": 0.8})
        monitor.reset()
        headroom = monitor.get_headroom()
        assert headroom["spend_usd"]["current"] == 0.0

    def test_disabled_switch_ignored(self):
        monitor = KillSwitchMonitor([
            KillSwitch(limit_type=LimitType.SPEND_USD, threshold=0.01, enabled=False),
        ])
        monitor.update({"spend_usd": 100.0})
        assert monitor.check() == []
