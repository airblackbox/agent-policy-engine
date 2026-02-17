"""
PE-2: Rule engine.

Evaluates actions against policies. Takes an action context (what the agent
wants to do) and evaluates it against all applicable policies. Returns
allow/deny/escalate decisions.
"""

from __future__ import annotations

from typing import Any

from pkg.models.policy import (
    Action,
    AutonTier,
    Condition,
    Policy,
    PolicyDecision,
    PolicyResult,
    ToolRisk,
)


class PolicyEvaluator:
    """Evaluates agent actions against policies."""

    def __init__(self, policies: list[Policy] | None = None) -> None:
        self.policies: list[Policy] = policies or []
    def add_policy(self, policy: Policy) -> None:
        self.policies.append(policy)

    def evaluate(
        self,
        agent_id: str,
        action_context: dict[str, Any],
    ) -> PolicyResult:
        """Evaluate an action against all applicable policies.

        action_context should contain:
          - tool_name (str): the tool being called
          - model (str): the model being used
          - step_type (str): llm_call, tool_call, etc.
          - cost_usd (float): estimated cost
          - tokens (int): estimated tokens
          Plus any other fields policies might check.
        """
        applicable = self._get_applicable_policies(agent_id)
        decisions: list[PolicyDecision] = []

        for policy in applicable:
            decision = self._evaluate_policy(policy, action_context)
            decisions.append(decision)

        # Determine final action: most restrictive wins
        final_action = self._resolve_decisions(decisions, applicable)
        tier = applicable[0].autonomy_tier if applicable else AutonTier.SHADOW

        return PolicyResult(
            final_action=final_action,
            decisions=decisions,
            agent_id=agent_id,
            autonomy_tier=tier,
        )
    def _get_applicable_policies(self, agent_id: str) -> list[Policy]:
        """Get policies that apply to this agent."""
        applicable = []
        for p in self.policies:
            if not p.enabled:
                continue
            if p.agent_id is None or p.agent_id == agent_id:
                applicable.append(p)
        return applicable

    def _evaluate_policy(
        self, policy: Policy, context: dict[str, Any],
    ) -> PolicyDecision:
        """Evaluate a single policy against an action context."""
        triggered: list[str] = []

        # Check tool risk
        tool_name = context.get("tool_name")
        if tool_name:
            tool_decision = self._check_tool_risk(policy, tool_name)
            if tool_decision:
                return tool_decision

        # Check conditions
        for condition in policy.conditions:
            if self._evaluate_condition(condition, context):
                triggered.append(f"{condition.field} {condition.operator} {condition.value}")
        # If conditions triggered, apply the policy's default action
        if triggered:
            return PolicyDecision(
                action=policy.default_action,
                reason=f"Conditions triggered: {', '.join(triggered)}",
                policy_id=policy.policy_id,
                policy_name=policy.name,
                triggered_conditions=triggered,
            )

        # Check autonomy tier restrictions
        tier_action = self._check_autonomy_tier(policy, context)
        if tier_action:
            return tier_action

        return PolicyDecision(
            action=Action.ALLOW,
            reason="No policy violations",
            policy_id=policy.policy_id,
            policy_name=policy.name,
        )
    def _check_tool_risk(self, policy: Policy, tool_name: str) -> PolicyDecision | None:
        """Check if a tool is classified as risky."""
        for tr in policy.tool_risks:
            if tr.tool_name == tool_name:
                if tr.risk_tier.value == "critical":
                    return PolicyDecision(
                        action=Action.DENY if policy.autonomy_tier != AutonTier.AUTONOMOUS else Action.ESCALATE,
                        reason=f"Tool '{tool_name}' classified as critical risk",
                        policy_id=policy.policy_id,
                        policy_name=policy.name,
                        triggered_conditions=[f"tool_risk:{tool_name}=critical"],
                    )
                if tr.requires_approval and policy.autonomy_tier != AutonTier.AUTONOMOUS:
                    return PolicyDecision(
                        action=Action.ESCALATE,
                        reason=f"Tool '{tool_name}' requires human approval",
                        policy_id=policy.policy_id,
                        policy_name=policy.name,
                        triggered_conditions=[f"tool_approval:{tool_name}"],
                    )
        return None
    def _check_autonomy_tier(self, policy: Policy, context: dict[str, Any]) -> PolicyDecision | None:
        """Apply autonomy tier restrictions."""
        tier = policy.autonomy_tier
        step_type = context.get("step_type", "")

        if tier == AutonTier.SHADOW:
            return PolicyDecision(
                action=Action.LOG,
                reason="Shadow mode — action logged but not executed",
                policy_id=policy.policy_id,
                policy_name=policy.name,
            )

        if tier == AutonTier.GATED and step_type in ("tool_call", "decision"):
            return PolicyDecision(
                action=Action.ESCALATE,
                reason="Gated mode — tool calls require human approval",
                policy_id=policy.policy_id,
                policy_name=policy.name,
            )

        return None
    def _evaluate_condition(self, condition: Condition, context: dict[str, Any]) -> bool:
        """Evaluate a single condition against context."""
        value = context.get(condition.field)
        if value is None:
            return False

        op = condition.operator
        target = condition.value

        if op == "eq":
            return value == target
        elif op == "neq":
            return value != target
        elif op == "in":
            return value in target
        elif op == "not_in":
            return value not in target
        elif op == "gt":
            return float(value) > float(target)
        elif op == "lt":
            return float(value) < float(target)
        elif op == "gte":
            return float(value) >= float(target)
        elif op == "lte":
            return float(value) <= float(target)
        elif op == "contains":
            return str(target) in str(value)
        return False
    def _resolve_decisions(self, decisions: list[PolicyDecision], policies: list[Policy]) -> Action:
        """Resolve multiple decisions — most restrictive wins."""
        if not decisions:
            return Action.DENY  # no policies = deny by default

        priority = {Action.DENY: 0, Action.ESCALATE: 1, Action.LOG: 2, Action.ALLOW: 3}
        sorted_decisions = sorted(decisions, key=lambda d: priority.get(d.action, 3))
        return sorted_decisions[0].action