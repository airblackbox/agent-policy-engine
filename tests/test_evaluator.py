"""Tests for PE-2: Rule engine."""

from __future__ import annotations

import pytest

from pkg.engine.evaluator import PolicyEvaluator
from pkg.models.policy import Action, AutonTier, Condition, Policy, RiskTier, ToolRisk


class TestPolicyEvaluator:
    def test_allow_safe_action(self, basic_policy):
        evaluator = PolicyEvaluator([basic_policy])
        result = evaluator.evaluate("agent-1", {"tool_name": "web_search", "step_type": "tool_call"})
        # Gated mode + tool_call = escalate
        assert result.final_action == Action.ESCALATE

    def test_deny_critical_tool(self, basic_policy):
        evaluator = PolicyEvaluator([basic_policy])
        result = evaluator.evaluate("agent-1", {"tool_name": "db_delete", "step_type": "tool_call"})
        assert result.final_action == Action.DENY

    def test_escalate_approval_required(self, basic_policy):
        evaluator = PolicyEvaluator([basic_policy])
        result = evaluator.evaluate("agent-1", {"tool_name": "send_email", "step_type": "tool_call"})
        assert result.final_action == Action.ESCALATE

    def test_autonomous_allows_most_tools(self, autonomous_policy):
        evaluator = PolicyEvaluator([autonomous_policy])
        result = evaluator.evaluate("agent-1", {"tool_name": "web_search", "step_type": "tool_call"})
        assert result.final_action == Action.ALLOW

    def test_autonomous_escalates_critical(self, autonomous_policy):
        evaluator = PolicyEvaluator([autonomous_policy])
        result = evaluator.evaluate("agent-1", {"tool_name": "db_delete", "step_type": "tool_call"})
        assert result.final_action == Action.ESCALATE

    def test_shadow_mode_logs_only(self):
        policy = Policy(name="shadow", autonomy_tier=AutonTier.SHADOW)
        evaluator = PolicyEvaluator([policy])
        result = evaluator.evaluate("agent-1", {"tool_name": "anything", "step_type": "tool_call"})
        assert result.final_action == Action.LOG

    def test_condition_triggers_deny(self):
        policy = Policy(
            name="cost-limit",
            autonomy_tier=AutonTier.AUTONOMOUS,
            conditions=[Condition(field="cost_usd", operator="gt", value=0.5)],
            default_action=Action.DENY,
        )
        evaluator = PolicyEvaluator([policy])
        result = evaluator.evaluate("agent-1", {"cost_usd": 0.8, "step_type": "llm_call"})
        assert result.final_action == Action.DENY

    def test_no_policies_denies(self):
        evaluator = PolicyEvaluator([])
        result = evaluator.evaluate("agent-1", {"tool_name": "anything"})
        assert result.final_action == Action.DENY

    def test_agent_specific_policy(self):
        general = Policy(name="general", agent_id=None, autonomy_tier=AutonTier.GATED)
        specific = Policy(name="specific", agent_id="agent-1", autonomy_tier=AutonTier.AUTONOMOUS)
        evaluator = PolicyEvaluator([general, specific])
        result = evaluator.evaluate("agent-1", {"step_type": "llm_call"})
        # Both apply, but autonomous allows LLM calls
        assert result.final_action in (Action.ALLOW, Action.LOG)
