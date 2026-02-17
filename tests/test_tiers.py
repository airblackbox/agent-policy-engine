"""Tests for PE-3: Autonomy tiers."""

from __future__ import annotations

import pytest

from pkg.models.policy import AutonTier, TrustScore
from pkg.tiers.autonomy import TierManager


class TestTierManager:
    def test_shadow_for_new_agent(self, low_trust_score):
        manager = TierManager()
        tier = manager.evaluate_tier(low_trust_score)
        assert tier == AutonTier.SHADOW

    def test_autonomous_for_trusted_agent(self, high_trust_score):
        manager = TierManager()
        tier = manager.evaluate_tier(high_trust_score)
        assert tier == AutonTier.AUTONOMOUS

    def test_can_upgrade_from_shadow(self):
        manager = TierManager()
        trust = TrustScore(
            agent_id="a", current_tier=AutonTier.SHADOW,
            recommended_tier=AutonTier.GATED,
            weighted_score=0.6, correctness=0.5, safety=0.7,
            cost_stability=30.0, episodes_evaluated=5,
        )
        assert manager.can_upgrade(AutonTier.SHADOW, trust)

    def test_cannot_upgrade_without_episodes(self):
        manager = TierManager()
        trust = TrustScore(
            agent_id="a", current_tier=AutonTier.SHADOW,
            recommended_tier=AutonTier.SHADOW,
            weighted_score=0.9, correctness=0.9, safety=0.99,
            cost_stability=5.0, episodes_evaluated=0,
        )
        assert not manager.can_upgrade(AutonTier.SHADOW, trust)

    def test_should_downgrade_poor_scores(self):
        manager = TierManager()
        trust = TrustScore(
            agent_id="a", current_tier=AutonTier.SUPERVISED,
            recommended_tier=AutonTier.SHADOW,
            weighted_score=0.3, correctness=0.2, safety=0.4,
            cost_stability=80.0, episodes_evaluated=5,
        )
        assert manager.should_downgrade(AutonTier.SUPERVISED, trust)

    def test_get_next_tier(self):
        manager = TierManager()
        assert manager.get_next_tier(AutonTier.SHADOW) == AutonTier.GATED
        assert manager.get_next_tier(AutonTier.GATED) == AutonTier.SUPERVISED
        assert manager.get_next_tier(AutonTier.AUTONOMOUS) is None
