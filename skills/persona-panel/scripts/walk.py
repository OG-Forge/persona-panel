"""A tiny stateful browser CLI for a live-walker persona.

Each walker gets its own headless Chromium (own profile, own cookies), kept
alive between commands over CDP, so a cart drawer or modal opened by one
command is still there for the next. Every action prints a compact "look"
(URL, a numbered list of clickable things in view, a short text excerpt and a
screenshot path) so a walker needs one tool call per step.

Usage (SESSION is a directory, one per walker):
  walk.py SESSION start URL [--device NAME]   (default mobile)
  walk.py SESSION look
  walk.py SESSION click REF          | click-text "Add to cart"
  walk.py SESSION type REF "text"    | select REF "option"
  walk.py SESSION press Enter        | scroll down|up | back | goto URL
  walk.py SESSION stop

NAME is a profile from devices.py PROFILES: mobile, mobile_large, tablet, laptop,
laptop_hd, desktop (desktop_legacy is kept for old runs).
"""
import sys

sys.dont_write_bytecode = True  # keep the skill folder read-only

import json
import os
import re
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from devices import PROFILES

# Same device sizes as capture.py and probe.py.
DEVICES = {name: {"size": (p["viewport"]["width"], p["viewport"]["height"]), "ua": p["ua"], "touch": p["mobile"]}
           for name, p in PROFILES.items()}

LOOK_JS = r"""
(prefix) => {
  const vh = window.innerHeight, vw = window.innerWidth;
  const sel = 'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=link], [role=tab], [role=checkbox], [role=radio], [role=option], [onclick], label[for]';
  // Collect matches from the document and every open shadow root (cart drawers, checkout widgets).
  const roots = [document], all = [];
  for (let i = 0; i < roots.length; i++) {
    for (const el of roots[i].querySelectorAll('*')) if (el.shadowRoot) roots.push(el.shadowRoot);
  }
  for (const root of roots) {
    root.querySelectorAll('[data-pp-ref]').forEach(e => e.removeAttribute('data-pp-ref'));
    all.push(...root.querySelectorAll(sel));
  }
  const deepPoint = (x, y) => { let t = document.elementFromPoint(x, y);
    while (t && t.shadowRoot) { const inner = t.shadowRoot.elementFromPoint(x, y); if (!inner || inner === t) break; t = inner; }
    return t; };
  const deepContains = (a, b) => { for (let e = b; e; e = e.parentNode || e.host) if (e === a) return true; return false; };
  const out = []; let n = 0;
  for (const el of all) {
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    if (r.width < 2 || r.height < 2 || s.visibility === 'hidden' || s.display === 'none' || +s.opacity === 0) continue;
    if (r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) continue;
    const cx = Math.min(Math.max(r.left + r.width / 2, 0), vw - 1), cy = Math.min(Math.max(r.top + r.height / 2, 0), vh - 1);
    const top = deepPoint(cx, cy);
    if (top && !deepContains(el, top) && !deepContains(top, el)) continue;   // covered by something else
    let name = (el.getAttribute('aria-label') || el.innerText || el.value || el.placeholder || el.title || '').trim().replace(/\s+/g, ' ');
    if (!name) { const img = el.querySelector('img[alt]'); if (img) name = img.alt.trim(); }
    const tag = el.tagName.toLowerCase(); const type = el.type ? `:${el.type}` : '';
    if (tag === 'input' && ['checkbox', 'radio'].includes(el.type)) name = (name || (el.labels && el.labels[0] ? el.labels[0].innerText.trim() : '')) + (el.checked ? ' [checked]' : '');
    n++; el.setAttribute('data-pp-ref', prefix + n);
    out.push(`[${prefix}${n}] ${tag}${type} "${name.slice(0, 60)}"${r.width < 24 || r.height < 24 ? ' (tiny target)' : ''}`);
    if (n >= 45) break;
  }
  // Visible text of what is on screen now (shadow roots included), de-duplicated (marquees repeat a lot).
  const seen = new Set(), lines = [];
  for (const root of roots) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let t = walker.nextNode(); t; t = walker.nextNode()) {
      const v = t.textContent.trim().replace(/\s+/g, ' '); const p = t.parentElement;
      if (!v || seen.has(v) || !p || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(p.tagName)) continue;
      const r = p.getBoundingClientRect();
      if (r.width < 1 || r.bottom < 0 || r.top > vh || getComputedStyle(p).visibility === 'hidden') continue;
      seen.add(v); lines.push(v);
    }
  }
  const text = lines.join(' | ');
  const scrollPct = Math.round(100 * (window.scrollY + vh) / Math.max(document.documentElement.scrollHeight, 1));
  return { title: document.title, url: location.href, items: out, scrollPct, text };
}
"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def state_path(session):
    return session / "state.json"


def load_state(session):
    p = state_path(session)
    if not p.exists():
        sys.exit("No browser for this session. Run: walk.py SESSION start URL")
    return json.loads(p.read_text())


def site_host(url):
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def on_site(url, state):
    """The walker may only be on the site under test (or blank pages)."""
    return not state.get("site") or url.startswith(("about:", "data:")) or site_host(url) == state["site"]


def guard(page, state, blocked):
    """Enforce the walker safety rules in code, not just in the prompt: block top-level navigation to other sites."""
    def handle(route):
        req = route.request
        if req.is_navigation_request() and req.frame == page.main_frame and not on_site(req.url, state):
            blocked.append(req.url)
            route.abort()
        else:
            route.continue_()
    page.route("**/*", handle)


def connect(pw, state):
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{state['port']}")
    ctx = browser.contexts[0]
    # Close any tab that wandered off-site (e.g. a target=_blank marketplace link) and stay on the site.
    for extra in ctx.pages:
        if not on_site(extra.url, state) and len(ctx.pages) > 1:
            extra.close()
    on = [p for p in ctx.pages if on_site(p.url, state)]
    page = on[-1] if on else (ctx.pages[-1] if ctx.pages else ctx.new_page())
    # Viewport emulation lives on the CDP connection, so re-apply it every time.
    w, h = DEVICES[state['device']]['size']
    page.set_viewport_size({'width': w, 'height': h})
    return browser, page


def visible_frames(page):
    """Main frame plus child frames (cart drawers, checkout widgets) that are actually on screen."""
    frames = [page.main_frame]
    for f in page.frames[1:]:
        try:
            box = f.frame_element().bounding_box()
        except Exception:
            continue
        if box and box['width'] > 50 and box['height'] > 50:
            frames.append(f)
    return frames


def locate(page, ref):
    """Refs look like '12' (main page) or 'f2.5' (fifth item in the second visible frame)."""
    frames = visible_frames(page)
    if ref.startswith('f') and '.' in ref:
        idx = int(ref[1:ref.index('.')])
        frame = frames[idx] if idx < len(frames) else page.main_frame
        return frame.locator(f'[data-pp-ref="{ref}"]').first
    return page.locator(f'[data-pp-ref="{ref}"]').first


def look(page, session, state):
    page.wait_for_timeout(600)
    info = page.evaluate(LOOK_JS, '')
    for i, frame in enumerate(visible_frames(page)[1:], start=1):
        try:
            sub = frame.evaluate(LOOK_JS, f'f{i}.')
        except Exception:
            continue
        if sub['items']:
            info['items'] += [f'-- inside embedded frame {i} ({sub["url"][:60]}):'] + sub['items']
            info['text'] = sub['text'][:400] + ' || ' + info['text']
    state["step"] = state.get("step", 0) + 1
    shot = session / f"step_{state['step']:02d}.jpg"
    page.screenshot(path=str(shot), type="jpeg", quality=65)
    state_path(session).write_text(json.dumps(state))
    pos = page.evaluate("[Math.round(scrollY), document.documentElement.scrollHeight, innerHeight]")
    print(f"URL: {info['url']}\nTITLE: {info['title']}\n"
          f"SCROLL: at {pos[0]}px of a {pos[1]}px page (screen is {pos[2]}px tall, {info['scrollPct']}% seen)")
    print(f"SCREENSHOT: {shot}")
    print("CLICKABLE IN VIEW:")
    print("\n".join(info["items"]) or "(nothing clickable in view)")
    visible = info["text"]
    print("ON-SCREEN TEXT:", visible[:700].replace("\n", " | "))


def start(session, url, device):
    session.mkdir(parents=True, exist_ok=True)
    if state_path(session).exists():
        stop(session, quiet=True)
    spec = DEVICES[device]
    port = free_port()
    with sync_playwright() as pw:
        exe = pw.chromium.executable_path
    args = [exe, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={session / 'profile'}",
            f"--window-size={spec['size'][0]},{spec['size'][1]}", f"--user-agent={spec['ua']}",
            "--no-first-run", "--no-default-browser-check", "--hide-scrollbars", "about:blank"]
    if spec["touch"]:
        args.insert(1, "--touch-events=enabled")
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    state = {"port": port, "pid": proc.pid, "device": device, "step": 0, "site": site_host(url)}
    state_path(session).write_text(json.dumps(state))
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.2)
    with sync_playwright() as pw:
        _, page = connect(pw, state)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        look(page, session, state)


def stop(session, quiet=False):
    p = state_path(session)
    if not p.exists():
        return
    state = json.loads(p.read_text())
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(state["pid"]), "/T", "/F"], capture_output=True)
    else:
        try:
            os.kill(state["pid"], 15)
        except OSError:
            pass
    p.unlink()
    if not quiet:
        print("Browser stopped.")


def act(session, cmd, rest):
    state = load_state(session)
    with sync_playwright() as pw:
        _, page = connect(pw, state)
        blocked = []
        guard(page, state, blocked)
        try:
            if cmd == "look":
                pass
            elif cmd == "click":
                locate(page, rest[0]).click(timeout=8000)
            elif cmd == "click-text":
                page.get_by_text(rest[0], exact=False).first.click(timeout=8000)
            elif cmd == "type":
                loc = locate(page, rest[0])
                kind = loc.evaluate("e => [e.type || '', e.name || '', e.autocomplete || '', e.id || '', e.placeholder || ''].join(' ').toLowerCase()")
                if re.search(r"password|e-?mail|\btel\b|phone|mobile|cc-|card|cvv|otp|address|\bname\b", kind):
                    raise RuntimeError(f"refused: walkers may not type into personal-data fields ({kind.strip()[:60]})")
                loc.fill(rest[1], timeout=8000)
            elif cmd == "select":
                locate(page, rest[0]).select_option(label=rest[1], timeout=8000)
            elif cmd == "press":
                page.keyboard.press(rest[0])
            elif cmd == "scroll":
                h = page.viewport_size["height"] if page.viewport_size else 700
                page.mouse.wheel(0, int(h * 0.85) * (-1 if rest and rest[0] == "up" else 1))
            elif cmd == "back":
                page.go_back(wait_until="domcontentloaded", timeout=30000)
            elif cmd == "goto":
                if not on_site(rest[0], state):
                    raise RuntimeError(f"refused: {rest[0]} is not on the site under test")
                page.goto(rest[0], wait_until="domcontentloaded", timeout=60000)
            else:
                sys.exit(f"Unknown command: {cmd}")
        except Exception as e:
            print(f"ACTION FAILED: {str(e).splitlines()[0][:200]}")
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(1200)
        # The click may have opened a new tab: follow it if it's on the site, close it if it isn't.
        for p in page.context.pages:
            if p != page and not on_site(p.url, state):
                blocked.append(p.url)
                p.close()
        on = [p for p in page.context.pages if on_site(p.url, state)]
        page = on[-1] if on else page
        for url in dict.fromkeys(blocked):
            print(f"BLOCKED: leaving the site is not allowed ({url[:100]}). You are still on the site.")
        look(page, session, state)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    session, cmd, rest = Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
    if cmd == "start":
        device = "mobile"
        if "--device" in rest:
            i = rest.index("--device")
            device = rest[i + 1]
            rest = rest[:i] + rest[i + 2:]
        start(session, rest[0], device)
    elif cmd == "stop":
        stop(session)
    else:
        act(session, cmd, rest)


if __name__ == "__main__":
    main()
