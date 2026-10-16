"""One-time setup: create persona-panel's private venv and install Playwright + Chromium.

Usage: python scripts/setup_env.py     (any Python 3.10+)
The venv goes to ~/.persona-panel/.venv (or $PERSONA_PANEL_HOME/.venv), outside the
skill folder, so plugin updates don't wipe it. Chromium goes to Playwright's own
browser cache. Prints the venv's python path, which every other script should be run with.
"""
import sys

sys.dont_write_bytecode = True  # keep the skill folder read-only

import subprocess

import paths

# Same pins as requirements.txt at the repo root; used when the skill folder was copied on its own.
FALLBACK_REQUIREMENTS = ("playwright>=1.50", "pillow>=10")


def target_venv():
    return paths.home_venv_dir()


def requirements_file():
    """requirements.txt at the repo / plugin root, if this skill still sits inside it."""
    f = paths.SKILL_DIR.parent.parent / "requirements.txt"
    return f if f.exists() else None


def run(*cmd):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def main():
    if sys.version_info < (3, 10):
        sys.exit(f"persona-panel needs Python 3.10+, this is {sys.version.split()[0]}")
    venv = target_venv()
    py = paths.venv_python(venv)
    if not py.exists():
        venv.parent.mkdir(parents=True, exist_ok=True)
        run(sys.executable, "-m", "venv", venv)
    run(py, "-m", "pip", "install", "-q", "--upgrade", "pip")
    req = requirements_file()
    if req:
        run(py, "-m", "pip", "install", "-q", "-r", req)
    else:
        run(py, "-m", "pip", "install", "-q", *FALLBACK_REQUIREMENTS)
    run(py, "-m", "playwright", "install", "chromium")
    print(f"\nReady. Python for this skill: {py}")
    if paths.venv_python(paths.legacy_venv_dir()).exists():
        print(f"(An old venv from an earlier version is still at {paths.legacy_venv_dir()}; it is no longer used "
              f"and can be deleted.)")


if __name__ == "__main__":
    main()
