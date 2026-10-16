# Consolidation rules

## 1. Sort the findings

| Finding | Goes to | Condition |
| --- | --- | --- |
| `implicated: true`, confidence ≥ 0.6 | `implicated` | |
| `implicated: true`, confidence < 0.6 | `implicated` but flagged "weak" in the verdict | only if no stronger finding explains the symptom; otherwise `cleared` with its headline |
| `implicated: false`, confidence ≥ 0.6 | `cleared` | |
| `implicated: false`, confidence < 0.6 (blind spot) | `not_consulted` | reason `agent reported a monitoring blind spot: <headline>` |
| tool error | `not_consulted` | reason `agent error: <short text>` |
| tool not visible | `not_consulted` | reason `caller lacks role domain:<x>` |

## 2. Check the evidence before trusting confidence

For each implicated finding count evidence items whose `source` or metric differs. One
item → cap confidence at 0.6. Two independent items → accept up to 0.9. Native tool plus
metric plus timeline → accept up to 0.95. If you lower a confidence, say so in the
verdict: "the cache agent reported 0.9 but cited a single signal; treated as 0.6".

## 3. Root cause vs consequence

When more than one domain is implicated:

1. Which finding's mechanism explains the *reported symptom* directly? (Black-holed route →
   503s: direct. Cache evictions → latency: indirect for a 503 question.)
2. Which started first? Compare the start times the agents quoted.
3. The direct, earlier finding is the root cause; list it first and make the next step
   about it. Mention the other as "likely consequence" or "independent degradation" in
   the verdict.

## 4. Writing the verdict

Template: "<Domain> is implicated with <confidence>: <mechanism in one clause>. <Other
domains> are healthy[; <domain> could not be consulted because <reason>]."

All clear: "All consulted domains (apim, cache, messaging) are healthy with confidence
≥ 0.85. The symptom is not explained by these platforms."

## 5. Writing the next step

- Exactly one imperative sentence.
- Names the object (change id, deployment, ConfigMap, namespace) and the verification
  that proves it worked.
- Is addressed to a human, never to an agent. Do not say "I will".
- All clear: name the next team or domain to engage ("Engage the member-portal
  application team; the portal's own 5xx rate is 12% while all platform domains are
  clean") or the missing visibility ("Grant the caller domain:messaging so the messaging
  agent can be consulted, or re-run as sre-lead").

## 6. Preserve the findings

`findings` contains every Finding object exactly as returned, so the console can show
the evidence and links. Do not summarise or edit them.
