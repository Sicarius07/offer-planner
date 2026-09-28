---
name: enrich_persona
version: 1
stage: enrich
description: OFFLINE, run once per catalog change. Map a shopper persona's free-text affinities and dislikes onto our controlled vocabulary.
---

# System

You are mapping a shopper persona onto a controlled vocabulary so a scoring model can compare it with advertisers. Use only these tags, each with a strength: `strong`, `moderate` or `light`.

Interests (from category_affinities and description):
{{interests}}

Values (from messaging_preferences):
{{values}}

Occasions:
{{occasions}}

`price_tiers`: which of value, mid, premium, luxury this persona realistically buys, from price_sensitivity and typical_aov_usd.

`dislikes`: map `disinterested_in` onto these positioning traits (only clear matches):
{{positioning}}

# User

<persona>
{{record}}
</persona>
