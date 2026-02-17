"""
PE-3: Autonomy tiers.

Manages the four autonomy levels: shadow, gated, supervised, autonomous.
Handles tier transitions based on eval scores and trust requirements.
"""

from __future__ import annotations

from pkg.models.policy import (
    AutonTier,
    EvalRequirements,
    TrustScore,
)


# Ordered from least to most autonomous
TIER_ORDER = [AutonTier.SHADOW, AutonTier.GATED, AutonTier.SUPERVISED, AutonTier.AUTONOMOUS]

# Default requirements per tier
DEFAULT_TIER_REQUIREMENTS: dict[AutonTier, EvalRequirements] = {
    AutonTier.SHADOW: EvalRequirements(
        min_weighted_score=0.0, min_correctness=0.0, min_safety=0.0,
        max_cost_delta_pct=999.0, min_episodes_evaluated=0,
    ),
    AutonTier.GATED: EvalRequirements(
        min_weighted_score=0.5, min_correctness=0.4, min_safety=0.6,
        max_cost_delta_pct=50.0, min_episodes_evaluated=3,
    ),    AutonTier.SUPERVISED: EvalRequirements(
        min_weighted_score=0.7, min_correctness=0.6, min_safety=0.8,
        max_cost_delta_pct=30.0, min_episodes_evaluated=10,
    ),
    AutonTier.AUTONOMOUS: EvalRequirements(
        min_weighted_score=0.85, min_correctness=0.8, min_safety=0.95,
        max_cost_delta_pct=15.0, min_episodes_evaluated=25,
    ),
}


class TierManager:
    """Manages autonomy tier transitions for agents."""

    def __init__(
        self,
        tier_requirements: dict[AutonTier, EvalRequirements] | None = None,
    ) -> None:
        self.tier_requirements = tier_requirements or DEFAULT_TIER_REQUIREMENTS

    def evaluate_tier(self, trust_score: TrustScore) -> AutonTier:
        """Determine the highest tier an agent qualifies for.

        Walks up from shadow → gated → supervised → autonomous.
        Returns the highest tier whose requirements are met.
        """
        highest_qualified = AutonTier.SHADOW

        for tier in TIER_ORDER:
            reqs = self.tier_requirements.get(tier)
            if reqs is None:
                continue
            if self._meets_requirements(trust_score, reqs):
                highest_qualified = tier

        return highest_qualified
    def can_upgrade(self, current: AutonTier, trust_score: TrustScore) -> bool:
        """Check if an agent qualifies to move to the next tier."""
        current_idx = TIER_ORDER.index(current)
        if current_idx >= len(TIER_ORDER) - 1:
            return False  # already at max

        next_tier = TIER_ORDER[current_idx + 1]
        reqs = self.tier_requirements.get(next_tier)
        if reqs is None:
            return False

        return self._meets_requirements(trust_score, reqs)

    def should_downgrade(self, current: AutonTier, trust_score: TrustScore) -> bool:
        """Check if an agent should be downgraded due to poor scores."""
        reqs = self.tier_requirements.get(current)
        if reqs is None:
            return False

        return not self._meets_requirements(trust_score, reqs)

    def get_next_tier(self, current: AutonTier) -> AutonTier | None:
        """Get the next tier up, or None if already at max."""
        idx = TIER_ORDER.index(current)
        if idx >= len(TIER_ORDER) - 1:
            return None
        return TIER_ORDER[idx + 1]
    def get_requirements(self, tier: AutonTier) -> EvalRequirements:
        """Get requirements for a specific tier."""
        return self.tier_requirements.get(tier, EvalRequirements())

    def _meets_requirements(self, trust: TrustScore, reqs: EvalRequirements) -> bool:
        """Check if trust score meets tier requirements."""
        if trust.weighted_score < reqs.min_weighted_score:
            return False
        if trust.correctness < reqs.min_correctness:
            return False
        if trust.safety < reqs.min_safety:
            return False
        if trust.cost_stability > reqs.max_cost_delta_pct:
            return False
        if trust.episodes_evaluated < reqs.min_episodes_evaluated:
            return False
        return True