"""
PE-1: Policy schema and rule models.

Defines the data structures for policies, risk tiers, autonomy levels,
tool risk classifications, and kill switches. A policy is a set of rules
that determine what an agent can and cannot do at runtime.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class RiskTier(str, Enum):
    """Risk classification for tools and actions."""
    LOW = "low"            # e.g. read files, search web
    MEDIUM = "medium"      # e.g. send messages, create resources
    HIGH = "high"          # e.g. modify data, execute code
    CRITICAL = "critical"  # e.g. delete data, move money, deploy

class AutonTier(str, Enum):
    """Autonomy level for an agent."""
    SHADOW = "shadow"          # logs what it would do, does nothing
    GATED = "gated"            # pauses for human approval
    SUPERVISED = "supervised"  # executes but flags for review
    AUTONOMOUS = "autonomous"  # executes freely within policy bounds


class LimitType(str, Enum):
    """Types of runtime limits (kill switches)."""
    SPEND_USD = "spend_usd"
    TOTAL_TOKENS = "total_tokens"
    DURATION_SECONDS = "duration_seconds"
    TOOL_CALLS = "tool_calls"
    ERROR_COUNT = "error_count"
    STEP_COUNT = "step_count"


class KillSwitchType(str, Enum):
    """What happens when a kill switch triggers."""
    HALT = "halt"              # stop execution immediately
    PAUSE = "pause"            # pause and wait for human
    DOWNGRADE = "downgrade"    # reduce autonomy tier
    ALERT = "alert"            # continue but fire alert


class Action(str, Enum):
    """Policy decision action."""
    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"  # require human approval
    LOG = "log"            # allow but flag for audit

class ToolRisk(BaseModel):
    """Risk classification for a specific tool."""
    tool_name: str
    risk_tier: RiskTier
    description: str = ""
    requires_approval: bool = False
    max_calls_per_episode: int | None = None


class KillSwitch(BaseModel):
    """A runtime limit that triggers action when exceeded."""
    switch_id: str = Field(default_factory=lambda: str(uuid4()))
    limit_type: LimitType
    threshold: float
    action: KillSwitchType = KillSwitchType.HALT
    description: str = ""
    enabled: bool = True


class Condition(BaseModel):
    """A single policy condition to evaluate."""
    field: str           # e.g. "tool_name", "model", "cost_usd", "step_type"
    operator: str        # "eq", "neq", "in", "not_in", "gt", "lt", "gte", "lte", "contains"
    value: Any           # the value to compare against

class EvalRequirements(BaseModel):
    """Minimum eval scores required for an autonomy tier."""
    min_weighted_score: float = 0.7
    min_correctness: float = 0.6
    min_safety: float = 0.8
    max_cost_delta_pct: float = 30.0
    min_episodes_evaluated: int = 5


class Policy(BaseModel):
    """A complete policy definition for an agent or agent group."""
    policy_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: str = ""
    agent_id: str | None = None       # None = applies to all agents
    autonomy_tier: AutonTier = AutonTier.GATED
    tool_risks: list[ToolRisk] = Field(default_factory=list)
    kill_switches: list[KillSwitch] = Field(default_factory=list)
    conditions: list[Condition] = Field(default_factory=list)
    eval_requirements: EvalRequirements = Field(default_factory=EvalRequirements)
    default_action: Action = Action.DENY
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

class PolicyDecision(BaseModel):
    """Result of evaluating a single action against a policy."""
    action: Action
    reason: str
    policy_id: str
    policy_name: str
    triggered_conditions: list[str] = Field(default_factory=list)
    kill_switch_triggered: str | None = None


class PolicyResult(BaseModel):
    """Complete result of evaluating an action against all applicable policies."""
    final_action: Action
    decisions: list[PolicyDecision] = Field(default_factory=list)
    agent_id: str
    autonomy_tier: AutonTier
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TrustScore(BaseModel):
    """An agent's trust score derived from eval results."""
    agent_id: str
    current_tier: AutonTier
    recommended_tier: AutonTier
    weighted_score: float = 0.0
    correctness: float = 0.0
    safety: float = 0.0
    cost_stability: float = 0.0
    episodes_evaluated: int = 0
    meets_requirements: bool = False
    last_evaluated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentProfile(BaseModel):
    """Runtime profile for an agent, combining policy + trust."""
    agent_id: str
    policies: list[Policy] = Field(default_factory=list)
    trust_score: TrustScore | None = None
    effective_tier: AutonTier = AutonTier.SHADOW
    active_kill_switches: list[KillSwitch] = Field(default_factory=list)
    tool_risks: dict[str, ToolRisk] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))