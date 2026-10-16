"""paths.py: home dir, venv location, config precedence and validation."""
import os
from pathlib import Path

import pytest

import paths
from conftest import write_json


def test_home_dir_defaults_to_dot_persona_panel_in_user_home(tmp_path, monkeypatch):
    monkeypatch.delenv("PERSONA_PANEL_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert paths.home_dir() == tmp_path / ".persona-panel"


def test_home_dir_env_override(home):
    assert paths.home_dir() == home


def test_home_dir_env_expands_user(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("PERSONA_PANEL_HOME", "~/pp")
    assert paths.home_dir() == tmp_path / "pp"


def _fake_python(venv):
    py = paths.venv_python(venv)
    py.parent.mkdir(parents=True)
    py.write_text("")
    return py


def test_venv_lives_in_home(home):
    assert paths.venv_dir() == home / ".venv"
    assert paths.venv_python().parent.parent == home / ".venv"


def test_legacy_skill_venv_used_when_home_venv_missing(home, tmp_path, monkeypatch):
    legacy = tmp_path / "skill" / ".venv"
    monkeypatch.setattr(paths, "LEGACY_VENV_DIR", legacy)
    _fake_python(legacy)
    assert paths.venv_dir() == legacy
    _fake_python(home / ".venv")
    assert paths.venv_dir() == home / ".venv"


def test_defaults_when_no_config_files(home):
    cfg, sources = paths.load_config_with_sources()
    assert cfg["market"] == "india"
    assert cfg["n"] == 100
    assert cfg["live"] == 4
    assert cfg["lens"] == ""
    assert cfg["seed"] == 7
    assert cfg["min_per_screen"] == 10
    assert cfg["batch_size"] == 10
    assert cfg["wave_size"] == 3
    assert cfg["panel_model"] == "haiku"
    assert cfg["synthesis_model"] == "sonnet"
    assert cfg["default_focus"] == ""
    assert Path(cfg["runs_dir"]) == home / "runs"
    assert set(sources.values()) == {"default"}
    assert set(cfg) == set(paths.DEFAULTS)


def test_project_config_overrides_user_config(home):
    write_json(home / "config.json", {"market": "global", "n": 50, "live": 0})
    write_json(Path.cwd() / ".persona-panel.json", {"n": 30})
    cfg, sources = paths.load_config_with_sources()
    assert (cfg["market"], cfg["n"], cfg["live"], cfg["seed"]) == ("global", 30, 0, 7)
    assert sources["market"].startswith("user")
    assert sources["n"].startswith("project")
    assert sources["seed"] == "default"


def test_relative_runs_dir_resolves_against_its_config_file(home):
    write_json(Path.cwd() / ".persona-panel.json", {"runs_dir": "panel-runs"})
    assert Path(paths.load_config()["runs_dir"]) == Path.cwd() / "panel-runs"
    assert paths.runs_dir() == Path.cwd() / "panel-runs"


def test_runs_dir_expands_user(home, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    write_json(home / "config.json", {"runs_dir": "~/my-runs"})
    assert paths.runs_dir() == tmp_path / "my-runs"


def test_comment_keys_ignored_and_unknown_keys_warn(home, capsys):
    write_json(home / "config.json", {"_comment": "hi", "nn": 5})
    cfg = paths.load_config()
    assert "_comment" not in cfg and "nn" not in cfg
    assert "nn" in capsys.readouterr().err


@pytest.mark.parametrize("bad", [{"n": "ten"}, {"n": 0}, {"live": -1}, {"market": 3}, {"n": True}, {"wave_size": 0}])
def test_invalid_values_raise_config_error(home, bad):
    write_json(home / "config.json", bad)
    with pytest.raises(paths.ConfigError) as e:
        paths.load_config()
    assert str(home / "config.json") in str(e.value)


def test_broken_json_raises_config_error(home):
    (home).mkdir(parents=True)
    (home / "config.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(paths.ConfigError):
        paths.load_config()


def test_config_must_be_an_object(home):
    write_json(home / "config.json", [1, 2])
    with pytest.raises(paths.ConfigError):
        paths.load_config()


def test_lens_aliases_mean_full_review(home):
    write_json(home / "config.json", {"lens": "default"})
    assert paths.load_config()["lens"] == ""


def test_home_dir_relative_env_resolves_to_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERSONA_PANEL_HOME", "rel-home")
    assert paths.home_dir() == (tmp_path / "rel-home").resolve()
    assert paths.home_dir().is_absolute()


def test_relative_market_path_resolves_against_its_config_file(home, tmp_path, monkeypatch):
    write_json(home / "config.json", {"market": "my-markets/shop.json"})
    assert Path(paths.load_config()["market"]) == (home / "my-markets" / "shop.json").resolve()
    sub = Path.cwd() / "sub"
    write_json(sub / ".persona-panel.json", {"market": "./local.json"})
    assert Path(paths.load_config(cwd=sub)["market"]) == (sub / "local.json").resolve()


def test_market_path_in_config_expands_user(home, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    write_json(home / "config.json", {"market": "~/m/shop.json"})
    assert Path(paths.load_config()["market"]) == tmp_path / "m" / "shop.json"


def test_market_name_in_config_is_left_alone(home):
    write_json(home / "config.json", {"market": "global"})
    assert paths.load_config()["market"] == "global"


def test_null_values_in_config_are_skipped(home):
    write_json(home / "config.json", {"n": None, "market": "global", "runs_dir": None})
    write_json(Path.cwd() / ".persona-panel.json", {"market": None})
    cfg, sources = paths.load_config_with_sources()
    assert cfg["n"] == 100 and sources["n"] == "default"
    assert cfg["market"] == "global" and sources["market"].startswith("user")
    assert Path(cfg["runs_dir"]) == home / "runs"


def test_sources_keep_paths_separately(home):
    write_json(home / "config.json", {"n": 5})
    cfg, sources, files = paths.load_config_with_files()
    assert sources["n"].startswith("user")
    assert files == [home / "config.json"]


def test_run_dir_arg_expands_user_and_resolves(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert paths.run_dir_arg("~/r1") == tmp_path / "r1"
    monkeypatch.chdir(tmp_path)
    assert paths.run_dir_arg("r2") == (tmp_path / "r2").resolve()


def test_every_run_script_uses_run_dir_arg():
    from conftest import SCRIPTS
    for name in ("sample_personas.py", "prepare_briefs.py", "aggregate.py", "report.py", "capture.py", "probe.py"):
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "paths.run_dir_arg(args.run)" in text, name
        assert "Path(args.run)" not in text, name
