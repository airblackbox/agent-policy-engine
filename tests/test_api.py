"""Tests for PE-7: Policy API."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from pkg.api.routes import create_app, _policies, _profiles


@pytest.fixture
async def client():
    app = create_app()
    _policies.clear()
    _profiles.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health(self, client):
        resp = await client.get("/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "agent-policy-engine"


class TestPolicyCRUD:
    @pytest.mark.asyncio
    async def test_create_and_list(self, client):
        resp = await client.post("/v1/policies", json={
            "name": "test-policy",
            "autonomy_tier": "gated",
        })
        assert resp.status_code == 200
        policy_id = resp.json()["policy_id"]

        resp = await client.get("/v1/policies")
        assert len(resp.json()) == 1

        resp = await client.get(f"/v1/policies/{policy_id}")
        assert resp.json()["name"] == "test-policy"

    @pytest.mark.asyncio
    async def test_delete_policy(self, client):
        resp = await client.post("/v1/policies", json={"name": "to-delete"})
        pid = resp.json()["policy_id"]
        resp = await client.delete(f"/v1/policies/{pid}")
        assert resp.json()["deleted"] == pid
        resp = await client.get("/v1/policies")
        assert len(resp.json()) == 0

    @pytest.mark.asyncio
    async def test_get_not_found(self, client):
        resp = await client.get("/v1/policies/fake-id")
        assert resp.status_code == 404


class TestEvaluation:
    @pytest.mark.asyncio
    async def test_evaluate_action(self, client):
        await client.post("/v1/policies", json={
            "name": "eval-test",
            "autonomy_tier": "autonomous",
        })
        resp = await client.post("/v1/evaluate", json={
            "agent_id": "test-agent",
            "action_context": {"tool_name": "web_search", "step_type": "llm_call"},
        })
        assert resp.status_code == 200
        assert "action" in resp.json()


class TestTiers:
    @pytest.mark.asyncio
    async def test_list_tiers(self, client):
        resp = await client.get("/v1/tiers")
        assert resp.status_code == 200
        data = resp.json()
        assert "shadow" in data
        assert "autonomous" in data
