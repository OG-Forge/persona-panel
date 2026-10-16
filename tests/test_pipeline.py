"""Concept-mode pipeline end to end, offline: sample -> briefs -> fake results -> aggregate -> report."""
import json
import re
from pathlib import Path

import pytest

from conftest import SKILL, read_json, write_json

CONCEPT = "A subscription box of themed party kits for kids' birthdays, Rs 1,999/month."


@pytest.fixture
def concept_run(home, run_script, tmp_path):
    run = tmp_path / "run"
    run_script("sample_personas.py", "--run", run, "--mode", "concept", "--n", 30, "--seed", 5)
    (run / "concept.md").write_text(f"# Concept\n\n{CONCEPT}\n", encoding="utf-8")
    return run


def brief_files(run):
    return sorted((run / "briefs").glob("b*.md"))


def test_concept_briefs_written_for_every_batch(concept_run, run_script):
    r = run_script("prepare_briefs.py", "--run", concept_run, "--python", "PY")
    batches = read_json(concept_run / "batches.json")
    files = brief_files(concept_run)
    assert [f.stem for f in files] == [b["batch_id"] for b in batches["panel"]]
    assert (concept_run / "results").is_dir()
    for b, f in zip(batches["panel"], files):
        text = f.read_text(encoding="utf-8")
        assert CONCEPT in text
        for pid in b["persona_ids"]:
            assert f"**{pid}**" in text
        assert str(concept_run / "results" / f"{b['batch_id']}.json") in text
        assert "## Output" in text
    assert not (concept_run / "lens.json").exists()
    assert "panel briefs" in r.stdout


def test_lens_from_config(concept_run, run_script, home):
    write_json(home / "config.json", {"lens": "ux"})
    run_script("prepare_briefs.py", "--run", concept_run)
    assert read_json(concept_run / "lens.json") == read_json(SKILL / "references" / "lenses" / "ux.json")


def test_cli_lens_overrides_config_lens(concept_run, run_script, home):
    write_json(home / "config.json", {"lens": "ux"})
    run_script("prepare_briefs.py", "--run", concept_run, "--lens", "default")
    assert not (concept_run / "lens.json").exists()


def test_unknown_lens_fails(concept_run, run_script):
    r = run_script("prepare_briefs.py", "--run", concept_run, "--lens", "nope", check=False)
    assert r.returncode != 0 and "nope" in r.stderr


def test_default_focus_from_config_and_cli_override(concept_run, run_script, home):
    write_json(home / "config.json", {"default_focus": "Is the price clear?"})
    run_script("prepare_briefs.py", "--run", concept_run)
    text = brief_files(concept_run)[0].read_text(encoding="utf-8")
    assert "The owner especially wants to know" in text and "Is the price clear?" in text
    run_script("prepare_briefs.py", "--run", concept_run, "--focus", "Would you gift it?")
    text = brief_files(concept_run)[0].read_text(encoding="utf-8")
    assert "Would you gift it?" in text and "Is the price clear?" not in text


def test_redo_briefs_only_cover_requested_personas(concept_run, run_script):
    run_script("prepare_briefs.py", "--run", concept_run, "--only", "p002", "p029")
    redo = sorted((concept_run / "briefs").glob("*_redo.md"))
    assert redo
    text = "".join(f.read_text(encoding="utf-8") for f in redo)
    assert set(re.findall(r"\*\*(p\d{3})\*\*", text)) == {"p002", "p029"}


def fake_result(pid, k):
    outcome = ("buy", "maybe", "no")[k % 3]
    return {"id": pid, "first_impression": "Looks handy", "understood_offer": k % 4 != 0, "left_at": None,
            "outcome": outcome, "scores": {"clarity": 3 + k % 3, "trust": "2", "appeal": 4.4, "ease": 3, "value": None},
            "price_feel": "pricey" if k % 2 else "fair",
            "issues": [{"where": "pricing", "severity": "major", "category": "price",
                        "what": "Monthly price feels high", "fix": "Offer a single box", "shot": None}],
            "liked": ["Saves planning time"], "would_change_mind": "A trial box", "quote": f"Persona {pid} quote"}


def test_aggregate_and_report(concept_run, run_script):
    run_script("prepare_briefs.py", "--run", concept_run)
    batches = read_json(concept_run / "batches.json")
    dropped = batches["panel"][0]["persona_ids"][0]
    k = 0
    for b in batches["panel"]:
        rows = []
        for pid in b["persona_ids"]:
            if pid != dropped:
                rows.append(fake_result(pid, k))
            k += 1
        write_json(concept_run / "results" / f"{b['batch_id']}.json", rows)
    (concept_run / "results" / "broken.json").write_text("{oops", encoding="utf-8")

    r = run_script("aggregate.py", "--run", concept_run)
    agg = read_json(concept_run / "aggregate.json")
    assert agg["mode"] == "concept"
    assert agg["n_personas"] == 30 and agg["n_results"] == 29
    assert agg["missing"] == [dropped]
    assert any("broken.json" in p for p in agg["problems"])
    ov = agg["overall"]
    assert ov["buy_pct"] + ov["maybe_pct"] + ov["no_pct"] in (99, 100, 101)
    assert agg["issue_count"] == 29
    assert agg["segments"], "expected segment breakdowns"
    assert f"MISSING 1: {dropped}" in r.stdout
    assert (concept_run / "issues_digest.md").exists()

    ids = [b["persona_ids"][1] for b in batches["panel"]]
    write_json(concept_run / "synthesis.json", {
        "headline": "Price is the sticking point",
        "summary": ["Most liked the idea."],
        "themes": [{"title": "Monthly price feels high", "severity": "high", "where": "pricing", "persona_ids": ids,
                    "who": "Everyone", "evidence": "Many said it", "fix": "Offer a single box", "effort": "low", "impact": 4}],
        "quick_wins": ["Monthly price feels high"],
        "strengths": [{"title": "Saves time", "persona_ids": ids[:1]}],
        "segment_insights": [], "open_questions": [],
    })
    r = run_script("report.py", "--run", concept_run, "--title", "Party Box <Test>", "--subject", "concept")
    html = (concept_run / "report.html").read_text(encoding="utf-8")
    assert html.lstrip().lower().startswith("<!doctype html")
    assert "Party Box &lt;Test&gt;" in html
    assert "Monthly price feels high" in html
    assert "Price is the sticking point" in html
    assert "report.html" in r.stdout


HOSTILE = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'


def test_report_escapes_hostile_result_strings(concept_run, run_script):
    batches = read_json(concept_run / "batches.json")
    pids = [pid for b in batches["panel"] for pid in b["persona_ids"]]
    rows = []
    for k, pid in enumerate(pids):
        r = fake_result(pid, k)
        r.update(outcome=HOSTILE if k == 0 else r["outcome"], quote=HOSTILE, would_change_mind=HOSTILE,
                 journey=[HOSTILE], reached=HOSTILE)
        r["issues"][0].update(what=HOSTILE, where=HOSTILE, severity=HOSTILE, fix=HOSTILE)
        rows.append(r)
    write_json(concept_run / "results" / "b01.json", rows[:10])
    write_json(concept_run / "results" / "live_x.json", rows[10:])
    run_script("aggregate.py", "--run", concept_run)
    write_json(concept_run / "synthesis.json", {
        "headline": HOSTILE, "summary": [HOSTILE], "quick_wins": [HOSTILE], "segment_insights": [HOSTILE],
        "open_questions": [{"title": HOSTILE}], "strengths": [{"title": HOSTILE, "persona_ids": pids[:1]}],
        "themes": [{"title": HOSTILE, "severity": HOSTILE, "where": HOSTILE, "persona_ids": pids[:3], "devices": [HOSTILE],
                    "who": HOSTILE, "evidence": HOSTILE, "fix": HOSTILE, "effort": HOSTILE, "impact": HOSTILE,
                    "shots": [HOSTILE], "probe_ids": [HOSTILE]}]})
    run_script("report.py", "--run", concept_run, "--title", HOSTILE, "--subject", HOSTILE)
    html = (concept_run / "report.html").read_text(encoding="utf-8")
    assert "<script>alert" not in html and "<img src=x" not in html and 'onerror=alert(2)>' not in html
    assert html.count("<script>") == 1, "only the report's own script block"
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
