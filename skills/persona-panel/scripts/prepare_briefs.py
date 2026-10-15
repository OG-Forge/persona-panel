"""Write one self-contained brief per panel batch and per live walker.

A brief holds everything a persona agent needs (instructions, persona cards,
the exact screenshots to open, the site digest or concept, and the output
schema), so the dispatch prompt is one line and the agent needs no extra
lookups: one turn to read, one turn to write.

Usage:
  python prepare_briefs.py --run RUN_DIR [--max-images 10] [--focus "questions the owner cares about"]
Site mode expects RUN_DIR/capture/ (from capture.py). Concept mode expects RUN_DIR/concept.md
(plus optional images listed in it).
"""
import argparse
import json
from pathlib import Path

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--max-images", type=int, default=10)
    ap.add_argument("--focus", default="", help="Specific questions the owner wants the panel to answer")
    ap.add_argument("--python", default="python", help="Python executable walkers should use for walk.py")
    ap.add_argument("--lens", default="", help="Focus lens from references/lenses (e.g. visual); default = full customer review")
    ap.add_argument("--only", nargs="*", help="Write redo briefs for just these panel persona ids (missing results)")
    args = ap.parse_args()

    run = Path(args.run).resolve()
    personas = {p["id"]: p for p in json.loads((run / "personas.json").read_text(encoding="utf-8"))}
    batches = json.loads((run / "batches.json").read_text(encoding="utf-8"))
    mode = batches.get("mode", "site")
    (run / "briefs").mkdir(exist_ok=True)
    (run / "results").mkdir(exist_ok=True)
    schema = (REF / "result-schema.md").read_text(encoding="utf-8")
    focus = f"\n## The owner especially wants to know\n{args.focus}\n" if args.focus else ""

    if mode == "concept":
        concept = (run / "concept.md").read_text(encoding="utf-8")
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
        schema = ""
        (run / "lens.json").write_text((lens_dir / f"{args.lens}.json").read_text(encoding="utf-8"), encoding="utf-8")

    panel = batches["panel"]
    if args.only:
        panel = [{**b, "batch_id": b["batch_id"] + "_redo", "persona_ids": [i for i in b["persona_ids"] if i in args.only]}
                 for b in panel if set(b["persona_ids"]) & set(args.only)]
        batches["live"] = []
    for b in panel:
        out = run / "results" / f"{b['batch_id']}.json"
        cards = []
        for pid in b["persona_ids"]:
            p = personas[pid]
            if mode == "concept":
                cards.append(f"- **{pid}** — {p['card']}")
            else:
                cards.append(f"- **{pid}** — {p['card']}{slow_note(p, run, manifest)}\n"
                             f"  Arrives at: {p['entry_page'].replace('_', ' ')} page. Sees: {screen_plan(p, manifest, b['profile'])}.")
        parts = [f"# Persona panel brief {b['batch_id']} ({len(b['persona_ids'])} personas)", "", panel_rules, focus]
        if mode == "concept":
            parts += ["## The concept being evaluated", concept]
        else:
            imgs = core_images(manifest, b["profile"], run, args.max_images)
            parts += [f"## Screenshots to open ({b['profile']} view) — Read ALL of these in ONE turn (parallel Read calls)",
                      *[f"- {i}" for i in imgs], "",
                      "## Site digest (measured facts from the capture; trust these over guesses)",
                      profile_digest(digest, b["profile"])]
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
                     "## Output schema", schema]
            (run / "briefs" / f"live_{pid}.md").write_text("\n".join(parts), encoding="utf-8")

    n_live = len(batches["live"]) if mode == "site" else 0
    print(f"Wrote {len(panel)} panel briefs and {n_live} live-walker briefs to {run / 'briefs'}")


if __name__ == "__main__":
    main()
