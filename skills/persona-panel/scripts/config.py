"""Show, create and check the persona-panel configuration (stdlib only; any Python 3.10+).

Usage:
  python config.py show [--json]          effective config, where each value came from, and key paths
  python config.py init [--market india] [--n 100] [--live 4] [--lens ux|visual|default] [--seed 7]
                        [--min-per-screen 10] [--batch-size 10] [--wave-size 3]
                        [--panel-model haiku] [--synthesis-model sonnet]
                        [--runs-dir PATH] [--default-focus "..."] [--project] [--force]
                                          write ~/.persona-panel/config.json (or ./.persona-panel.json
                                          with --project); refuses to overwrite without --force
  python config.py doctor [--skip-browser]
                                          check Python, venv, Playwright + Chromium, runs dir, markets
                                          and lens; prints a fix for each problem; exit 1 on failure

Precedence (later wins): defaults < ~/.persona-panel/config.json < ./.persona-panel.json < CLI flags.
$PERSONA_PANEL_HOME moves ~/.persona-panel.

init writes only the keys you pass (plus a comment), so built-in defaults you didn't
set keep tracking new releases. show --json prints paths with forward slashes, which
work in PowerShell, cmd and Git Bash alike.
"""
import sys

sys.dont_write_bytecode = True  # keep the skill folder read-only

import argparse
import json
import subprocess
import uuid
from pathlib import Path

import paths

INIT_FLAGS = {  # config key -> (flag, type)
    "market": ("--market", str), "n": ("--n", int), "live": ("--live", int), "lens": ("--lens", str),
    "seed": ("--seed", int), "min_per_screen": ("--min-per-screen", int), "batch_size": ("--batch-size", int),
    "wave_size": ("--wave-size", int), "panel_model": ("--panel-model", str),
    "synthesis_model": ("--synthesis-model", str), "runs_dir": ("--runs-dir", str),
    "default_focus": ("--default-focus", str),
}
COMMENT = ("persona-panel config. Keys starting with '_' are ignored; keys you leave out use the built-in "
           "defaults. Precedence: defaults < this file (~/.persona-panel/config.json) < ./.persona-panel.json "
           "< command-line flags. Check with: config.py show / config.py doctor")
SETUP = f'python "{paths.SCRIPTS_DIR / "setup_env.py"}"'


def path_info(fmt=str):
    """Key paths as strings; fmt=posix gives forward slashes (for --json)."""
    venv = paths.venv_dir()
    py = paths.venv_python(venv)
    return {
        "home": fmt(paths.home_dir()),
        "user_config": fmt(paths.user_config_path()),
        "user_config_exists": paths.user_config_path().exists(),
        "project_config": fmt(paths.project_config_path()),
        "project_config_exists": paths.project_config_path().exists(),
        "user_markets": fmt(paths.user_markets_dir()),
        "venv": fmt(venv),
        "python": fmt(py),
        "venv_exists": py.exists(),
        "legacy_venv": venv != paths.home_venv_dir(),
        "skill_dir": fmt(paths.SKILL_DIR),
        "scripts_dir": fmt(paths.SCRIPTS_DIR),
    }


def posix(p):
    return Path(p).as_posix()


def cmd_show(args):
    try:
        cfg, sources = paths.load_config_with_sources()
    except paths.ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2
    if args.json:
        cfg = dict(cfg, runs_dir=posix(cfg["runs_dir"]))
        if paths.is_path_like(cfg["market"]):
            cfg["market"] = posix(cfg["market"])
        out = {"config": cfg, "sources": sources, "paths": path_info(posix),
               "markets": {k: posix(v) for k, v in paths.available_markets().items()},
               "lenses": paths.available_lenses()}
        print(json.dumps(out, indent=1, ensure_ascii=False))
        return 0
    info = path_info()
    width = max(len(k) for k in cfg)
    print("persona-panel config (value, then where it came from)")
    for key, value in cfg.items():
        if key == "lens" and not value:
            shown = '"" (full customer review)'
        elif key == "runs_dir":
            shown = value
        else:
            shown = json.dumps(value, ensure_ascii=False)
        print(f"  {key.ljust(width)}  {shown}  [{sources[key]}]")
    print("\nPaths")
    for key in ("home", "user_config", "project_config", "user_markets", "python", "skill_dir"):
        note = ""
        if key == "python" and not info["venv_exists"]:
            note = f"  (missing: run {SETUP})"
        elif key.endswith("_config") and not info[f"{key}_exists"]:
            note = "  (not created)"
        print(f"  {key.ljust(width)}  {info[key]}{note}")
    print(f"\nMarkets: {', '.join(paths.available_markets())}   Lenses: {', '.join(paths.available_lenses())}")
    return 0


def whole_number(flag):
    def parse(text):
        try:
            return int(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{flag} needs a whole number, got {text!r}")
    return parse


def cmd_init(args):
    target = paths.project_config_path() if args.project else paths.user_config_path()
    if target.exists() and not args.force:
        print(f"{target} already exists. Re-run with --force to overwrite it, or edit it by hand.", file=sys.stderr)
        return 1
    given = {key: getattr(args, key) for key in INIT_FLAGS if getattr(args, key) is not None}
    if "lens" in given:
        given["lens"] = paths.normalize_lens(given["lens"])
        if given["lens"] and given["lens"] not in paths.available_lenses():
            print(f"Unknown lens '{given['lens']}'. Available: default, {', '.join(paths.available_lenses())}", file=sys.stderr)
            return 1
    if "market" in given:
        try:
            paths.find_market(given["market"])
        except FileNotFoundError as e:
            print(e, file=sys.stderr)
            return 1
    if not args.project:  # a user config lives elsewhere, so pin relative paths to the cwd now
        for key in ("runs_dir", "market"):
            value = given.get(key)
            if value and (key == "runs_dir" or paths.is_path_like(value)):
                if not value.startswith("~") and not Path(value).is_absolute():
                    given[key] = str(Path(value).resolve())
    try:
        paths.validate(given, "command line")
    except paths.ConfigError as e:
        print(e, file=sys.stderr)
        return 1
    if args.project:
        data = {"_comment": "persona-panel project config; overrides ~/.persona-panel/config.json", **given}
    else:
        data = {"_comment": COMMENT, **given}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {target}")
    return 0


BROWSER_CHECK = """
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    b.close()
print("ok")
"""


class Doctor:
    def __init__(self):
        self.failed = 0

    def ok(self, what):
        print(f"[ok]   {what}")

    def warn(self, what, fix=""):
        print(f"[warn] {what}" + (f"\n       fix: {fix}" if fix else ""))

    def fail(self, what, fix=""):
        self.failed += 1
        print(f"[FAIL] {what}" + (f"\n       fix: {fix}" if fix else ""))


def market_problems(path):
    try:
        m = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        return f"not valid JSON ({e})"
    if not isinstance(m, dict):
        return "must be a JSON object"
    missing = [k for k in ("name", "attributes", "rules") if k not in m]
    if missing:
        return f"missing {', '.join(missing)} (see references/custom-market.md)"
    attrs = m["attributes"]
    if not isinstance(attrs, list) or not attrs:
        return "'attributes' must be a non-empty list"
    for a in attrs:
        if not isinstance(a, dict) or not isinstance(a.get("key"), str) or not isinstance(a.get("values"), dict) or not a["values"]:
            return f"bad attribute entry {a!r:.80}: needs 'key' and non-empty 'values'"
    return ""


def cmd_doctor(args):
    d = Doctor()
    v = sys.version_info
    if v >= (3, 10):
        d.ok(f"Python {v.major}.{v.minor} ({sys.executable})")
    else:
        d.fail(f"Python {v.major}.{v.minor} is too old", "install Python 3.10 or newer")

    try:
        cfg, sources, files = paths.load_config_with_files()
        listed = ", ".join(str(f) for f in files)
        d.ok("config loads" + (f" ({listed})" if files else " (defaults only; create one with: config.py init)"))
    except paths.ConfigError as e:
        d.fail(f"config error: {e}", "fix the JSON by hand, or recreate it with: config.py init --force")
        cfg = dict(paths.DEFAULTS, runs_dir=str(paths.home_dir() / "runs"))

    info = path_info()
    py = info["python"]
    venv_ok = False
    if not info["venv_exists"]:
        d.fail(f"venv missing: {py}", f"{SETUP}   (about 2 minutes; installs Playwright + Chromium)")
    else:
        if info["legacy_venv"]:
            d.warn(f"using the old venv inside the skill folder ({info['venv']})",
                   f"{SETUP} to create the new one in {paths.home_venv_dir()}")
        r = subprocess.run([py, "-c", "import sys, PIL, playwright; print('%d.%d' % sys.version_info[:2])"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            venv_ok = True
            d.ok(f"venv Python {r.stdout.strip()} with Playwright and Pillow ({py})")
        else:
            last = (r.stderr.strip().splitlines() or [f"exit code {r.returncode}"])[-1]
            d.fail(f"venv at {info['venv']} can't import Playwright/Pillow: {last}", SETUP)

    if args.skip_browser:
        d.warn("Chromium launch not checked (--skip-browser)")
    elif venv_ok:
        try:
            r = subprocess.run([py, "-c", BROWSER_CHECK], capture_output=True, text=True, timeout=180)
            launched = r.returncode == 0 and "ok" in r.stdout
            err = (r.stderr.strip().splitlines() or ["no output"])[-1]
        except subprocess.TimeoutExpired:
            launched, err = False, "timed out after 180s"
        if launched:
            d.ok("Chromium launches (headless)")
        else:
            fix = f'"{py}" -m playwright install chromium'
            if sys.platform.startswith("linux"):
                fix += f'   (Linux may also need system libraries: "{py}" -m playwright install-deps chromium)'
            d.fail(f"Chromium won't launch: {err}", fix)

    runs = Path(cfg["runs_dir"])
    try:
        runs.mkdir(parents=True, exist_ok=True)
        probe = runs / f".write-test-{uuid.uuid4().hex}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        d.ok(f"runs dir writable: {runs}")
    except OSError as e:
        d.fail(f"runs dir not writable: {runs} ({e})", 'set another folder: config.py init --force --runs-dir PATH')

    markets = paths.available_markets()
    bad = 0
    for name, path in markets.items():
        problem = market_problems(path)
        if problem:
            bad += 1
            d.fail(f"market {name} ({path}): {problem}", "fix or remove that file")
    if not bad:
        d.ok(f"markets load: {', '.join(markets)}")
    try:
        mpath = paths.find_market(cfg["market"])
        if mpath.stem not in markets or markets[mpath.stem] != mpath:
            problem = market_problems(mpath)
            if problem:
                d.fail(f"configured market {mpath}: {problem}")
        d.ok(f"configured market '{cfg['market']}' -> {mpath}")
    except FileNotFoundError as e:
        d.fail(f"configured market: {e}", "config.py init --force --market india   (or add the market file)")

    lens = cfg.get("lens") or ""
    if lens and lens not in paths.available_lenses():
        d.fail(f"configured lens '{lens}' not found (available: {', '.join(paths.available_lenses())})",
               "config.py init --force --lens default")
    else:
        d.ok(f"lens: {lens or 'full customer review'}")

    print("\nAll checks passed." if not d.failed else f"\n{d.failed} check(s) failed. Apply the fixes above and re-run doctor.")
    return 1 if d.failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="persona-panel configuration")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show", help="Print the effective config and where each value came from")
    s.add_argument("--json", action="store_true", help="Machine-readable output")
    i = sub.add_parser("init", help="Write a config file (user config unless --project)")
    for key, (flag, typ) in INIT_FLAGS.items():
        i.add_argument(flag, dest=key, type=whole_number(flag) if typ is int else str,
                       help=f"default: {paths.DEFAULTS[key] if paths.DEFAULTS[key] is not None else 'HOME_DIR/runs'}")
    i.add_argument("--project", action="store_true", help="Write ./.persona-panel.json in the current folder instead")
    i.add_argument("--force", action="store_true", help="Overwrite an existing file")
    dr = sub.add_parser("doctor", help="Check the install and print fixes")
    dr.add_argument("--skip-browser", action="store_true", help="Don't launch Chromium")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    return {"show": cmd_show, "init": cmd_init, "doctor": cmd_doctor}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
