"""Plugin manifests, requirements, setup_env, and the 'never write under SKILL_DIR' rule."""
import os
import re
import subprocess
import sys
from pathlib import Path

import setup_env
from conftest import REPO, SKILL, read_json

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
REPO_URL = "https://github.com/OG-Forge/persona-panel"


def test_plugin_manifest():
    p = read_json(REPO / ".claude-plugin" / "plugin.json")
    assert p["name"] == "persona-panel"
    assert SEMVER.match(p["version"])
    assert p["description"]
    assert p["license"] == "MIT"
    assert p["homepage"] == REPO_URL and p["repository"] == REPO_URL
    assert isinstance(p["keywords"], list) and p["keywords"]
    assert p["author"]["name"]


def test_marketplace_manifest():
    m = read_json(REPO / ".claude-plugin" / "marketplace.json")
    plugin = read_json(REPO / ".claude-plugin" / "plugin.json")
    assert m["name"] == "og-forge"
    assert m["owner"]["name"]
    assert m["description"]
    assert len(m["plugins"]) == 1
    entry = m["plugins"][0]
    assert entry["name"] == plugin["name"]
    assert entry["source"] == "./"
    assert entry["description"]
    assert "version" not in entry, "version lives in plugin.json only"


def test_skill_frontmatter():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "SKILL.md needs YAML frontmatter"
    fields = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
    assert fields["name"].strip() == "persona-panel"
    assert len(fields["description"].strip()) > 50


def test_no_hardcoded_local_paths_or_skill_dir_state():
    for f in list(SKILL.rglob("*.md")) + list(SKILL.rglob("*.py")) + list((REPO / ".claude-plugin").glob("*.json")):
        if ".venv" in f.parts or "runs" in f.parts:
            continue
        text = f.read_text(encoding="utf-8")
        for local in ("D:" + "/OG Forge", "D:" + "\\OG Forge"):  # split so this file doesn't match itself
            assert local not in text, f
    skill_md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "SKILL_DIR/.venv" not in skill_md and "SKILL_DIR/runs" not in skill_md


def test_requirements_match_setup_env_fallback():
    lines = [l.strip() for l in (REPO / "requirements.txt").read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
    assert lines == list(setup_env.FALLBACK_REQUIREMENTS)
    assert any(l.startswith("playwright") for l in lines) and any(l.startswith("pillow") for l in lines)
    dev = (REPO / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "pytest" in dev


def test_setup_env_targets_home_venv(home):
    assert setup_env.target_venv() == home / ".venv"
    assert setup_env.requirements_file() == REPO / "requirements.txt"


def test_config_example_is_valid(home):
    import paths
    example = read_json(REPO / "config.example.json")
    keys = {k for k in example if not k.startswith("_")}
    assert keys <= set(paths.DEFAULTS)
    assert keys == set(paths.DEFAULTS) - {"runs_dir"}, "example should document every key except runs_dir"
    comments = " ".join(v for k, v in example.items() if k.startswith("_"))
    assert "runs_dir" in comments and "~/.persona-panel" in comments, "explain the runs_dir default in a comment"
    paths.validate(example, "config.example.json")


def test_scripts_never_write_bytecode_into_skill(tmp_path, monkeypatch, skill_copy):
    copy = skill_copy
    monkeypatch.setenv("PERSONA_PANEL_HOME", str(tmp_path / "home"))
    env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
    for args in (["sample_personas.py", "--run", str(tmp_path / "run"), "--mode", "concept", "--n", "30"],
                 ["config.py", "show"]):
        subprocess.run([sys.executable, str(copy / "scripts" / args[0]), *args[1:]], check=True,
                       capture_output=True, cwd=tmp_path, env=env)
    assert not list(copy.rglob("__pycache__"))
    assert not list(copy.rglob("*.pyc"))


def test_gitattributes_normalises_line_endings():
    text = (REPO / ".gitattributes").read_text(encoding="utf-8")
    for line in ("* text=auto eol=lf", "*.png binary", "*.jpg binary", "*.ps1 text eol=crlf"):
        assert line in text


def test_gitignore_ignores_local_claude_settings():
    assert ".claude/settings.local.json" in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_docs_never_use_session_plugin_update_command():
    for f in [*REPO.glob("*.md"), *(REPO / "docs").glob("*.md"), *SKILL.rglob("*.md")]:
        if ".venv" in f.parts:
            continue
        text = f.read_text(encoding="utf-8")
        assert "/plugin update" not in text, f
        assert "restart claude code" not in text.lower(), f
