"""config.py CLI: show, init, doctor."""
import json
from pathlib import Path

from conftest import read_json, write_json


def show_json(run_script, **kw):
    return json.loads(run_script("config.py", "show", "--json", **kw).stdout)


def test_show_json_defaults_and_paths(home, run_script, skill_copy):
    out = show_json(run_script, scripts=skill_copy / "scripts")
    assert out["config"]["market"] == "india"
    assert out["config"]["panel_model"] == "haiku"
    assert Path(out["config"]["runs_dir"]) == home / "runs"
    assert out["sources"]["market"] == "default"
    p = out["paths"]
    assert Path(p["home"]) == home
    assert Path(p["user_config"]) == home / "config.json"
    assert Path(p["project_config"]) == Path.cwd() / ".persona-panel.json"
    assert Path(p["user_markets"]) == home / "markets"
    assert Path(p["venv"]) == home / ".venv"
    assert Path(p["python"]).parent.parent == home / ".venv"
    assert p["venv_exists"] is False
    assert Path(p["skill_dir"]) == skill_copy
    assert set(out["markets"]) >= {"india", "global"}
    assert set(out["lenses"]) >= {"ux", "visual"}


def test_show_reports_sources(home, run_script):
    write_json(home / "config.json", {"market": "global"})
    write_json(Path.cwd() / ".persona-panel.json", {"n": 40})
    out = show_json(run_script)
    assert out["config"]["market"] == "global" and out["config"]["n"] == 40
    assert out["sources"]["market"].startswith("user")
    assert out["sources"]["n"].startswith("project")
    text = run_script("config.py", "show").stdout
    assert "market" in text and "global" in text and "user" in text


def test_init_writes_user_config_with_flags(home, run_script):
    r = run_script("config.py", "init", "--market", "global", "--n", 50, "--lens", "ux", "--live", 0,
                   "--runs-dir", "~/pp-runs", "--default-focus", "Is pricing clear?", "--wave-size", 4)
    cfg = read_json(home / "config.json")
    assert cfg["market"] == "global" and cfg["n"] == 50 and cfg["lens"] == "ux" and cfg["live"] == 0
    assert cfg["runs_dir"] == "~/pp-runs" and cfg["default_focus"] == "Is pricing clear?" and cfg["wave_size"] == 4
    assert set(cfg) == {"_comment", "market", "n", "lens", "live", "runs_dir", "default_focus", "wave_size"}
    assert str(home / "config.json") in r.stdout


def test_init_refuses_to_overwrite_without_force(home, run_script):
    run_script("config.py", "init", "--n", 50)
    r = run_script("config.py", "init", "--n", 60, check=False)
    assert r.returncode != 0 and "--force" in (r.stderr + r.stdout)
    assert read_json(home / "config.json")["n"] == 50
    run_script("config.py", "init", "--n", 60, "--force")
    assert read_json(home / "config.json")["n"] == 60


def test_init_project_writes_cwd_file(home, run_script):
    run_script("config.py", "init", "--project", "--market", "global")
    assert read_json(Path.cwd() / ".persona-panel.json")["market"] == "global"
    assert not (home / "config.json").exists()


def test_init_rejects_bad_values(home, run_script):
    assert run_script("config.py", "init", "--n", "0", check=False).returncode != 0
    assert run_script("config.py", "init", "--lens", "nope", check=False).returncode != 0
    assert run_script("config.py", "init", "--market", "nope", check=False).returncode != 0
    assert not (home / "config.json").exists()


def test_init_lens_default_stored_as_full_review(home, run_script):
    run_script("config.py", "init", "--lens", "default")
    assert read_json(home / "config.json")["lens"] == ""


def test_doctor_without_venv_fails_and_suggests_setup(home, run_script, skill_copy):
    r = run_script("config.py", "doctor", "--skip-browser", check=False, scripts=skill_copy / "scripts")
    assert r.returncode != 0
    assert "setup_env.py" in r.stdout
    assert "runs dir" in r.stdout.lower()


def test_doctor_reports_bad_config(home, run_script):
    (home).mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text("{nope", encoding="utf-8")
    r = run_script("config.py", "doctor", "--skip-browser", check=False)
    assert r.returncode != 0 and "config.json" in r.stdout


def test_doctor_reports_broken_user_market(home, run_script):
    (home / "markets").mkdir(parents=True)
    (home / "markets" / "bad.json").write_text("{}", encoding="utf-8")
    r = run_script("config.py", "doctor", "--skip-browser", check=False)
    assert r.returncode != 0 and "bad.json" in r.stdout


def test_doctor_runs_dir_is_writable(home, run_script):
    r = run_script("config.py", "doctor", "--skip-browser", check=False)
    assert (home / "runs").is_dir()
    assert not list((home / "runs").iterdir()), "doctor must clean up its probe file"


def test_init_user_writes_only_comment_and_given_keys(home, run_script):
    run_script("config.py", "init", "--n", 50)
    assert set(read_json(home / "config.json")) == {"_comment", "n"}
    run_script("config.py", "init", "--force")
    assert set(read_json(home / "config.json")) == {"_comment"}


def test_init_user_stores_market_path_absolute(home, run_script, tmp_path):
    from conftest import SKILL
    write_json(Path.cwd() / "mk" / "shop.json", read_json(SKILL / "data" / "markets" / "global.json"))
    run_script("config.py", "init", "--market", "mk/shop.json")
    stored = read_json(home / "config.json")["market"]
    assert Path(stored).is_absolute() and Path(stored) == (Path.cwd() / "mk" / "shop.json").resolve()
    run_script("config.py", "init", "--force", "--market", "global")
    assert read_json(home / "config.json")["market"] == "global"


def test_show_json_paths_use_forward_slashes(home, run_script):
    out = show_json(run_script)
    for key, value in out["paths"].items():
        if isinstance(value, str):
            assert "\\" not in value, (key, value)
    assert "\\" not in out["config"]["runs_dir"]
    assert all("\\" not in v for v in out["markets"].values())


def test_doctor_lists_config_file_paths_with_parentheses(tmp_path, run_script, monkeypatch):
    odd = tmp_path / "pp (odd)"
    monkeypatch.setenv("PERSONA_PANEL_HOME", str(odd))
    write_json(odd / "config.json", {"n": 5})
    r = run_script("config.py", "doctor", "--skip-browser", check=False, env_extra={"PERSONA_PANEL_HOME": str(odd)})
    assert f"config loads ({odd / 'config.json'})" in r.stdout


def test_doctor_venv_import_failure_shows_last_line(home, run_script, skill_copy):
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(home / ".venv")], check=True)
    r = run_script("config.py", "doctor", "--skip-browser", check=False, scripts=skill_copy / "scripts")
    line = next(l for l in r.stdout.splitlines() if "can't import" in l)
    assert "No module named" in line and "['" not in line and '["' not in line
