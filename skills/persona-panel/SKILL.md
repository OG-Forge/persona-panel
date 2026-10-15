---
name: persona-panel
description: Run a cheap simulated customer panel of 100+ diverse personas (age, city tier, income, device, network, language, payment habits, shopper type, accessibility needs) that reviews a live website or an idea/concept and returns a prioritised fix list. Use when the user wants consumer feedback, synthetic user testing, a persona/focus-group review, or "what would customers think" about a URL, landing page, product idea, pricing or pitch.
---

# Persona Panel

A large simulated customer panel, built to keep token costs low:

- **Scripts do the heavy lifting.** Sampling, the site capture, counting and the report are all Python.
- **Haiku plays the personas**, about 10 per agent. The batch shares one set of screenshots and writes everything in one file.
- **Agents run in small waves**, never all at once.
- **One synthesis pass** clusters the issues.

You, the orchestrator, only run scripts and dispatch agents. **Don't read screenshots, briefs or result files yourself.** That's where the tokens go.

## Paths

- `SKILL_DIR` is this skill's base directory.
- `PY` is `SKILL_DIR/.venv/Scripts/python.exe` on Windows, or `SKILL_DIR/.venv/bin/python` elsewhere. If it doesn't exist, run `python SKILL_DIR/scripts/setup_env.py` once (about 2 minutes).
- `RUN` is `SKILL_DIR/runs/<short-kebab-slug>-<YYYYMMDD-HHMM>`.

## 1. Pin down the inputs (ask only for what's missing)

- **Mode:**
  - `site`: a URL.
  - `concept`: an idea, pitch, product description, pricing, landing copy, or images of a mockup or deck.
- **Audience:** the built-in markets are `india` (Indian online shoppers, the default for Indian brands and ₹ prices) and `global`.
  - If the user describes a narrower target ("18-30 streetwear fans"), write an overrides file (format in the `sample_personas.py` docstring).
  - If the audience isn't consumer shoppers at all, write a custom market (`references/custom-market.md`).
- **Size:** `--n` (default 100, at least 30 to be useful).
- **Live walkers** (site mode only): default 3. Use 0 to save tokens, or up to 6 when checkout flows matter.
- **Focus questions** (optional): what the owner most wants to learn. Pass them as `--focus`.

Then tell the user the plan and rough cost in one line. Example: "100 personas = 10 Haiku batches in waves of 3, plus 3 live walkers and 1 synthesis pass."

## 2. Prepare (scripts only)

**Site mode:**

```
PY SKILL_DIR/scripts/capture.py --url URL --run RUN            # ~2-4 min; add --extra-urls for pages that matter
```

Skim only the first ~15 lines of `RUN/capture/digest.md`. If it says PASSWORD/LOGIN WALL, or almost nothing was captured, stop and tell the user.

**Concept mode:** write `RUN/concept.md` with the user's concept verbatim, plus any facts they gave (price, audience, channel). If they gave image files, list their absolute paths under a "## Images" heading. Don't embellish the concept.

**Both modes:**

```
PY SKILL_DIR/scripts/sample_personas.py --run RUN --mode site|concept --market india|global|RUN/market.json --n 100 --live 3 [--overrides RUN/overrides.json]
PY SKILL_DIR/scripts/prepare_briefs.py --run RUN --python PY [--focus "..."]
```

## 3. Run the panel in waves

`RUN/batches.json` lists the panel batches and live walkers. Dispatch with the Agent tool, `model: "haiku"`, `subagent_type: "general-purpose"`, **3 agents per wave** (4 at most). Send each wave's Agent calls in one message, and start the next wave only when all of them have finished. Each prompt is just:

> Read the brief at `RUN/briefs/<batch_id>.md` and follow it exactly. When the output file is written, reply with only the word: done

Live walkers use the same prompt with `RUN/briefs/live_<pid>.md`. Each one runs its own browser, so they don't conflict, and they can fill spare slots in the last panel wave.

After the first wave, spot-check one result file. Check that it's valid JSON, that the personas sound different from each other, and that the issues point to things actually on the site. If it's badly off, fix the brief before spending more tokens.

## 4. Check, fill gaps, synthesize

```
PY SKILL_DIR/scripts/aggregate.py --run RUN
```

If it reports missing personas or invalid files, re-dispatch only those batches, once. Then run one synthesis agent with `model: "sonnet"`:

> Read `SKILL_DIR/references/synthesis.md` and follow it for the run folder `RUN`. Reply with only: done

## 5. Report

```
PY SKILL_DIR/scripts/report.py --run RUN --title "<site or concept name>" --subject "<URL or one-line description>"
```

Give the user the path to `RUN/report.html`, plus a 5-line summary: the headline, the top 3 fixes with how many personas hit each, and the segment that struggled most. Offer to publish the report as an artifact only if they want to share it.

Clean up any leftover walker browsers: `PY SKILL_DIR/scripts/walk.py RUN/walk/<pid> stop` for each live walker.

## Honesty rules

- These are simulated customers. They're good at finding friction, confusion and missing information, but they don't measure real conversion. Say so once in the summary.
- Never pad the results. If a batch failed twice, report fewer personas rather than inventing them.
- Live walkers never pay, sign up, log in or enter real personal data (enforced in their brief). Don't relax that.
