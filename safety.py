import re
from groq import Groq
from config import GROQ_API_KEY, LLM_MODEL, VALID_TIERS

_client = Groq(api_key=GROQ_API_KEY)


# ---------------------------------------------------------------------------
# Prompt (see specs/classifier-spec.md for the design rationale)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a home-repair safety classifier. Your only job is to assign one safety tier to a home-repair question. You do not answer the question or give repair instructions. You classify it.

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

Do not add markdown, quotes, bullet points, or any other text."""


def _user_message(question: str) -> str:
    return (
        "Classify the following home-repair question.\n\n"
        "Apply the decision rule and the critical rules. Decide the reason first, "
        "then the tier. Respond with exactly the two lines specified.\n\n"
        f"Question: {question}"
    )


# Contrastive few-shot turns. The first two are the load-bearing
# replace-vs-add pair; #3 inoculates against the "tiny job" framing trap; #4
# anchors the safe/caution side so routine plumbing is not over-refused.
_FEW_SHOT = [
    (
        "Can I replace an electrical outlet that stopped working?",
        "Reason: Swapping an existing outlet at the same location on the existing circuit is a like-for-like component swap whose worst case is a tripped breaker, not fire.\nTier: caution",
    ),
    (
        "Can I add a new electrical outlet to my garage?",
        "Reason: Adding a new outlet requires running new wire from the panel and a permit, and an amateur mistake is a latent fire hazard.\nTier: refuse",
    ),
    (
        "I just want to move my light switch six inches to the left.",
        "Reason: Relocating a switch requires running new wire, which is new-circuit work with a latent fire risk, regardless of the small framing.\nTier: refuse",
    ),
    (
        "How do I replace a bathroom faucet?",
        "Reason: Replacing a faucet is a like-for-like fixture swap on existing supply lines whose worst case is a recoverable leak.\nTier: caution",
    ),
]


def _build_messages(question: str) -> list[dict]:
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for ex_q, ex_a in _FEW_SHOT:
        messages.append({"role": "user", "content": _user_message(ex_q)})
        messages.append({"role": "assistant", "content": ex_a})
    messages.append({"role": "user", "content": _user_message(question)})
    return messages


# ---------------------------------------------------------------------------
# Parsing (tolerant of capitalization, markdown, quotes, and code fences)
# ---------------------------------------------------------------------------

_TIER_VARIANTS = {
    "safe": "safe",
    "safely": "safe",
    "caution": "caution",
    "cautious": "caution",
    "cautionary": "caution",
    "refuse": "refuse",
    "refused": "refuse",
    "refusal": "refuse",
}

# Priority order for the keyword fallback: most restrictive wins, so a response
# that mentions two tiers resolves to the safer one.
_TIER_PRIORITY = ["refuse", "caution", "safe"]


def _normalize_tier(raw: str) -> str:
    """Lowercase, strip wrappers, take the first word, and map common variants."""
    token = raw.strip().strip("*`\"'").strip()
    token = re.split(r"[\s,.:;]+", token.lower(), maxsplit=1)[0]
    return _TIER_VARIANTS.get(token, token)


def _parse_tier_and_reason(text: str) -> tuple[str, str]:
    """Extract (tier, reason) from the raw LLM response. Tier is NOT yet
    validated against VALID_TIERS; classify_safety_tier() does that."""
    # Drop any surrounding code fence lines the model may have added.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("```")]

    tier = ""
    reason = ""
    for ln in lines:
        low = ln.lower()
        m = re.match(r"^[>*\-\s]*tier\s*[:\-]\s*(.+)$", low)
        if m and not tier:
            tier = _normalize_tier(ln.split(":", 1)[1] if ":" in ln else ln.split("-", 1)[1])
        if low.startswith("reason") and not reason:
            after = re.split(r"[:\-]", ln, maxsplit=1)
            if len(after) > 1:
                reason = after[1].strip().strip("*`\"'").strip()

    # Keyword fallback: no clean "Tier:" line, so scan the whole text by priority.
    if tier not in VALID_TIERS:
        haystack = text.lower()
        for candidate in _TIER_PRIORITY:
            if re.search(rf"\b{candidate}\b", haystack):
                tier = candidate
                break

    if not reason:
        # Use the first line that is not the tier line as a best-effort reason.
        non_tier = [ln for ln in lines if not ln.lower().startswith("tier")]
        reason = non_tier[0] if non_tier else text.strip()

    return tier, reason


def classify_safety_tier(question: str) -> dict:
    """
    Classify a home repair question into one of three safety tiers.

    LLM-as-judge classifier (see specs/classifier-spec.md). Sends one Groq chat
    completion built from a tier-definition system prompt plus a contrastive
    few-shot set, parses two labeled lines (Reason / Tier) tolerantly, validates
    the tier against VALID_TIERS, and fails closed to "caution" on any error or
    unparseable output.

    Returns a dict with:
      - "tier"   : str — one of "safe", "caution", "refuse"
      - "reason" : str — a brief explanation of why this tier was assigned
    """
    fallback = {
        "tier": "caution",
        "reason": "Could not reliably classify this question; defaulting to caution as a safety precaution.",
    }

    try:
        response = _client.chat.completions.create(
            model=LLM_MODEL,
            messages=_build_messages(question),
            temperature=0,
            max_tokens=250,
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            return fallback

        tier, reason = _parse_tier_and_reason(text)
        if tier not in VALID_TIERS:
            return fallback

        return {"tier": tier, "reason": reason or fallback["reason"]}

    except Exception:
        return fallback
