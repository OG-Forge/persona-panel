"""Capture a website once so a large persona panel can review it cheaply.

Crawls the most shopper-relevant same-origin pages (home, collections, a
product, cart, policies, about/contact), then for each page and device profile
saves screenshot slices and a structured digest: headings, CTAs, prices, trust
signals, form labels, missing alt text, tiny text and tap targets, horizontal
overflow, console errors, and load time on a throttled mobile connection.

Usage:
  python capture.py --url https://example.com --run RUN_DIR
      [--max-pages 12] [--profiles mobile,desktop] [--extra-urls URL ...]
      [--max-slices 8]
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import asyncio

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

PROFILES = {
    "mobile": {
        "viewport": {"width": 360, "height": 780}, "device_scale_factor": 1, "is_mobile": True, "has_touch": True,
        "user_agent": "Mozilla/5.0 (Linux; Android 13; SM-A145F) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Mobile Safari/537.36",
    },
    "desktop": {
        "viewport": {"width": 1366, "height": 800}, "device_scale_factor": 1,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36",
    },
}

# Throttled load is only measured for the first pages of the mobile profile.
SLOW_4G = {"offline": False, "latency": 150, "downloadThroughput": 1.6 * 1024 * 1024 / 8,
           "uploadThroughput": 750 * 1024 / 8}

PAGE_KEYWORDS = [
    ("product", r"/products?/|/p/|/item/|/shop/[^/]+/[^/]+"),
    ("collection", r"/collections?/|/category|/categories|/shop|/catalog|/store|party-kit|kits?/|kits?$|/look"),
    ("cart", r"/cart|/bag|/basket"),
    ("shipping_returns", r"ship|return|refund|exchange|deliver"),
    ("size_guide", r"size"),
    ("faq", r"faq|help|support"),
    ("about", r"about|story|our-"),
    ("contact", r"contact"),
    ("policy", r"privacy|terms|policy|policies"),
]

EXTRACT_JS = r"""
(isMobile) => {
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0'; };
  const txt = el => (el.innerText || el.value || el.getAttribute('aria-label') || el.title || '').trim().replace(/\s+/g, ' ');
  const nameOf = el => {
    const aria = el.getAttribute('aria-label'); if (aria) return aria.trim();
    const lb = el.getAttribute('aria-labelledby'); if (lb) { const t = document.getElementById(lb); if (t) return txt(t); }
    const t = txt(el); if (t) return t;
    const img = el.querySelector('img[alt]'); if (img && img.alt.trim()) return img.alt.trim();
    return el.title || '';
  };
  const headings = [...document.querySelectorAll('h1,h2,h3')].filter(vis).slice(0, 40)
    .map(h => h.tagName.toLowerCase() + ': ' + txt(h).slice(0, 120));
  const ctas = [...document.querySelectorAll('button, a[role=button], input[type=submit], [class*=btn], [class*=button]')]
    .filter(vis).map(b => txt(b).slice(0, 60)).filter(Boolean);
  const unnamedControls = [...document.querySelectorAll('button, a[href], input:not([type=hidden]), select, textarea')]
    .filter(vis).filter(el => !nameOf(el) && !(el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`)) && !el.closest('label')).length;
  const inputs = [...document.querySelectorAll('input:not([type=hidden]), select, textarea')].filter(vis).map(el => {
    const lab = (el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`)) || el.closest('label');
    return { type: el.type || el.tagName.toLowerCase(), label: lab ? txt(lab).slice(0, 60) : '',
             placeholder: el.placeholder || '', aria: el.getAttribute('aria-label') || '' };
  }).slice(0, 25);
  const imgs = [...document.images].filter(vis);
  const noAlt = imgs.filter(i => !i.hasAttribute('alt')).length;
  const brokenImgs = imgs.filter(i => i.complete && i.naturalWidth === 0).length;
  let tinyText = 0, sampled = 0;
  for (const el of document.querySelectorAll('p, span, a, li, label, small, div')) {
    if (sampled > 1500) break;
    if (!el.childNodes.length || ![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
    if (!vis(el)) continue; sampled++;
    if (parseFloat(getComputedStyle(el).fontSize) < 12) tinyText++;
  }
  let smallTargets = 0, smallTargetExamples = [];
  if (isMobile) for (const el of document.querySelectorAll('a[href], button, input, select, [role=button]')) {
    if (!vis(el)) continue; const r = el.getBoundingClientRect();
    if (r.width < 24 || r.height < 24) { smallTargets++; if (smallTargetExamples.length < 6) smallTargetExamples.push(nameOf(el).slice(0, 30) || el.tagName); }
  }
  const body = document.body ? document.body.innerText : '';
  const lower = body.toLowerCase();
  const signals = {
    cod: /cash on delivery|\bcod\b/.test(lower), free_shipping: /free (shipping|delivery)/.test(lower),
    returns: /return|exchange|refund/.test(lower), reviews: /review|rating|★|stars?\b/.test(lower),
    contact_phone_or_whatsapp: /whatsapp|\+?\d[\d\s-]{8,}\d/.test(lower), email: /[\w.+-]+@[\w-]+\.[\w.]+/.test(body),
    secure_payment: /secure|razorpay|stripe|paytm|phonepe|upi|visa|mastercard|paypal/.test(lower),
    size_chart: /size (chart|guide)/.test(lower), delivery_time: /deliver(y|ed)? (in|within)|\d+\s*-\s*\d+\s*(business )?days/.test(lower),
    discount: /% off|sale|discount|coupon|offer/.test(lower),
  };
  const prices = [...new Set((body.match(/(₹|rs\.?|inr|\$|€|£)\s?[\d,]+(\.\d{2})?/gi) || []).map(s => s.trim()))].slice(0, 20);
  const dialogs = [...document.querySelectorAll('[role=dialog], [aria-modal=true], .modal, [class*=popup], [class*=Popup]')]
    .filter(vis).map(d => txt(d).slice(0, 120)).slice(0, 3);
  return {
    title: document.title, lang: document.documentElement.lang || '',
    meta_description: (document.querySelector('meta[name=description]') || {}).content || '',
    headings, ctas: [...new Set(ctas)].slice(0, 40), inputs, unnamed_controls: unnamedControls,
    images: imgs.length, images_missing_alt: noAlt, broken_images: brokenImgs,
    tiny_text_elements: tinyText, small_tap_targets: smallTargets, small_tap_target_examples: smallTargetExamples,
    horizontal_overflow: document.documentElement.scrollWidth > window.innerWidth + 2,
    page_height: document.documentElement.scrollHeight, signals, prices, visible_dialogs: dialogs,
    text: body.replace(/\n{2,}/g, '\n').slice(0, 5000),
  };
}
"""

LINKS_JS = """() => [...document.querySelectorAll('a[href]')].map(a => ({href: a.href, text: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 60),
  zone: a.closest('header, nav') ? 'nav' : a.closest('footer') ? 'footer' : 'main'}))"""


def norm(url):
    u = urlparse(url)
    return urlunparse((u.scheme, u.netloc.lower(), u.path.rstrip("/") or "/", "", u.query if "variant" in u.query else "", ""))


def slug_for(url, idx):
    path = urlparse(url).path.strip("/") or "home"
    return f"{idx:02d}-" + re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")[:50]


def classify(url):
    path = urlparse(url).path.lower()
    if path in ("", "/"):
        return "home"
    for kind, pat in PAGE_KEYWORDS:
        if re.search(pat, path):
            return kind
    return "other"


def pick_pages(start, links, max_pages, extra):
    origin = urlparse(start).netloc.lower()
    chosen = [norm(start)] + [norm(u) for u in extra]
    seen = set(chosen)
    buckets = {}
    for link in links:
        u = urlparse(link["href"])
        if u.scheme not in ("http", "https") or u.netloc.lower() != origin:
            continue
        if re.search(r"\.(jpg|jpeg|png|webp|gif|pdf|zip|xml)$|/account|/login|/signin|/checkout|logout|/search\?", u.path.lower()):
            continue
        n = norm(link["href"])
        if n in seen:
            continue
        kind = classify(n)
        # Nav links first, then main, then footer.
        rank = {"nav": 0, "main": 1, "footer": 2}[link["zone"]]
        buckets.setdefault(kind, []).append((rank, n))
    order = ["product", "collection", "cart", "shipping_returns", "size_guide", "faq", "about", "contact", "policy", "other"]
    quotas = {"product": 2, "collection": 2, "other": 0}
    # "other" pages: one per top-level section first (shallowest, nav first), so the capture spans the site.
    others = sorted(buckets.get("other", []), key=lambda rn: (urlparse(rn[1]).path.strip("/").count("/"), rn[0]))
    sections, spread = set(), []
    for rank, n in others:
        sec = urlparse(n).path.strip("/").split("/")[0]
        if sec not in sections:
            sections.add(sec)
            spread.append((rank, n))
    buckets["other"] = spread + [o for o in others if o not in spread]
    for kind in order:
        for _, n in sorted(buckets.get(kind, []))[:quotas.get(kind, 1)]:
            if len(chosen) >= max_pages:
                break
            if n not in seen:
                chosen.append(n)
                seen.add(n)
    # Top up with anything left if we still have room (section-spread "other" pages first).
    for kind in ["other"] + order[:-1]:
        for _, n in (buckets.get(kind, []) if kind == "other" else sorted(buckets.get(kind, []))):
            if len(chosen) >= max_pages:
                break
            if n not in seen:
                chosen.append(n)
                seen.add(n)
    return chosen


async def settle(page):
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except PWTimeout:
        pass
    # Scroll through the page to trigger lazy-loaded images, then return to top.
    height = await page.evaluate("document.documentElement.scrollHeight")
    step = page.viewport_size["height"]
    for y in range(0, min(height, 20000), step):
        await page.evaluate(f"window.scrollTo(0, {y})")
        await page.wait_for_timeout(120)
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(500)


async def slice_screens(page, out_dir, max_slices):
    vh = page.viewport_size["height"]
    height = await page.evaluate("document.documentElement.scrollHeight")
    shots = []
    for i in range(max_slices):
        y = i * vh
        if y >= height:
            break
        await page.evaluate(f"window.scrollTo(0, {y})")
        await page.wait_for_timeout(250)
        path = out_dir / f"screen_{i + 1:02d}.jpg"
        await page.screenshot(path=str(path), type="jpeg", quality=70)
        shots.append(path.name)
    await page.evaluate("window.scrollTo(0, 0)")
    return shots, height


NAV_TIMING_JS = """() => { const n = performance.getEntriesByType('navigation')[0];
  const fcp = performance.getEntriesByType('paint').find(e => e.name === 'first-contentful-paint');
  return { dom_ready_seconds: n ? +(n.domContentLoadedEventEnd / 1000).toFixed(1) : null,
           load_seconds: n && n.loadEventEnd ? +(n.loadEventEnd / 1000).toFixed(1) : null,
           first_contentful_paint_seconds: fcp ? +(fcp.startTime / 1000).toFixed(1) : null,
           transfer_kb: n ? Math.round(performance.getEntriesByType('resource').reduce((s, r) => s + (r.transferSize || 0), n.transferSize || 0) / 1024) : null }; }"""


async def throttled_load(browser, url, profile):
    ctx = await browser.new_context(**PROFILES[profile])
    page = await ctx.new_page()
    cdp = await ctx.new_cdp_session(page)
    await cdp.send("Network.enable")
    await cdp.send("Network.emulateNetworkConditions", SLOW_4G)
    await cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    try:
        await page.goto(url, wait_until="load", timeout=45000)
        result = await page.evaluate(NAV_TIMING_JS)
    except PWTimeout:
        result = await page.evaluate(NAV_TIMING_JS)
        result["load_seconds"] = ">45"
    finally:
        await ctx.close()
    return result


async def discover_links(browser, url, profile):
    ctx = await browser.new_context(**PROFILES[profile])
    page = await ctx.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2500)
        return await page.evaluate(LINKS_JS)
    except Exception as e:
        print(f"  ! link discovery failed for {url} ({profile}): {e}", flush=True)
        return []
    finally:
        await ctx.close()


async def capture_page(browser, url, profile, out_dir, max_slices):
    ctx = await browser.new_context(**PROFILES[profile])
    page = await ctx.new_page()
    console_errors, failed = [], []
    page.on("console", lambda m: m.type == "error" and len(console_errors) < 10 and console_errors.append(m.text[:200]))
    page.on("requestfailed", lambda r: len(failed) < 10 and failed.append(r.url[:150]))
    status = None
    try:
        try:
            resp = await page.goto(url, wait_until="load", timeout=45000)
            status = resp.status if resp else None
        except PWTimeout:
            status = "timeout"
        timing = await page.evaluate(NAV_TIMING_JS)
        await settle(page)
        out_dir.mkdir(parents=True, exist_ok=True)
        data = await page.evaluate(EXTRACT_JS, profile == "mobile")
        shots, height = await slice_screens(page, out_dir, max_slices)
        data.update({"url": page.url, "requested_url": url, "status": status, "profile": profile,
                     "timing": timing, "screens": shots,
                     "screens_cover_fraction": round(min(1, len(shots) * page.viewport_size["height"] / max(height, 1)), 2),
                     "console_errors": console_errors, "failed_requests": failed})
        (out_dir / "data.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        return data
    finally:
        await ctx.close()


def digest_entry(slug, kind, d):
    s = d["signals"]
    t = d["timing"]
    flags = []
    if d["horizontal_overflow"]:
        flags.append("HORIZONTAL SCROLL/OVERFLOW")
    if d["broken_images"]:
        flags.append(f"{d['broken_images']} broken images")
    if d["console_errors"]:
        flags.append(f"{len(d['console_errors'])} console errors")
    if norm(d["url"]) != norm(d["requested_url"]):
        flags.append(f"redirected from {d['requested_url']}" + (" (PASSWORD/LOGIN WALL?)" if re.search(r"password|login|signin", d["url"]) else ""))
    if d["visible_dialogs"]:
        flags.append("possible popup/dialog on load: " + " | ".join(d["visible_dialogs"]))
    speed = f"fast-network load {t.get('load_seconds')}s"
    if d.get("throttled"):
        th = d["throttled"]
        speed += (f" | SLOW 4G + slow CPU (budget phone): first paint {th.get('first_contentful_paint_seconds')}s, "
                  f"full load {th.get('load_seconds')}s, {th.get('transfer_kb')} KB")
    lines = [
        f"### {slug} [{kind}] ({d['profile']}) {d['url']}",
        f"status {d['status']} | title: {d['title']!r} | {speed}",
        f"screens: {', '.join(d['screens'])} (cover {int(d['screens_cover_fraction'] * 100)}% of page)",
        "headings: " + " / ".join(h for h in d["headings"][:15] if h.split(":", 1)[1].strip()),
        "buttons/CTAs: " + " | ".join(d["ctas"][:20]),
        "prices seen: " + ", ".join(d["prices"][:10]),
        "trust signals present: " + ", ".join(k for k, v in s.items() if v) + " | missing: " + ", ".join(k for k, v in s.items() if not v),
        f"a11y: {d['images_missing_alt']}/{d['images']} images missing alt, {d['unnamed_controls']} unnamed controls, "
        f"{d['tiny_text_elements']} tiny-text elements (<12px)"
        + (f", {d['small_tap_targets']} small tap targets (<24px) e.g. {d['small_tap_target_examples']}" if d["profile"] == "mobile" else ""),
    ]
    if d["inputs"]:
        lines.append("form fields: " + "; ".join(f"{i['type']}:{i['label'] or i['aria'] or i['placeholder'] or 'NO LABEL'}" for i in d["inputs"][:12]))
    if flags:
        lines.append("FLAGS: " + "; ".join(flags))
    return "\n".join(lines)


async def run_capture(args):
    run = Path(args.run)
    cap = run / "capture"
    cap.mkdir(parents=True, exist_ok=True)
    profiles = [p.strip() for p in args.profiles.split(",") if p.strip()]
    manifest = {"start_url": args.url, "captured_at": time.strftime("%Y-%m-%d %H:%M"), "profiles": profiles, "pages": []}
    origin = urlparse(args.url).netloc.lower()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        print(f"Discovering pages from {args.url} ...", flush=True)
        desktop_links, mobile_links = await asyncio.gather(discover_links(browser, args.url, "desktop"),
                                                           discover_links(browser, args.url, "mobile"))
        pages = pick_pages(args.url, desktop_links + mobile_links, args.max_pages, args.extra_urls)

        # If no product page was linked from home, look one level deeper (a collection page).
        if not any(classify(u) == "product" for u in pages):
            for u in [u for u in pages if classify(u) == "collection"][:2]:
                deeper = await discover_links(browser, u, "desktop")
                products = [norm(l["href"]) for l in deeper
                            if urlparse(l["href"]).netloc.lower() == origin and classify(norm(l["href"])) == "product"]
                if products:
                    pages.insert(1, products[0])
                    pages = list(dict.fromkeys(pages))[:args.max_pages]
                    break

        sem = asyncio.Semaphore(args.concurrency)
        jobs = [(idx, url, profile) for idx, url in enumerate(pages) for profile in profiles]

        async def job(idx, url, profile):
            slug = slug_for(url, idx)
            async with sem:
                try:
                    data = await capture_page(browser, url, profile, cap / slug / profile, args.max_slices)
                    if profile == "mobile" and idx < args.throttled_pages:
                        data["throttled"] = await throttled_load(browser, url, profile)
                        (cap / slug / profile / "data.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
                except Exception as e:
                    print(f"  ! {slug} {profile}: {e}", flush=True)
                    return idx, url, profile, None
            print(f"  captured {slug} [{classify(url)}] {profile}: {len(data['screens'])} screens", flush=True)
            return idx, url, profile, data

        results = await asyncio.gather(*(job(*j) for j in jobs))
        await browser.close()

    digest = [f"# Site capture: {args.url}",
              f"Captured {manifest['captured_at']}. Profiles: mobile = 360x780 budget Android, desktop = 1366x800.",
              "Screens are consecutive viewport-height slices from the top of each page (screen_01 is what you see on arrival).", ""]
    for idx, url in enumerate(pages):
        slug, kind = slug_for(url, idx), classify(url)
        entry = {"slug": slug, "url": url, "kind": kind, "profiles": {}}
        for _, _, profile, data in (r for r in results if r[0] == idx):
            if data is None:
                continue
            entry["profiles"][profile] = {"dir": f"capture/{slug}/{profile}", "screens": data["screens"],
                                          "final_url": data["url"], "status": data["status"]}
            digest += [digest_entry(slug, kind, data), ""]
        if entry["profiles"]:
            manifest["pages"].append(entry)

    (cap / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    (cap / "digest.md").write_text("\n".join(digest), encoding="utf-8")
    print(f"Captured {len(manifest['pages'])} pages -> {cap}")
    if not manifest["pages"]:
        sys.exit("No pages captured")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--max-pages", type=int, default=12)
    ap.add_argument("--profiles", default="mobile,desktop")
    ap.add_argument("--extra-urls", nargs="*", default=[])
    ap.add_argument("--max-slices", type=int, default=8)
    ap.add_argument("--throttled-pages", type=int, default=3)
    ap.add_argument("--concurrency", type=int, default=4)
    asyncio.run(run_capture(ap.parse_args()))


if __name__ == "__main__":
    main()
