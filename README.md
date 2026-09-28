# Take-Home Exercise: Ad Placement & Creative Generation

Hey, thanks for making it this far. Here's the exercise.

## The problem

Build a working prototype where an advertiser describes their business in a sentence or two (something like *"We sell premium dog food for senior dogs, targeting owners who care about joint health"*), and the system produces:

1. **A ranked list of recommended publishers** from the provided catalog, with reasoning. Show *why* each publisher is a fit, and ideally, why some publishers in the catalog were *excluded*.

2. **3 to 5 ad creative variants** (headline + body copy), each tuned for a different shopper persona that the system thinks is plausible for this advertiser. Make the persona reasoning visible to the user.

3. **A structured campaign config**: targeting attributes, suggested budget allocation across recommended publishers, bid strategy, whatever fields you think a real ad system would need to actually run this. Make your own call on the shape of it and justify it in the README.

We've given you a small mock data pack in `data/`:

- `publishers.json`: ~20 publishers across categories (apparel, wellness, pet, home, etc.) with audience demographics, AOV, and qualitative notes
- `shopper_personas.json`: 10 personas with category affinities, messaging preferences, and what they're disinterested in
- `example_advertisers.txt`: sample advertiser one-liners ranging from clear to deliberately ambiguous

If you don't have ad-tech background, see `GLOSSARY.md`. It covers everything you need (advertiser, publisher, campaign config, CPM, creative, targeting, etc.). The JD specifically says we're not looking for someone who grew up in ad-tech, so don't worry if these terms are new to you.

Use whatever LLM, framework, or stack you want. We don't care if it's Next.js or Streamlit or a CLI with a tiny web front-end glued on. We care that we can click through it and see it work.

## Ground rules

- **Time budget: aim for 6 to 8 hours over a few days.** We would much rather see a tight, working thing than a sprawling half-finished one.
- **Use AI tools.** Claude Code, Cursor, whatever you live in. We're not testing whether you can type code from scratch. We're testing whether you can direct these tools to ship something real and understand every line that comes out. We will ask you about the code in the follow-up.
- **No decks. No Figma. No Loom walkthroughs.** Build the thing.

## What to submit

1. **A working demo**, either hosted (Vercel, Render, Railway, wherever) or runnable locally with clear instructions. If local, a single `npm install && npm run dev` or equivalent.
2. **The code**, in a GitHub repo (public or shared with us).
3. **Your prompts**, in a `prompts/` directory in the repo. Every prompt your system uses, in whatever structure makes sense to you.
4. **A one-page README** covering:
   - What you built and how to run it
   - What you would do next if you had another week
   - What you intentionally cut and why
   - Which parts of this problem you think are genuinely hard vs. which are easy, and where you think the interesting engineering work actually lives

Keep the README to one page. If it spills onto a second, cut something.

## What we'll do with this

Our engineering team will read the code and run the demo. If it clears that bar, we'll invite you to a 90-minute follow-up where we go deep. You walk us through the demo, we ask about your technical choices, we'll have you make a live change to the code, and we'll talk about how you'd take this from prototype to production at meaningful scale.

Good luck. Have fun with it.

The Disco team
