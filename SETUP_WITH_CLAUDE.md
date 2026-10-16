# Set up persona-panel (instructions for an AI agent)

You are an AI coding agent (normally Claude Code) helping a user install and configure persona-panel from https://github.com/OG-Forge/persona-panel. Follow these steps in order. Every command you may run is listed here; don't run anything else that installs or deletes software.

Rules:

- **Ask before installing anything** (step 3 and step 5) and **before anything that spends tokens** (step 8). Wait for a yes.
- Don't use `sudo`, don't install system packages, don't change global Python. Everything this tool installs goes into `~/.persona-panel/` and Playwright's browser cache.
- Show the user each command's important output (errors, final lines). If a step fails, stop and report the error and the fix that `config.py doctor` or the error message suggests.

## 1. Detect the environment

Work out the OS from your environment (or `uname -s`; on Windows `$env:OS` in PowerShell). Then find a Python 3.10+ interpreter, trying in order:

- Windows: `py -3 --version`, then `python --version`
- macOS / Linux: `python3 --version`, then `python --version`

Call the first one that reports 3.10 or newer `PYTHON`. If none does, stop and tell the user to install Python 3.10+ from https://www.python.org/downloads/ (or their package manager), then re-run these instructions.

Check whether persona-panel is already installed:

```bash
claude plugin list --json
```

Look for an entry with `"id": "persona-panel@og-forge"`. Also check whether `~/.claude/skills/persona-panel` exists (a manual install). If it is installed already, set `SKILL` and skip to step 4:

- **Plugin already installed:** `SKILL` is that entry's `installPath` followed by `/skills/persona-panel`.
- **Manual install already linked:** `SKILL` is `~/.claude/skills/persona-panel` (written out as a full path, e.g. `$HOME/.claude/skills/persona-panel`).

In every command below, `PYTHON` is the interpreter from above (it may be two words, such as `py -3`, so it is not quoted) and `SKILL` is replaced by the full path. Keep the double quotes around paths: `SKILL` often contains spaces.

## 2. Choose the install route

Prefer the **plugin** route. Use the **manual** route only if the user asks for it, wants to edit the skill, or the `claude` command isn't available. Never set up both: Claude Code would load two copies of the skill.

## 3. Install (ask first)

Tell the user what you are about to run and ask for a yes.

**Plugin route** (works from a terminal; the user can type the same thing as `/plugin ...` inside Claude Code):

```bash
claude plugin marketplace add OG-Forge/persona-panel
claude plugin install persona-panel@og-forge
```

Then find the skill folder: run `claude plugin list --json`, take the `installPath` of `persona-panel@og-forge`, and append `/skills/persona-panel`. Call that `SKILL`.

The plugin loads in the user's Claude Code sessions after `/reload-plugins` or in a new session. (Installing from the `/plugin` panel inside a session reloads automatically.)

**Manual route.** Ask the user where to clone (default: their home folder), then:

```bash
git clone https://github.com/OG-Forge/persona-panel.git <CLONE>
```

Link the `skills/persona-panel` subfolder (not the repo root):

```powershell
# Windows (PowerShell; a junction needs no admin rights)
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
New-Item -ItemType Junction -Path "$HOME\.claude\skills\persona-panel" -Target "<CLONE>\skills\persona-panel"
```

```bash
# macOS / Linux
mkdir -p ~/.claude/skills
ln -s "<CLONE>/skills/persona-panel" ~/.claude/skills/persona-panel
```

`SKILL` is `<CLONE>/skills/persona-panel`.

## 4. Ask the configuration questions

Show the current values first:

```bash
PYTHON "SKILL/scripts/config.py" show
```

Then ask the user, in one message, offering the current values as defaults:

1. **Who are your customers?** `india` (Indian online shoppers), `global` (English-speaking international shoppers), or a description of another audience.
2. **Default panel size** (`n`, default 100; at least 30).
3. **Live browser walkers per site run** (`live`, default 4; 0 saves tokens).
4. **Default lens:** full customer review (default), `ux` (usability and looks only) or `visual` (looks only).
5. **Where should reports go?** (default `~/.persona-panel/runs`)
6. **Any standing question** the panel should always answer? (optional)
7. **For all projects, or just the current folder?** (user config vs project config)

If they describe a different audience, write a custom market to `~/.persona-panel/markets/<name>.json` following `SKILL/references/custom-market.md`, show it to them, and use `<name>` as the market.

## 5. Install the runtime (ask first)

Say: "This creates a Python venv in ~/.persona-panel/.venv and installs Playwright, Pillow and Chromium (about 150-300 MB, ~2 minutes). OK?" Then:

```bash
PYTHON "SKILL/scripts/setup_env.py"
```

It prints the venv's Python path at the end.

## 6. Write the config

Pass only the answers that differ from the defaults. For a user-wide config:

```bash
PYTHON "SKILL/scripts/config.py" init --market MARKET --n N --live L --lens ux|visual|default --runs-dir "DIR" --default-focus "QUESTION"
```

Add `--project` to write `./.persona-panel.json` for the current folder instead. If the file already exists, ask before adding `--force` (it overwrites).

## 7. Check

```bash
PYTHON "SKILL/scripts/config.py" doctor
```

Apply the fixes it prints and re-run until it says "All checks passed." On Linux, if Chromium fails for missing libraries, the fix it prints (`playwright install-deps`) may need `sudo`: show it to the user and let them run it.

A free (no tokens) sanity check of the sampler:

```bash
PYTHON "SKILL/scripts/sample_personas.py" --run "RUNS_DIR/setup-check-YYYYMMDD" --mode concept --n 30
```

`RUNS_DIR` is the `runs_dir` value from `config.py show` and `YYYYMMDD` is today's date. It should print "Wrote 30 personas, 3 panel batches, 0 live walkers". Don't delete anything: tell the user the `setup-check-YYYYMMDD` folder in their runs folder is only this check and they can delete it whenever they like.

## 8. Optional smoke test (ask first: it spends tokens)

Ask: "Want a small test run? It's a 30-persona concept panel: 3 Haiku agents and 1 Sonnet pass, no browser." Only if they say yes: the skill loads after `/reload-plugins` or in a new Claude Code session, so ask the user to run `/reload-plugins` (or open a new session) and then:

```
/persona-panel:persona-panel concept: <a one-line idea of theirs> -- 30 personas
```

(`/persona-panel` for a manual install.)

## 9. Report to the user

Tell the user:

- the install route used and where the skill lives (`SKILL`);
- the config file written and its values (paste `config.py show` output);
- the `doctor` result;
- how to run it: `/persona-panel:persona-panel https://their-site.com` or `/persona-panel:persona-panel concept: ...` (or `/persona-panel ...` for a manual install), or plain language;
- that a newly installed plugin loads after `/reload-plugins` or in a new session (installing from the `/plugin` panel reloads automatically);
- how to update: in a session, `/plugin` → Marketplaces → `og-forge` → Update marketplace (or `/plugin` → Installed → `persona-panel` → Update now); from a shell, `claude plugin marketplace update og-forge` then `claude plugin update persona-panel@og-forge`; then `/reload-plugins` or a new session. Auto-update is off by default for third-party marketplaces; it can be turned on in `/plugin` → Marketplaces. For a manual install, `git pull` in the clone;
- that results are simulated customers, useful for finding friction but not for predicting conversion, and that they should only run it against sites they own or may test.

Docs: https://github.com/OG-Forge/persona-panel/tree/main/docs
