# Reasoning about consumer lag

Lag = log-end offset − committed offset, summed over partitions. It is the single most
useful messaging signal, but it only tells you *that* consumption is behind, not *why*.
Combine it with two more numbers to tell the stories apart.

## The decision table

| Lag trend | Members | Produce rate | Story | Who fixes it |
| --- | --- | --- | --- | --- |
| growing at ≈ produce rate | 0 | normal | consumer is gone | consumer owner (member portal) |
| growing slower than produce rate | ≥ 1 | normal | consumer too slow | consumer owner; maybe partitions |
| saw-tooth | oscillating | normal | rebalance storm | consumer owner |
| flat and high | 0 | 0 | producers also stopped; broker? | messaging platform if broker down |
| flat and low | ≥ 1 | normal | healthy | nobody |
| falling | ≥ 1 | normal | recovering after a fix | nobody; report ETA |
| any | any | 0 with publish errors | broker/topic problem | messaging platform |

## Dating the incident

1. `query_prometheus_range` on members over 30 minutes: the sample where it hits 0.
2. `query_prometheus_range` on lag: the sample where growth begins.
3. These should coincide within one scrape (15 s). Quote the timestamp as the start.

## Blast radius

`member.events` feeds downstream processing (notifications, analytics in a real
enterprise; here, the portal-consumer's counters). Consumption stalling means those are
delayed, not lost — Kafka retains the messages. State this explicitly so responders
don't escalate a delay into a data-loss incident. The portal's synchronous API does not
wait on consumption, so lag never explains API errors.

## Wording for the human

- "Consumer outage, broker healthy" when members are 0 and producers fine.
- "Messaging platform outage" only when the broker or topic is actually unavailable.
- Give the drain estimate; responders want to know when it will be caught up.
