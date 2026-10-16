"""Bundled market profiles are valid, and user markets shadow bundled ones."""
import json
from pathlib import Path

import pytest

import paths
from conftest import SKILL, read_json, write_json

BUNDLED = sorted((SKILL / "data" / "markets").glob("*.json"))
SITE_KEYS = {"device", "network", "patience", "traffic_source", "context", "accessibility_need"}


def test_there_are_bundled_markets():
    assert {p.stem for p in BUNDLED} >= {"india", "global"}


@pytest.mark.parametrize("path", BUNDLED, ids=lambda p: p.stem)
def test_bundled_market_is_valid(path):
    m = json.loads(path.read_text(encoding="utf-8"))
    assert m["name"] == path.stem
    assert isinstance(m.get("description"), str) and m["description"]
    attrs = {a["key"]: a["values"] for a in m["attributes"]}
    assert len(attrs) == len(m["attributes"]), "duplicate attribute keys"
    for key, values in attrs.items():
        assert isinstance(values, dict) and values, key
        assert all(isinstance(w, (int, float)) and w >= 0 for w in values.values()), key
        assert any(w > 0 for w in values.values()), key
    assert {"age_band", "gender"} <= set(attrs)
    assert "location_tier" in attrs or "region" in attrs
    assert SITE_KEYS <= set(attrs), "bundled markets must support site mode"
    for rule in m.get("rules", []):
        for k, v in rule["if"].items():
            assert k in attrs and v in attrs[k], f"rule condition {k}={v}"
        for k, mults in rule["then"].items():
            assert k in attrs, f"rule target {k}"
            for v in mults:
                assert v in attrs[k], f"rule target value {k}.{v}"
    place = "location_tier" if "location_tier" in attrs else "region"
    assert set(m["cities"]) >= {v for v, w in attrs[place].items() if w > 0}
    assert set(m["names"]) >= {v for v, w in attrs["gender"].items() if w > 0}


def test_find_market_bundled(home):
    assert paths.find_market("india") == SKILL / "data" / "markets" / "india.json"


def test_user_market_shadows_bundled(home):
    mine = write_json(home / "markets" / "india.json", {"name": "my-india"})
    assert paths.find_market("india") == mine


def test_user_only_market_is_found_and_listed(home):
    mine = write_json(home / "markets" / "b2b.json", {"name": "b2b"})
    assert paths.find_market("b2b") == mine
    assert paths.available_markets()["b2b"] == mine
    assert "india" in paths.available_markets()


def test_market_path_accepted(home, tmp_path):
    p = write_json(tmp_path / "custom" / "market.json", {"name": "x"})
    assert paths.find_market(str(p)) == p


def test_unknown_market_error_lists_available(home):
    write_json(home / "markets" / "b2b.json", {"name": "b2b"})
    with pytest.raises(FileNotFoundError) as e:
        paths.find_market("nope")
    assert "india" in str(e.value) and "b2b" in str(e.value)


def test_sampler_uses_user_market(home, run_script, tmp_path):
    m = read_json(SKILL / "data" / "markets" / "global.json")
    m["name"] = "my-india"
    write_json(home / "markets" / "india.json", m)
    run = tmp_path / "run"
    run_script("sample_personas.py", "--run", run, "--mode", "concept", "--n", 30)
    assert read_json(run / "batches.json")["market"] == "my-india"


def test_sampler_accepts_market_path(home, run_script, tmp_path):
    m = read_json(SKILL / "data" / "markets" / "global.json")
    m["name"] = "from-path"
    p = write_json(tmp_path / "market.json", m)
    run = tmp_path / "run"
    run_script("sample_personas.py", "--run", run, "--mode", "concept", "--n", 30, "--market", p)
    assert read_json(run / "batches.json")["market"] == "from-path"


def test_sampler_unknown_market_fails_cleanly(home, run_script, tmp_path):
    r = run_script("sample_personas.py", "--run", tmp_path / "run", "--market", "nope", check=False)
    assert r.returncode != 0
    assert "nope" in r.stderr and "india" in r.stderr
    assert "Traceback" not in r.stderr
