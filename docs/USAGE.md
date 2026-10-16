# Usage

Examples use the plugin command `/persona-panel:persona-panel`. With a manual install it is `/persona-panel`. Plain language works for both: "run a persona panel on https://example.com", "what would customers think of this pricing?".

Claude asks only for what's missing, tells you the plan and a rough cost in one line, then runs. In site mode, capture and the UX checks take about 6-9 minutes before any agent starts; the panel then runs in waves of `wave_size` agents.

## Site mode

Give it a URL:

```
/persona-panel:persona-panel https://your-site.com
```

What happens:

1. **Capture** (~3-5 min, no tokens): the home page and the pages a shopper would reach (collections, product pages), on phone, tablet, laptop and desktop. Screenshot slices plus a facts digest: load times on a throttled budget phone, trust signals, prices, missing alt text, small tap targets, console errors, popups.
2. **UX checks** (~3-4 min, no tokens): a real browser on 6 screen sizes scrolls, clicks in-page buttons and presses Back, and records section and card fit, in-page jumps, Back-button scroll restore, sticky overlays and horizontal overflow, with annotated screenshots.
3. **Panel**: Haiku agents each play about 10 personas from the screenshots their device would show.
4. **Live walkers** (default 4, one per screen type): agents drive a real headless browser through the site, up to the first checkout screen.
5. **Synthesis and report.**

Extra pages: ask Claude to include specific URLs ("also check /pricing and /checkout-info"); they're passed to capture as `--extra-urls`.

If the site is behind a password or login wall, capture stops and Claude tells you. Only public pages can be reviewed.

## Concept mode

Give it an idea, pitch, pricing, landing copy, or mockup images:

```
/persona-panel:persona-panel concept: a subscription box of themed party kits for kids' birthdays, ₹1,999/month, sold on Instagram
/persona-panel:persona-panel concept: the pitch in ./pitch.md with the mockups in ./mockups/*.png
```

Your concept is written to the run folder verbatim, plus any facts you gave (price, audience, channel). No browser and no walkers. Personas react to the idea itself: would they understand it, want it, pay that price, and what would stop them.

## Who is on the panel

- `india` (default) or `global`, or any market in `~/.persona-panel/markets/`. Say "use the global market" or set `market` in your config.
- Describe a narrower audience ("women 25-40 in metros who shop on Myntra") and Claude writes an overrides file for the run.
- For a non-shopper audience (B2B buyers, teachers, clinicians), Claude can write a custom market. See [CONFIGURATION.md](CONFIGURATION.md#markets).
- Size: "use 40 personas" (`--n`). At least 30 for useful segment breakdowns.

## Lenses

| You want | Say | Lens |
|---|---|---|
| Would customers buy? Trust, price, payment, delivery, everything | nothing (default) | full review |
| Is it easy to use and does it look right on every screen? | "ux lens" | `ux` |
| Just the look | "visual lens" | `visual` |

```
/persona-panel:persona-panel https://your-site.com --lens ux
```

A lens changes the panel's instructions, the outcome words (for example "smooth / some friction / frustrating" instead of "buy / maybe / no") and the scores in the report. It works in concept mode too. If your config sets a lens, say "full review" (`--lens default`; `full` and `none` mean the same) to get the full customer review for one run. To add your own lens, see [CONFIGURATION.md](CONFIGURATION.md#lenses).

## Focus questions

Add specific questions the panel should answer:

```
/persona-panel:persona-panel https://your-site.com -- focus: is the size guide easy to find? would you pay by UPI?
```

A standing question can go in config as `default_focus`; a question given for a run replaces it.

## Live walkers

Site mode only. Each walker plays one persona on their own device and tries to: orient, scroll, use an in-page button, open a section and press Back, then pursue their goal up to the first checkout screen. They catch what screenshots can't (Back-button behaviour, drawers, filters, add-to-bag, hand-offs to other sites).

They never pay, sign up, log in, leave the site, or type into personal-data fields; `walk.py` enforces this in code. Say "no live walkers" (or set `live: 0`) to save tokens.

## Re-running

- **Same personas:** the same `seed`, market, size and overrides give the same panel, so a re-run after fixes compares like for like.
- **Same capture:** to try a different lens or focus on the same snapshot of the site, ask Claude to reuse the earlier run's capture. It copies `capture/`, `probes/` and any overrides into the new run folder instead of capturing again.
- **After a fix:** run fresh (new capture) with the same seed.

## Reading the report

Each run is a folder `<runs_dir>/<slug>-<YYYYMMDD-HHMM>/`. Open `report.html` in a browser; it is self-contained.

- **Headline and summary**: the verdict in a sentence, then 3-5 sentences.
- **Themes**: ranked by impact (1-5), which weighs how many personas hit it, how severe it was, and whether they left. Each shows severity, the personas who raised it, the segments most affected ("tier-3 COD-only buyers: 70% vs 15% of metro UPI users"), the screens affected, a concrete fix, effort, and 1-3 evidence screenshots. Click a screenshot to enlarge. **Copy as bug** copies a ready-to-file ticket.
- **Measured UX checks**: what the browser measured per screen size, with annotated screenshots. These are facts, not opinions.
- **Outcomes and segments**: how many personas would buy / maybe / not (or the lens's outcome words), and scores by segment and screen type.

Other files in the run folder, if you want to dig in: `personas.md` (the panel), `capture/digest.md` (site facts), `probes/probes.md` (UX checks), `results/` (raw persona output), `aggregate.json` and `synthesis.json`.

## What to trust

- Simulated customers are good at friction, confusion and missing information. They do not predict real conversion rates. Treat the outcome percentages as relative signals, not forecasts.
- Measured checks are facts from a real browser; persona reactions are opinions. The report keeps them apart.
- The panel never pads results. If a batch fails twice, the report has fewer personas rather than invented ones.
- Validate the top themes with real people before big decisions.
