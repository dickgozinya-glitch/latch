# LATCH

Independent permission layer for agents that spend, hire, and ship.

Production is cheap. Permission is scarce. This repo is the gate.

```
pip-free:  python3 server.py
then:      python3 examples/spend_agent.py
```

## What this is

An agent is about to move money. Latch answers **allow / deny / escalate**, then issues a **Seal** — a signed artifact a human can forward in Slack when something breaks.

The model does not vote. Policy is deterministic.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/mandates` | Principal issues a scoped writ |
| GET | `/v1/mandates/{id}` | Read a mandate |
| POST | `/v1/decisions` | Pre-action check. Returns Seal. |
| GET | `/v1/seals/{id}` | Fetch a Seal |
| POST | `/v1/seals/{id}/verify` | Verify signature + replay the decision |
| GET | `/v1/meter` | Usage counts for invoicing |

## First dollar

Invoice a monthly floor the week the first decision fires. See `sales/`.

Do not wait for rails, wallets, or a protocol committee.
