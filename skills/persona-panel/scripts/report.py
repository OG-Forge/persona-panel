"""Render the persona-panel report as one self-contained HTML file.

Usage: python report.py --run RUN_DIR --title "Site or concept name" [--subject URL-or-short-description]
Reads personas.json, aggregate.json, synthesis.json and results/*.json and
writes RUN_DIR/report.html.
"""
import argparse
import html
import json
from pathlib import Path

SEG_LABELS = {
    "age_band": "Age", "location_tier": "City tier", "region": "Region", "income": "Income", "device": "Device",
    "network": "Network", "language": "Language", "payment_pref": "Payment preference", "shopper_type": "Shopper type",
    "shopping_experience": "Online shopping experience", "trust_baseline": "Trust baseline",
    "accessibility_need": "Accessibility need", "traffic_source": "Arrived from", "tech_comfort": "Tech comfort",
    "gender": "Gender", "patience": "Patience",
}
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def e(s):
    return html.escape(str(s if s is not None else ""))


def label(v):
    return str(v).replace("_", " ")


def load_results(run):
    out = {}
    for f in sorted((run / "results").glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for r in data if isinstance(data, list) else [data]:
            if isinstance(r, dict) and "id" in r:
                r["_live"] = f.name.startswith("live_")
                out[r["id"]] = r
    return out


def who(p):
    bits = [f"{p['name']}, {p['age']}", p.get("city", "")]
    for k in ("device", "payment_pref", "shopper_type"):
        if p.get(k):
            bits.append(label(p[k]))
    if p.get("accessibility_need") not in (None, "none"):
        bits.append(label(p["accessibility_need"]))
    return " · ".join(b for b in bits if b)


def outcome_chip(o):
    return f'<span class="chip out-{e(o)}">{e(o)}</span>'


def bar(pct, cls=""):
    return f'<span class="bar {cls}"><span style="width:{max(0, min(100, pct or 0))}%"></span></span>'


def render(run, title, subject):
    personas = {p["id"]: p for p in json.loads((run / "personas.json").read_text(encoding="utf-8"))}
    agg = json.loads((run / "aggregate.json").read_text(encoding="utf-8"))
    syn_path = run / "synthesis.json"
    syn = json.loads(syn_path.read_text(encoding="utf-8")) if syn_path.exists() else {}
    results = load_results(run)
    n = agg["n_results"]
    ov = agg["overall"]
    mode = agg.get("mode", "site")

    themes = sorted(syn.get("themes", []), key=lambda t: (-int(t.get("impact", 0)), SEV_ORDER.get(t.get("severity"), 9),
                                                          -len(t.get("persona_ids", []))))
    quick = set(syn.get("quick_wins", []))

    def theme_html(i, t):
        ids = [pid for pid in t.get("persona_ids", []) if pid in personas]
        pct = round(100 * len(ids) / n) if n else 0
        voices = "".join(
            f'<li><q>{e(results[pid].get("quote", ""))}</q> <span class="muted">— {e(who(personas[pid]))}</span></li>'
            for pid in ids[:6] if pid in results and results[pid].get("quote"))
        qw = '<span class="chip qw">quick win</span>' if t.get("title") in quick else ""
        return f"""
<article class="theme sev-{e(t.get('severity'))}">
  <header><span class="rank">{i}</span><h3>{e(t.get('title'))}</h3>
    <span class="chip sev">{e(t.get('severity'))}</span><span class="chip">effort: {e(t.get('effort'))}</span>{qw}</header>
  <div class="reach">{bar(pct)}<span><b>{len(ids)}</b> of {n} personas ({pct}%) · {e(t.get('where'))}</span></div>
  <p><b>Who:</b> {e(t.get('who'))}</p>
  <p><b>Evidence:</b> {e(t.get('evidence'))}</p>
  <p class="fix"><b>Fix:</b> {e(t.get('fix'))}</p>
  {f'<details><summary>What they said</summary><ul class="voices">{voices}</ul></details>' if voices else ''}
</article>"""

    seg_html = []
    for key, groups in agg.get("segments", {}).items():
        if key not in SEG_LABELS:
            continue
        rows = []
        for v, s in groups.items():
            positive = s["buy_pct"] + s["maybe_pct"]
            rows.append(f"<tr><td>{e(label(v))}</td><td class=num>{s['n']}</td>"
                        f"<td>{bar(positive, 'pos')}<span class=num>{positive}%</span></td>"
                        f"<td class=num>{s['scores'].get('trust') or '–'}</td><td class=num>{s['scores'].get('clarity') or '–'}</td>"
                        f"<td class=num>{s['scores'].get('ease') or '–'}</td></tr>")
        seg_html.append(f"""<details class="seg"><summary>{e(SEG_LABELS[key])}</summary>
<table><thead><tr><th></th><th class=num>n</th><th>buy + maybe</th><th class=num>trust</th><th class=num>clarity</th><th class=num>ease</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></details>""")

    live_html = []
    for pid, r in results.items():
        if not r.get("_live") or pid not in personas:
            continue
        steps = "".join(f"<li>{e(s)}</li>" for s in r.get("journey", []))
        live_html.append(f"""<article class="walker"><header><h3>{e(who(personas[pid]))}</h3>{outcome_chip(r.get('outcome'))}
<span class="chip">reached: {e(r.get('reached', '?'))}</span></header><ol>{steps}</ol>
<p><q>{e(r.get('quote'))}</q></p></article>""")

    left = ov.get("left_at", {})
    left_max = max(left.values()) if left else 1
    left_html = "".join(f"<li><span>{e(label(k))}</span>{bar(100 * v / left_max)}<span class=num>{v}</span></li>"
                        for k, v in left.items())

    gallery = []
    for pid, p in personas.items():
        r = results.get(pid)
        if not r:
            continue
        iss = "".join(f"<li><b>{e(i.get('severity'))}</b> · {e(i.get('where'))}: {e(i.get('what'))}</li>" for i in r.get("issues", []))
        scores = " · ".join(f"{k} {v}" for k, v in (r.get("scores") or {}).items())
        gallery.append(f"""<details class="persona" data-outcome="{e(r.get('outcome'))}">
<summary>{outcome_chip(r.get('outcome'))}<span class="pname">{e(who(p))}</span>{'<span class="chip">live</span>' if r.get('_live') else ''}</summary>
<p class="muted">{e(p['card'])}</p><p><q>{e(r.get('quote'))}</q></p><p class="muted">{e(scores)}</p><ul>{iss}</ul>
<p><b>Would change their mind:</b> {e(r.get('would_change_mind'))}</p></details>""")

    def tile(lbl, val, sub=""):
        return f'<div class="tile"><div class="tl">{e(lbl)}</div><div class="tv">{e(val)}</div><div class="ts">{e(sub)}</div></div>'

    sc = ov["scores"]
    tiles = "".join([
        tile("Would buy", f"{ov['buy_pct']}%", f"maybe {ov['maybe_pct']}% · no {ov['no_pct']}%"),
        tile("Got the offer quickly", f"{ov.get('understood_offer_pct', 0)}%", "understood what it is"),
        tile("Trust", f"{sc.get('trust') or '–'}/5"), tile("Clarity", f"{sc.get('clarity') or '–'}/5"),
        tile("Ease", f"{sc.get('ease') or '–'}/5"), tile("Value", f"{sc.get('value') or '–'}/5"),
    ])
    summary = "".join(f"<li>{e(s)}</li>" for s in syn.get("summary", []))
    insights = "".join(f"<li>{e(s)}</li>" for s in syn.get("segment_insights", []))
    strengths = "".join(f"<li>{e(s.get('title'))} <span class=muted>({len(s.get('persona_ids', []))} personas)</span></li>"
                        for s in syn.get("strengths", []))
    questions = "".join(f"<li>{e(q)}</li>" for q in syn.get("open_questions", []))
    stack = (f'<div class="stack"><span class="s-buy" style="flex:{ov["buy_pct"]}"></span>'
             f'<span class="s-maybe" style="flex:{ov["maybe_pct"]}"></span><span class="s-no" style="flex:{ov["no_pct"]}"></span></div>')

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} panel</title>
<style>
:root{{--bg:#f7f6f3;--card:#fff;--ink:#1d1d1f;--muted:#6b6b70;--line:#e4e2dc;--accent:#2f5bea;--pos:#2e8b57;--mid:#d4a017;--neg:#c8423b;--chip:#efede7}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#141416;--card:#1d1d20;--ink:#ececef;--muted:#9a9aa2;--line:#2c2c31;--accent:#7b9bff;--pos:#4fbf80;--mid:#e0b43a;--neg:#ef6b63;--chip:#2a2a2f}}}}
:root[data-theme=dark]{{--bg:#141416;--card:#1d1d20;--ink:#ececef;--muted:#9a9aa2;--line:#2c2c31;--accent:#7b9bff;--pos:#4fbf80;--mid:#e0b43a;--neg:#ef6b63;--chip:#2a2a2f}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:32px 16px 64px}}h1{{font-size:28px;margin:0 0 4px}}h2{{font-size:19px;margin:40px 0 12px}}h3{{font-size:16px;margin:0}}
.muted{{color:var(--muted)}}.headline{{font-size:18px;font-weight:600;margin:16px 0 8px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:16px 0}}
.tile{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}}.tl{{font-size:12px;color:var(--muted)}}.tv{{font-size:24px;font-weight:700}}.ts{{font-size:12px;color:var(--muted)}}
.stack{{display:flex;height:12px;border-radius:6px;overflow:hidden;margin:8px 0 4px}}.s-buy{{background:var(--pos)}}.s-maybe{{background:var(--mid)}}.s-no{{background:var(--neg)}}
.theme,.walker{{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--line);border-radius:10px;padding:14px 16px;margin:10px 0}}
.sev-critical{{border-left-color:var(--neg)}}.sev-high{{border-left-color:#e07b39}}.sev-medium{{border-left-color:var(--mid)}}.sev-low{{border-left-color:var(--muted)}}
.theme header,.walker header{{display:flex;flex-wrap:wrap;gap:8px;align-items:center}}.theme p{{margin:6px 0}}.fix{{background:var(--chip);padding:6px 10px;border-radius:6px}}
.rank{{font-weight:700;color:var(--muted)}}.chip{{font-size:12px;background:var(--chip);border-radius:20px;padding:2px 9px}}.qw{{background:var(--accent);color:#fff}}
.out-buy{{background:var(--pos);color:#fff}}.out-maybe{{background:var(--mid);color:#111}}.out-no{{background:var(--neg);color:#fff}}
.reach{{display:flex;align-items:center;gap:10px;font-size:13px;margin:8px 0}}
.bar{{display:inline-block;width:120px;height:8px;background:var(--chip);border-radius:4px;overflow:hidden;vertical-align:middle;margin-right:6px}}.bar span{{display:block;height:100%;background:var(--accent)}}.bar.pos span{{background:var(--pos)}}
table{{width:100%;border-collapse:collapse;font-size:14px}}td,th{{padding:5px 8px;border-bottom:1px solid var(--line);text-align:left}}.num{{text-align:right;font-variant-numeric:tabular-nums}}
details{{margin:6px 0}}summary{{cursor:pointer}}.seg{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px}}.seg summary{{font-weight:600}}
.leftat{{list-style:none;padding:0}}.leftat li{{display:grid;grid-template-columns:160px 1fr 40px;gap:8px;align-items:center;margin:4px 0}}.leftat .bar{{width:100%}}
.persona{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 12px}}.persona summary{{display:flex;gap:8px;align-items:center}}.pname{{font-size:14px}}
.filters button{{font:inherit;font-size:13px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:20px;padding:3px 12px;margin-right:6px;cursor:pointer}}.filters button.on{{background:var(--ink);color:var(--bg)}}
.voices{{padding-left:18px}}q{{font-style:italic}}
@media (max-width:600px){{.leftat li{{grid-template-columns:110px 1fr 32px}}.bar{{width:70px}}h1{{font-size:23px}}}}
</style></head><body><main>
<p class="muted">Persona panel · {e(mode)} review · {e(agg.get('market'))} market · {n} simulated customers{f" ({agg['n_live']} walked the live site)" if agg.get('n_live') else ''}</p>
<h1>{e(title)}</h1><p class="muted">{e(subject)}</p>
<p class="headline">{e(syn.get('headline', ''))}</p><ul>{summary}</ul>
<div class="tiles">{tiles}</div>{stack}<p class="muted">green = would buy · amber = maybe · red = no</p>
<h2>What to fix, in order</h2>{''.join(theme_html(i + 1, t) for i, t in enumerate(themes)) or '<p class=muted>No synthesis yet.</p>'}
{f'<h2>How segments differed</h2><ul>{insights}</ul>' if insights else ''}
<h2>Segment breakdown</h2>{''.join(seg_html)}
{f'<h2>Where people gave up</h2><ul class="leftat">{left_html}</ul>' if left_html else ''}
{f'<h2>Live walk-throughs</h2>{"".join(live_html)}' if live_html else ''}
{f'<h2>What works</h2><ul>{strengths}</ul>' if strengths else ''}
{f'<h2>Validate with real customers</h2><ul>{questions}</ul>' if questions else ''}
<h2>All {n} personas</h2>
<div class="filters"><button class="on" data-f="all">All</button><button data-f="buy">Buy</button><button data-f="maybe">Maybe</button><button data-f="no">No</button></div>
<div id="gallery">{''.join(gallery)}</div>
<h2>Method and caveats</h2>
<p class="muted">Personas were sampled from weighted demographic distributions with coherence rules and guaranteed coverage of minority segments, then role-played by small AI models in batches. {'Panelists reviewed screenshots and measured page facts (load times on a throttled budget phone, accessibility checks); a few walked the live site in a real browser.' if mode == 'site' else 'Panelists reacted to the written concept.'} These are simulated customers: they're good at surfacing friction, confusion and missing information, but they don't predict real conversion rates. Confirm the top themes with a handful of real customers before big changes.</p>
</main><script>
document.querySelectorAll('.filters button').forEach(b=>b.onclick=()=>{{document.querySelectorAll('.filters button').forEach(x=>x.classList.toggle('on',x===b));
document.querySelectorAll('#gallery .persona').forEach(p=>p.style.display=(b.dataset.f==='all'||p.dataset.outcome===b.dataset.f)?'':'none')}});
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--subject", default="")
    args = ap.parse_args()
    run = Path(args.run)
    (run / "report.html").write_text(render(run, args.title, args.subject), encoding="utf-8")
    print(f"Report: {(run / 'report.html').resolve()}")


if __name__ == "__main__":
    main()
