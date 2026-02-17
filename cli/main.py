"""
PE-8: CLI for the policy engine.

Commands for managing policies, checking agent trust, and monitoring limits.
"""

from __future__ import annotations

import asyncio
import json
import sys

import click
from rich.console import Console
from rich.table import Table

from pkg.models.policy import (
    Action,
    AutonTier,
    KillSwitch,
    KillSwitchType,
    LimitType,
    Policy,
    ToolRisk,
    RiskTier,
)
from pkg.engine.evaluator import PolicyEvaluator
from pkg.enforcement.middleware import PolicyEnforcer
from pkg.limits.killswitch import KillSwitchMonitor
from pkg.models.policy import AgentProfile
from pkg.tiers.autonomy import TierManager, DEFAULT_TIER_REQUIREMENTS
from pkg.trust.scorer import TrustScorer

console = Console()


@click.group()
def cli():
    """agent-policy-engine — Risk-tiered autonomy for AI agents."""
    pass


@cli.command()
def tiers():
    """Show autonomy tiers and their requirements."""
    table = Table(title="Autonomy Tiers")
    table.add_column("Tier")
    table.add_column("Min Score")
    table.add_column("Min Correctness")
    table.add_column("Min Safety")
    table.add_column("Max Cost Δ%")
    table.add_column("Min Episodes")

    for tier, reqs in DEFAULT_TIER_REQUIREMENTS.items():
        table.add_row(
            tier.value,
            f"{reqs.min_weighted_score:.1f}",
            f"{reqs.min_correctness:.1f}",
            f"{reqs.min_safety:.1f}",
            f"{reqs.max_cost_delta_pct:.0f}%",
            str(reqs.min_episodes_evaluated),
        )
    console.print(table)


@cli.command()
@click.argument("policy_file", type=click.Path(exists=True))
def load(policy_file):
    """Load and validate a policy JSON file."""
    with open(policy_file) as f:
        data = json.load(f)
    try:
        policy = Policy(**data)
        console.print(f"[green]Policy loaded: {policy.name}[/]")
        console.print(f"  ID: {policy.policy_id}")
        console.print(f"  Tier: {policy.autonomy_tier.value}")
        console.print(f"  Tool risks: {len(policy.tool_risks)}")
        console.print(f"  Kill switches: {len(policy.kill_switches)}")
        console.print(f"  Conditions: {len(policy.conditions)}")
    except Exception as e:
        console.print(f"[red]Invalid policy: {e}[/]")
        sys.exit(1)


@cli.command()
@click.option("--agent-id", required=True, help="Agent ID to evaluate")
@click.option("--tool", default=None, help="Tool name to check")
@click.option("--policy-file", default=None, help="Policy JSON file")
def check(agent_id, tool, policy_file):
    """Check if an action would be allowed."""
    if policy_file:
        with open(policy_file) as f:
            policy = Policy(**json.load(f))
    else:
        policy = Policy(name="default", autonomy_tier=AutonTier.GATED)

    evaluator = PolicyEvaluator([policy])
    context = {"tool_name": tool or "unknown", "step_type": "tool_call"}
    result = evaluator.evaluate(agent_id, context)

    color = {"allow": "green", "deny": "red", "escalate": "yellow", "log": "blue"}.get(
        result.final_action.value, "white"
    )
    console.print(f"[{color}]{result.final_action.value.upper()}[/] for agent={agent_id} tool={tool}")
    for d in result.decisions:
        console.print(f"  [{color}]{d.action.value}[/]: {d.reason}")


@cli.command()
@click.option("--store-url", default="http://localhost:8100", help="Episode store URL")
@click.option("--agent-id", required=True, help="Agent ID")
def trust(store_url, agent_id):
    """Compute trust score for an agent."""
    async def _compute():
        scorer = TrustScorer(episode_store_url=store_url)
        score = await scorer.compute_trust(agent_id)
        console.print(f"\n[bold]Trust Score: {agent_id}[/]")
        console.print(f"  Weighted: {score.weighted_score:.2f}")
        console.print(f"  Correctness: {score.correctness:.2f}")
        console.print(f"  Safety: {score.safety:.2f}")
        console.print(f"  Cost Stability: {score.cost_stability:.1f}%")
        console.print(f"  Episodes: {score.episodes_evaluated}")
        console.print(f"  Current Tier: {score.current_tier.value}")
        console.print(f"  Recommended: {score.recommended_tier.value}")

    asyncio.run(_compute())


if __name__ == "__main__":
    cli()
