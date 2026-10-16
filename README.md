# persona-panel

[![CI](https://github.com/OG-Forge/persona-panel/actions/workflows/ci.yml/badge.svg)](https://github.com/OG-Forge/persona-panel/actions/workflows/ci.yml)

A Claude Code plugin that runs a **simulated customer panel of 100+ diverse personas** against a live website or a product idea, and turns their reactions into a prioritised fix list with screenshots.

- **Site mode:** give it a URL. A real browser captures the site on phone, tablet, laptop and desktop, runs free automated UX checks (section and card fit, in-page jumps, Back-button scroll restore, sticky overlays, overflow), and a few live walkers browse it. Then the panel reviews what each persona would actually see.
- **Concept mode:** give it an idea, pitch, pricing or mockup images. No browser needed.

Personas are sampled from weighted demographic distributions (age, city tier or region, income, device, network, language, payment habits, shopper type, patience, accessibility needs), not invented by an LLM, so minority segments don't get dropped. Built-in markets: `india` (default) and `global`. You can add your own.

It is built to be cheap: Python does the capture, sampling and counting; small Haiku agents play about 10 personas each, in waves; one Sonnet pass writes the synthesis.

## What you get

A self-contained `report.html` in the run folder:

- a one-line headline and a short summary;
- 6-14 themes ranked by impact, each with the personas who hit it, the segments most affected, the screens affected, a concrete fix, and 1-3 evidence screenshots (click to enlarge, "Copy as bug" button);
- the measured UX checks per screen size, kept separate from persona opinions;
- outcomes and scores broken down by segment.

## Quick start

Needs Claude Code and Python 3.10+. Inside Claude Code:

```
/plugin marketplace add OG-Forge/persona-panel
/plugin install persona-panel@og-forge
```

On Claude Code 2.1.275 or later this also works in one step:

```
/plugin install persona-panel --marketplace OG-Forge/persona-panel
```

Installing from the `/plugin` panel loads the plugin straight away; after a typed install command, run `/reload-plugins` (or start a new session). Then run the one-time setup. It asks a few questions, then creates a Python venv with Playwright and Pillow in `~/.persona-panel/` and downloads Chromium into Playwright's own browser cache:

```
/persona-panel:persona-panel setup
```

**Or let Claude do it.** Paste this into Claude Code:

```
Read https://raw.githubusercontent.com/OG-Forge/persona-panel/v0.2.0/SETUP_WITH_CLAUDE.md and follow it to set up persona-panel for me.
```

That link is pinned to the v0.2.0 release. For the latest instructions on `main`, use https://raw.githubusercontent.com/OG-Forge/persona-panel/main/SETUP_WITH_CLAUDE.md instead.

Manual install (clone and link), updating and uninstalling: [docs/INSTALL.md](docs/INSTALL.md).

## First runs

```
/persona-panel:persona-panel https://your-site.com
/persona-panel:persona-panel https://your-site.com --lens ux
/persona-panel:persona-panel concept: a subscription box of themed party kits for kids' birthdays, ₹1,999/month
```

Plain language works too: "run a persona panel on https://your-site.com with 60 US shoppers". If you installed manually, the command is `/persona-panel` instead of `/persona-panel:persona-panel`.

Runs go to `~/.persona-panel/runs/<slug>-<timestamp>/`. Open `report.html` there.

## Rough cost

For 100 personas with the defaults: 10-11 Haiku panel agents (each reads ~10 small screenshots and an ~8k-token brief, writes one file), 4 Haiku live walkers (at most 22 browser commands each), and 1 Sonnet synthesis pass. The capture and UX checks use no tokens. Use `live: 0` or a smaller `n` to spend less; see [docs/CONFIGURATION.md](docs/CONFIGURATION.md#models-and-cost).

## Docs

- [docs/INSTALL.md](docs/INSTALL.md): plugin and manual install, updates, uninstall, troubleshooting
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md): config files, every key, markets, overrides, lenses, worked examples
- [docs/USAGE.md](docs/USAGE.md): site vs concept mode, lenses, focus questions, re-runs, reading the report
- [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md): pipeline and architecture
- [SETUP_WITH_CLAUDE.md](SETUP_WITH_CLAUDE.md): setup instructions written for an AI agent
- [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), [CHANGELOG.md](CHANGELOG.md)

## Caveat

These are simulated customers. They are good at surfacing friction, confusion and missing information, but they don't predict real conversion. Validate the top themes with real people.

Running capture, UX checks and live walkers against a website is your responsibility: only point it at sites you own or are allowed to test.

## License

MIT. See [LICENSE](LICENSE).
