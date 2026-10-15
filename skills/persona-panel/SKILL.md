---
name: persona-panel
description: Run a cheap simulated customer panel of 100+ diverse personas (age, city tier, income, device and screen size, network, language, payment habits, shopper type, accessibility needs) that reviews a live website or an idea/concept, plus free automated UX checks across phone/tablet/laptop/desktop (section and card fit, in-page jumps, Back-button scroll restore, sticky overlays), and returns a prioritised fix list with screenshots per issue. Use when the user wants consumer or UX feedback, synthetic user testing, a persona/focus-group review, or "what would customers think" about a URL, landing page, product idea, pricing or pitch.
---

# Persona Panel

A large simulated customer panel, built to keep token costs low. Four layers, cheapest first:

1. **Measured UX checks** (`probe.py`, no LLM tokens). A real browser scrolls, clicks in-page buttons and presses Back on 6 screen sizes, and annotates screenshots of every problem. Screenshots alone miss these.
2. **Panel personas.** Haiku plays about 10 personas per agent from shared screenshots, plus the measured facts for their screen type.
3. **Live walkers.** A few Haiku agents drive a real browser on phone, tablet, laptop and desktop, covering navigation, Back, in-page buttons and the goal flow.
4. **One synthesis pass** clusters everything into themes, and every theme carries evidence screenshots.

You, the orchestrator, only run scripts and dispatch agents. **Don't read screenshots, briefs or result files yourself.** That's where the tokens go.

## Paths

- `SKILL_DIR` is this skill's base directory.
- `PY` is `SKILL_DIR/.venv/Scripts/python.exe` on Windows, or `SKILL_DIR/.venv/bin/python` elsewhere. If it doesn't exist, run `python SKILL_DIR/scripts/setup_env.py` once (about 2 minutes).
- `RUN` is `SKILL_DIR/runs/<short-kebab-slug>-<YYYYMMDD-HHMM>`.
- Device sizes live in `scripts/devices.py`:

  | Name | Screen |
  |---|---|
  | mobile | 360x780 |
  | mobile_large | 393x852 |
  | tablet | 820x1180 |
  | laptop | 1366x768 |
  | laptop_hd | 1536x864 |
  | desktop | 1920x1080 |

## 1. Pin down the inputs (ask only for what's missing)

- **Mode:**
  - `site`: a URL.
  - `concept`: an idea, pitch, product description, pricing, landing copy, or images of a mockup or deck.
- **Audience:** the built-in markets are `india` (Indian online shoppers, the default for Indian brands and ₹ prices) and `global`.
  - If the user describes a narrower target, write an overrides file (format in the `sample_personas.py` docstring).
  - If the audience isn't consumer shoppers at all, write a custom market (`references/custom-market.md`).
- **Size:** `--n` (default 100, at least 30 to be useful). `--min-per-screen 10` (the default) guarantees tablet, laptop and desktop reviewers even in phone-heavy markets.
- **Lens:** what the panel judges.
  - **Default:** a full customer review, including trust, price and buying.
  - **`--lens ux`:** usability plus looks (navigation, scrolling, fit per screen, interactions, readability, visuals), ignoring what's sold.
  - **`--lens visual`:** looks only.
  - Lenses live in `references/lenses/<name>.md` (instructions plus schema) and `<name>.json` (outcome words, score keys). Add one by copying an existing pair.
- **Live walkers** (site mode only): default 4, which gives one per screen type. Use 0 to save tokens.
- **Focus questions** (optional): pass them as `--focus`.
- **Re-running on the same site:** copy `capture/`, `probes/` and any overrides from the earlier run into the new run folder instead of capturing again. The same `--seed` gives the same personas, so runs compare like for like.

Then tell the user the plan and rough cost in one line. Example: "100 personas = 10 Haiku batches in waves of 3, plus 4 live walkers and 1 synthesis pass. The UX checks are free."

## 2. Prepare (scripts only)

**Site mode:**

```
PY SKILL_DIR/scripts/capture.py --url URL --run RUN     # ~3-5 min; phone, tablet, laptop, desktop; add --extra-urls for key pages
PY SKILL_DIR/scripts/probe.py --run RUN                 # ~3-4 min, no tokens: section/card fit, in-page jumps, Back restore, overlays, overflow
```

Skim only the first ~15 lines of `RUN/capture/digest.md` and the last line of probe's output. If the digest says PASSWORD/LOGIN WALL, or almost nothing was captured, stop and tell the user.

**Concept mode:** write `RUN/concept.md` with the user's concept verbatim, plus any facts they gave (price, audience, channel). If they gave image files, list their absolute paths under a "## Images" heading. Don't embellish the concept.

**Both modes:**

```
PY SKILL_DIR/scripts/sample_personas.py --run RUN --mode site|concept --market india|global|RUN/market.json --n 100 --live 4 [--overrides RUN/overrides.json]
PY SKILL_DIR/scripts/prepare_briefs.py --run RUN --python PY [--lens ux|visual] [--focus "..."] [--max-images 12]
```

## 3. Run the panel in waves

`RUN/batches.json` lists the panel batches and live walkers. Dispatch with the Agent tool, `model: "haiku"`, `subagent_type: "general-purpose"`, **3 agents per wave** (4 at most). Send each wave's Agent calls in one message, and start the next wave only when all of them have finished. Each prompt is just:

> Read the brief at `RUN/briefs/<batch_id>.md` and follow it exactly. When the output file is written, reply with only the word: done

Live walkers use the same prompt with `RUN/briefs/live_<pid>.md`. Each one runs its own browser, so they don't conflict, and they can fill spare slots in the last panel wave.

After the first wave, spot-check one result file. Check that it's valid JSON, that the personas sound different from each other, that the issues point to things actually on the site, and that `shot` fields are filled. If it's badly off, fix the brief before spending more tokens.

## 4. Check, fill gaps, synthesize

```
PY SKILL_DIR/scripts/aggregate.py --run RUN
```

If it reports missing personas, write small redo briefs with `prepare_briefs.py ... --only p074 p081` (same flags as before) and dispatch `briefs/<batch>_redo.md`, once. Don't re-run a whole batch for one missing persona. Then run one synthesis agent with `model: "sonnet"`:

> Read `SKILL_DIR/references/synthesis.md` and follow it for the run folder `RUN`. Reply with only: done

For a lens run, add one sentence naming the lens and its scope.

## 5. Report

```
PY SKILL_DIR/scripts/report.py --run RUN --title "<site or concept name>" --subject "<URL or one-line description>"
```

The report embeds evidence screenshots next to every theme and measured check (click to enlarge). Each one has a "Copy as bug" button that copies a ready-to-file ticket.

Before summarising, open 2-3 of the top themes' screenshots yourself to confirm they show what the theme claims. Give the user the path to `RUN/report.html`, plus a short summary: the headline, the top fixes with how many personas or devices hit each, and the segment or screen type that struggled most. Offer to publish the report as an artifact only if they want to share it.

Clean up any leftover walker browsers: `PY SKILL_DIR/scripts/walk.py RUN/walk/<pid> stop` for each live walker.

## Honesty rules

- These are simulated customers. They're good at finding friction, confusion and missing information, but they don't measure real conversion. Say so once in the summary.
- Measured checks are facts; persona reactions are opinions. Keep that distinction in the summary.
- Never pad the results. If a batch failed twice, report fewer personas rather than inventing them.
- Live walkers never pay, sign up, log in, follow links to other sites, or enter real personal data (enforced in their brief). Don't relax that.
