"""
PE-5: Trust scorer.

Converts eval harness results into trust scores that determine
what autonomy tier an agent qualifies for. Connects to the eval
harness to pull recent eval data.
"""

from __future__ import annotations

from typing import Any

import httpx

from pkg.models.policy import AutonTier, TrustScore
from pkg.tiers.autonomy import TierManager


class TrustScorer:
    """Computes trust scores from eval harness results."""

    def __init__(
        self,
        eval_harness_url: str = "http://localhost:8200",
        episode_store_url: str = "http://localhost:8100",
        tier_manager: TierManager | None = None,
    ) -> None:
        self.eval_url = eval_harness_url.rstrip("/")
        self.store_url = episode_store_url.rstrip("/")
        self.tier_manager = tier_manager or TierManager()

    async def compute_trust(
        self,
        agent_id: str,
        current_tier: AutonTier = AutonTier.SHADOW,
    ) -> TrustScore:
        """Compute trust score for an agent from episode store data.

        Pulls recent episodes, calculates aggregate metrics,
        and recommends an autonomy tier.
        """
        episodes = await self._fetch_episodes(agent_id)

        if not episodes:
            return TrustScore(
                agent_id=agent_id,
                current_tier=current_tier,
                recommended_tier=AutonTier.SHADOW,
                episodes_evaluated=0,
                meets_requirements=False,
            )

        # Compute aggregate scores
        total = len(episodes)
        success_count = sum(1 for e in episodes if e.get("status") == "success")
        correctness = success_count / total if total > 0 else 0.0

        # Safety: ratio of episodes without error steps
        safe_count = sum(
            1 for e in episodes
            if not any(s.get("step_type") == "error" for s in e.get("steps", []))
        )
        safety = safe_count / total if total > 0 else 0.0

        # Cost stability: avg cost delta from median
        costs = [e.get("total_cost_usd", 0.0) for e in episodes]
        cost_stability = self._compute_cost_stability(costs)

        # Weighted composite
        weighted = correctness * 0.4 + safety * 0.3 + max(0, 1.0 - cost_stability / 100) * 0.3

        trust = TrustScore(
            agent_id=agent_id,
            current_tier=current_tier,
            recommended_tier=AutonTier.SHADOW,  # computed below
            weighted_score=round(weighted, 4),
            correctness=round(correctness, 4),
            safety=round(safety, 4),
            cost_stability=round(cost_stability, 2),
            episodes_evaluated=total,
        )

        # Determine recommended tier
        trust.recommended_tier = self.tier_manager.evaluate_tier(trust)
        trust.meets_requirements = (
            trust.recommended_tier.value >= current_tier.value
            if self._tier_index(trust.recommended_tier) >= self._tier_index(current_tier)
            else False
        )

        return trust

    def compute_trust_from_data(
        self,
        agent_id: str,
        episodes: list[dict],
        current_tier: AutonTier = AutonTier.SHADOW,
    ) -> TrustScore:
        """Compute trust score from pre-fetched episode data (sync version)."""
        if not episodes:
            return TrustScore(
                agent_id=agent_id,
                current_tier=current_tier,
                recommended_tier=AutonTier.SHADOW,
                episodes_evaluated=0,
            )

        total = len(episodes)
        success_count = sum(1 for e in episodes if e.get("status") == "success")
        correctness = success_count / total

        safe_count = sum(
            1 for e in episodes
            if not any(s.get("step_type") == "error" for s in e.get("steps", []))
        )
        safety = safe_count / total

        costs = [e.get("total_cost_usd", 0.0) for e in episodes]
        cost_stability = self._compute_cost_stability(costs)

        weighted = correctness * 0.4 + safety * 0.3 + max(0, 1.0 - cost_stability / 100) * 0.3

        trust = TrustScore(
            agent_id=agent_id,
            current_tier=current_tier,
            recommended_tier=AutonTier.SHADOW,
            weighted_score=round(weighted, 4),
            correctness=round(correctness, 4),
            safety=round(safety, 4),
            cost_stability=round(cost_stability, 2),
            episodes_evaluated=total,
        )

        trust.recommended_tier = self.tier_manager.evaluate_tier(trust)
        trust.meets_requirements = (
            self._tier_index(trust.recommended_tier) >= self._tier_index(current_tier)
        )

        return trust

    async def _fetch_episodes(self, agent_id: str) -> list[dict]:
        """Fetch recent episodes from the episode store."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.store_url}/v1/episodes",
                    params={"agent_id": agent_id, "limit": 50},
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError:
            return []

    def _compute_cost_stability(self, costs: list[float]) -> float:
        """Compute cost stability as coefficient of variation (%)."""
        if not costs or len(costs) < 2:
            return 0.0
        mean = sum(costs) / len(costs)
        if mean == 0:
            return 0.0
        variance = sum((c - mean) ** 2 for c in costs) / len(costs)
        std = variance ** 0.5
        return (std / mean) * 100

    @staticmethod
    def _tier_index(tier: AutonTier) -> int:
        order = [AutonTier.SHADOW, AutonTier.GATED, AutonTier.SUPERVISED, AutonTier.AUTONOMOUS]
        return order.index(tier) if tier in order else 0
