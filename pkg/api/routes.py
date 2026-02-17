"""
PE-7: Policy API.

FastAPI routes for managing policies, evaluating actions,
checking trust scores, and monitoring kill switches.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel

from pkg.engine.evaluator import PolicyEvaluator
from pkg.enforcement.middleware import PolicyEnforcer
from pkg.limits.killswitch import KillSwitchMonitor
from pkg.models.policy import (
    Action,
    AgentProfile,
    AutonTier,
    KillSwitch,
    KillSwitchType,
    LimitType,
    Policy,
    ToolRisk,
    TrustScore,
)
from pkg.tiers.autonomy import TierManager
from pkg.trust.scorer import TrustScorer

router = APIRouter(prefix="/v1")

# In-memory store (replace with DB in production)
_policies: dict[str, Policy] = {}
_profiles: dict[str, AgentProfile] = {}
_enforcers: dict[str, PolicyEnforcer] = {}


# --- Request models ---

class CreatePolicyRequest(BaseModel):
    name: str
    description: str = ""
    agent_id: str | None = None
    autonomy_tier: AutonTier = AutonTier.GATED
    tool_risks: list[ToolRisk] = []
    kill_switches: list[KillSwitch] = []
    default_action: Action = Action.DENY


class EvaluateRequest(BaseModel):
    agent_id: str
    action_context: dict[str, Any]


class UpdateMetricsRequest(BaseModel):
    agent_id: str
    metrics: dict[str, float]


# --- Health ---

@router.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "agent-policy-engine",
        "version": "0.1.0",
        "policies": len(_policies),
        "agents": len(_profiles),
    }


# --- Policy CRUD ---

@router.post("/policies")
async def create_policy(req: CreatePolicyRequest):
    policy = Policy(
        name=req.name,
        description=req.description,
        agent_id=req.agent_id,
        autonomy_tier=req.autonomy_tier,
        tool_risks=req.tool_risks,
        kill_switches=req.kill_switches,
        default_action=req.default_action,
    )
    _policies[policy.policy_id] = policy
    _rebuild_profiles()
    return policy.model_dump(mode="json")


@router.get("/policies")
async def list_policies():
    return [p.model_dump(mode="json") for p in _policies.values()]


@router.get("/policies/{policy_id}")
async def get_policy(policy_id: str):
    if policy_id not in _policies:
        raise HTTPException(404, "Policy not found")
    return _policies[policy_id].model_dump(mode="json")


@router.delete("/policies/{policy_id}")
async def delete_policy(policy_id: str):
    if policy_id not in _policies:
        raise HTTPException(404, "Policy not found")
    del _policies[policy_id]
    _rebuild_profiles()
    return {"deleted": policy_id}


# --- Enforcement ---

@router.post("/evaluate")
async def evaluate_action(req: EvaluateRequest):
    """Evaluate an action against all applicable policies."""
    profile = _get_or_create_profile(req.agent_id)
    enforcer = PolicyEnforcer(profile)
    result = enforcer.check_action(req.action_context)
    return result.to_dict()


@router.post("/metrics")
async def update_metrics(req: UpdateMetricsRequest):
    """Update kill switch counters for an agent."""
    if req.agent_id in _enforcers:
        _enforcers[req.agent_id].update_metrics(req.metrics)
    return {"updated": req.agent_id}


@router.get("/agents/{agent_id}/headroom")
async def get_headroom(agent_id: str):
    """Get remaining headroom for all kill switches."""
    if agent_id in _enforcers:
        return _enforcers[agent_id].get_headroom()
    return {}


@router.get("/agents/{agent_id}/profile")
async def get_profile(agent_id: str):
    """Get the runtime profile for an agent."""
    profile = _get_or_create_profile(agent_id)
    return profile.model_dump(mode="json")


@router.get("/tiers")
async def list_tiers():
    """List autonomy tiers and their requirements."""
    manager = TierManager()
    tiers = {}
    for tier in AutonTier:
        reqs = manager.get_requirements(tier)
        tiers[tier.value] = reqs.model_dump()
    return tiers


# --- Helpers ---

def _get_or_create_profile(agent_id: str) -> AgentProfile:
    if agent_id not in _profiles:
        applicable = [p for p in _policies.values() if p.agent_id is None or p.agent_id == agent_id]
        all_switches = []
        all_tool_risks = {}
        tier = AutonTier.SHADOW
        for p in applicable:
            all_switches.extend(p.kill_switches)
            for tr in p.tool_risks:
                all_tool_risks[tr.tool_name] = tr
            tier = p.autonomy_tier

        _profiles[agent_id] = AgentProfile(
            agent_id=agent_id,
            policies=applicable,
            effective_tier=tier,
            active_kill_switches=all_switches,
            tool_risks=all_tool_risks,
        )
    return _profiles[agent_id]


def _rebuild_profiles():
    """Rebuild all agent profiles when policies change."""
    _profiles.clear()
    _enforcers.clear()


# --- App factory ---

def create_app() -> FastAPI:
    app = FastAPI(title="Agent Policy Engine", version="0.1.0")
    app.include_router(router)
    return app
