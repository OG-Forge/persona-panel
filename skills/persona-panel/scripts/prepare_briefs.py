"""Write one self-contained brief per panel batch and per live walker.

A brief holds everything a persona agent needs (instructions, persona cards,
the exact screenshots to open, the site digest or concept, and the output
schema), so the dispatch prompt is one line and the agent needs no extra
lookups: one turn to read, one turn to write.

Usage:
  python prepare_briefs.py --run RUN_DIR [--max-images 10] [--focus "questions the owner cares about"]
Site mode expects RUN_DIR/capture/ (from capture.py). Concept mode expects RUN_DIR/concept.md
(plus optional images listed in it).
--lens and --focus default to the config's "lens" and "default_focus" (config.py show);
--lens default forces the full customer review.
"""
import sys

sys.dont_write_bytecode = True  # keep the skill folder read-only

import argparse
import json
import re
import shutil
from pathlib import Path

import paths

HERE = Path(__file__).resolve().parent
REF = HERE.parent / "references"
WALK = HERE / "walk.py"

SLOW_FACTOR = {"fast_wifi": None, "good_4g_5g": None, "patchy_4g": 1.0, "slow_3g": 1.8}
ENTRY_KIND_ORDER = {"product": ["product", "collection", "home"], "collection": ["collection", "home", "product"],
                    "home_or_collection": ["home", "collection", "product"], "home": ["home", "product", "collection"]}


def load_capture(run):
    manifest = json.loads((run / "capture" / "manifest.json").read_text(encoding="utf-8"))
    digest = (run / "capture" / "digest.md").read_text(encoding="utf-8")
    return manifest, digest


def first_page(manifest, kind, profile):
    for page in manifest["pages"]:
        if page["kind"] == kind and profile in page["profiles"]:
            return page
    return None


def slow_note(persona, run, manifest):
    factor = SLOW_FACTOR.get(persona.get("network"))
    if not factor:
        return ""
    home = manifest["pages"][0]
    data_path = run / "capture" / home["slug"] / "mobile" / "data.json"
    if not data_path.exists():
        return ""
    th = json.loads(data_path.read_text(encoding="utf-8")).get("throttled") or {}
    fcp, load = th.get("first_contentful_paint_seconds"), th.get("load_seconds")
    if fcp is None:
        return ""
    def scale(v):
        if v is None:
            return "?"
        return f">{round(45 * factor)}" if isinstance(v, str) else round(v * factor, 1)
    return (f" On their connection the first page shows something after ~{scale(fcp)}s and finishes loading after "
            f"~{scale(load)}s ({th.get('transfer_kb')} KB on a data plan).")


def screen_plan(persona, manifest, profile):
    """Which screens this persona actually sees, given entry point and attention budget."""
    budget = persona["attention_budget_screens"]
    plan, seen = [], 0
    for kind in ENTRY_KIND_ORDER.get(persona["entry_page"], ["home", "product", "collection"]):
        page = first_page(manifest, kind, profile)
        if not page or seen >= budget:
            continue
        n = min(len(page["profiles"][profile]["screens"]), budget - seen, 4)
        plan.append(f"{page['slug']} screens 1-{n}")
        seen += n
    return "; ".join(plan) + " (then continues only if still interested and the budget allows)"


def core_images(manifest, profile, run, max_images):
    """The shared screenshot set for a batch: the arrival screens of the key pages."""
    picks = []
    quotas = [("home", 3), ("product", 3), ("collection", 2), ("cart", 1), ("shipping_returns", 1), ("about", 1)]
    for kind, quota in quotas:
        page = first_page(manifest, kind, profile)
        if not page:
            continue
        for shot in page["profiles"][profile]["screens"][:quota]:
            picks.append(str((run / page["profiles"][profile]["dir"] / shot).resolve()))
    # Fill from other pages if the site has few of the standard kinds.
    for page in manifest["pages"]:
        if len(picks) >= max_images:
            break
        if profile in page["profiles"]:
            shot = str((run / page["profiles"][profile]["dir"] / page["profiles"][profile]["screens"][0]).resolve())
            if shot not in picks:
                picks.append(shot)
    return picks[:max_images]


def profile_digest(digest, profile):
    """Keep only the digest sections for one device profile."""
    blocks = digest.split("\n### ")
    head, rest = blocks[0], blocks[1:]
    return head + "".join("\n### " + b for b in rest if f"({profile})" in b.split("\n", 1)[0])


FALLBACK_PROFILES = {"mobile": ["mobile", "mobile_large", "tablet"], "tablet": ["tablet", "laptop", "mobile", "desktop"],
                     "laptop": ["laptop", "laptop_hd", "desktop_legacy", "desktop", "tablet"],
                     "desktop": ["desktop", "desktop_legacy", "laptop_hd", "laptop"]}


def captured_profile(manifest, wanted):
    """The batch's screen type if it was captured, else the nearest one that was (a partial --profiles capture)."""
    have = set(manifest.get("profiles") or [p for page in manifest["pages"] for p in page["profiles"]])
    for p in FALLBACK_PROFILES.get(wanted, [wanted]):
        if p in have:
            return p
    if have:
        return sorted(have)[0]
    raise SystemExit("The capture has no screenshots for any device profile")


def lens_schema(lens_md):
    """The '## Output schema' section of a lens file (walker briefs need it too)."""
    marker = "## Output schema"
    return lens_md[lens_md.index(marker) + len(marker):].strip() if marker in lens_md else ""


PROBE_PROFILES = {"mobile": ("mobile", "mobile_large"), "tablet": ("tablet",), "laptop": ("laptop", "laptop_hd"),
                  "desktop": ("desktop",), "desktop_legacy": ("laptop", "desktop")}


def probe_facts(run, profile):
    """Measured UX checks that apply to this screen type, one line per problem group."""
    path = run / "probes" / "probes.json"
    if not path.exists():
        return ""
    findings = json.loads(path.read_text(encoding="utf-8"))["findings"]
    mine, seen = [], set()
    for f in findings:
        if f["profile"] in PROBE_PROFILES.get(profile, (profile,)) and f["group"] not in seen:
            seen.add(f["group"])
            mine.append(f"- [{f['id']}] ({f['severity']}, {f['device']}, page {f['page']}) {f['title']}. {f['detail']}")
    if not mine:
        return ""
    header = "## Measured UX checks on this screen type (a real browser clicked, scrolled and pressed Back; these are facts)"
    return "\n".join([header, *mine[:25], ""])


IMAGES_HEADING = re.compile(r"^#{1,6}\s*images?\s*:?\s*$", re.I)


def split_concept_images(concept):
    """(concept text without its '## Images' section, the image paths listed in that section)."""
    keep, images, in_images = [], [], False
    for line in concept.splitlines():
        if re.match(r"^#{1,6}\s", line):
            in_images = bool(IMAGES_HEADING.match(line.strip()))
            if in_images:
                continue
        if not in_images:
            keep.append(line)
            continue
        item = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line).strip().strip("`'\"<>")
        if item:
            images.append(item)
    return "\n".join(keep).strip() + "\n", images


def copy_concept_images(run, listed):
    """Copy the concept's images into RUN/concept_images/ as i01.png, i02.jpg...; returns {id: copy path}.
    Panelists (and the report) only ever open files inside the run, never the user's originals."""
    out = run / "concept_images"
    if out.exists():
        shutil.rmtree(out)
    ids = {}
    for item in listed:
        src = Path(item).expanduser()
        src = src if src.is_absolute() else run / src
        if src.suffix.lower() not in paths.IMAGE_SUFFIXES or not src.is_file():
            print(f"Skipped concept image (not a .png/.jpg/.jpeg/.webp file): {item}")
            continue
        out.mkdir(exist_ok=True)
        key = f"i{len(ids) + 1:02d}"
        dest = out / f"{key}{src.suffix.lower()}"
        shutil.copyfile(src, dest)
        ids[key] = str(dest)
    return ids


def main():
    cfg = paths.config_or_exit()
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--max-images", type=int, default=10)
    ap.add_argument("--focus", default=cfg["default_focus"], help="Specific questions the owner wants the panel to answer")
    ap.add_argument("--python", default="python", help="Python executable walkers should use for walk.py")
    ap.add_argument("--lens", default=cfg["lens"],
                    help="Focus lens from references/lenses (e.g. ux, visual); 'default' = full customer review")
    ap.add_argument("--only", nargs="*", help="Write redo briefs for just these panel persona ids (missing results)")
    args = ap.parse_args()
    args.lens = paths.normalize_lens(args.lens)

    run = paths.run_dir_arg(args.run)
    personas = {p["id"]: p for p in json.loads((run / "personas.json").read_text(encoding="utf-8"))}
    batches = json.loads((run / "batches.json").read_text(encoding="utf-8"))
    mode = batches.get("mode", "site")
    (run / "briefs").mkdir(exist_ok=True)
    (run / "results").mkdir(exist_ok=True)
    schema = (REF / "result-schema.md").read_text(encoding="utf-8")
    focus = f"\n## The owner especially wants to know\n{args.focus}\n" if args.focus else ""

    if mode == "concept":
        concept, listed = split_concept_images((run / "concept.md").read_text(encoding="utf-8"))
        concept_ids = copy_concept_images(run, listed)
        panel_rules = (REF / "panelist-concept.md").read_text(encoding="utf-8")
    else:
        manifest, digest = load_capture(run)
        panel_rules = (REF / "panelist-site.md").read_text(encoding="utf-8")
    if args.lens:
        # A lens replaces the panel instructions and the output schema, and tells aggregate/report its vocabulary.
        lens_dir = REF / "lenses"
        if not (lens_dir / f"{args.lens}.md").exists():
            raise SystemExit(f"Unknown lens '{args.lens}'. Available: {[f.stem for f in lens_dir.glob('*.md')]}")
        panel_rules = (lens_dir / f"{args.lens}.md").read_text(encoding="utf-8")
        walker_schema = lens_schema(panel_rules)
        schema = ""
        (run / "lens.json").write_text((lens_dir / f"{args.lens}.json").read_text(encoding="utf-8"), encoding="utf-8")
    else:
        walker_schema = schema
        if (run / "lens.json").exists() and not args.only:
            # A full (non-redo) default run must not inherit an earlier lens's outcome words.
            (run / "lens.json").unlink()

    panel = batches["panel"]
    if args.only:
        panel = [{**b, "batch_id": b["batch_id"] + "_redo", "persona_ids": [i for i in b["persona_ids"] if i in args.only]}
                 for b in panel if set(b["persona_ids"]) & set(args.only)]
        batches["live"] = []
    for b in panel:
        out = run / "results" / f"{b['batch_id']}.json"
        cards = []
        shot_profile = captured_profile(manifest, b["profile"]) if mode != "concept" else None
        for pid in b["persona_ids"]:
            p = personas[pid]
            if mode == "concept":
                cards.append(f"- **{pid}** — {p['card']}")
            else:
                cards.append(f"- **{pid}** — {p['card']}{slow_note(p, run, manifest)}\n"
                             f"  Arrives at: {p['entry_page'].replace('_', ' ')} page. Sees: {screen_plan(p, manifest, shot_profile)}.")
        parts = [f"# Persona panel brief {b['batch_id']} ({len(b['persona_ids'])} personas)", "", panel_rules, focus]
        if mode == "concept":
            parts += ["## The concept being evaluated", concept]
            (run / "briefs" / f"{b['batch_id']}_images.json").write_text(json.dumps(concept_ids, indent=1), encoding="utf-8")
            if concept_ids:
                parts += ["## Concept images — Read ALL of these in ONE turn (parallel Read calls)",
                          "In an issue's `shot`, use the short id in brackets (e.g. i02), not the path.",
                          *[f"- [{k}] {v}" for k, v in concept_ids.items()], ""]
        else:
            imgs = core_images(manifest, shot_profile, run, args.max_images)
            ids = {f"i{n + 1:02d}": path for n, path in enumerate(imgs)}
            (run / "briefs" / f"{b['batch_id']}_images.json").write_text(json.dumps(ids, indent=1), encoding="utf-8")
            note = "" if shot_profile == b["profile"] else (f" These were captured on {shot_profile} because {b['profile']} wasn't "
                                                           f"captured; imagine them on your {b['profile']} screen.")
            parts += [f"## Screenshots to open ({shot_profile} view) — Read ALL of these in ONE turn (parallel Read calls)",
                      "In an issue's `shot`, use the short id in brackets (e.g. i03), not the path." + note,
                      *[f"- [{k}] {Path(v).parent.parent.name}/{Path(v).stem}: {v}" for k, v in ids.items()], "",
                      probe_facts(run, b["profile"]),
                      "## Site digest (measured facts from the capture; trust these over guesses)",
                      profile_digest(digest, shot_profile)]
        parts += ["## Your personas", *cards, "", "## Output", f"Write ONE file: `{out}`" + (" (format: see Output schema above)" if not schema else ""), schema]
        (run / "briefs" / f"{b['batch_id']}.md").write_text("\n".join(parts), encoding="utf-8")

    if mode == "site" and batches["live"]:
        walker_rules = (REF / "live-walker.md").read_text(encoding="utf-8")
        for pid in batches["live"]:
            p = personas[pid]
            session = run / "walk" / pid
            out = run / "results" / f"live_{pid}.json"
            entry = first_page(manifest, "product" if p["entry_page"] == "product" else "home", "mobile") or manifest["pages"][0]
            cmd = f'"{args.python}" "{WALK}" "{session}"'
            text = walker_rules.replace("{WALK}", cmd).replace("{DEVICE}", p["view_profile"]) \
                               .replace("{START_URL}", entry["url"]).replace("{OUT}", str(out)).replace("{PID}", pid)
            parts = [f"# Live walker brief {pid}", "", f"## You are\n{p['card']}{slow_note(p, run, manifest)}", "", text, focus,
                     "## Output schema", walker_schema]
            (run / "briefs" / f"live_{pid}.md").write_text("\n".join(parts), encoding="utf-8")

    n_live = len(batches["live"]) if mode == "site" else 0
    print(f"Wrote {len(panel)} panel briefs and {n_live} live-walker briefs to {run / 'briefs'}")


if __name__ == "__main__":
    main()
