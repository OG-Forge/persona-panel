"""One-time setup: create the skill's private venv and install Playwright + Chromium.

Usage: python scripts/setup_env.py     (any Python 3.10+)
Prints the venv's python path, which every other script should be run with.
"""
import os
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
VENV = SKILL_DIR / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(*cmd):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def main():
    if not PY.exists():
        run(sys.executable, "-m", "venv", VENV)
    run(PY, "-m", "pip", "install", "-q", "--upgrade", "pip")
    run(PY, "-m", "pip", "install", "-q", "playwright>=1.50", "pillow>=10")
    run(PY, "-m", "playwright", "install", "chromium")
    print(f"\nReady. Python for this skill: {PY}")


if __name__ == "__main__":
    main()
