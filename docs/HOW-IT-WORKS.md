# How it works

For contributors and the curious. For day-to-day use see [USAGE.md](USAGE.md).

## Design goals

1. **Cheap.** Anything that doesn't need judgement is Python: capture, UX measurement, sampling, counting, rendering. LLM tokens go only to role-play and one synthesis pass.
2. **Diverse panels.** LLM-invented personas collapse into the same upbeat, middle-of-the-road customer. Personas are sampled from weighted distributions instead, with rules that keep combinations believable, and every non-zero value is guaranteed to appear.
3. **Grounded.** Personas react only to what their device would show and to measured facts. Measured checks and opinions stay separate all the way to the report.
4. **Safe to point at a real site.** Walkers can't leave the site, pay, sign up or type personal data, and that is enforced in code.

## Pipeline

```
                    site mode                                   concept mode
   capture.py ──> capture/ (screens + digest.md)          concept.md (verbatim idea, images)
   probe.py   ──> probes/  (measured UX checks)                     │
        └───────────────────────┬───────────────────────────────────┘
                                v
   sample_personas.py ──> personas.json, personas.md, batches.json
   prepare_briefs.py  ──> briefs/<batch>.md, briefs/live_<pid>.md (+ lens.json)
                                v
   Agent tool, panel_model, wave_size at a time:
     panel agents  ──> results/<batch>.json   (~10 personas each, from screenshots)
     live walkers  ──> results/live_<pid>.json (drive walk.py)
                                v
   aggregate.py ──> aggregate.json, issues_digest.md  (counts, segments, missing personas)
   synthesis agent (synthesis_model) ──> synthesis.json  (themes, fixes, evidence)
   report.py ──> report.html  (self-contained)
```

### 1. Capture (`capture.py`, site mode)

Crawls up to `--max-pages` (12) pages a shopper would see, starting from the URL plus any `--extra-urls`, with headless Chromium on the profiles in `--profiles` (mobile, tablet, laptop, desktop). For each page and profile it saves viewport-height screenshot slices and a `data.json`. It also loads a few pages (`--throttled-pages`) on a throttled budget phone for load times. `capture/digest.md` summarises facts per page: trust signals, prices, missing alt text, small tap targets, console errors, popups, and a PASSWORD/LOGIN WALL flag.

### 2. UX checks (`probe.py`, site mode, no tokens)

Opens up to `--pages` (5) captured pages on six screen sizes (from `devices.py`: 360x780, 393x852, 820x1180, 1366x768, 1536x864, 1920x1080) and measures what screenshots miss: sections and cards cut off by the fold on tablet and up, in-page jump buttons that land in the wrong place, Back not restoring the scroll position, sticky overlays covering content, horizontal overflow. Every finding gets an id (`u001`...) and an annotated screenshot. Output: `probes/probes.json` and `probes/probes.md`.

### 3. Sampling (`sample_personas.py`)

Loads a market (user market first, then bundled), applies an optional overrides file, then draws `n` personas attribute by attribute. Each attribute's weights are adjusted by the market's `rules` given the persona's values so far (older → lower tech comfort, low income → fewer iPhones). Duplicates are re-drawn. Then:

- **coverage:** every value with non-zero weight appears at least once, when the panel is at least twice the number of values;
- **screens** (site mode): at least `min_per_screen` tablet, laptop and desktop personas each, converted from phone users;
- **live walkers:** `live` personas picked to be as different from each other as possible;
- **batches:** panel personas grouped by screen type, `batch_size` per batch, so one agent reviews one set of screenshots.

Each persona gets a name, age, city and occupation, an entry point (an Instagram ad lands on a product page, a typed URL on the home page), and a "Sees" plan: which screens they look at before their patience runs out. Same seed and inputs, same panel.

Concept mode drops the browsing-only attributes (`device`, `network`, `context`, `traffic_source`, `patience`, `accessibility_need`) and sets `live` to 0.

### 4. Briefs (`prepare_briefs.py`)

Writes one self-contained brief per batch: instructions (`references/panelist-site.md`, `panelist-concept.md`, or a lens file), the persona cards, the exact screenshots to open, the digest and relevant UX checks (or the concept), focus questions, and the output schema. Live walker briefs (`references/live-walker.md`) include the `walk.py` command line. The dispatch prompt is then one line, and an agent needs one turn to read and one to write. `--only p074 p081` writes small redo briefs for personas missing from the results.

### 5. Panel and walkers (Agent tool)

The orchestrating Claude dispatches `wave_size` agents per message on `panel_model` and waits for the wave before sending the next. After the first wave it spot-checks one result file before spending more.

Live walkers use `walk.py`, a small stateful browser CLI: each walker gets its own headless Chromium kept alive over CDP between commands, so a cart drawer opened by one command is still there for the next. Every command prints the URL, scroll position, a numbered list of clickable things (including inside iframes and shadow DOM) and a screenshot path, so the walker usually works from text and reads screenshots only when judging visuals. Budget: at most 22 commands.

### 6. Aggregate, synthesise, report

`aggregate.py` reads every result, computes outcomes, scores and per-segment breakdowns, merges in the UX checks, lists missing personas, and writes `issues_digest.md`: one line per issue with persona id and screenshot tag. A single synthesis agent reads only the digest and `aggregate.json` (`references/synthesis.md`) and clusters issues by root cause into themes with persona ids, evidence screenshots, fixes and impact. `report.py` renders `report.html` with the screenshots embedded.

## Architecture

```
.claude-plugin/plugin.json          plugin manifest (version lives here only)
.claude-plugin/marketplace.json     marketplace "og-forge", source "./"
skills/persona-panel/
  SKILL.md                          orchestrator instructions (what Claude does)
  data/markets/*.json               bundled markets
  references/                       agent briefs: panelist-*, live-walker, synthesis, result-schema,
                                    custom-market, lenses/<name>.{md,json}
  scripts/
    paths.py                        state locations + config loading (stdlib)
    config.py                       show / init / doctor (stdlib)
    setup_env.py                    creates the venv, installs Playwright + Chromium (stdlib)
    sample_personas.py              sampling (stdlib)
    prepare_briefs.py               briefs (stdlib)
    aggregate.py                    counting (stdlib)
    report.py                       HTML report (Pillow)
    capture.py, probe.py, walk.py   browser work (Playwright, Pillow)
    devices.py                      screen sizes and user agents
tests/                              offline pytest suite (no browser, network or LLM)
```

**The orchestrator stays cheap.** SKILL.md tells the main Claude to run scripts and dispatch agents, and never to read screenshots, briefs or result files itself; the one exception is opening 2-3 top evidence screenshots at the end to check the themes are real. All the heavy reading happens inside small Haiku agents whose context is thrown away.

**Scripts never call an LLM.** They are deterministic and testable offline. All LLM work goes through Claude Code's Agent tool, so it uses the user's own Claude Code plan and model settings.

## Why state lives in `~/.persona-panel`

The skill folder is treated as read-only. Everything mutable lives in `~/.persona-panel/` (or `$PERSONA_PANEL_HOME`): the venv, `config.json`, `markets/`, and `runs/`. Scripts set `sys.dont_write_bytecode = True` so not even `__pycache__` is written next to them.

- **Not in the skill folder (`SKILL_DIR`).** A plugin install lives in a versioned cache under `~/.claude/plugins/cache/` that is replaced on every update. A venv, config or reports stored there would vanish on update. Before 0.2.0 the venv and runs were in the skill folder; `paths.py` still falls back to an old `SKILL_DIR/.venv` until the new one exists.
- **Not in `CLAUDE_PLUGIN_DATA`.** Claude Code's per-plugin data folder is deleted when the plugin is uninstalled, isn't set in the Bash environment the scripts run in, and doesn't exist for a manual (clone and link) install. One fixed, documented folder works the same for plugin and manual installs, and a user can reinstall without losing their markets and reports.
- **Chromium** stays in Playwright's own cache, shared with other Playwright tools.

`config.py show --json` prints every resolved path; SKILL.md reads it at the start of each run.
