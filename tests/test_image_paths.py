"""Screenshots that end up in briefs and the report must be images inside the runs folder (or the run)."""
import json
from pathlib import Path

import pytest

import paths
from conftest import read_json, write_json

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
       b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82")


def png(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG)
    return path


@pytest.fixture
def runs(home):
    """The configured runs folder (default: HOME/runs) with one run in it."""
    root = paths.runs_dir()
    run = root / "shop-20261016-1200"
    run.mkdir(parents=True)
    return root, run


def test_safe_image_accepts_images_inside_the_roots(runs):
    root, run = runs
    shot = png(run / "capture" / "home" / "mobile" / "01.png")
    assert paths.safe_image(shot, [root]) == shot.resolve()
    for suffix in (".jpg", ".jpeg", ".webp", ".PNG"):
        assert paths.safe_image(png(run / f"x{suffix}"), [root])


def test_safe_image_rejects_paths_outside_the_roots(runs, tmp_path):
    root, run = runs
    outside = png(tmp_path / "secret.png")
    assert paths.safe_image(outside, [root]) is None
    assert paths.safe_image(run / ".." / ".." / outside.name, [root]) is None
    assert paths.safe_image(str(run) + "/../../" + outside.name, [root]) is None


def test_safe_image_rejects_other_file_types_and_missing_files(runs):
    root, run = runs
    (run / "notes.txt").write_text("x", encoding="utf-8")
    (run / "page.html").write_text("x", encoding="utf-8")
    assert paths.safe_image(run / "notes.txt", [root]) is None
    assert paths.safe_image(run / "page.html", [root]) is None
    assert paths.safe_image(run / "missing.png", [root]) is None
    assert paths.safe_image(run, [root]) is None
    assert paths.safe_image(None, [root]) is None
    assert paths.safe_image("", [root]) is None


def test_safe_image_root_prefix_is_not_enough(runs, tmp_path):
    root, run = runs
    sibling = png(Path(str(root) + "-evil") / "x.png")  # shares the string prefix, not the folder
    assert paths.safe_image(sibling, [root]) is None


def test_safe_image_is_case_insensitive_on_windows_only(runs):
    root, run = runs
    shot = png(run / "a.png")
    upper = Path(str(root).upper())
    import os
    assert bool(paths.safe_image(shot, [upper])) == (os.name == "nt")


def test_run_relative(runs, tmp_path):
    root, run = runs
    assert paths.run_relative(run, run / "probes" / "001-x.jpg") == "probes/001-x.jpg"
    assert paths.run_file(run, "probes/001-x.jpg") == run / "probes" / "001-x.jpg"
    assert paths.run_file(run, str(run / "probes" / "001-x.jpg")) == run / "probes" / "001-x.jpg"


# --- aggregate.resolve_shot -------------------------------------------------------------------------

def test_resolve_shot_rejects_outside_and_traversal(runs, tmp_path):
    import aggregate
    root, run = runs
    outside = png(tmp_path / "elsewhere" / "secret.png")
    inside = png(run / "walk" / "p001" / "step_03.jpg")
    bases = [run / "walk" / "p001", run]
    assert aggregate.resolve_shot(str(outside), {}, bases, [root]) is None
    assert aggregate.resolve_shot("../../../elsewhere/secret.png", {}, bases, [root]) is None
    assert aggregate.resolve_shot("step_03.jpg", {}, bases, [root]) == str(inside.resolve())
    assert aggregate.resolve_shot(str(inside), {}, bases, [root]) == str(inside.resolve())
    assert aggregate.resolve_shot("i01", {"i01": str(outside)}, bases, [root]) is None
    assert aggregate.resolve_shot("i01", {"i01": str(inside)}, bases, [root]) == str(inside.resolve())
    assert aggregate.resolve_shot("u4", {}, bases, [root]) == "u004"
    (run / "results").mkdir()
    (run / "results" / "b01.json").write_text("[]", encoding="utf-8")
    assert aggregate.resolve_shot("results/b01.json", {}, bases, [root]) is None


def test_aggregate_drops_hostile_shot_paths(runs, run_script, tmp_path):
    root, run = runs
    outside = png(tmp_path / "elsewhere" / "secret.png")
    inside = png(run / "capture" / "home" / "mobile" / "01.png")
    write_json(run / "personas.json", [{"id": "p001", "card": "x", "age_band": "18-24"},
                                       {"id": "p002", "card": "y", "age_band": "25-34"}])
    write_json(run / "batches.json", {"mode": "concept", "panel": [{"batch_id": "b01", "persona_ids": ["p001", "p002"]}],
                                      "live": []})
    write_json(run / "briefs" / "b01_images.json", {"i01": str(inside)})
    issue = {"where": "home", "severity": "major", "category": "trust", "what": "x", "fix": "y"}
    write_json(run / "results" / "b01.json", [
        {"id": "p001", "outcome": "no", "issues": [{**issue, "shot": str(outside)}, {**issue, "shot": "i01"}]},
        {"id": "p002", "outcome": "no", "issues": [{**issue, "shot": "../../../elsewhere/secret.png"}]}])
    run_script("aggregate.py", "--run", run)
    agg = read_json(run / "aggregate.json")
    assert list(agg["shots"].values()) == [str(inside.resolve())]


def test_aggregate_reads_relative_probe_shots(runs, run_script):
    root, run = runs
    shot = png(run / "probes" / "001-x.jpg")
    write_json(run / "personas.json", [{"id": "p001", "card": "x"}])
    write_json(run / "batches.json", {"mode": "site", "panel": [], "live": []})
    write_json(run / "results" / "b01.json", [{"id": "p001", "outcome": "no", "issues": []}])
    write_json(run / "probes" / "probes.json", {"findings": [
        {"id": "u001", "check": "overflow", "group": "overflow", "page": "home", "profile": "mobile", "device": "phone",
         "severity": "major", "title": "t", "detail": "d", "shots": ["probes/001-x.jpg"]}]})
    run_script("aggregate.py", "--run", run)
    assert read_json(run / "aggregate.json")["probe_groups"][0]["shots"] == [str(shot.resolve())]


# --- report.img_uri / resolve -----------------------------------------------------------------------

def test_report_img_uri_refuses_outside_paths(runs, tmp_path):
    import report
    root, run = runs
    report._ROOTS[:] = [root]
    report._IMG_CACHE.clear()
    assert report.img_uri(str(png(run / "a.png"))).startswith("data:image/jpeg;base64,")
    assert report.img_uri(str(png(tmp_path / "outside.png"))) is None
    assert report.img_uri(str(run / ".." / ".." / "outside.png")) is None
    (run / "fake.txt").write_bytes(PNG)
    assert report.img_uri(str(run / "fake.txt")) is None


def test_report_embeds_only_safe_theme_screenshots(runs, run_script, tmp_path):
    root, run = runs
    outside = png(tmp_path / "outside.png")
    inside = png(run / "probes" / "001-x.jpg")
    write_json(run / "personas.json", [{"id": "p001", "card": "x", "name": "A", "age": 30}])
    write_json(run / "aggregate.json", {"n_results": 1, "overall": {"buy_pct": 0, "maybe_pct": 0, "no_pct": 100, "scores": {}},
                                        "shots": {"s1": str(outside)}, "probe_groups": []})
    write_json(run / "probes" / "probes.json", {"findings": [
        {"id": "u001", "check": "overflow", "group": "overflow", "page": "home", "profile": "mobile", "device": "phone",
         "severity": "major", "title": "t", "detail": "d", "shots": ["probes/001-x.jpg"]}]})
    write_json(run / "synthesis.json", {"themes": [
        {"title": "A", "severity": "high", "persona_ids": ["p001"], "shots": ["s1", str(outside)], "probe_ids": ["u001"]}]})
    run_script("report.py", "--run", run, "--title", "T")
    html = (run / "report.html").read_text(encoding="utf-8")
    assert html.count("data:image/jpeg;base64,") == 1
    assert str(outside) not in html


# --- concept images ---------------------------------------------------------------------------------

def test_concept_images_are_copied_into_the_run(runs, run_script, tmp_path):
    root, run = runs
    mock = png(tmp_path / "my mockups" / "hero.png")
    other = png(tmp_path / "my mockups" / "pricing.webp")
    (tmp_path / "my mockups" / "notes.txt").write_text("x", encoding="utf-8")
    run_script("sample_personas.py", "--run", run, "--mode", "concept", "--n", 30, "--seed", 5)
    (run / "concept.md").write_text(
        f"# Concept\n\nA party box.\n\n## Images\n- {mock}\n- `{other}`\n- {tmp_path / 'my mockups' / 'notes.txt'}\n"
        f"- {tmp_path / 'missing.png'}\n\n## Price\nRs 999\n", encoding="utf-8")
    r = run_script("prepare_briefs.py", "--run", run)
    copies = sorted((run / "concept_images").iterdir())
    assert [p.name for p in copies] == ["i01.png", "i02.webp"]
    assert copies[0].read_bytes() == PNG
    batches = read_json(run / "batches.json")
    for b in batches["panel"]:
        ids = read_json(run / "briefs" / f"{b['batch_id']}_images.json")
        assert ids == {"i01": str(copies[0]), "i02": str(copies[1])}
        brief = (run / "briefs" / f"{b['batch_id']}.md").read_text(encoding="utf-8")
        assert f"[i01]" in brief and str(copies[0]) in brief
        assert str(mock) not in brief, "the brief must point at the copies, not the originals"
        assert "Rs 999" in brief
    assert "notes.txt" in r.stdout and "missing.png" in r.stdout
