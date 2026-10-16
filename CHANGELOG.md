# Changelog

All notable changes to persona-panel. Versions follow [semantic versioning](https://semver.org/); the version lives in `.claude-plugin/plugin.json`.

## 0.2.0 - 2026-10-16

First public release as the `og-forge` plugin marketplace on GitHub.

### Added

- Plugin marketplace: install with `/plugin marketplace add OG-Forge/persona-panel` and `/plugin install persona-panel@og-forge`.
- Configuration: user config `~/.persona-panel/config.json` and project config `./.persona-panel.json`, with keys `market`, `n`, `live`, `lens`, `seed`, `min_per_screen`, `batch_size`, `wave_size`, `panel_model`, `synthesis_model`, `runs_dir`, `default_focus`. Script flags default to the config.
- `scripts/config.py`: `show [--json]`, `init` (with `--project`, `--force`) and `doctor [--skip-browser]`. `init` writes only the keys you pass, so unset keys follow future default changes.
- Config files: a `null` value is skipped; relative `runs_dir` and market-file paths resolve against the config file's folder, with `~` expanded.
- Every script's `--run` expands `~` and accepts relative paths.
- User markets in `~/.persona-panel/markets/<name>.json`; they shadow built-in markets with the same name. `--market` also accepts a path.
- Setup flow in the skill: `/persona-panel:persona-panel setup` asks a few questions, installs the runtime and writes the config.
- `PERSONA_PANEL_HOME` environment variable to move the state folder.
- `requirements.txt` and `requirements-dev.txt`.
- Offline pytest suite and CI on Ubuntu and Windows, Python 3.10 and 3.12.
- Docs: install, configuration, usage, how it works, setup instructions for an AI agent, contributing, security policy, code of conduct.

### Changed

- **State moved out of the skill folder.** The venv is now `~/.persona-panel/.venv` and runs go to `~/.persona-panel/runs/` (or `runs_dir`), so plugin updates don't wipe them. Scripts no longer write anything, including `__pycache__`, inside the skill folder.
- Panel and synthesis models and the wave size come from the config instead of being fixed in SKILL.md.
- Market and overrides files may start with a UTF-8 byte-order mark (as some Windows editors save them); a broken one stops with a one-line message naming the file.

### Upgrading from 0.1.0

- Run `setup_env.py` once to create the new venv. Until then the old `skills/persona-panel/.venv` is still used, and `config.py doctor` warns about it.
- Move any runs you want to keep out of `skills/persona-panel/runs/`, then delete that folder and the old `.venv`.
- If you used a manual link and now install the plugin, remove the link so the skill isn't loaded twice.

## 0.1.0

Initial version, installed by cloning and linking the skill folder.

- Simulated customer panel of 100+ personas sampled from weighted market profiles (`india`, `global`) with coherence rules and guaranteed segment coverage; overrides files and custom markets.
- Site mode: `capture.py` (screenshots on phone, tablet, laptop and desktop plus a facts digest), live walkers driving `walk.py` with code-enforced safety rules.
- Measured UX checks (`probe.py`) on six screen sizes: section and card fit, in-page jumps, Back-button scroll restore, sticky overlays, overflow, with annotated screenshots.
- Concept mode for ideas, pitches, pricing and mockups.
- Lenses: `ux` and `visual`.
- Aggregation, one synthesis pass, and a self-contained HTML report with evidence screenshots and "Copy as bug".
- Redo briefs for missing personas (`prepare_briefs.py --only`).
