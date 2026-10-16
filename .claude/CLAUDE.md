# persona-panel: notes for Claude working on this repo

A Claude Code plugin (marketplace `og-forge`, plugin `persona-panel`) with one skill in `skills/persona-panel/`. Read `docs/HOW-IT-WORKS.md` for the pipeline and `CONTRIBUTING.md` for the rules.

## Commands

```bash
python -m pip install -r requirements-dev.txt   # in a repo-local .venv
python -m pytest                                # offline suite; must pass before any PR
python -m compileall -q skills tests            # CI also byte-compiles
claude plugin validate .                        # after touching .claude-plugin/*.json
```

Use a scratch `PERSONA_PANEL_HOME` when running scripts by hand, so you don't touch the user's real `~/.persona-panel`.

## Rules

- Tests are offline: no Playwright, browser, network or LLM. CI installs only `pytest` and `pillow`, on Ubuntu and Windows, Python 3.10 and 3.12.
- `paths.py`, `config.py`, `setup_env.py`, `sample_personas.py`, `prepare_briefs.py`, `aggregate.py` stay stdlib-only.
- Scripts never call an LLM. Agent work is dispatched by the orchestrator per `SKILL.md`.
- Nothing writes under `skills/persona-panel/` at run time. Runnable scripts set `sys.dont_write_bytecode = True` before other imports. State goes through `paths.py` (`~/.persona-panel` or `$PERSONA_PANEL_HOME`).
- Never relax the live-walker safety rules in `walk.py` (same-site only, no personal-data fields, no pay/sign-up/log-in).
- Keep `SKILL.md` short; it is read on every run. Keep script output to a few lines.
- A new config key touches `paths.DEFAULTS`, `config.py` `INIT_FLAGS`, `config.example.json`, `docs/CONFIGURATION.md` and tests.
- Don't bump `version` in `.claude-plugin/plugin.json` or edit `CHANGELOG.md` unless asked to prepare a release.
- Work on a branch and open a PR; `main` is protected (code-owner review, `ci-ok` check, squash merge).
