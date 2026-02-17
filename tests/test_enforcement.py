"""Tests for PE-6: Runtime enforcement."""

from __future__ import annotations

import pytest

from pkg.enforcement.middleware import PolicyEnforcer
from pkg.models.policy import (
    Action,
    AgentProfile,
    AutonTier,
    KillSwitch,
    KillSwitchType,
    LimitType,
    Policy,
    RiskTier,
    ToolRisk,
)


class TestPolicyEnforcer:
    def test_allow_safe_action(self):
        policy = Policy(name="test", autonomy_tier=AutonTier.AUTONOMOUS)
        profile = AgentProfile(agent_id="a", policies=[policy])
        enforcer = PolicyEnforcer(profile)
        result = enforcer.check_action({"tool_name": "web_search", "step_type": "llm_call"})
        assert result.allowed

    def test_deny_critical_tool(self):
        policy = Policy(
            name="test", autonomy_tier=AutonTier.GATED,
            tool_risks=[ToolRisk(tool_name="db_delete", risk_tier=RiskTier.CRITICAL)],
        )
        profile = AgentProfile(agent_id="a", policies=[policy])
        enforcer = PolicyEnforcer(profile)
        result = enforcer.check_action({"tool_name": "db_delete", "step_type": "tool_call"})
        assert not result.allowed
        assert result.action == Action.DENY

    def test_kill_switch_halts(self):
        switch = KillSwitch(limit_type=LimitType.SPEND_USD, threshold=1.0, action=KillSwitchType.HALT)
        profile = AgentProfile(agent_id="a", active_kill_switches=[switch])
        enforcer = PolicyEnforcer(profile)
        enforcer.update_metrics({"spend_usd": 1.5})
        result = enforcer.check_action({"step_type": "llm_call"})
        assert not result.allowed
        assert result.action == Action.DENY

    def test_headroom_tracking(self):
        switch = KillSwitch(limit_type=LimitType.TOTAL_TOKENS, threshold=10000)
        profile = AgentProfile(agent_id="a", active_kill_switches=[switch])
        enforcer = PolicyEnforcer(profile)
        enforcer.update_metrics({"total_tokens": 3000})
        headroom = enforcer.get_headroom()
        assert headroom["total_tokens"]["remaining"] == 7000
