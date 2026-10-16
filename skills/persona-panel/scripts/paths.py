"""Where persona-panel keeps its state, and the merged user configuration (stdlib only).

The skill folder is read-only at run time (a plugin install lives in a cache that
is replaced on every update), so everything mutable lives in HOME_DIR:

  HOME_DIR = $PERSONA_PANEL_HOME, else ~/.persona-panel
    .venv/          Python venv with Playwright + Pillow (setup_env.py creates it)
    config.json     user config
    markets/        user market profiles; <name>.json shadows a bundled market
    runs/           run folders (unless config "runs_dir" says otherwise)

Config precedence (later wins): built-in defaults < HOME_DIR/config.json
< ./.persona-panel.json (current directory) < command-line flags.
Keys starting with "_" are comments and are ignored. A key set to null in a config
file is skipped, so the lower layer (or the default) still applies. Path-like values
for "runs_dir" and "market" ("~" allowed) are resolved against the folder of the
config file they appear in.
"""
import json
import os
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
BUNDLED_MARKETS_DIR = SKILL_DIR / "data" / "markets"
LENSES_DIR = SKILL_DIR / "references" / "lenses"
PROJECT_CONFIG_NAME = ".persona-panel.json"
LEGACY_VENV_DIR = SKILL_DIR / ".venv"  # where versions before 0.2 put the venv

DEFAULTS = {
    "market": "india",          # bundled or user market name, or a path to a market JSON
    "n": 100,                   # personas per panel
    "live": 4,                  # live browser walkers (site mode)
    "lens": "",                 # "" = full customer review; or a lens name such as ux / visual
    "seed": 7,                  # same seed = same personas
    "min_per_screen": 10,       # site mode: minimum tablet/laptop/desktop reviewers each
    "batch_size": 10,           # personas per panel agent
    "wave_size": 3,             # panel agents dispatched at once
    "panel_model": "haiku",     # model for panel batches and live walkers
    "synthesis_model": "sonnet",
    "runs_dir": None,           # None = HOME_DIR/runs
    "default_focus": "",        # focus questions used when --focus isn't given
}
INT_MIN = {"n": 1, "live": 0, "seed": None, "min_per_screen": 0, "batch_size": 1, "wave_size": 1}
STR_KEYS = {"market", "lens", "panel_model", "synthesis_model", "runs_dir", "default_focus"}
FULL_REVIEW_ALIASES = {"", "default", "none", "full"}


class ConfigError(Exception):
    pass


def home_dir():
    env = os.environ.get("PERSONA_PANEL_HOME", "").strip()
    return Path(env).expanduser().resolve() if env else Path.home() / ".persona-panel"


def run_dir_arg(value):
    """A --run argument as an absolute path ("~" expanded, relative paths against the cwd)."""
    return Path(str(value)).expanduser().resolve()


def is_path_like(value):
    """True when a market value names a file rather than a market."""
    value = str(value)
    return bool(Path(value).suffix) or "/" in value or "\\" in value or value.startswith("~")


def venv_python(venv=None):
    venv = Path(venv) if venv else venv_dir()
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def home_venv_dir():
    return home_dir() / ".venv"


def legacy_venv_dir():
    return LEGACY_VENV_DIR


def venv_dir():
    new = home_venv_dir()
    if not venv_python(new).exists() and venv_python(legacy_venv_dir()).exists():
        return legacy_venv_dir()
    return new


def user_config_path():
    return home_dir() / "config.json"


def project_config_path(cwd=None):
    return Path(cwd or Path.cwd()) / PROJECT_CONFIG_NAME


def user_markets_dir():
    return home_dir() / "markets"


def normalize_lens(value):
    return "" if str(value).strip().lower() in FULL_REVIEW_ALIASES else str(value).strip()


def validate(data, where):
    """Check a config dict; returns the known keys (comments dropped). Raises ConfigError."""
    if not isinstance(data, dict):
        raise ConfigError(f"{where}: config must be a JSON object")
    out = {}
    for key, value in data.items():
        if key.startswith("_") or key.startswith("$") or value is None:
            continue  # comments, and nulls (the lower config layer or the default applies)
        if key not in DEFAULTS:
            print(f"persona-panel: ignoring unknown config key '{key}' in {where} "
                  f"(known: {', '.join(DEFAULTS)})", file=sys.stderr)
            continue
        if key in INT_MIN:
            if not isinstance(value, int) or isinstance(value, bool):
                raise ConfigError(f"{where}: '{key}' must be a whole number, got {value!r}")
            low = INT_MIN[key]
            if low is not None and value < low:
                raise ConfigError(f"{where}: '{key}' must be at least {low}, got {value}")
        elif key in STR_KEYS:
            if not isinstance(value, str):
                raise ConfigError(f"{where}: '{key}' must be a string, got {value!r}")
            elif key in ("market", "panel_model", "synthesis_model", "runs_dir") and not value.strip():
                raise ConfigError(f"{where}: '{key}' must not be empty")
        if key == "lens":
            value = normalize_lens(value)
        out[key] = value
    return out


def read_config_file(path):
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise ConfigError(f"{path}: not valid JSON ({e})")
    data = validate(data, str(path))
    for key in ("runs_dir", "market"):
        if data.get(key) and (key == "runs_dir" or is_path_like(data[key])):
            p = Path(data[key]).expanduser()
            data[key] = str(p if p.is_absolute() else (path.parent / p).resolve())
    return data


def load_config_with_files(cwd=None):
    """(config, sources, files): merged config; per key 'default', 'user (<path>)' or 'project (<path>)';
    and the config files that supplied at least one value, in load order."""
    cfg = dict(DEFAULTS)
    sources = {k: "default" for k in DEFAULTS}
    files = []
    for label, path in (("user", user_config_path()), ("project", project_config_path(cwd))):
        data = read_config_file(path)
        for key, value in data.items():
            cfg[key] = value
            sources[key] = f"{label} ({path})"
        if data:
            files.append(path)
    if not cfg["runs_dir"]:
        cfg["runs_dir"] = str(home_dir() / "runs")
    return cfg, sources, files


def load_config_with_sources(cwd=None):
    """(config, sources): see load_config_with_files."""
    return load_config_with_files(cwd)[:2]


def load_config(cwd=None):
    return load_config_with_sources(cwd)[0]


def config_or_exit():
    """For scripts: the merged config, or exit with a readable message."""
    try:
        return load_config()
    except ConfigError as e:
        sys.exit(f"persona-panel config error: {e}\nFix the file, or run: python \"{SCRIPTS_DIR / 'config.py'}\" doctor")


def runs_dir(cfg=None):
    return Path((cfg or load_config())["runs_dir"])


IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


def _norm(path):
    """Resolved, case-normalised (on Windows) form of a path, for containment checks."""
    return Path(os.path.normcase(str(Path(path).expanduser().resolve())))


def is_inside(path, root):
    """True if `path` resolves to `root` or something under it (symlinks and '..' resolved first)."""
    try:
        return _norm(path).is_relative_to(_norm(root))
    except (OSError, ValueError):
        return False


def safe_image(path, roots):
    """The resolved path of an existing .png/.jpg/.jpeg/.webp file inside one of `roots`, else None.

    Screenshot paths come from agent output (which a hostile website may have steered), so
    briefs and the report only ever open images that this check accepts."""
    if not path:
        return None
    try:
        p = Path(str(path)).expanduser().resolve()
    except (OSError, ValueError):
        return None
    if p.suffix.lower() not in IMAGE_SUFFIXES or not p.is_file():
        return None
    return p if any(is_inside(p, r) for r in roots if r) else None


def image_roots(run, cfg=None):
    """Where run screenshots may live: the configured runs folder, and the run folder itself."""
    try:
        roots = [runs_dir(cfg)]
    except ConfigError:
        roots = []
    return roots + [Path(run)]


def run_relative(run, path):
    """`path` relative to the run folder, with forward slashes (how probes.json stores screenshots)."""
    return Path(path).resolve().relative_to(Path(run).resolve()).as_posix()


def run_file(run, path):
    """A path stored in run data: relative paths are relative to the run folder (older runs stored absolute ones)."""
    p = Path(str(path))
    return p if p.is_absolute() else Path(run) / p


def available_markets():
    """name -> path; user markets shadow bundled ones."""
    found = {p.stem: p for p in sorted(BUNDLED_MARKETS_DIR.glob("*.json"))}
    if user_markets_dir().is_dir():
        found.update({p.stem: p for p in sorted(user_markets_dir().glob("*.json"))})
    return found


def find_market(name_or_path):
    """A market name (user markets first, then bundled) or a path to a market JSON."""
    value = str(name_or_path)
    p = Path(value).expanduser()
    if is_path_like(value):
        if p.exists():
            return p
        raise FileNotFoundError(f"Market file not found: {p}")
    markets = available_markets()
    if value in markets:
        return markets[value]
    raise FileNotFoundError(f"Market '{value}' not found. Available: {', '.join(sorted(markets))} "
                            f"(add your own as {user_markets_dir() / (value + '.json')})")


def available_lenses():
    return sorted(p.stem for p in LENSES_DIR.glob("*.md") if (LENSES_DIR / f"{p.stem}.json").exists())
