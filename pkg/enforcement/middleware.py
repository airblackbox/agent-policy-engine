"""
PE-6: Runtime enforcement middleware.

Sits between the agent and the gateway/tools. Before any action,
checks the policy engine and kill switches. Returns allow/deny/escalate.
Designed to be called as a pre-hook before each agent step.
"""

from __future__ import annotations

from typing import Any

from pkg.engine.evaluator import PolicyEvaluator
from pkg.limits.killswitch import KillSwitchMonitor
from pkg.models.policy import (
    Action,
    AgentProfile,
    AutonTier,
    KillSwitch,
    KillSwitchType,
    LimitType,
    Policy,
    PolicyDecision,
    PolicyResult,
)


class EnforcementResult:
    """Result of enforcement check."""

    def __init__(
        self,
        allowed: bool,
        action: Action,
        reason: str,
        decisions: list[PolicyDecision] | None = None,
    ) -> None:
        self.allowed = allowed
        self.action = action
        self.reason = reason
        self.decisions = decisions or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "action": self.action.value,
            "reason": self.reason,
            "decisions": [
                {"action": d.action.value, "reason": d.reason, "policy": d.policy_name}
                for d in self.decisions
            ],
        }


class PolicyEnforcer:
    """Runtime enforcement layer for agent actions.

    Usage:
        enforcer = PolicyEnforcer(profile)
        result = enforcer.check_action({"tool_name": "db_delete", ...})
        if not result.allowed:
            # block or escalate
    """

    def __init__(self, profile: AgentProfile) -> None:
        self.profile = profile
        self.evaluator = PolicyEvaluator(profile.policies)
        self.monitor = KillSwitchMonitor(profile.active_kill_switches)

    def check_action(self, action_context: dict[str, Any]) -> EnforcementResult:
        """Check if an action is allowed under current policies.

        This is the main entry point — call before each agent step.
        """
        # Check kill switches first (fastest check)
        kill_decisions = self.monitor.check()
        if kill_decisions:
            worst = min(kill_decisions, key=lambda d: {Action.DENY: 0, Action.ESCALATE: 1, Action.LOG: 2}.get(d.action, 3))
            return EnforcementResult(
                allowed=(worst.action != Action.DENY),
                action=worst.action,
                reason=worst.reason,
                decisions=kill_decisions,
            )

        # Evaluate policies
        policy_result = self.evaluator.evaluate(self.profile.agent_id, action_context)

        allowed = policy_result.final_action in (Action.ALLOW, Action.LOG)
        return EnforcementResult(
            allowed=allowed,
            action=policy_result.final_action,
            reason=self._summarize(policy_result),
            decisions=policy_result.decisions,
        )

    def update_metrics(self, metrics: dict[str, float]) -> None:
        """Update kill switch counters after a step completes."""
        self.monitor.update(metrics)

    def get_headroom(self) -> dict:
        """Get remaining headroom for all limits."""
        return self.monitor.get_headroom()

    def _summarize(self, result: PolicyResult) -> str:
        """Summarize policy evaluation."""
        if result.final_action == Action.ALLOW:
            return "Action allowed by policy"
        deny_reasons = [d.reason for d in result.decisions if d.action in (Action.DENY, Action.ESCALATE)]
        return "; ".join(deny_reasons) if deny_reasons else f"Action {result.final_action.value}"
