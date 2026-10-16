# Configuration

Everything is optional. With no config at all you get 100 personas from the `india` market, 4 live walkers, a full customer review, Haiku panel agents and a Sonnet synthesis pass.

Below, `<skill>` is the skill folder (see [INSTALL.md](INSTALL.md#first-time-setup) to find it) and `python` means any Python 3.10+.

## Where config lives and what wins

Later wins:

1. built-in defaults
2. user config: `~/.persona-panel/config.json`
3. project config: `.persona-panel.json` in the current working directory (normally the folder you started Claude Code in)
4. command-line flags for that run (or what you ask Claude for: "use 40 personas")

`PERSONA_PANEL_HOME` moves `~/.persona-panel` (venv, user config, markets, default runs folder) somewhere else.

See the effective values and where each one came from:

```bash
python <skill>/scripts/config.py show          # human-readable
python <skill>/scripts/config.py show --json   # what the skill reads at the start of every run
```

Check that everything loads (config, markets, lens, runs folder, venv, Chromium):

```bash
python <skill>/scripts/config.py doctor
```

## Writing a config

Ask Claude (`/persona-panel:persona-panel setup`), write the JSON by hand (start from [config.example.json](../config.example.json)), or use `config.py init`:

```bash
# user config: ~/.persona-panel/config.json, holds only the keys you pass
python <skill>/scripts/config.py init --market global --n 60 --live 2 --lens ux

# project config: ./.persona-panel.json, holds only the keys you pass
python <skill>/scripts/config.py init --project --n 40 --default-focus "Is the pricing page clear?"
```

`init` flags: `--market`, `--n`, `--live`, `--lens`, `--seed`, `--min-per-screen`, `--batch-size`, `--wave-size`, `--panel-model`, `--synthesis-model`, `--runs-dir`, `--default-focus`, plus `--project` and `--force`.

- `init` refuses to overwrite an existing file; add `--force` to replace it.
- `init` writes a `_comment` plus only the keys you pass, for the user config as well as the project config. Keys you leave out keep using the built-in defaults, so if a later release changes a default you get the new one. To pin a value, pass it (or add it by hand).
- For the user config, `init` turns a relative `--runs-dir` or market file path into an absolute path, since the file lives in `~/.persona-panel/` rather than where you ran the command. `~` is kept as written.
- `init` checks that the market and lens exist before writing.
- Keys starting with `_` (like `_comment`) are ignored. Unknown keys are ignored with a warning. A key set to `null` is skipped, as if it weren't there: the lower layer (or the default) applies. Bad values (wrong type, below the minimum, empty strings) stop every script with a message naming the file and key.

`.persona-panel.json` is in this repo's `.gitignore`. In your own projects, commit it if your team should share the settings.

## Keys

| Key | Default | Allowed | Used for | Per-run flag |
|---|---|---|---|---|
| `market` | `"india"` | a market name, or a path to a market JSON | who the personas are | `sample_personas.py --market` |
| `n` | `100` | whole number ≥ 1 (30+ to be useful) | panel size | `--n` |
| `live` | `4` | whole number ≥ 0 | live browser walkers in site mode (concept mode always uses 0) | `--live` |
| `lens` | `""` | `""` (full customer review), `ux`, `visual`, or another lens name | what the panel judges | `prepare_briefs.py --lens` |
| `seed` | `7` | whole number | random seed; the same seed and settings give the same personas | `--seed` |
| `min_per_screen` | `10` | whole number ≥ 0 | site mode: at least this many tablet, laptop and desktop reviewers each, converted from phone users | `--min-per-screen` |
| `batch_size` | `10` | whole number ≥ 1 | personas per panel agent | `--batch-size` |
| `wave_size` | `3` | whole number ≥ 1 | panel agents dispatched at the same time | read by the skill |
| `panel_model` | `"haiku"` | a model name the Agent tool accepts (`haiku`, `sonnet`, `opus`) | panel batches and live walkers | read by the skill |
| `synthesis_model` | `"sonnet"` | same | the one synthesis pass | read by the skill |
| `runs_dir` | `~/.persona-panel/runs` | a folder path | where run folders go | read by the skill |
| `default_focus` | `""` | text | focus questions used when a run doesn't give `--focus` | `prepare_briefs.py --focus` |

Notes:

- `lens`: `"default"`, `"none"` and `"full"` all mean the full customer review and are stored as `""`. `--lens default` on a run overrides a configured lens.
- `runs_dir`: `~` is expanded. A relative path in a config file is relative to that file's folder, so `"runs_dir": "persona-runs"` in a project config means `<project>/persona-runs`.
- `market`: a value that looks like a path (it has a file extension, a `/` or `\`, or starts with `~`) is treated the same way: `~` is expanded and a relative path is relative to the config file's folder, so `"market": "markets/b2b.json"` in a project config means `<project>/markets/b2b.json`. Anything else is a market name.
- `--run` on every script also expands `~` and turns a relative path into an absolute one.
- Live walkers take personas out of the panel: with `n: 100` and `live: 4`, 96 personas review screenshots and 4 browse the real site.

## Markets

A market is a JSON file of weighted attributes plus rules that keep combinations believable (for example, older personas get lower tech comfort; low income makes iPhones rarer).

Built in:

- `india`: Indian online shoppers. Weighted toward mobile, tier-2/3 cities, Hinglish and regional-language readers, and COD-heavy payment. Prices in ₹.
- `global`: English-speaking international shoppers across North America, UK/Ireland, Western Europe, Australia/NZ, South-East Asia, Latin America and the Middle East. Prices in $.

Both cover: `age_band`, `gender`, `location_tier` (india) or `region` (global), `income`, `device`, `network`, `language`, `tech_comfort`, `shopping_experience`, `payment_pref`, `shopper_type`, `traffic_source`, `intent`, `patience`, `trust_baseline`, `accessibility_need`, `aesthetic_taste`, `context`.

**Your own markets** go in `~/.persona-panel/markets/<name>.json`. Then use `--market <name>` or `"market": "<name>"`. They survive plugin updates. A user market named `india` or `global` replaces the built-in one. `market` also accepts a path to a JSON file, which is handy for a one-off market saved inside a run folder.

The format and rules are in [skills/persona-panel/references/custom-market.md](../skills/persona-panel/references/custom-market.md). In short: keep `age_band` (bands `18-24`, `25-34`, `35-44`, `45-54`, `55+`), `gender`, and `location_tier` or `region`; add any attributes you need with a `phrases` entry per value; for site mode keep `device`, `network`, `patience`, `traffic_source`, `context` and `accessibility_need`. `config.py doctor` validates every market it finds. Or describe the audience to Claude and it will write the file.

## Overrides: narrowing a market for one run

To tilt an existing market rather than write a new one, use an overrides file and pass it to `sample_personas.py --overrides FILE`. It is per run, not a config key; Claude writes one into the run folder when you describe a narrower audience.

```json
{
  "set":      {"age_band": {"18-24": 50, "25-34": 40, "35-44": 10, "45-54": 0, "55+": 0}},
  "multiply": {"device": {"desktop_laptop": 0.5}},
  "notes":    "Brand targets 18-30 streetwear fans"
}
```

- `set` replaces all of an attribute's weights. Values you leave out, or set to 0, never appear.
- `multiply` scales the listed weights and leaves the rest alone.
- Weights are relative; they don't need to add up to 100.
- An unknown attribute name stops the run with an error.
- Every value with a non-zero weight appears at least once when the panel is large enough, so rare segments (screen-reader users, slow-3G visitors) are never silently dropped.

## Lenses

| Lens | Judges | Ignores |
|---|---|---|
| (none) | the full customer experience: first impression, trust, price, payment, delivery, whether they'd buy | nothing |
| `ux` | navigation, scrolling, how sections and cards fit each screen, interactions, readability, visual design, hand-offs to other sites | what is sold, prices, payment and delivery policies |
| `visual` | look only: typography, colour, layout, spacing, imagery, hierarchy, consistency, fit on the screen | business model, pricing, payments, policies |

Each lens is a pair in `skills/persona-panel/references/lenses/`: `<name>.md` (instructions and output schema for the panel) and `<name>.json` (outcome words, score keys and issue categories used by the report). Adding a lens means adding a pair there, which is a code change: in a plugin install that folder is replaced on update, so contribute it (see [CONTRIBUTING.md](../CONTRIBUTING.md)) or use a manual install.

## Models and cost

The token cost is roughly:

```
about (n - live) / batch_size panel agents   on panel_model   (a few more: each batch holds one screen type)
+ live walkers                                on panel_model
+ 1 synthesis pass                            on synthesis_model
```

Capture, the UX checks, sampling, aggregation and the report are plain Python and cost no tokens. Each panel agent reads ~10 small screenshots plus an ~8k-token brief and writes one file; each walker uses at most 22 browser commands.

To spend less:

- `live: 0`: no walkers. You lose the findings that need a real browser session (Back button, menus, multi-step flows); the free UX checks still run.
- Smaller `n`. 30 is about the floor for useful segment breakdowns.
- Larger `batch_size`: fewer, bigger agents. Each agent then has more personas to keep distinct, so check that they still sound different.
- Keep `panel_model: "haiku"`. The panel agents are the biggest line item, so a larger panel model multiplies most of the cost.

`wave_size` doesn't change the total; it controls how many agents run at once. Raise it only if your plan allows more parallel agents.

`synthesis_model` is a single pass, so changing it has little effect on cost.

## Worked examples

### 1. Indian D2C fashion store

A streetwear brand selling through its own site, mostly to 18-34-year-olds from Instagram, with lots of COD orders. The built-in `india` market fits; the defaults are already right, so only a standing focus question goes in the user config:

```bash
python <skill>/scripts/config.py init --market india --default-focus "Would you pay by UPI, or only by COD? What would make you trust a new brand?"
```

For runs on this store, ask Claude to narrow the panel ("18-34 streetwear fans, mostly from Instagram and influencers, COD-heavy"). It writes an overrides file like this into the run folder:

```json
{
  "set": {"age_band": {"18-24": 55, "25-34": 35, "35-44": 10, "45-54": 0, "55+": 0}},
  "multiply": {"traffic_source": {"instagram_ad": 1.5, "influencer_link": 1.5},
               "payment_pref": {"cod_only": 1.3}},
  "notes": "Streetwear brand, 18-34, mostly from Instagram; COD is a big share of orders"
}
```

Run: `/persona-panel:persona-panel https://your-store.in`.

### 2. US SaaS landing page, UX review

A product team wants usability feedback on their marketing site, not opinions on their pricing. They keep the config in the repo so everyone gets the same panel. In the project folder:

```bash
python <skill>/scripts/config.py init --project --market global --lens ux --n 60 --live 2 --runs-dir persona-runs --default-focus "Can you tell what the product does within 10 seconds? Is the sign-up path obvious?"
```

That writes `./.persona-panel.json`:

```json
{
  "_comment": "persona-panel project config; overrides ~/.persona-panel/config.json",
  "market": "global",
  "n": 60,
  "live": 2,
  "lens": "ux",
  "runs_dir": "persona-runs",
  "default_focus": "Can you tell what the product does within 10 seconds? Is the sign-up path obvious?"
}
```

To keep the panel to US visitors arriving the way SaaS buyers do, add an overrides file for the run (Claude can write it):

```json
{
  "set": {"region": {"north_america": 100},
          "traffic_source": {"google_search": 40, "reddit_thread": 15, "email_newsletter": 15,
                             "friend_shared_link": 15, "typed_url_or_bookmark": 15}},
  "notes": "US visitors evaluating a SaaS tool"
}
```

Runs land in `<project>/persona-runs/`. Add that folder to the project's `.gitignore` unless you want reports in the repo.

### 3. B2B concept test with a custom market

Testing a pitch for an IT tool on the people who would buy it. Shoppers are the wrong panel, so write a market and save it as `~/.persona-panel/markets/b2b-it-buyers.json`:

```json
{
  "name": "b2b-it-buyers",
  "description": "People who evaluate and buy software for mid-size companies. Weights are guesses, not data.",
  "currency": "$",
  "attributes": [
    {"key": "age_band", "values": {"25-34": 35, "35-44": 40, "45-54": 20, "55+": 5}},
    {"key": "gender", "values": {"female": 35, "male": 63, "nonbinary": 2}},
    {"key": "region", "values": {"north_america": 50, "uk_ireland": 20, "western_europe": 20, "india": 10}},
    {"key": "role", "values": {"it_manager": 30, "cto": 15, "procurement": 20, "team_lead": 35}},
    {"key": "company_size", "values": {"50_200": 45, "200_1000": 40, "1000_plus": 15}},
    {"key": "budget_authority", "values": {"signs_off": 30, "recommends": 50, "researches_only": 20}},
    {"key": "biggest_worry", "values": {"security": 30, "cost": 25, "migration_effort": 25, "vendor_lock_in": 20}},
    {"key": "tech_comfort", "values": {"medium": 30, "high": 70}}
  ],
  "rules": [
    {"if": {"role": "procurement"}, "then": {"biggest_worry": {"cost": 2.5}, "tech_comfort": {"medium": 2}}},
    {"if": {"role": "cto"}, "then": {"budget_authority": {"signs_off": 3}, "biggest_worry": {"vendor_lock_in": 1.8}}}
  ],
  "phrases": {
    "role": {"it_manager": "Runs IT for the company.", "cto": "CTO; owns the technical roadmap.",
             "procurement": "Works in procurement; compares vendors on price and terms.",
             "team_lead": "Leads an engineering team that would use the tool daily."},
    "company_size": {"50_200": "Company of 50-200 people.", "200_1000": "Company of 200-1,000 people.",
                     "1000_plus": "Company of over 1,000 people."},
    "budget_authority": {"signs_off": "Can sign off the purchase.", "recommends": "Recommends; someone else signs.",
                         "researches_only": "Only researches options."},
    "biggest_worry": {"security": "Worried most about security reviews.", "cost": "Worried most about cost.",
                      "migration_effort": "Worried most about migration effort.",
                      "vendor_lock_in": "Worried most about lock-in."}
  },
  "cities": {"north_america": ["Austin", "Toronto"], "uk_ireland": ["Manchester", "Dublin"],
             "western_europe": ["Berlin", "Amsterdam"], "india": ["Bengaluru", "Pune"]},
  "names": {"female": ["Maria", "Priya"], "male": ["James", "Arjun"], "nonbinary": ["Alex"]},
  "occupations": {"25-34": ["engineering lead"], "35-44": ["IT manager"], "45-54": ["CTO"], "55+": ["VP of operations"]}
}
```

It is concept-only, so it skips the browsing attributes (`device`, `network`, and so on). Check it with `config.py doctor`, then run:

```
/persona-panel:persona-panel concept: <your pitch, pricing and who it's for> -- use the b2b-it-buyers market, 40 personas
```

To make it the default for one project, put `{"market": "b2b-it-buyers", "n": 40}` in that project's `.persona-panel.json`.
