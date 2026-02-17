# agent-policy-engine

A production-ready policy engine for risk-tiered autonomy control in AI agents. Dynamically manages agent capability levels (Shadow → Gated → Supervised → Autonomous) based on demonstrated competence, enforces tool-level restrictions, and kills execution when limits are exceeded.

## Overview

The agent-policy-engine sits between an AI agent and its execution environment, making real-time decisions about what actions are allowed. Policies are risk-based: agents start in Shadow mode (observe-only), earn autonomy through successful evaluations, and can be downgraded immediately if they exceed cost or error thresholds.

**Key features:**

- **Autonomy tiers**: Progressive trust levels with eval-driven tier advancement
- **Runtime policy engine**: Millisecond-fast action evaluation before tool calls
- **Tool risk classification**: CRITICAL/MEDIUM/LOW risk tools with approval requirements
- **Kill switches**: Hard limits on spend, tokens, errors, tool calls—with pause/halt actions
- **Trust scoring**: Converts eval harness episodes into actionable tier recommendations
- **Condition-based rules**: Field operators (gt, lt, eq, regex) for custom policies
- **REST API + CLI**: Full CRUD management and per-agent decision introspection

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         AI Agent                                 │
│                  (reasoning, planning, acting)                   │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     │ action_context
                     │ {tool_name, cost, step_type, ...}
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│           PolicyEnforcer (PE-6: Middleware)                      │
│  ┌─────────────────┐  ┌────────────────────┐                    │
│  │ Kill Switches   │  │ Policy Evaluator   │                    │
│  │ (PE-4)          │  │ (PE-2)             │                    │
│  └─────────────────┘  └────────────────────┘                    │
│           │                      │                              │
│           └─────────┬────────────┘                              │
│                     ▼                                           │
│         allow / deny / escalate / log                           │
└────────────────────┬────────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
   Allow → Tool Call         Deny/Escalate → Human Review
   
┌─────────────────────────────────────────────────────────────────┐
│              Policy Engine Backend                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Policies     │  │ Agent        │  │ Kill Limits  │           │
│  │ (PE-1)       │  │ Profiles     │  │ Monitors     │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Tier Mgmt    │  │ Trust Scorer │  │ REST API     │           │
│  │ (PE-3)       │  │ (PE-5)       │  │ (PE-7)       │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
  Episode Store              eval-harness
  (eval results)             (run evals)
```

## Quick Start

### Install

```bash
pip install -e /Users/jasonshotwell/Desktop/agent-policy-engine
```

### Run the server

```bash
python -m app.server
# Server running on http://0.0.0.0:8200
```

### Create a policy via CLI

```bash
# Show available tiers
agent-policy tiers

# Create a gated policy file
cat > policy.json << 'EOF'
{
  "name": "production-policy",
  "autonomy_tier": "gated",
  "tool_risks": [
    {"tool_name": "db_delete", "risk_tier": "critical"},
    {"tool_name": "send_email", "risk_tier": "medium", "requires_approval": true}
  ],
  "kill_switches": [
    {"limit_type": "spend_usd", "threshold": 1.0, "action": "halt"},
    {"limit_type": "total_tokens", "threshold": 100000, "action": "pause"}
  ]
}
EOF

# Load and validate
agent-policy load policy.json

# Check if an action is allowed
agent-policy check --agent-id myagent --tool db_delete

# Get trust score (requires eval store)
agent-policy trust --agent-id myagent --store-url http://localhost:8100
```

## API Reference

All endpoints return JSON. Base path: `/v1`

### Health

```
GET /v1/health
```

Returns service status and policy/agent counts.

### Policies (CRUD)

```
POST   /v1/policies                   Create policy
GET    /v1/policies                   List all policies
GET    /v1/policies/{policy_id}       Get single policy
DELETE /v1/policies/{policy_id}       Delete policy
```

**Create policy request:**

```json
{
  "name": "production-policy",
  "description": "Policy for prod agents",
  "agent_id": null,
  "autonomy_tier": "gated",
  "tool_risks": [
    {
      "tool_name": "db_delete",
      "risk_tier": "critical",
      "requires_approval": false
    }
  ],
  "kill_switches": [
    {
      "limit_type": "spend_usd",
      "threshold": 10.0,
      "action": "halt",
      "enabled": true
    }
  ],
  "default_action": "deny"
}
```

### Enforcement

```
POST /v1/evaluate
```

Evaluate an action against all applicable policies.

**Request:**

```json
{
  "agent_id": "myagent",
  "action_context": {
    "tool_name": "db_delete",
    "step_type": "tool_call",
    "cost_usd": 0.12
  }
}
```

**Response:**

```json
{
  "allowed": false,
  "action": "deny",
  "reason": "Tool db_delete has risk tier CRITICAL in GATED mode",
  "decisions": [
    {
      "action": "deny",
      "reason": "Tool db_delete has risk tier CRITICAL in GATED mode",
      "policy": "production-policy"
    }
  ]
}
```

### Metrics & Monitoring

```
POST /v1/metrics
```

Update kill switch counters after each step.

**Request:**

```json
{
  "agent_id": "myagent",
  "metrics": {
    "spend_usd": 0.45,
    "total_tokens": 2500,
    "tool_calls": 3,
    "errors": 0
  }
}
```

### Agent Profile & Headroom

```
GET /v1/agents/{agent_id}/profile
GET /v1/agents/{agent_id}/headroom
```

Get the runtime profile (policies, tier, limits) and remaining headroom for an agent.

**Headroom response:**

```json
{
  "spend_usd": {
    "threshold": 1.0,
    "current": 0.35,
    "remaining": 0.65,
    "pct_used": 35.0
  },
  "total_tokens": {
    "threshold": 100000,
    "current": 45000,
    "remaining": 55000,
    "pct_used": 45.0
  }
}
```

### Tiers

```
GET /v1/tiers
```

List autonomy tier definitions and requirements.

## Autonomy Tiers

| Tier | Score | Correctness | Safety | Cost Δ% | Episodes | Tools | Approval |
|------|-------|-------------|--------|---------|----------|-------|----------|
| **SHADOW** | — | — | — | — | 0+ | None | All |
| **GATED** | ≥0.50 | ≥0.40 | ≥0.50 | ≤50% | 5+ | LOW only | MEDIUM+ |
| **SUPERVISED** | ≥0.70 | ≥0.60 | ≥0.75 | ≤30% | 15+ | LOW, MEDIUM | CRITICAL |
| **AUTONOMOUS** | ≥0.85 | ≥0.80 | ≥0.90 | ≤15% | 30+ | All (escalate CRITICAL) | None |

**Definitions:**

- **Score**: Weighted average of correctness, safety, and cost stability
- **Correctness**: Fraction of episodes that succeeded
- **Safety**: Fraction of episodes without error steps
- **Cost Δ%**: Coefficient of variation in episode costs (0% = stable)
- **Episodes**: Minimum episodes evaluated to qualify
- **Tools**: Risk levels allowed without approval
- **Approval**: Risk levels requiring human escalation

## Tool Risk Tiers

| Tier | Examples | SHADOW | GATED | SUPERVISED | AUTONOMOUS |
|------|----------|--------|-------|------------|------------|
| **LOW** | web_search, web_scrape | Log | Allow | Allow | Allow |
| **MEDIUM** | send_email, update_calendar | Log | Escalate | Allow | Allow |
| **CRITICAL** | db_delete, aws_terminate | Log | Deny | Escalate | Escalate |

## Kill Switch Types

| Limit | Type | Threshold | Action | Use Case |
|-------|------|-----------|--------|----------|
| **spend_usd** | Cumulative USD | 0.01–100+ | halt/pause | Prevent cost overruns |
| **total_tokens** | Cumulative tokens | 1000–1M | halt/pause | Prevent runaway loops |
| **tool_calls** | Tool call count | 1–1000 | halt/pause | Limit batch operations |
| **errors** | Error step count | 1–100 | halt/pause | Stop failing agents |

**Actions:**

- **halt**: Immediately DENY all future actions (Action.DENY)
- **pause**: Escalate to human (Action.ESCALATE)

## CLI Commands

```bash
# Show tier requirements
agent-policy tiers

# Load and validate a policy JSON
agent-policy load path/to/policy.json

# Check if action is allowed
agent-policy check --agent-id <id> --tool <name> [--policy-file path.json]

# Compute trust score from eval store
agent-policy trust --agent-id <id> [--store-url http://localhost:8100]
```

## Integration Example

```python
from pkg.enforcement.middleware import PolicyEnforcer
from pkg.models.policy import AgentProfile, Policy, AutonTier

# Load agent profile (policies + limits)
policy = Policy(name="prod", autonomy_tier=AutonTier.GATED)
profile = AgentProfile(agent_id="myagent", policies=[policy])

# Create enforcer
enforcer = PolicyEnforcer(profile)

# Before each agent step
action_context = {
    "tool_name": "db_delete",
    "step_type": "tool_call",
    "cost_usd": 0.12,
}
result = enforcer.check_action(action_context)

if not result.allowed:
    print(f"BLOCKED: {result.reason}")
else:
    # Execute tool call
    tool_result = run_tool(action_context)

# After step completes, update metrics
enforcer.update_metrics({
    "spend_usd": 0.12,
    "total_tokens": 2500,
    "errors": 0,
})

# Check remaining headroom
headroom = enforcer.get_headroom()
print(f"Remaining spend: ${headroom['spend_usd']['remaining']:.2f}")
```

## Modules (PE-1 through PE-8)

- **PE-1** (`pkg/models/policy.py`): Core models — Policy, ToolRisk, KillSwitch, TrustScore, AgentProfile
- **PE-2** (`pkg/engine/evaluator.py`): Rule engine — PolicyEvaluator with tool risk checking, condition evaluation
- **PE-3** (`pkg/tiers/autonomy.py`): Tier manager — Tier advancement/downgrade based on trust scores
- **PE-4** (`pkg/limits/killswitch.py`): Kill switch monitor — Tracks limits and triggers halt/pause actions
- **PE-5** (`pkg/trust/scorer.py`): Trust scorer — Converts eval harness episodes into tier recommendations
- **PE-6** (`pkg/enforcement/middleware.py`): Runtime enforcement — PolicyEnforcer for pre-hook action checking
- **PE-7** (`pkg/api/routes.py`): FastAPI server — REST endpoints for policies, evaluation, monitoring
- **PE-8** (`cli/main.py`): CLI tool — Commands for tier lookup, policy validation, action checks, trust scoring

## Testing

Run all tests:

```bash
pytest tests/
pytest tests/test_evaluator.py -v
pytest tests/test_tiers.py -v
pytest tests/test_killswitch.py -v
pytest tests/test_trust.py -v
pytest tests/test_enforcement.py -v
pytest tests/test_api.py -v
```

## Roadmap

- [x] PE-1: Core models (Policy, ToolRisk, KillSwitch, Condition, AutonTier, TrustScore, AgentProfile)
- [x] PE-2: Policy evaluator (rule engine with tool risk & condition checking)
- [x] PE-3: Tier manager (tier advancement/downgrade)
- [x] PE-4: Kill switch monitor (hard limits enforcement)
- [x] PE-5: Trust scorer (eval harness integration)
- [x] PE-6: Runtime middleware (pre-hook enforcement)
- [x] PE-7: Policy API (FastAPI server with CRUD + evaluation)
- [x] PE-8: CLI tool (tier, load, check, trust commands)

Future enhancements:

- Database backend for policies and audit logs
- Audit trail and decision logging for compliance
- Tier auto-update on eval completion
- Webhook/callback for escalations
- Metrics dashboard (Prometheus + Grafana)
- Fine-grained RBAC for policy management
- Policy versioning and rollback
- Integration with external secret management (Vault, AWS Secrets)

## License

Apache-2.0
