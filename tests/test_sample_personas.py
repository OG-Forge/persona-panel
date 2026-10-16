"""sample_personas.py: determinism, coverage, overrides, config defaults."""
import json
from collections import Counter
from pathlib import Path

from conftest import SKILL, read_json, write_json

INDIA = read_json(SKILL / "data" / "markets" / "india.json")
BROWSING_ONLY = {"device", "network", "context", "traffic_source", "patience", "accessibility_need"}


def sample(run_script, run, *args):
    run_script("sample_personas.py", "--run", run, *args)
    return read_json(Path(run) / "personas.json"), read_json(Path(run) / "batches.json")


def test_same_seed_gives_identical_panel(home, run_script, tmp_path):
    sample(run_script, tmp_path / "a", "--seed", 11)
    sample(run_script, tmp_path / "b", "--seed", 11)
    for name in ("personas.json", "batches.json", "personas.md"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name


def test_different_seed_gives_different_panel(home, run_script, tmp_path):
    a, _ = sample(run_script, tmp_path / "a", "--seed", 1)
    b, _ = sample(run_script, tmp_path / "b", "--seed", 2)
    assert [p["card"] for p in a] != [p["card"] for p in b]


def test_site_panel_size_ids_and_coverage(home, run_script, tmp_path):
    personas, batches = sample(run_script, tmp_path / "run", "--n", 100)
    assert len(personas) == 100
    assert [p["id"] for p in personas] == [f"p{i:03d}" for i in range(1, 101)]
    for attr in INDIA["attributes"]:
        seen = Counter(p[attr["key"]] for p in personas)
        for value, weight in attr["values"].items():
            if weight > 0:
                assert seen[value] >= 1, f"{attr['key']}={value} missing"


def test_site_panel_has_every_screen_type(home, run_script, tmp_path):
    personas, batches = sample(run_script, tmp_path / "run", "--n", 100, "--min-per-screen", 10)
    screens = Counter(p["view_profile"] for p in personas)
    for prof in ("tablet", "laptop", "desktop"):
        assert screens[prof] >= 10, screens
    assert {b["profile"] for b in batches["panel"]} == {"mobile", "tablet", "laptop", "desktop"}


def test_batches_partition_panel_and_live(home, run_script, tmp_path):
    personas, batches = sample(run_script, tmp_path / "run", "--n", 60, "--live", 3, "--batch-size", 7)
    in_batches = [pid for b in batches["panel"] for pid in b["persona_ids"]]
    assert len(in_batches) == len(set(in_batches))
    assert len(batches["live"]) == 3
    assert set(in_batches) | set(batches["live"]) == {p["id"] for p in personas}
    assert not set(in_batches) & set(batches["live"])
    assert all(len(b["persona_ids"]) <= 7 for b in batches["panel"])


def test_concept_mode_drops_browsing_attributes_and_walkers(home, run_script, tmp_path):
    personas, batches = sample(run_script, tmp_path / "run", "--mode", "concept", "--n", 40, "--live", 4)
    assert batches["mode"] == "concept"
    assert batches["live"] == []
    assert not BROWSING_ONLY & set(batches["attributes"])
    assert all(not BROWSING_ONLY & set(p) for p in personas)
    assert {b["profile"] for b in batches["panel"]} == {"concept"}


def test_overrides_set_and_multiply(home, run_script, tmp_path):
    ov = write_json(tmp_path / "overrides.json", {
        "set": {"age_band": {"18-24": 60, "25-34": 40, "35-44": 0, "45-54": 0, "55+": 0}},
        "multiply": {"income": {"high": 0}},
    })
    personas, _ = sample(run_script, tmp_path / "run", "--mode", "concept", "--n", 60, "--overrides", ov)
    assert {p["age_band"] for p in personas} == {"18-24", "25-34"}
    assert "high" not in {p["income"] for p in personas}


def test_override_for_unknown_attribute_fails(home, run_script, tmp_path):
    ov = write_json(tmp_path / "overrides.json", {"set": {"shoe_size": {"9": 1}}})
    r = run_script("sample_personas.py", "--run", tmp_path / "run", "--overrides", ov, check=False)
    assert r.returncode != 0 and "shoe_size" in r.stderr


def test_user_config_supplies_defaults(home, run_script, tmp_path):
    write_json(home / "config.json", {"market": "global", "n": 30, "batch_size": 5, "seed": 3, "live": 2})
    personas, batches = sample(run_script, tmp_path / "run")
    assert len(personas) == 30
    assert batches["market"] == "global"
    assert batches["live"] and len(batches["live"]) == 2
    assert all(len(b["persona_ids"]) <= 5 for b in batches["panel"])
    assert "seed 3" in (tmp_path / "run" / "personas.md").read_text(encoding="utf-8")


def test_project_config_beats_user_and_cli_beats_both(home, run_script, tmp_path):
    write_json(home / "config.json", {"n": 30})
    write_json(Path.cwd() / ".persona-panel.json", {"n": 35})
    personas, _ = sample(run_script, tmp_path / "a", "--mode", "concept")
    assert len(personas) == 35
    personas, _ = sample(run_script, tmp_path / "b", "--mode", "concept", "--n", 40)
    assert len(personas) == 40


def test_bad_config_fails_with_message(home, run_script, tmp_path):
    write_json(home / "config.json", {"n": "lots"})
    r = run_script("sample_personas.py", "--run", tmp_path / "run", check=False)
    assert r.returncode != 0
    assert "config.json" in r.stderr and "Traceback" not in r.stderr


def test_user_market_with_bom_loads(home, run_script, tmp_path):
    market = read_json(SKILL / "data" / "markets" / "global.json")
    market["name"] = "bommed"
    (home / "markets").mkdir(parents=True)
    (home / "markets" / "bommed.json").write_bytes(b"\xef\xbb\xbf" + json.dumps(market).encode("utf-8"))
    ov = tmp_path / "ov.json"
    ov.write_bytes(b"\xef\xbb\xbf" + b'{"notes": "bom"}')
    personas, batches = sample(run_script, tmp_path / "run", "--market", "bommed", "--mode", "concept",
                               "--n", 20, "--overrides", ov)
    assert batches["market"] == "bommed" and len(personas) == 20


def test_invalid_market_json_fails_with_message(home, run_script, tmp_path):
    (home / "markets").mkdir(parents=True)
    (home / "markets" / "broken.json").write_text("{nope", encoding="utf-8")
    r = run_script("sample_personas.py", "--run", tmp_path / "run", "--market", "broken", check=False)
    assert r.returncode != 0
    assert "broken.json: not valid JSON" in r.stderr and "Traceback" not in r.stderr


def test_invalid_overrides_json_fails_with_message(home, run_script, tmp_path):
    ov = tmp_path / "ov.json"
    ov.write_text("{nope", encoding="utf-8")
    r = run_script("sample_personas.py", "--run", tmp_path / "run", "--overrides", ov, check=False)
    assert r.returncode != 0
    assert "ov.json: not valid JSON" in r.stderr and "Traceback" not in r.stderr


def test_relative_market_path_in_user_config(home, run_script, tmp_path):
    market = read_json(SKILL / "data" / "markets" / "global.json")
    market["name"] = "relmarket"
    write_json(home / "shop" / "m.json", market)
    write_json(home / "config.json", {"market": "shop/m.json"})
    _, batches = sample(run_script, tmp_path / "run", "--mode", "concept", "--n", 20)
    assert batches["market"] == "relmarket"


def test_run_dir_tilde_is_expanded(home, run_script, tmp_path):
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    env = {"HOME": str(fake_home), "USERPROFILE": str(fake_home)}
    run_script("sample_personas.py", "--run", "~/r", "--mode", "concept", "--n", 20, env_extra=env)
    assert (fake_home / "r" / "personas.json").exists()
    run_script("prepare_briefs.py", "--run", "~/r", env_extra=env, check=False)
    assert not (Path.cwd() / "~").exists()


def test_bad_config_hint_quotes_config_py_path(home, run_script, tmp_path):
    write_json(home / "config.json", {"n": "lots"})
    r = run_script("sample_personas.py", "--run", tmp_path / "run", check=False)
    assert 'config.py" doctor' in r.stderr
