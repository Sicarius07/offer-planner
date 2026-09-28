# Glossary

A quick reference for the ad-tech terms used in this exercise. If you've worked in ad-tech, you can skip this. If you haven't, this should be enough to do the exercise without learning a whole industry. These are the basics, kept practical.

## The core players

**Advertiser**
A business that wants to pay to put their product or message in front of people. In this exercise, the advertiser is the *user*. They describe their business and your system helps them set up a campaign. Examples: a dog food brand, a meditation app, a sustainable activewear company.

**Publisher**
A business that has an audience and sells access to that audience. Could be a website, a newsletter, a retailer's checkout page, a streaming service, anywhere ads can show up. In this exercise, publishers are pre-defined in `publishers.json` and your system picks which ones an advertiser should run on.

**Audience / Shopper Persona**
A description of a type of person who might see an ad. Real ad systems segment audiences by demographics, behavior, interests, and intent. In this exercise, we've simplified this into 10 hand-written personas in `shopper_personas.json`. Think of them as the kinds of people who shop on the publishers in the catalog.

## What gets created

**Campaign**
The whole package an advertiser sets up to run ads. A campaign typically includes: who it's for (targeting), where it should run (publishers / placements), how much they'll spend (budget), how aggressively they'll bid, and the actual ads themselves (creative).

**Campaign Config**
The structured settings that define a campaign. Real systems have hundreds of fields. For this exercise, you decide what fields actually matter and design a sensible shape. Examples of fields you might include: target audience attributes, daily/total budget, suggested bid range, publisher allocation, geographic targeting.

**Creative**
The actual ad: the headline, body copy, and visuals that a shopper sees. In this exercise, you're generating *text* creative (headlines + body copy), not images. A "creative variant" is one version of an ad. Advertisers usually run multiple variants to test which performs best.

**Targeting**
The rules that decide who sees an ad. Could be demographic ("women 25 to 40"), interest-based ("people interested in fitness"), behavioral ("recent purchasers of pet food"), or contextual ("people on a wellness publisher"). For this exercise, targeting is mostly about matching the advertiser to publishers and personas where they'll resonate.

## How money flows (very simplified)

**Bid / Bid Strategy**
Advertisers compete for ad placements. A bid is what they're willing to pay for one impression or click. A bid strategy is how they decide that price (e.g., "bid the same amount every time," or "bid higher when the user looks like a high-converter"). For this exercise, you don't need to model real auction dynamics. Just suggest a sensible starting bid range and explain your reasoning.

**Budget**
How much the advertiser is willing to spend in total, or per day. Usually allocated across the publishers they're running on.

**CPM (Cost Per Mille)**
Cost per 1,000 ad impressions. The standard pricing unit in display advertising. If a publisher's CPM is $25, the advertiser pays $25 every time their ad is shown 1,000 times. You don't need to compute real CPMs. Just use it as a unit if it's helpful when you're suggesting budget allocation.

**CPC (Cost Per Click)**
Cost per click on an ad. Instead of paying for impressions, the advertiser pays only when someone actually clicks. Common in performance-focused campaigns where the advertiser wants to drive traffic to their site. Typical CPCs range from a few cents to several dollars depending on the audience and category.

**CPA (Cost Per Acquisition)**
Cost per conversion, i.e., what the advertiser pays for each actual purchase, signup, or other goal action driven by the ad. The most outcome-oriented pricing model. Advertisers care about CPA because it tells them whether the ads are profitable: if their CPA is $30 and their average order value is $80, the math works.

**AOV (Average Order Value)**
How much, on average, a shopper on a publisher spends per purchase. Useful for advertisers because it tells them whether their product economics make sense for a given audience. The publisher catalog includes this. You may or may not find it useful in your reasoning.

## What this exercise is asking for, in plain language

You're building the brain of an ad system: an advertiser tells you what they sell, and your system figures out *where* their ads should run, *who* the ads should speak to, and *what those ads should say*. The output is a draft campaign that a human (or downstream system) could review and launch.

The hard parts are:

- **Matching well.** Not every advertiser fits every publisher. A premium dog food brand probably belongs on a pet-focused publisher, not on a meditation app. Some matches are obvious; some are subtle.
- **Writing creative that actually fits the audience.** Generic ad copy is everywhere. Your system should generate copy that feels written *for* a specific persona, not pasted in from a template.
- **Handling messy input.** Real advertisers don't always describe their business clearly. Your system should do something reasonable when the input is vague, off-topic, or low-signal.
- **Showing your work.** Black-box recommendations are hard to trust. The advertiser should be able to see *why* your system made the calls it did.
