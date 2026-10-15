"""Merge persona results, compute stats and segment breakdowns, and write a
compact issue digest for the synthesis step.

Usage: python aggregate.py --run RUN_DIR
Writes RUN_DIR/aggregate.json and RUN_DIR/issues_digest.md, and prints any
personas with missing or invalid results (re-run just their batch).
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCORE_KEYS = ("clarity", "trust", "appeal", "ease", "value")
SEGMENT_KEYS = ("age_band", "gender", "location_tier", "region", "income", "device", "network", "language",
                "tech_comfort", "shopping_experience", "payment_pref", "shopper_type", "traffic_source",
                "trust_baseline", "accessibility_need", "patience")
SEV_WEIGHT = {"blocker": 3, "major": 2, "minor": 1}
OUTCOMES = ("buy", "maybe", "no")


def load_results(run):
    results, problems = {}, []
    for f in sorted((run / "results").glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            problems.append(f"{f.name}: invalid JSON ({e})")
            continue
        for r in data if isinstance(data, list) else [data]:
            if not isinstance(r, dict) or "id" not in r:
                problems.append(f"{f.name}: entry without id")
                continue
            r["_source"] = "live" if f.name.startswith("live_") else "panel"
            results[r["id"]] = r
    return results, problems


def norm_where(w):
    """'home 1', 'Home screen 3', '01-baby-showers-shop-theme' -> 'home', 'baby showers shop theme'."""
    w = re.sub(r"screens?|[\d_\-]+|\(.*?\)", " ", str(w or "other").lower())
    return " ".join(w.split()) or "other"


def clean(r):
    r["outcome"] = r.get("outcome") if r.get("outcome") in OUTCOMES else OUTCOMES[-1]
    scores = r.get("scores") or {}
    r["scores"] = {k: max(1, min(5, int(scores[k]))) for k in SCORE_KEYS if isinstance(scores.get(k), (int, float))}
    r["issues"] = [i for i in (r.get("issues") or []) if isinstance(i, dict) and i.get("what")][:5]
    for i in r["issues"]:
        i["severity"] = i.get("severity") if i.get("severity") in SEV_WEIGHT else "minor"
        i["category"] = (i.get("category") or "other").lower()
        i["where"] = norm_where(i.get("where"))
    return r


def avg(xs):
    return round(sum(xs) / len(xs), 2) if xs else None


def summarize(group):
    n = len(group)
    oc = Counter(r["outcome"] for r in group)
    pos, mid, neg = OUTCOMES
    return {
        "n": n,
        "buy_pct": round(100 * oc[pos] / n) if n else 0,
        "maybe_pct": round(100 * oc[mid] / n) if n else 0,
        "no_pct": round(100 * oc[neg] / n) if n else 0,
        "scores": {k: avg([r["scores"][k] for r in group if k in r["scores"]]) for k in SCORE_KEYS},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    args = ap.parse_args()
    run = Path(args.run)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # A lens (e.g. visual) brings its own outcome words and score keys; buy_pct etc. hold its 1st/2nd/3rd outcome.
    global OUTCOMES, SCORE_KEYS
    lens = json.loads((run / "lens.json").read_text(encoding="utf-8")) if (run / "lens.json").exists() else {}
    OUTCOMES = tuple(lens.get("outcomes", OUTCOMES))
    SCORE_KEYS = tuple(lens.get("scores", SCORE_KEYS))

    personas = {p["id"]: p for p in json.loads((run / "personas.json").read_text(encoding="utf-8"))}
    batches = json.loads((run / "batches.json").read_text(encoding="utf-8"))
    results, problems = load_results(run)
    results = {pid: clean(r) for pid, r in results.items() if pid in personas}
    missing = sorted(set(personas) - set(results))
    rows = list(results.values())
    if not rows:
        sys.exit("No results found in results/")

    overall = summarize(rows)
    overall["understood_offer_pct"] = round(100 * sum(1 for r in rows if r.get("understood_offer")) / len(rows))
    overall["price_feel"] = dict(Counter(r.get("price_feel", "unclear") for r in rows).most_common())
    overall["left_at"] = dict(Counter(norm_where((r.get("left_at") or "stayed").split(",")[0])
                                      for r in rows).most_common(10))

    segments = {}
    for key in SEGMENT_KEYS:
        groups = defaultdict(list)
        for r in rows:
            v = personas[r["id"]].get(key)
            if v is not None:
                groups[v].append(r)
        if len(groups) > 1:
            segments[key] = {v: summarize(g) for v, g in sorted(groups.items(), key=lambda kv: -len(kv[1]))}

    issues = []
    for r in rows:
        for i in r["issues"]:
            issues.append({"pid": r["id"], **{k: i.get(k, "") for k in ("where", "category", "severity", "what", "fix")}})
    buckets = defaultdict(list)
    for i in issues:
        buckets[(i["where"], i["category"])].append(i)
    bucket_rank = sorted(buckets.items(), key=lambda kv: -sum(SEV_WEIGHT[i["severity"]] for i in kv[1]))

    agg = {
        "mode": batches.get("mode", "site"), "market": batches.get("market"), "lens": lens,
        "n_personas": len(personas), "n_results": len(rows), "missing": missing, "problems": problems,
        "n_live": sum(1 for r in rows if r["_source"] == "live"),
        "overall": overall, "segments": segments, "issue_count": len(issues),
        "buckets": [{"where": w, "category": c, "count": len(v), "weight": sum(SEV_WEIGHT[i["severity"]] for i in v)}
                    for (w, c), v in bucket_rank],
    }
    (run / "aggregate.json").write_text(json.dumps(agg, indent=1, ensure_ascii=False), encoding="utf-8")

    # Compact digest for the synthesizer: grouped by (where, category), one line per issue.
    lines = [f"# Issue digest: {len(issues)} issues from {len(rows)} personas",
             f"Overall: {OUTCOMES[0]} {overall['buy_pct']}% / {OUTCOMES[1]} {overall['maybe_pct']}% / {OUTCOMES[2]} {overall['no_pct']}%; "
             f"avg scores {overall['scores']}; understood offer {overall['understood_offer_pct']}%; left at {overall['left_at']}",
             "Line format: pid|severity|what => fix", ""]
    for (w, c), items in bucket_rank:
        lines.append(f"## {w} / {c} ({len(items)})")
        lines += [f"{i['pid']}|{i['severity']}|{i['what']} => {i['fix']}" for i in items]
        lines.append("")
    lines.append("## What personas liked")
    liked = Counter(l.strip().lower() for r in rows for l in (r.get("liked") or []) if isinstance(l, str))
    lines += [f"{n}x {t}" for t, n in liked.most_common(40)]
    lines += ["", "## What would change their mind (no/maybe personas)"]
    lines += [f"{r['id']}: {r.get('would_change_mind', '')}" for r in rows if r["outcome"] != OUTCOMES[0] and r.get("would_change_mind")]
    (run / "issues_digest.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"{len(rows)}/{len(personas)} personas have results; {len(issues)} issues in {len(buckets)} buckets.")
    print(f"Outcome: {OUTCOMES[0]} {overall['buy_pct']}% / {OUTCOMES[1]} {overall['maybe_pct']}% / {OUTCOMES[2]} {overall['no_pct']}%")
    if missing:
        by_batch = [b["batch_id"] for b in batches["panel"] if set(b["persona_ids"]) & set(missing)]
        live_missing = [pid for pid in batches.get("live", []) if pid in missing]
        print(f"MISSING {len(missing)}: {', '.join(missing)}")
        print(f"Re-run batches: {', '.join(by_batch) or '-'}; live walkers: {', '.join(live_missing) or '-'}")
    for p in problems:
        print("PROBLEM:", p)


if __name__ == "__main__":
    main()
