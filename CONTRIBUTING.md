# Contributing

Thanks for helping. Bug reports, new markets, new lenses, fixes and doc improvements are all welcome. For anything bigger than a small fix, open an issue first so we can agree on the approach before you write it.

By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Report security problems privately, see [SECURITY.md](SECURITY.md).

## Workflow

1. Fork `OG-Forge/persona-panel` and clone your fork.
2. Create a branch from `main`: `git checkout -b fix/back-button-probe`.
3. Make the change, with tests (see below).
4. Run the checks locally.
5. Push to your fork and open a pull request against `main`. Fill in the template.

Commit messages: short imperative subject ("Add tablet fit check to probe"), a body if the why isn't obvious.

## Dev setup

Python 3.10+.

```bash
git clone https://github.com/<you>/persona-panel.git
cd persona-panel
python -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\Activate.ps1      # Windows PowerShell
```

```bash
source .venv/bin/activate       # macOS / Linux
```

Then:

```bash
python -m pip install -r requirements-dev.txt     # pytest, playwright, pillow
python -m playwright install chromium             # only needed to run capture/probe/walk by hand
```

`.venv/` and `runs/` are git-ignored.

To try your working copy in Claude Code, link `skills/persona-panel` from your clone into `~/.claude/skills/persona-panel` (see [docs/INSTALL.md](docs/INSTALL.md#option-2-manual-clone-and-link)) and uninstall the plugin version while you do, so there is only one copy. Set `PERSONA_PANEL_HOME` to a scratch folder if you don't want test runs mixed with your real config and reports.

## Tests and checks

```bash
python -m pytest
```

The suite is offline: no browser, no network, no LLM calls. Each test gets its own `PERSONA_PANEL_HOME` and working directory, so it never touches your real `~/.persona-panel`.

CI (`.github/workflows/ci.yml`) runs on pushes to `main` and on pull requests, on Ubuntu and Windows with Python 3.10 and 3.12, installing only `pytest` and `pillow` (no Playwright). It byte-compiles `skills/` and `tests/`, validates every JSON file and the plugin manifests, and runs pytest. The `ci-ok` job is the required check; it passes only if every matrix job passed. So:

- tests must not import Playwright or need a browser;
- keep code working on Python 3.10 and on Windows paths;
- run `python -m compileall -q skills tests` if you touched syntax you're unsure about on 3.10.

If you changed the plugin manifests, also run `claude plugin validate .` if you have Claude Code installed.

**Runtime dependencies are listed twice and must change together:** `requirements.txt` and `FALLBACK_REQUIREMENTS` in `skills/persona-panel/scripts/setup_env.py` (used when the plugin cache has no `requirements.txt`). `tests/test_packaging.py::test_requirements_match_setup_env_fallback` fails until both match, so a Dependabot pip PR needs the same bump in `setup_env.py` before it can merge.

Pull requests from forks need a maintainer's approval before CI runs on them. That is a GitHub safety setting, not a judgement on your PR.

## Design principles

These keep the tool cheap and safe. PRs that break them will be asked to change.

1. **Stdlib first.** `paths.py`, `config.py`, `setup_env.py`, `sample_personas.py`, `prepare_briefs.py` and `aggregate.py` use only the standard library, so they run before setup and in CI. Only browser and image work may use Playwright and Pillow. Don't add a dependency without discussing it in an issue.
2. **No LLM calls inside scripts.** Scripts are deterministic and testable offline. All model work goes through Claude Code's Agent tool, as SKILL.md describes.
3. **The orchestrator stays token-cheap.** The main Claude runs scripts and dispatches agents. It must not need to read screenshots, briefs or result files. Script output it reads should be a few lines; put detail in files in the run folder.
4. **The skill folder is read-only at run time.** Write only to the run folder or `~/.persona-panel` (via `paths.py`). Every runnable script sets `sys.dont_write_bytecode = True` before its other imports (imported modules like `paths.py` don't need to).
5. **Walker safety rules must not be relaxed.** Live walkers never pay, sign up, log in, leave the site under test, or type into personal-data fields, and `walk.py` enforces this in code (`guard`, `on_site`, the field check in `act`). Changes may tighten these rules, never loosen them, and need a test.
6. **Measured facts and persona opinions stay separate** all the way to the report.
7. **No invented data.** Missing results are reported as missing, never filled in.

## Adding a market

1. Open a "New market" issue with the audience, the attributes, and where the weights come from (real data or honest guesses).
2. Write `skills/persona-panel/data/markets/<name>.json` following [references/custom-market.md](skills/persona-panel/references/custom-market.md). For site mode keep `device`, `network`, `patience`, `traffic_source`, `context` and `accessibility_need`. Give every value a `phrases` entry, and say in `description` where the numbers come from.
3. `tests/test_markets.py` checks every bundled market automatically. Also try it: `python skills/persona-panel/scripts/sample_personas.py --run <tmp> --market <name> --n 100` and read `personas.md` to see if the people are believable.
4. Add it to the market list in `docs/CONFIGURATION.md` and `README.md`.

## Adding a lens

A lens is a pair in `skills/persona-panel/references/lenses/`:

- `<name>.md`: the panel instructions. It must contain a `## Output schema` section; walker briefs reuse that part.
- `<name>.json`: `name`, `description`, `outcomes`, `outcome_labels`, `scores`, `score_labels`, `categories`. `aggregate.py` and `report.py` use these words.

Copy `ux.md` / `ux.json` and edit. Add a test (see `tests/test_pipeline.py` for lens tests), and document it in the lens tables in `docs/CONFIGURATION.md` and `docs/USAGE.md`.

## Adding or changing a script

- Start with `import sys` then `sys.dont_write_bytecode = True`, then other imports.
- Use `paths.py` for every location and `paths.config_or_exit()` for config defaults; CLI flags should default to the config value and still override it.
- A new config key goes in `paths.DEFAULTS` (with validation), `config.py` `INIT_FLAGS`, `config.example.json`, `docs/CONFIGURATION.md`, and tests.
- Keep the output short and the run folder layout stable; `aggregate.py`, `report.py` and SKILL.md depend on it.
- Update SKILL.md if the orchestrator should call it, and keep SKILL.md short: every line there is read on every run.
- Add offline tests. Put shared fixtures in `tests/conftest.py`.

## Pull request checklist

- [ ] `python -m pytest` passes locally
- [ ] Tests added or updated for the change
- [ ] No Playwright import or browser needed in tests
- [ ] Nothing written under the skill folder at run time
- [ ] Walker safety rules unchanged or tightened
- [ ] Docs updated (README / docs / SKILL.md) for anything user-visible
- [ ] No secrets, personal data, or captured third-party site content committed

Don't bump the version or edit `CHANGELOG.md`; the maintainer does that at release time. Describe user-visible changes in the PR so they can go in the changelog.

## Review and merging

`main` is protected by a ruleset:

- changes land only through pull requests;
- 1 approving review, including the code owner ([@darthfl45h](https://github.com/darthfl45h));
- the `ci-ok` check must pass;
- squash merge only, linear history, no force pushes.

Only the maintainer merges. The maintainer's own PRs go through the same PR and CI flow and are merged with the ruleset bypass, since nobody else can approve them.

## Releases (maintainer)

Claude Code decides whether an installed plugin needs updating from the `version` in `.claude-plugin/plugin.json`. Changes merged without a version bump don't reach plugin users.

1. Pick the next version (semver: patch for fixes, minor for features or new markets/lenses, major for breaking config or run-folder changes).
2. In a release PR: bump `version` in `.claude-plugin/plugin.json` (the only place it lives; `marketplace.json` has none) and add a dated `CHANGELOG.md` entry. Note there if users must re-run `setup_env.py` (requirements changed) or change their config.
3. Merge, then tag the merge commit `vX.Y.Z` and create a GitHub release with the changelog entry.
