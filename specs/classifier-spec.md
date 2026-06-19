# Spec: `classify_safety_tier()`

**File:** `safety.py`
**Status:** Spec incomplete — fill in all blank fields before implementing

---

## Purpose

Determine whether a home repair question is safe to answer directly, requires a cautionary response, or should be refused with a referral to a licensed professional.

---

## Input / Output Contract

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `question` | `str` | The user's home repair question |

**Output:** `dict`

| Key | Type | Description |
|-----|------|-------------|
| `"tier"` | `str` | One of: `"safe"`, `"caution"`, `"refuse"` |
| `"reason"` | `str` | One sentence explaining why this tier was assigned |

---

## Design Decisions

*Complete the fields below before writing any code. Use your AI tool in Plan or Ask mode to help you reason through what belongs here — but the decisions are yours.*

---

### Tier definitions

*Write a one-sentence definition for each tier that is precise enough to use as part of your classification prompt. Vague definitions produce inconsistent classifications.*

**safe:**
```
A routine, low-risk repair a typical homeowner can do with basic tools, no permit, and no licensed professional, where the worst realistic outcome if it goes wrong is cosmetic damage or a broken fixture, never fire, flooding, structural failure, injury, or death.
```

**caution:**
```
A repair a motivated homeowner can do as a like-for-like swap or fix at an existing location, typically without a permit, that touches a water or electrical system, where a mistake has real cost or mild injury risk but the worst realistic outcome is recoverable, such as a leak, a tripped breaker, or a damaged fixture.
```

**refuse:**
```
A repair where an amateur mistake can cause fire, flooding, structural failure, serious injury, or death, or where code requires a licensed professional and a permit, including all electrical panel or service work, adding any new outlet, switch, or circuit, any gas work or gas smell, modifying a wall not confirmed non-load-bearing, replacing the main water shutoff, replacing a water heater, and running new plumbing lines.
```

---

### Classification approach

*How will the LLM classify the question? Will you give it just the tier definitions, or also examples (few-shot)? Will you ask it to reason step-by-step before naming the tier, or output the tier directly?*

*Consider: what happens when a question is genuinely ambiguous — e.g., "can I replace my own outlets?" Which tier should that land in, and how does your approach handle questions at the boundary?*

```
Hybrid approach: tier definitions, plus a small contrastive few-shot set, plus a reason-before-tier output order.

I tested all three options in my head against the hardest graded case (replace an outlet vs add an outlet). Definitions alone are not enough, because "replace an outlet" and "add an outlet" share surface words and the model tends to lump all "outlet" questions into one tier. Few-shot examples fix this by teaching the discriminator (existing circuit vs new wire run) instead of just the label. Asking the model to state its reason before the tier forces it to surface "this requires running new wire" before it commits, which is what defeats the "it's just a tiny job" framing trap.

So the prompt gives the definitions and the decision rule, then four few-shot turns (replace-outlet -> caution, add-outlet -> refuse, move-switch-six-inches -> refuse, replace-faucet -> caution), then the real question. The two electrical shots are the load-bearing pair; the move-switch shot inoculates against framing; the faucet shot anchors the caution side so the model does not over-refuse routine plumbing.

For a genuinely ambiguous question like "can I replace my own outlets?", the prompt has an explicit tie-break rule: when unsure, choose the more restrictive tier (refuse over caution, caution over safe). "Replace" with no "add/new" signal reads as a like-for-like swap, so it lands in caution; if the model is unsure whether new wiring is implied, the tie-break keeps it from drifting down to safe.
```

---

### Output format

*How will the LLM communicate the tier and reason back to you? Describe the exact text format you'll ask it to use, so you can parse it reliably.*

*The format you used in Lab 3 (`Label: X / Reasoning: Y`) is a reasonable starting point, but you're not required to use it. Whatever you choose, you'll need to parse it in code — so consider how much variation the LLM might introduce and how you'll handle that.*

```
Two labeled lines, reason first:

Reason: <one sentence naming the worst-case consequence and whether this is a like-for-like swap or new-wire, permit, or structural work>
Tier: <safe or caution or refuse>

Reason comes first so the model commits to the consequence before it names a label. The tier sits on its own line as a single word, which gives the model the smallest possible surface to editorialize ("Tier: caution, but really..."). Parsing keys on the line prefixes, not on position, so if the model reorders the lines or adds a stray preamble the parser still finds the tier. This is the Lab 3 idiom (a labeled-line format with tolerant parsing), so the parsing code carries forward.
```

---

### Prompt structure

*Write the actual prompt you'll use — both the system message and the user message. Don't describe it — write it. Vague prompt descriptions produce vague prompts, which produce inconsistent classifications.*

**System message:**
```
You are a home-repair safety classifier. Your only job is to assign one safety tier to a home-repair question. You do not answer the question or give repair instructions. You classify it.

There are exactly three tiers:

safe: A routine, low-risk repair a typical homeowner can do with basic tools, no permit, and no licensed professional. If it goes wrong, the worst realistic outcome is cosmetic damage or a broken fixture, never fire, flooding, structural failure, injury, or death. Examples: patch a small drywall hole, paint, replace a bulb, plunge or hand-snake a drain, tighten hardware, replace weatherstripping, change an HVAC filter, replace a toilet seat, cosmetic re-caulk.

caution: A repair a motivated homeowner can do as a like-for-like swap or fix at an EXISTING location, typically without a permit, that touches a water or electrical system. A mistake has real cost or mild injury risk, but the worst realistic outcome is recoverable: a leak, a tripped breaker, or a damaged fixture. Examples: replace a faucet, replace a toilet or flapper, reset or replace a GFCI outlet at the same location like-for-like, replace an EXISTING outlet, switch, light fixture, or ceiling fan at the same location, install a smart thermostat replacing an existing one, patch a large drywall hole, re-grout tile, replace a showerhead.

refuse: A repair where an amateur mistake can cause fire, flooding, structural failure, serious injury, or death, OR where code requires a licensed professional and a permit. Examples: ANY electrical panel or service-entrance work, ADDING a new outlet, switch, circuit, or wiring anywhere, ANY gas line work or a gas smell, removing or modifying any wall not already confirmed non-load-bearing by an engineer, replacing the main water shutoff valve, replacing a water heater, running new plumbing lines, foundation work, structural roof work.

THE DECISION RULE (apply this first, every time):
Ask: "If this repair goes wrong, can it cause fire, flooding, structural failure, injury, or death?"
- If YES, the tier is refuse.
- If the worst case is a leak, a tripped breaker, or a broken fixture, the tier is caution.
- If the worst case is only cosmetic damage, the tier is safe.

CRITICAL RULES (these override surface impressions):

1. REPLACING EXISTING vs ADDING NEW (electrical). Replacing an outlet, switch, light fixture, or ceiling fan at the SAME location on the EXISTING circuit is caution. It is a component swap, no new wire, worst case a tripped breaker. ADDING a new outlet, switch, or circuit ANYWHERE is refuse. It requires running new wire from the panel, opening the panel, and a permit, and an amateur mistake is a latent fire hazard. The words "add," "new," "extend," "run," or "another" push electrical work to refuse.

2. FRAMING DOES NOT CHANGE THE TIER. Classify by what the work ACTUALLY requires, not how the user describes it. "I just want to move my switch six inches" is refuse, because moving it requires running new wire. Phrases like "it's a tiny job," "just a small fix," or "only takes a minute" never lower the tier.

3. GAS IS ALWAYS refuse. Any gas line, gas appliance connect or disconnect, or any mention of a gas smell or suspected leak is refuse, with no exceptions.

4. WALLS. Any question about removing or modifying a wall is refuse unless the user explicitly states the wall has ALREADY been confirmed non-load-bearing by a structural engineer.

5. WATER HEATERS. Replacing a water heater is refuse (permit plus pressure-relief-valve explosion risk). Only a clearly minor component, an anode rod or heating element, may be caution.

When a question is genuinely ambiguous or you are unsure, choose the MORE restrictive tier (prefer refuse over caution, and caution over safe). It is safer to over-warn than to under-warn.

OUTPUT FORMAT. Respond with EXACTLY two lines and nothing else:
Reason: <one sentence that names the worst-case consequence and whether this is a like-for-like swap or new-wire, permit, or structural work>
Tier: <safe or caution or refuse>

Do not add markdown, quotes, bullet points, or any other text.
```

*Plus four few-shot turns inserted between the system message and the real question (each a user turn with "Question: ..." and an assistant turn with the two-line answer):*
```
1. "Can I replace an electrical outlet that stopped working?"  -> Tier: caution
2. "Can I add a new electrical outlet to my garage?"           -> Tier: refuse
3. "I just want to move my light switch six inches to the left." -> Tier: refuse
4. "How do I replace a bathroom faucet?"                       -> Tier: caution
```

**User message:**
```
Classify the following home-repair question.

Apply the decision rule and the critical rules. Decide the reason first, then the tier. Respond with exactly the two lines specified.

Question: {question}
```

---

### Caution/refuse boundary

*The most consequential classification decision is whether a question lands in "caution" or "refuse." Write down your rule for this boundary — one sentence. Then give two examples of questions that sit close to the line and explain which side they fall on and why.*

```
Rule: A repair is caution if the worst realistic failure is recoverable (a leak, a tripped breaker, a damaged fixture) and it is a like-for-like swap at an existing location with no permit; it is refuse the moment failure can cause fire, flooding, structural failure, injury, or death, or the work requires new wiring, new plumbing, a permit, or a licensed professional.

Example 1: "Can I replace the GFCI outlet in my bathroom, same spot, same wires?" -> caution. This is a like-for-like swap on the existing circuit. The worst case is a non-working outlet or a tripped breaker, which stays on the recoverable side of the rule.

Example 2: "Can I replace my water heater's gas control valve myself?" -> refuse. It reads like a minor-component swap (an anode rod or element would be caution), but it is gas plus pressure-system work, where failure risks fire or explosion. Both the gas-always-refuse rule and the consequence rule push it over the line.
```

---

### Fallback behavior

*What does your function return if the LLM response can't be parsed — e.g., if it produces free-form prose instead of your expected format? What happens when tier validation against `VALID_TIERS` fails?*

*Note: failing open (returning "safe" as a fallback) is more dangerous than failing closed (returning "caution"). Which makes more sense here, and why?*

```
On any of these conditions the function returns {"tier": "caution", "reason": "Could not reliably classify this question; defaulting to caution as a safety precaution."}:
- the API call raises (network, rate limit, no choices),
- the response content is empty or None,
- no tier line can be parsed and the keyword fallback finds nothing,
- the parsed value is not in VALID_TIERS.

The function never raises; it always returns the dict, so the pipeline cannot be crashed by one bad response.

Failing closed to caution rather than open to safe is the right call here. If a parse bug silently returned safe, the responder would hand a user confident step-by-step instructions for a repair that was never actually classified, which is the exact failure the safety layer exists to prevent. Caution rather than refuse is the calibrated choice for the fallback: refuse would block a routine drywall question every time the API hiccuped, hurting usability with no safety gain, while caution still attaches a warning and routes to the guarded responder path.
```

---

## Implementation Notes

*Fill this in after implementing, before moving to Milestone 2.*

**One classification that surprised you — question, tier you expected, tier it returned, and why:**

```
Question: "How do I reset a GFCI outlet that won't reset?"
Expected: caution. Returned: caution.

What surprised me was that it held at caution rather than drifting up to refuse. The phrase "won't reset" hints that something deeper might be wrong with the circuit, and my prompt has a tie-break that pushes anything ambiguous toward the more restrictive tier, so I half-expected it to over-refuse. Instead the model correctly read this as a same-location reset operation whose worst case is a tripped breaker, which is exactly the caution definition. The explicit GFCI example in the caution list is what kept it pinned to the right side.
```

**One prompt change you made after seeing the first few outputs, and what it fixed:**

```
The change that mattered was made deliberately before the first full run, because I expected the failure: a definitions-only prompt treats "replace an outlet" and "add an outlet" the same way, since they share the word "outlet." I added two things to separate them: an explicit rule that the words "add," "new," "extend," "run," or "another" push electrical work to refuse, and a contrastive few-shot pair (replace-outlet -> caution, add-outlet -> refuse) so the model learns the discriminator (existing circuit vs new wire run) rather than the surface word.

On the first full run this produced 8/8 correct on the example set, with the two critical questions landing on opposite tiers (caution vs refuse), so no post-run correction to the prompt was needed.
```
