"""Shared fixtures. Tests are offline: no browser, no network, no LLM calls.

Every test gets its own PERSONA_PANEL_HOME and working directory under tmp_path,
so nothing touches the real ~/.persona-panel or a project config in the repo.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True  # never leave __pycache__ inside the skill folder

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "skills" / "persona-panel"
SCRIPTS = SKILL / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An isolated persona-panel home dir, and a clean cwd (no project config)."""
    import paths
    h = tmp_path / "pp-home"
    monkeypatch.setenv("PERSONA_PANEL_HOME", str(h))
    monkeypatch.setattr(paths, "LEGACY_VENV_DIR", tmp_path / "no-legacy-venv")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return h


@pytest.fixture
def skill_copy(tmp_path):
    """A copy of the skill folder without any local .venv/runs, for subprocess tests that must not
    see a developer's legacy SKILL_DIR/.venv."""
    copy = tmp_path / "skill-copy"
    shutil.copytree(SKILL, copy, ignore=shutil.ignore_patterns(".venv", "runs", "__pycache__"))
    return copy


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


@pytest.fixture
def run_script(home):
    """Run a skill script in a subprocess with the test's home and cwd; returns CompletedProcess."""
    def _run(name, *args, check=True, cwd=None, scripts=SCRIPTS, env_extra=None):
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1", **(env_extra or {})}
        env = {k: v for k, v in env.items() if v is not None}
        r = subprocess.run([sys.executable, str(Path(scripts) / name), *[str(a) for a in args]],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           cwd=str(cwd or os.getcwd()), env=env)
        if check and r.returncode != 0:
            raise AssertionError(f"{name} {args} exited {r.returncode}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}")
        return r
    return _run
