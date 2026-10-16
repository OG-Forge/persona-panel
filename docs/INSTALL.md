# Install

## Prerequisites

- **Claude Code.** The one-step install command needs 2.1.275 or later; the two-step one works on older versions with plugin support.
- **Python 3.10 or newer** on your PATH (`python`, `python3` or `py -3`). The scripts that run before setup (`config.py`, `setup_env.py`) use only the standard library.
- **Disk space:** about 150-300 MB for Playwright's Chromium, plus the venv.
- **Linux only:** Chromium may need system libraries. `config.py doctor` prints the exact command if it does.

Concept mode never opens a browser, but setup still installs Playwright so site mode works later.

## Option 1: plugin (recommended)

Inside Claude Code:

```
/plugin marketplace add OG-Forge/persona-panel
/plugin install persona-panel@og-forge
```

Or, on Claude Code 2.1.275+:

```
/plugin install persona-panel --marketplace OG-Forge/persona-panel
```

The same works from a terminal:

```bash
claude plugin marketplace add OG-Forge/persona-panel
claude plugin install persona-panel@og-forge
```

`claude plugin install` takes `--scope user|project|local` (default `user`). Use `--scope project` to enable it for one repository only.

Installing from the `/plugin` panel loads the plugin straight away. After a typed `/plugin install` or `claude plugin install`, run `/reload-plugins` in your session (or start a new one). The skill is invoked as `/persona-panel:persona-panel`, or in plain language ("run a persona panel on https://...").

## Option 2: manual clone and link

Use this if you want to edit the skill, or don't want the plugin system.

```bash
git clone https://github.com/OG-Forge/persona-panel.git
```

Link the **`skills/persona-panel`** folder (not the repo root) into your skills folder.

Windows (PowerShell, a junction needs no admin rights):

```powershell
New-Item -ItemType Junction -Path "$HOME\.claude\skills\persona-panel" -Target "C:\path\to\persona-panel\skills\persona-panel"
```

macOS / Linux:

```bash
mkdir -p ~/.claude/skills
ln -s "/path/to/persona-panel/skills/persona-panel" ~/.claude/skills/persona-panel
```

For one project only, link it into that project's `.claude/skills/persona-panel` instead of `~/.claude/skills/`.

A manual install is invoked as `/persona-panel`, or in plain language. Update it with `git pull` in the clone.

**Don't install both ways at once.** Claude Code would see two copies of the skill. If you switch to the plugin, remove the link first:

```powershell
# Windows: removes the junction only, not the clone
(Get-Item "$HOME\.claude\skills\persona-panel").Delete()
```

```bash
# macOS / Linux: removes the symlink only
rm ~/.claude/skills/persona-panel
```

## First-time setup

Setup creates a private venv with Playwright and Pillow in `~/.persona-panel/.venv`, and downloads Chromium into Playwright's browser cache. The easiest way is to ask Claude:

```
/persona-panel:persona-panel setup
```

(`/persona-panel setup` for a manual install.) Claude asks a few configuration questions, asks before installing anything, then runs the steps below.

To do it yourself, first find the skill folder, `<skill>`:

- Manual install: `<clone>/skills/persona-panel`.
- Plugin: run `claude plugin list --json`, take `installPath` of `persona-panel@og-forge`, and append `/skills/persona-panel`. It sits under `~/.claude/plugins/cache/` and changes with every version, which is why nothing is stored there.

Then:

```bash
python <skill>/scripts/setup_env.py          # about 2 minutes; prints the venv's python path
python <skill>/scripts/config.py init        # optional: write ~/.persona-panel/config.json (see CONFIGURATION.md)
python <skill>/scripts/config.py doctor      # checks everything and prints a fix for each problem
```

Use `python3` on macOS/Linux and `py -3` on Windows if `python` isn't 3.10+.

What goes where:

| What | Where |
|---|---|
| venv (Playwright, Pillow) | `~/.persona-panel/.venv` |
| user config | `~/.persona-panel/config.json` |
| your custom markets | `~/.persona-panel/markets/<name>.json` |
| run folders and reports | `~/.persona-panel/runs/` (or `runs_dir`) |
| Chromium | Playwright's cache: `%LOCALAPPDATA%\ms-playwright` (Windows), `~/Library/Caches/ms-playwright` (macOS), `~/.cache/ms-playwright` (Linux) |

Set the environment variable `PERSONA_PANEL_HOME` to move `~/.persona-panel` somewhere else. The skill folder itself is never written to.

## Updating

Plugin, inside a Claude Code session:

- `/plugin` → **Marketplaces** → `og-forge` → **Update marketplace**, or
- `/plugin` → **Installed** → `persona-panel` → **Update now**.

Plugin, from a shell:

```bash
claude plugin marketplace update og-forge
claude plugin update persona-panel@og-forge
```

Then run `/reload-plugins` in your session, or start a new session.

Auto-update is off by default for third-party marketplaces such as `og-forge`. Turn it on in `/plugin` → **Marketplaces** → `og-forge`.

Your venv, config, markets and runs live in `~/.persona-panel/` and survive updates. If a release changes `requirements.txt`, the CHANGELOG says so; re-run `setup_env.py` then.

Manual install: `git pull` in the clone.

Upgrading from 0.1.x: the old venv inside the skill folder still works until you run `setup_env.py`, which creates the new one in `~/.persona-panel/.venv`. `config.py doctor` warns while the old one is in use. Delete `skills/persona-panel/.venv` and `skills/persona-panel/runs` afterwards (move any runs you want to keep first).

## Uninstalling

Plugin:

```
/plugin uninstall persona-panel@og-forge
/plugin marketplace remove og-forge
```

Manual install: remove the link (see above) and delete the clone.

Then delete the state folder if you no longer want your config, markets and reports:

```powershell
Remove-Item -Recurse -Force "$HOME\.persona-panel"
```

```bash
rm -rf ~/.persona-panel
```

Chromium stays in Playwright's cache (shared with any other Playwright tools). Remove `chromium-*` there if nothing else uses it.

## Troubleshooting

Start with `python <skill>/scripts/config.py doctor`. It checks Python, the config files, the venv, a headless Chromium launch, the runs folder and every market, and prints a fix for each failure. `--skip-browser` skips the Chromium launch.

| Symptom | Fix |
|---|---|
| `venv missing` | `python <skill>/scripts/setup_env.py` |
| `Chromium won't launch` | `"<venv python>" -m playwright install chromium`; on Linux also `"<venv python>" -m playwright install-deps chromium` |
| `config error: ...` | Fix the JSON by hand, or `config.py init --force` with the values you want |
| `Market 'x' not found` | Check the name with `config.py show`, or add `~/.persona-panel/markets/x.json` |
| The skill isn't listed | Run `/reload-plugins` or start a new session. For a manual install, check the link points at `skills/persona-panel`, not the repo root |
| The skill appears twice | You have both the plugin and a manual link. Remove one |
| `python` is Python 2 or too old | Use `python3` (macOS/Linux) or `py -3` (Windows) |
| Capture says PASSWORD/LOGIN WALL | The site needs a login. persona-panel only reviews public pages |

`config.py show` prints the effective config, where each value came from, and every path above.
