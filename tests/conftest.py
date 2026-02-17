"""Shared test fixtures for policy engine tests."""

from __future__ import annotations

import pytest

from pkg.models.policy import (
    Action,
    AutonTier,
    Condition,
    EvalRequirements,
    KillSwitch,
    KillSwitchType,
    LimitType,
    Policy,
    RiskTier,
    ToolRisk,
    TrustScore,
)


@pytest.fixture
def basic_policy():
    """A basic gated policy with tool risks and kill switches."""
    return Policy(
        name="test-policy",
        autonomy_tier=AutonTier.GATED,
        tool_risks=[
            ToolRisk(tool_name="db_delete", risk_tier=RiskTier.CRITICAL),
            ToolRisk(tool_name="send_email", risk_tier=RiskTier.MEDIUM, requires_approval=True),
            ToolRisk(tool_name="web_search", risk_tier=RiskTier.LOW),
        ],
        kill_switches=[
            KillSwitch(limit_type=LimitType.SPEND_USD, threshold=1.0, action=KillSwitchType.HALT),
            KillSwitch(limit_type=LimitType.TOOL_CALLS, threshold=50, action=KillSwitchType.PAUSE),
        ],
        conditions=[
            Condition(field="cost_usd", operator="gt", value=0.5),
        ],
    )


@pytest.fixture
def autonomous_policy():
    """An autonomous policy for trusted agents."""
    return Policy(
        name="autonomous-policy",
        autonomy_tier=AutonTier.AUTONOMOUS,
        tool_risks=[
            ToolRisk(tool_name="db_delete", risk_tier=RiskTier.CRITICAL),
        ],
    )


@pytest.fixture
def high_trust_score():
    """A trust score that qualifies for autonomous tier."""
    return TrustScore(
        agent_id="trusted-agent",
        current_tier=AutonTier.SUPERVISED,
        recommended_tier=AutonTier.AUTONOMOUS,
        weighted_score=0.92,
        correctness=0.88,
        safety=0.97,
        cost_stability=10.0,
        episodes_evaluated=30,
        meets_requirements=True,
    )


@pytest.fixture
def low_trust_score():
    """A trust score that only qualifies for shadow tier."""
    return TrustScore(
        agent_id="new-agent",
        current_tier=AutonTier.SHADOW,
        recommended_tier=AutonTier.SHADOW,
        weighted_score=0.3,
        correctness=0.2,
        safety=0.5,
        cost_stability=80.0,
        episodes_evaluated=1,
        meets_requirements=False,
    )


@pytest.fixture
def sample_episodes():
    """Sample episode data for trust scoring."""
    return [
        {
            "episode_id": f"ep-{i}",
            "agent_id": "test-agent",
            "status": "success" if i % 5 != 0 else "failure",
            "steps": [
                {"step_index": 0, "step_type": "llm_call", "tokens": 100},
                {"step_index": 1, "step_type": "tool_call", "tool_name": "web_search", "tokens": 50},
            ] if i % 7 != 0 else [
                {"step_index": 0, "step_type": "error"},
            ],
            "tools_used": ["web_search"],
            "total_tokens": 150,
            "total_cost_usd": 0.004 + (i * 0.001),
            "total_duration_ms": 600,
        }
        for i in range(20)
    ]
