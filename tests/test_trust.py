"""Tests for PE-5: Trust scorer."""

from __future__ import annotations

import pytest

from pkg.models.policy import AutonTier
from pkg.trust.scorer import TrustScorer


class TestTrustScorer:
    def test_compute_from_good_data(self, sample_episodes):
        scorer = TrustScorer()
        trust = scorer.compute_trust_from_data("test-agent", sample_episodes)
        assert trust.agent_id == "test-agent"
        assert trust.episodes_evaluated == 20
        assert trust.correctness > 0.5
        assert trust.safety > 0.5
        assert trust.weighted_score > 0.0

    def test_empty_episodes_returns_shadow(self):
        scorer = TrustScorer()
        trust = scorer.compute_trust_from_data("new-agent", [])
        assert trust.recommended_tier == AutonTier.SHADOW
        assert trust.episodes_evaluated == 0

    def test_all_success_high_score(self):
        episodes = [
            {
                "episode_id": f"ep-{i}", "agent_id": "a",
                "status": "success",
                "steps": [{"step_index": 0, "step_type": "llm_call"}],
                "total_cost_usd": 0.004,
            }
            for i in range(30)
        ]
        scorer = TrustScorer()
        trust = scorer.compute_trust_from_data("a", episodes)
        assert trust.correctness == 1.0
        assert trust.safety == 1.0
        assert trust.weighted_score > 0.8

    def test_all_failures_low_score(self):
        episodes = [
            {
                "episode_id": f"ep-{i}", "agent_id": "a",
                "status": "failure",
                "steps": [{"step_index": 0, "step_type": "error"}],
                "total_cost_usd": 0.001,
            }
            for i in range(10)
        ]
        scorer = TrustScorer()
        trust = scorer.compute_trust_from_data("a", episodes)
        assert trust.correctness == 0.0
        assert trust.safety == 0.0
        assert trust.recommended_tier == AutonTier.SHADOW

    def test_cost_stability(self):
        scorer = TrustScorer()
        # Stable costs
        stable = scorer._compute_cost_stability([0.004, 0.004, 0.004, 0.004])
        assert stable < 1.0
        # Volatile costs
        volatile = scorer._compute_cost_stability([0.001, 0.1, 0.001, 0.1])
        assert volatile > 50.0
