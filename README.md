# persona-panel

A Claude Code skill that runs a **simulated customer panel of 100+ diverse personas** against a live website or an idea, and turns their reactions into a prioritised fix list. It's built to cost as little as possible: Python does the capture, sampling and counting, small Haiku agents play the personas in batches, and they run in waves rather than all at once.

## What it does

1. **Sample the panel.** `sample_personas.py` draws personas from weighted demographic distributions with coherence rules, covering age, city tier or region, income, device, network, language, payment habits, shopper type, trust, patience and accessibility needs. It guarantees every segment appears at least once. Distributions are sampled rather than invented by an LLM, because LLM-written personas collapse into the same upbeat, middle-of-the-road customer.
2. **Capture the site once** (site mode). `capture.py` crawls the pages a shopper would see and saves, for mobile and desktop:
   - screenshot slices;
   - a facts digest: load times on a throttled budget phone, trust signals, prices, missing alt text, tiny tap targets, console errors, popups.
3. **Brief the panel.** `prepare_briefs.py` writes one self-contained brief per batch of ~10 personas. Each brief holds the persona cards, the exact screens each persona would see given their entry point and patience, the digest, and the output schema.
4. **Run the agents.** Haiku agents role-play each batch in about 3 turns and write one JSON file. A few **live walkers** browse the real site through `walk.py`, a stateful headless Chrome CLI that also sees iframes and shadow-DOM cart drawers. Walkers go up to the first checkout screen and never enter personal data.
5. **Aggregate and synthesise.** `aggregate.py` computes outcomes and per-segment breakdowns. One synthesis agent clusters the issues into themes, and `report.py` renders a self-contained HTML report.

**Concept mode** skips the browser. Personas react to a written idea, pitch, pricing or mockup images.

## Install

```bash
git clone <this repo> "D:/OG Forge/persona-panel"
python "D:/OG Forge/persona-panel/skills/persona-panel/scripts/setup_env.py"   # venv + Playwright + Chromium
```

Then make the skill visible to Claude Code by linking it into your skills folder.

Windows:

```powershell
New-Item -ItemType Junction -Path "$HOME\.claude\skills\persona-panel" -Target "D:\OG Forge\persona-panel\skills\persona-panel"
```

macOS/Linux:

```bash
ln -s "<repo>/skills/persona-panel" ~/.claude/skills/persona-panel
```

## Use

In Claude Code:

```
/persona-panel https://your-site.com
/persona-panel concept: a subscription box of themed party kits for kids' birthdays, ₹1,999/month
```

Runs land in `skills/persona-panel/runs/<slug>-<timestamp>/`, which is git-ignored. Open `report.html` there.

## Rough cost

For 100 personas: 10-11 Haiku batch agents (each reads ~10 small screenshots plus an ~8k-token brief and writes one file), 3 Haiku live walkers (≤20 browser steps each), and 1 Sonnet synthesis pass. Set `--live 0` to skip the walkers.

## Markets

- `india` (default): Indian online shoppers, weighted toward mobile, tier-2/3 cities and COD-heavy payment.
- `global`: English-speaking international shoppers.
- Narrow an existing market with an overrides file, or write a custom market for any audience (`skills/persona-panel/references/custom-market.md`).

## Caveat

These are simulated customers. They're good at surfacing friction, confusion and missing information, but they don't predict real conversion. Validate the top themes with real people.

## License

MIT
