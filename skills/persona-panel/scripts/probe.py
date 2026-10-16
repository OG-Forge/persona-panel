"""Measured UX checks across device sizes: no LLM tokens, every finding comes with an annotated screenshot.

Static screenshots can't show what happens when you scroll, click or press Back, so this script does it:
  section_fit     each full-width section vs the visible screen (minus sticky header) per device
  in_page_jump    click hero/CTA buttons that scroll the page; where does it land?
  back_restore    scroll down, open a link, press Back: do you return to the same spot?
  sticky_overlay  how much of the screen fixed/sticky bars and widgets cover
  overflow        what causes sideways scrolling
  hero_cta        is the main call-to-action visible without scrolling?
  scroll_driven   pinned "scrollytelling" sections that need many scrolls to play out

Usage:
  python probe.py --run RUN_DIR [--profiles mobile,tablet,laptop,laptop_hd,desktop]
      [--pages 5] [--interaction-profiles mobile,tablet,laptop]
Needs RUN_DIR/capture/manifest.json (from capture.py). Writes RUN_DIR/probes/probes.json and probes.md.
"""
import sys

sys.dont_write_bytecode = True  # keep the skill folder read-only

import argparse
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

from PIL import Image, ImageDraw, ImageFont

import paths
from devices import PROFILES, context_options


def draw_fold(path, y, label):
    """Red dashed line across the screenshot at y, with a label: where the screen ends."""
    img = Image.open(path).convert("RGB")
    d = ImageDraw.Draw(img)
    if 0 < y < img.height:
        for x in range(0, img.width, 24):
            d.line([(x, y), (x + 14, y)], fill=(224, 36, 94), width=5)
        try:
            font = ImageFont.truetype("arial.ttf", 18)
        except OSError:
            font = ImageFont.load_default()
        box = d.textbbox((0, 0), label, font=font)
        w, h = box[2] - box[0], box[3] - box[1]
        x0 = img.width - w - 28
        d.rectangle([x0 - 8, y + 8, x0 + w + 8, y + h + 20], fill=(224, 36, 94))
        d.text((x0, y + 12), label, fill="white", font=font)
    img.save(path, quality=72)

SECTIONS_JS = r"""
() => {
  const vw = innerWidth, vh = innerHeight;
  const fixedTop = (() => { let h = 0;
    for (const el of document.querySelectorAll('body *')) {
      const s = getComputedStyle(el); if (s.position !== 'fixed' && s.position !== 'sticky') continue;
      const r = el.getBoundingClientRect();
      if (r.top <= 2 && r.height < vh * 0.4 && r.width > vw * 0.5 && r.bottom > 0) h = Math.max(h, r.bottom);
    } return Math.round(h); })();
  const full = el => { const r = el.getBoundingClientRect(); return r.width >= vw * 0.85 && r.height >= 120; };
  let c = [...document.querySelectorAll('section, [class*="section" i], main > div, main > article')].filter(full)
    .filter(el => !el.closest('header, footer, nav') && !['HEADER', 'FOOTER', 'NAV'].includes(el.tagName));
  if (c.length < 2) c = [...(document.querySelector('main') || document.body).children].filter(full);
  // Keep the innermost full-width blocks: those are the visual "sections".
  c = c.filter(el => !c.some(o => o !== el && el.contains(o) && o.getBoundingClientRect().height > 120));
  c.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
  return { fixedTop, vh, vw, sections: c.slice(0, 20).map((el, i) => {
    const r = el.getBoundingClientRect();
    const h = el.querySelector('h1, h2, h3');
    // Height of the tallest pinned (sticky) element inside: a big one means a scroll-driven section.
    let sticky = 0;
    for (const d of el.querySelectorAll('*')) { if (getComputedStyle(d).position === 'sticky') sticky = Math.max(sticky, d.getBoundingClientRect().height); }
    el.setAttribute('data-pp-sec', i);
    // Largest repeated card inside the section (siblings sharing a class, each at least 140x140).
    let card = 0, cardName = '', cardTop = 0, n = 0;
    for (const p of el.querySelectorAll('*')) {
      if (++n > 2500) break;
      const kids = [...p.children].filter(k => { const kr = k.getBoundingClientRect(); return kr.width >= 140 && kr.height >= 140; });
      const base = k => k.tagName + '.' + k.className.toString().split(' ')[0];
      if (kids.length < 2 || kids.filter(k => base(k) === base(kids[0])).length < 2) continue;
      for (const k of kids) { const kr = k.getBoundingClientRect();
        if (kr.height > card) { card = kr.height; cardTop = kr.top + scrollY; cardName = ((k.querySelector('h1,h2,h3,h4') || k).innerText || '').trim().replace(/\s+/g, ' ').slice(0, 40);
          document.querySelectorAll(`[data-pp-card="${i}"]`).forEach(x => x.removeAttribute('data-pp-card')); k.setAttribute('data-pp-card', i); } }
    }
    return { i, top: Math.round(r.top + scrollY), height: Math.round(r.height), sticky_inside: sticky,
             card_height: Math.round(card), card_name: cardName, card_top: Math.round(cardTop),
             heading: h ? h.innerText.trim().replace(/\s+/g, ' ').slice(0, 70) : (el.id || el.className.toString().slice(0, 40)) };
  }) };
}
"""

MARK_JS = r"""
([sel, label, color]) => {
  document.querySelectorAll('.pp-mark').forEach(e => e.remove());
  const els = [...document.querySelectorAll(sel)].slice(0, 12);
  for (const el of els) {
    const r = el.getBoundingClientRect();
    const box = document.createElement('div'); box.className = 'pp-mark';
    Object.assign(box.style, { position: 'absolute', left: (r.left + scrollX - 3) + 'px', top: (r.top + scrollY - 3) + 'px',
      width: (r.width + 6) + 'px', height: (r.height + 6) + 'px', border: `3px solid ${color}`, borderRadius: '4px',
      zIndex: 2147483647, pointerEvents: 'none', boxSizing: 'border-box' });
    document.body.appendChild(box);
  }
  if (label) {
    const tag = document.createElement('div'); tag.className = 'pp-mark'; tag.textContent = label;
    Object.assign(tag.style, { position: 'fixed', left: '8px', bottom: '8px', maxWidth: '90vw', background: color, color: '#fff',
      font: '600 13px/1.3 system-ui, sans-serif', padding: '6px 10px', borderRadius: '6px', zIndex: 2147483647, pointerEvents: 'none' });
    document.body.appendChild(tag);
  }
  return els.length;
}
"""

FOLD_JS = r"""
([y, label]) => {
  const line = document.createElement('div'); line.className = 'pp-mark';
  Object.assign(line.style, { position: 'absolute', left: 0, right: 0, top: y + 'px', height: '0', borderTop: '4px dashed #e0245e',
    zIndex: 2147483647, pointerEvents: 'none' });
  const tag = document.createElement('div'); tag.className = 'pp-mark'; tag.textContent = label;
  Object.assign(tag.style, { position: 'absolute', right: '12px', top: (y + 6) + 'px', background: '#e0245e', color: '#fff',
    font: '600 13px/1.3 system-ui, sans-serif', padding: '4px 8px', borderRadius: '4px', zIndex: 2147483647, pointerEvents: 'none' });
  document.body.append(line, tag);
}
"""

UNMARK_JS = "() => document.querySelectorAll('.pp-mark').forEach(e => e.remove())"

CTA_JS = r"""
() => {
  const vh = innerHeight, out = [];
  const els = [...document.querySelectorAll('a[href], button, [role=button]')];
  for (const el of els) {
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    if (r.width < 20 || r.height < 16 || s.visibility === 'hidden' || s.display === 'none') continue;
    if (el.closest('header, nav')) continue;
    const href = el.getAttribute('href') || '';
    const samePage = href.startsWith('#') || (href.includes('#') && el.pathname === location.pathname);
    const inHero = r.top + scrollY < vh * 1.2;
    const text = (el.innerText || el.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ');
    if (!text || text.length > 60) continue;
    if (samePage || (inHero && el.tagName === 'BUTTON')) {
      el.setAttribute('data-pp-cta', out.length);
      out.push({ idx: out.length, text, href, same_page: samePage, top: Math.round(r.top + scrollY) });
    }
    if (out.length >= 6) break;
  }
  return out;
}
"""

LINKS_MID_JS = r"""
() => {
  const vh = innerHeight, out = [], seen = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    const r = a.getBoundingClientRect(); const y = r.top + scrollY;
    if (a.closest('header, nav, footer') || r.width < 20 || r.height < 12) continue;
    if (a.origin !== location.origin || a.pathname === location.pathname || a.target === '_blank') continue;
    if (y < vh * 1.3 || seen.has(a.pathname)) continue;
    seen.add(a.pathname);
    a.setAttribute('data-pp-link', out.length);
    out.push({ idx: out.length, text: (a.innerText || a.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 50),
               path: a.pathname, top: Math.round(y) });
  }
  // Prefer links spread down the page.
  return out.filter((_, i) => i % Math.max(1, Math.floor(out.length / 3)) === 0).slice(0, 2);
}
"""

STICKY_JS = r"""
() => {
  const vw = innerWidth, vh = innerHeight, bars = [];
  for (const el of document.querySelectorAll('body *')) {
    const s = getComputedStyle(el); if (s.position !== 'fixed' && s.position !== 'sticky') continue;
    const r = el.getBoundingClientRect();
    if (r.width < 40 || r.height < 20 || r.bottom <= 0 || r.top >= vh || r.right <= 0 || r.left >= vw) continue;
    if (s.visibility === 'hidden' || s.display === 'none' || +s.opacity === 0) continue;
    if (r.height > vh * 0.4) continue;   // a pinned scroll stage is content, not an overlay
    // A sticky element only overlays content while it is stuck at its offset (e.g. top: 66px under a header).
    if (s.position === 'sticky') {
      const top = parseFloat(s.top), bottom = parseFloat(s.bottom);
      const stuck = (!isNaN(top) && Math.abs(r.top - top) <= 2) || (!isNaN(bottom) && Math.abs(vh - r.bottom - bottom) <= 2);
      if (!stuck) continue;
    }
    if (bars.some(b => b.el.contains(el))) continue;
    bars.push({ el, r, h: Math.round(r.height), w: Math.round(Math.min(r.right, vw) - Math.max(r.left, 0)),
                name: (el.getAttribute('aria-label') || el.id || el.tagName.toLowerCase() + '.' + el.className.toString().split(' ')[0]).slice(0, 40) });
  }
  bars.forEach((b, i) => b.el.setAttribute('data-pp-sticky', i));
  // Covered share of the screen, sampled on a grid so overlapping bars aren't counted twice.
  let hit = 0, total = 0;
  for (let y = 4; y < vh; y += 8) for (let x = 4; x < vw; x += 8) {
    total++; if (bars.some(b => x >= b.r.left && x <= b.r.right && y >= b.r.top && y <= b.r.bottom)) hit++;
  }
  return { covered_pct: Math.round(100 * hit / Math.max(total, 1)), bars: bars.map(b => ({ name: b.name, h: b.h, w: b.w })) };
}
"""

OVERFLOW_JS = r"""
() => {
  const vw = document.documentElement.clientWidth;
  if (document.documentElement.scrollWidth <= vw + 1) return [];
  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.right > vw + 1 && r.width > 0 && r.width < vw * 3 && ![...el.children].some(c => c.getBoundingClientRect().right > vw + 1)) {
      el.setAttribute('data-pp-over', out.length); out.push({ tag: el.tagName.toLowerCase(), cls: el.className.toString().slice(0, 40), over: Math.round(r.right - vw) });
      if (out.length >= 6) break;
    }
  }
  return out;
}
"""

HERO_JS = r"""
() => {
  const vh = innerHeight;
  const h1 = document.querySelector('h1');
  const ctas = [...document.querySelectorAll('a[href], button')].filter(el => {
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    const bg = s.backgroundColor; const filled = bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent';
    return r.width > 60 && r.height > 28 && !el.closest('header, nav') && (filled || /shop|book|get|start|explore|plan|buy|browse/i.test(el.innerText || ''));
  });
  const first = ctas.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)[0];
  if (first) first.setAttribute('data-pp-hero', '1');
  return { h1_bottom: h1 ? Math.round(h1.getBoundingClientRect().bottom) : null,
           cta_text: first ? first.innerText.trim().slice(0, 40) : null,
           cta_top: first ? Math.round(first.getBoundingClientRect().top) : null, vh };
}
"""


class Prober:
    def __init__(self, run, browser):
        self.run, self.browser = run, browser
        self.out = run / "probes"
        self.out.mkdir(parents=True, exist_ok=True)
        self.findings, self.summary = [], []

    def shot_path(self, name):
        # Numbered when the path is created (not from len(findings)), so checks running at the same time never collide.
        self.shots_taken = getattr(self, "shots_taken", 0) + 1
        return self.out / f"{self.shots_taken:03d}-{re.sub(r'[^a-z0-9]+', '-', name.lower())[:60]}.jpg"

    def add(self, check, page, profile, severity, title, detail, shots, measured=None):
        # Same problem on several devices/pages -> one group in the report.
        stem = re.sub(r"\s+(?:than\s+)?(?:on\s+)?an?\s+(?:budget|iPhone|tablet|laptop|desktop).*$", "", title)
        stem = re.sub(r"\d+%", "N%", stem)
        group = check if check in ("back_restore", "sticky_overlay", "overflow", "hero_cta") else f"{check}|{stem}"
        self.findings.append({"id": f"u{len(self.findings) + 1:03d}", "check": check, "group": group, "page": page["slug"], "url": page["url"],
                              "profile": profile, "device": PROFILES[profile]["label"], "severity": severity,
                              "title": title, "detail": detail, "measured": measured or {},
                              "shots": [paths.run_relative(self.run, s) for s in shots]})
        print(f"  [{severity}] {profile} {page['slug']}: {title}", flush=True)

    async def open(self, page_info, profile):
        ctx = await self.browser.new_context(**context_options(profile))
        pg = await ctx.new_page()
        try:
            await pg.goto(page_info["url"], wait_until="load", timeout=45000)
        except PWTimeout:
            pass
        try:
            await pg.wait_for_load_state("networkidle", timeout=6000)
        except PWTimeout:
            pass
        # Trigger lazy content, then return to the top.
        h = await pg.evaluate("document.documentElement.scrollHeight")
        for y in range(0, min(h, 15000), 600):
            await pg.evaluate(f"window.scrollTo(0, {y})")
            await pg.wait_for_timeout(60)
        await pg.evaluate("window.scrollTo(0, 0)")
        await pg.wait_for_timeout(600)
        return ctx, pg

    async def static_checks(self, page_info, profile):
        ctx, pg = await self.open(page_info, profile)
        try:
            await self.section_fit(pg, page_info, profile)
            await self.sticky(pg, page_info, profile)
            await self.overflow(pg, page_info, profile)
            if page_info["kind"] == "home":
                await self.hero(pg, page_info, profile)
        finally:
            await ctx.close()

    async def section_fit(self, pg, page_info, profile):
        info = await pg.evaluate(SECTIONS_JS)
        vh, top_bar = info["vh"], info["fixedTop"]
        avail = vh - top_bar
        rows = []
        is_phone = profile in ("mobile", "mobile_large")
        for s in info["sections"]:
            ratio = s["height"] / avail
            rows.append({**s, "ratio": round(ratio, 2)})
            # Pinned "scrollytelling": tall section with a big sticky stage. On phones a small sticky bar (add-to-cart) doesn't count.
            if s["sticky_inside"] >= (0.6 * vh if is_phone else 120) and s["height"] > 1.6 * vh:
                await self._section_shot_and_add(pg, page_info, profile, s, avail, top_bar, "scroll_driven", "minor",
                    f"Scroll-driven section '{s['heading']}' is {s['height'] / vh:.1f} screens tall",
                    "It pins content and plays out as you scroll. Anyone who jumps into it (a button or anchor) or scrolls fast lands mid-sequence with no cue.")
                continue
            if is_phone:
                continue   # phones scroll by nature; section and card fit matter on tablet and up
            if s["card_height"] > avail:
                await self._card_shot_and_add(pg, page_info, profile, s, avail, top_bar)
            elif 1.0 < ratio <= 1.35 or (s["i"] == 0 and ratio > 1.0):
                await self._section_shot_and_add(pg, page_info, profile, s, avail, top_bar, "section_fit", "major",
                    f"Section '{s['heading']}' doesn't fit a {PROFILES[profile]['label']} screen ({s['height']}px vs {avail}px visible)",
                    f"{s['height'] - avail}px ({(ratio - 1) * 100:.0f}%) spills below the fold after the {top_bar}px sticky header, so "
                    "the section never shows whole and its bottom (often cards or buttons) is cut off.")
        self.summary.append({"page": page_info["slug"], "profile": profile, "visible_height": avail, "sticky_header": top_bar,
                             "sections": [{k: r[k] for k in ("heading", "height", "ratio", "sticky_inside")} for r in rows]})

    async def _card_shot_and_add(self, pg, page_info, profile, s, avail, top_bar):
        await pg.evaluate(f"window.scrollTo(0, {max(0, s['card_top'] - top_bar - 10)})")
        await pg.wait_for_timeout(500)
        await pg.evaluate(MARK_JS, [f'[data-pp-card="{s["i"]}"]', "", "#2f5bea"])
        vw = PROFILES[profile]["viewport"]["width"]
        path = self.shot_path(f"card-fit-{profile}-{page_info['slug']}-{s['card_name']}")
        await pg.screenshot(path=str(path), type="jpeg", quality=70, full_page=True,
                            clip={"x": 0, "y": max(0, s["card_top"] - 20), "width": vw, "height": min(s["card_height"] + 40, int(avail * 2.2))})
        await pg.evaluate(UNMARK_JS)
        draw_fold(path, s["card_top"] - 10 + avail - max(0, s["card_top"] - 20), f"screen ends here on {PROFILES[profile]['label']}")
        self.add("card_fit", page_info, profile, "major",
                 f"Cards in '{s['heading']}' are taller than a {PROFILES[profile]['label']} screen",
                 f"One card ('{s['card_name']}') is {s['card_height']}px tall but only {avail}px is visible under the {top_bar}px sticky header, "
                 "so no card is ever seen whole and visitors must scroll inside each one.", [path],
                 {"card_height": s["card_height"], "visible_height": avail, "section": s["heading"]})

    async def _section_shot_and_add(self, pg, page_info, profile, s, avail, top_bar, check, sev, title, detail):
        await pg.evaluate(f"window.scrollTo(0, {max(0, s['top'] - top_bar)})")
        await pg.wait_for_timeout(500)
        await pg.evaluate(MARK_JS, [f'[data-pp-sec="{s["i"]}"]', "", "#2f5bea"])
        vw = PROFILES[profile]["viewport"]["width"]
        clip_h = min(s["height"] + 20, int(avail * 2.2))
        path = self.shot_path(f"{check}-{profile}-{page_info['slug']}-{s['heading']}")
        await pg.screenshot(path=str(path), type="jpeg", quality=70, full_page=True,
                            clip={"x": 0, "y": max(0, s["top"] - 10), "width": vw, "height": clip_h})
        await pg.evaluate(UNMARK_JS)
        # With the section's top just under the sticky header, the screen shows down to section top + visible height.
        draw_fold(path, s["top"] + avail - max(0, s["top"] - 10), f"screen ends here on {PROFILES[profile]['label']}")
        self.add(check, page_info, profile, sev, title, detail, [path],
                 {"section_height": s["height"], "visible_height": avail, "sticky_header": top_bar})

    async def sticky(self, pg, page_info, profile):
        await pg.evaluate("window.scrollTo(0, innerHeight * 1.5)")
        await pg.wait_for_timeout(500)
        info = await pg.evaluate(STICKY_JS)
        limit = 18 if PROFILES[profile]["mobile"] else 14
        if info["covered_pct"] > limit:
            await pg.evaluate(MARK_JS, ["[data-pp-sticky]", f"Fixed/sticky elements cover {info['covered_pct']}% of the screen", "#e0245e"])
            path = self.shot_path(f"sticky-{profile}-{page_info['slug']}")
            await pg.screenshot(path=str(path), type="jpeg", quality=70)
            await pg.evaluate(UNMARK_JS)
            self.add("sticky_overlay", page_info, profile, "major" if info["covered_pct"] > 25 else "minor",
                     f"Fixed bars and widgets cover {info['covered_pct']}% of the screen while scrolling",
                     "Bars: " + ", ".join(f"{b['name']} ({b['w']}x{b['h']})" for b in info["bars"][:5]), [path], info)

    async def overflow(self, pg, page_info, profile):
        culprits = await pg.evaluate(OVERFLOW_JS)
        if not culprits:
            return
        await pg.evaluate("document.querySelector('[data-pp-over=\"0\"]').scrollIntoView({block: 'center'})")
        await pg.wait_for_timeout(400)
        await pg.evaluate(MARK_JS, ["[data-pp-over]", "These elements stick out past the screen edge (sideways scroll)", "#e0245e"])
        path = self.shot_path(f"overflow-{profile}-{page_info['slug']}")
        await pg.screenshot(path=str(path), type="jpeg", quality=70)
        await pg.evaluate(UNMARK_JS)
        self.add("overflow", page_info, profile, "major", "Page scrolls sideways",
                 "Elements wider than the screen: " + "; ".join(f"{c['tag']}.{c['cls']} (+{c['over']}px)" for c in culprits), [path],
                 {"culprits": culprits})

    async def hero(self, pg, page_info, profile):
        await pg.evaluate("window.scrollTo(0, 0)")
        await pg.wait_for_timeout(300)
        h = await pg.evaluate(HERO_JS)
        if h["cta_top"] is not None and h["cta_top"] > h["vh"] - 40:
            await pg.evaluate(MARK_JS, ['[data-pp-hero="1"]', f"Main button '{h['cta_text']}' is below the first screen", "#e0245e"])
            path = self.shot_path(f"hero-{profile}-{page_info['slug']}")
            await pg.screenshot(path=str(path), type="jpeg", quality=70, full_page=True,
                                clip={"x": 0, "y": 0, "width": PROFILES[profile]["viewport"]["width"], "height": min(h["cta_top"] + 120, h["vh"] * 2)})
            await pg.evaluate(UNMARK_JS)
            self.add("hero_cta", page_info, profile, "major" if not PROFILES[profile]["mobile"] else "minor",
                     f"Main call-to-action '{h['cta_text']}' isn't visible on arrival",
                     f"It starts {h['cta_top']}px down on a {h['vh']}px-tall screen, so visitors must scroll to find what to do.", [path], h)

    async def interactions(self, page_info, profile):
        ctx, pg = await self.open(page_info, profile)
        try:
            await self.in_page_jumps(pg, page_info, profile)
            await self.back_restore(pg, page_info, profile)
        finally:
            await ctx.close()

    async def in_page_jumps(self, pg, page_info, profile):
        sections = (await pg.evaluate(SECTIONS_JS))
        ctas = await pg.evaluate(CTA_JS)
        for c in ctas:
            await pg.evaluate("window.scrollTo(0, 0)")
            await pg.wait_for_timeout(400)
            # Scroll the button into view the way a user would reach it, then click it.
            el = pg.locator(f'[data-pp-cta="{c["idx"]}"]').first
            try:
                await el.scroll_into_view_if_needed(timeout=3000)
                before_y = await pg.evaluate("scrollY")
                before_url = pg.url
                await el.click(timeout=4000)
            except Exception:
                continue
            await pg.wait_for_timeout(1800)
            if same_path(pg.url, before_url) is False:
                await pg.go_back()
                await pg.wait_for_timeout(1200)
                # A reload on Back wipes our data-pp-* markers; put them back so the remaining buttons still get tested.
                sections = await pg.evaluate(SECTIONS_JS)
                await pg.evaluate(CTA_JS)
                continue
            after_y = await pg.evaluate("scrollY")
            if abs(after_y - before_y) < 50:
                continue
            land = await pg.evaluate(r"""(top) => { const vh = innerHeight; const secs = [...document.querySelectorAll('[data-pp-sec]')]
                .map(s => ({ i: +s.dataset.ppSec, r: s.getBoundingClientRect(), h: (s.querySelector('h1,h2,h3') || {}).innerText }));
              const at = secs.filter(s => s.r.top <= top + 5 && s.r.bottom > top + 5)[0];
              return at ? { section: (at.h || '').trim().slice(0, 60), offset: Math.round(top - at.r.top), section_height: Math.round(at.r.height),
                            progress: Math.min(100, Math.round(100 * (top - at.r.top) / Math.max(at.r.height - vh, 1))),
                            visible_text: [...document.querySelectorAll('h1,h2,h3,h4,p,a,button,li,span')].filter(e => { const r = e.getBoundingClientRect();
                              const st = getComputedStyle(e); return r.bottom > top && r.top < vh && r.width > 0 && +st.opacity > 0.2 && st.visibility !== 'hidden' && e.children.length === 0; })
                              .reduce((n, e) => n + (e.innerText || '').trim().length, 0) } : null; }""", sections["fixedTop"])
            label = f"After clicking '{c['text']}' ({PROFILES[profile]['label']})"
            await pg.evaluate(MARK_JS, ["body > .pp-none", label, "#2f5bea"])
            path = self.shot_path(f"jump-{profile}-{page_info['slug']}-{c['text']}")
            await pg.screenshot(path=str(path), type="jpeg", quality=70)
            await pg.evaluate(UNMARK_JS)
            if not land:
                continue
            awkward = land["offset"] > 60 or land["offset"] < -10 or land.get("visible_text", 999) < 60
            in_scrolly = land["section_height"] > 1.6 * sections["vh"]
            if awkward or in_scrolly:
                why = []
                if land["offset"] > 60:
                    why.append(f"it lands {land['offset']}px into the section '{land['section']}' instead of at its start")
                if land["offset"] < -10:
                    why.append("the section start is hidden under the sticky header")
                if land.get("visible_text", 999) < 60:
                    why.append("the screen you land on is almost empty because its content only animates in as you keep scrolling")
                if in_scrolly:
                    why.append(f"the target is a scroll-driven section {land['section_height'] / sections['vh']:.1f} screens tall "
                               f"and you arrive {max(0, land['progress'])}% through it, with no cue that you should keep scrolling")
                self.add("in_page_jump", page_info, profile, "major",
                         f"'{c['text']}' leaves you at an awkward spot", "; ".join(why).capitalize() + ".", [path],
                         {"scroll_before": before_y, "scroll_after": after_y, **land})

    async def back_restore(self, pg, page_info, profile):
        links = await pg.evaluate(LINKS_MID_JS)
        for ln in links:
            await pg.evaluate("window.scrollTo(0, 0)")
            el = pg.locator(f'[data-pp-link="{ln["idx"]}"]').first
            try:
                await pg.evaluate(f"document.querySelector('[data-pp-link=\"{ln['idx']}\"]').scrollIntoView({{block: 'center'}})")
                await pg.wait_for_timeout(700)
                y0 = await pg.evaluate("scrollY")
                await pg.evaluate(MARK_JS, [f'[data-pp-link="{ln["idx"]}"]', f"1. Scrolled here and clicked '{ln['text']}'", "#2f5bea"])
                before = self.shot_path(f"back-before-{profile}-{page_info['slug']}-{ln['text']}")
                await pg.screenshot(path=str(before), type="jpeg", quality=70)
                await pg.evaluate(UNMARK_JS)
                start_url = pg.url
                try:
                    await el.click(timeout=4000)
                except PWTimeout:
                    # Something (a decorative overlay, a sticker) intercepts the pointer; a user's tap still reaches the link.
                    await el.evaluate("e => e.click()")
                # Any navigation away counts (servers may add a trailing slash or redirect).
                await pg.wait_for_url(lambda u: same_path(u, start_url) is False, timeout=10000)
                await pg.wait_for_timeout(1200)
                await pg.go_back(wait_until="load", timeout=20000)
            except Exception as e:
                print(f"  ! back check skipped for '{ln['text']}' ({profile}): {str(e).splitlines()[0][:100]}", flush=True)
                continue
            await pg.wait_for_timeout(2500)
            y1 = await pg.evaluate("scrollY")
            await pg.evaluate(LINKS_MID_JS)   # restore markers in case Back reloaded the page
            vh = PROFILES[profile]["viewport"]["height"]
            if abs(y1 - y0) > max(150, 0.25 * vh):
                await pg.evaluate(MARK_JS, ["body > .pp-none", f"2. After pressing Back: scrolled to {y1}px instead of {y0}px", "#e0245e"])
                after = self.shot_path(f"back-after-{profile}-{page_info['slug']}-{ln['text']}")
                await pg.screenshot(path=str(after), type="jpeg", quality=70)
                await pg.evaluate(UNMARK_JS)
                self.add("back_restore", page_info, profile, "major",
                         f"Back button doesn't return you to where you were (after opening '{ln['text']}')",
                         f"You were {y0}px down the page; Back put you at {y1}px ({'top of the page' if y1 < 50 else 'a different spot'}). "
                         "People lose their place every time they peek at a category.", [before, after],
                         {"scroll_before": y0, "scroll_after_back": y1, "link": ln["path"]})


def same_path(a, b):
    """True if two URLs are the same page (ignoring a trailing slash and the #hash)."""
    return urlparse(a).path.rstrip("/") == urlparse(b).path.rstrip("/")


def write_digest(run, findings, summary):
    lines = ["# Measured UX checks (automated, real browser)", ""]
    by_check = {}
    for f in findings:
        by_check.setdefault(f["check"], []).append(f)
    for check, items in by_check.items():
        lines.append(f"## {check} ({len(items)})")
        for f in items:
            lines.append(f"{f['id']}|{f['severity']}|{f['profile']}|{f['page']}| {f['title']}. {f['detail']}")
        lines.append("")
    lines.append("## Section heights vs visible screen (ratio > 1 = doesn't fit)")
    for s in summary:
        cells = ", ".join(f"{x['heading'][:28]!r} {x['ratio']}" for x in s["sections"][:10])
        lines.append(f"{s['profile']} {s['page']} (visible {s['visible_height']}px, sticky header {s['sticky_header']}px): {cells}")
    (run / "probes" / "probes.md").write_text("\n".join(lines), encoding="utf-8")


async def main_async(args):
    run = paths.run_dir_arg(args.run)
    manifest = json.loads((run / "capture" / "manifest.json").read_text(encoding="utf-8"))
    pages = manifest["pages"]
    # Home first, then one page per kind, then the rest.
    seen, picked = set(), []
    for p in pages:
        if p["kind"] not in seen or p["kind"] == "home":
            picked.append(p)
            seen.add(p["kind"])
    picked += [p for p in pages if p not in picked]
    picked = picked[:args.pages]
    profiles = [p for p in args.profiles.split(",") if p]
    inter = [p for p in args.interaction_profiles.split(",") if p]

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        prober = Prober(run, browser)
        sem = asyncio.Semaphore(args.concurrency)

        async def guarded(coro):
            async with sem:
                try:
                    await coro
                except Exception as e:
                    print(f"  ! {e}", flush=True)

        print(f"Static checks: {len(picked)} pages x {len(profiles)} devices", flush=True)
        await asyncio.gather(*(guarded(prober.static_checks(p, prof)) for p in picked for prof in profiles))
        print(f"Interaction checks: {min(3, len(picked))} pages x {len(inter)} devices", flush=True)
        await asyncio.gather(*(guarded(prober.interactions(p, prof)) for p in picked[:3] for prof in inter))
        await browser.close()

    sev = {"blocker": 0, "major": 1, "minor": 2}
    prober.findings.sort(key=lambda f: (sev.get(f["severity"], 3), f["check"], f["page"]))
    (run / "probes" / "probes.json").write_text(json.dumps({"findings": prober.findings, "sections": prober.summary}, indent=1,
                                                           ensure_ascii=False), encoding="utf-8")
    write_digest(run, prober.findings, prober.summary)
    print(f"{len(prober.findings)} findings -> {run / 'probes'}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--profiles", default="mobile,mobile_large,tablet,laptop,laptop_hd,desktop")
    ap.add_argument("--interaction-profiles", default="mobile,tablet,laptop")
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--concurrency", type=int, default=4)
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
