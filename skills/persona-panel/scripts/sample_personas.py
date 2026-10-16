"""Sample a diverse panel of shopper personas from a market profile.

Demographics come from weighted distributions plus coherence rules, not from
an LLM, because LLM-invented personas drift toward the same optimistic,
middle-of-the-road customer. Every value of every attribute is guaranteed to
appear at least once when the panel is large enough, so minority segments
(screen-reader users, first-time online shoppers, slow-3G visitors) are never
silently dropped.

Usage:
  python sample_personas.py --run RUN_DIR [--market india] [--n 100]
      [--batch-size 10] [--live 8] [--seed 7] [--overrides overrides.json]
Flag defaults come from the persona-panel config (see paths.py / config.py show).
--market takes a market name (~/.persona-panel/markets/<name>.json shadows the
bundled data/markets/<name>.json) or a path to a market JSON file.

overrides.json (all keys optional):
  {"set":      {"age_band": {"18-24": 50, "25-34": 40, "35-44": 10, "45-54": 0, "55+": 0}},
   "multiply": {"device": {"desktop_laptop": 0.5}},
   "notes":    "Brand targets 18-30 streetwear fans"}
"set" replaces an attribute's weights, "multiply" scales the listed values (set first), and
"notes" is free text the script ignores. An unknown attribute stops the run. Attribute keys
and values for the bundled markets: docs/CONFIGURATION.md, "Attribute reference".
"""
import sys

sys.dont_write_bytecode = True  # keep the skill folder read-only

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import paths

AGE_RANGES = {"18-24": (18, 24), "25-34": (25, 34), "35-44": (35, 44), "45-54": (45, 54), "55+": (55, 72)}

# How many screens a persona looks at before deciding to stay or leave.
ATTENTION = {"low": 3, "medium": 6, "high": 10}

ENTRY_PAGE = {
    "instagram_ad": "product", "influencer_link": "product", "whatsapp_forward": "product",
    "tiktok": "product", "friend_shared_link": "product", "saw_it_on_a_marketplace": "product",
    "email_newsletter": "collection", "google_search": "home_or_collection",
    "youtube": "home", "reddit_thread": "home", "typed_url_or_bookmark": "home",
}

PHRASES = {
    "device": {
        "budget_android": "a budget Android phone (small screen, slow processor, storage nearly full)",
        "midrange_android": "a mid-range Android phone",
        "iphone": "an iPhone",
        "desktop_laptop": "a laptop/desktop browser",
        "tablet": "a tablet",
    },
    "network": {
        "fast_wifi": "fast Wi-Fi", "good_4g_5g": "decent 4G/5G",
        "patchy_4g": "patchy 4G that drops in and out", "slow_3g": "a slow 3G-like connection",
    },
    "language": {
        "english_fluent": "Reads English fluently.",
        "hinglish_comfortable": "Comfortable with simple English and Hinglish; long or formal English slows them down.",
        "regional_language_first": "Thinks in their regional language; gets by with very simple English and relies on icons, prices and pictures.",
        "english_native": "Native English speaker.",
        "english_second_language": "English is a second language; idioms, slang and dense copy trip them up.",
    },
    "tech_comfort": {
        "low": "Not confident with apps or websites; afraid of pressing the wrong thing.",
        "medium": "Average with technology.",
        "high": "Very tech-savvy; notices sloppy UX instantly.",
    },
    "shopping_experience": {
        "first_time_online": "Has barely ever bought anything online.",
        "occasional": "Shops online now and then.",
        "frequent": "Shops online all the time and compares everything to Amazon/Myntra-level polish.",
    },
    "payment_pref": {
        "cod_only": "Will only pay Cash on Delivery; won't prepay an unknown brand.",
        "cod_preferred": "Prefers Cash on Delivery but would use UPI if the site feels trustworthy.",
        "upi": "Pays with UPI.",
        "card_or_emi": "Pays by card, sometimes EMI.",
        "card": "Pays by card.", "apple_google_pay": "Expects Apple Pay / Google Pay.",
        "paypal": "Prefers PayPal.", "buy_now_pay_later": "Likes buy-now-pay-later options.",
        "local_wallet": "Uses a local e-wallet and gives up if it isn't supported.",
    },
    "shopper_type": {
        "impulse_buyer": "Impulse buyer: buys fast if something grabs them, leaves fast if it doesn't.",
        "deal_hunter": "Deal hunter: looks for discounts, coupons and free shipping first.",
        "comparison_shopper": "Comparison shopper: opens other tabs to compare price and quality.",
        "brand_conscious": "Brand-conscious: cares how the brand looks and what wearing it says about them.",
        "quality_seeker": "Quality seeker: wants materials, specs, sizing and durability details before buying.",
        "gift_buyer": "Buying a gift for someone else; worries about size, delivery date and returns.",
        "casual_browser": "Casual browser: no plan to buy; needs a reason to care.",
        "skeptic": "Skeptic: assumes small online brands might be scams until proven otherwise.",
    },
    "trust_baseline": {
        "trusting": "Fairly trusting of new sites.",
        "cautious": "Cautious with new sites; looks for reviews and contact details.",
        "skeptical": "Very skeptical; needs strong proof (reviews, policies, real contact info) before buying.",
    },
    "accessibility_need": {
        "none": "",
        "low_vision": "Has low vision: uses large text/zoom, struggles with small or low-contrast text.",
        "color_blind": "Is red-green colour blind.",
        "screen_reader": "Is blind and uses a screen reader: experiences the page through headings, link/button names, alt text and form labels only.",
        "motor_tremor": "Has a hand tremor: small or tightly packed tap targets cause mis-taps.",
        "dyslexia": "Has dyslexia: long paragraphs, justified text and fancy fonts are hard work.",
        "adhd_easily_distracted": "Has ADHD: easily distracted, popups and clutter derail them.",
    },
    "aesthetic_taste": {
        "minimal_clean": "minimal, clean design", "bold_loud": "bold, loud, graphic stuff",
        "playful_quirky": "playful, quirky humour", "premium_luxury": "premium, luxury feel",
        "trend_chaser": "whatever is trending right now", "practical_no_fuss": "practical, no-fuss basics",
    },
    "context": {
        "relaxed_at_home": "relaxing at home", "late_night_scrolling": "scrolling late at night in bed",
        "on_commute": "on a bumpy commute, one-handed", "sneaking_a_look_at_work": "sneaking a look at work",
        "in_a_hurry": "in a hurry between things", "with_a_friend_deciding_together": "looking with a friend and deciding together",
    },
    "intent": {
        "ready_to_buy": "ready to buy if it checks out", "considering": "considering a purchase",
        "just_browsing": "just browsing", "researching_for_later": "researching for a later purchase",
    },
}

TRAFFIC_PHRASE = {
    "instagram_ad": "tapped an Instagram ad", "google_search": "found the site through a Google search",
    "whatsapp_forward": "opened a link a friend forwarded on WhatsApp", "influencer_link": "followed an influencer's link",
    "youtube": "came from a YouTube video", "typed_url_or_bookmark": "typed the URL after hearing about the brand",
    "saw_it_on_a_marketplace": "saw the brand on a marketplace and came to the official site",
    "tiktok": "came from a TikTok video", "friend_shared_link": "opened a link a friend sent",
    "reddit_thread": "clicked a link in a Reddit thread", "email_newsletter": "clicked a newsletter email",
}


def read_json_file(p):
    """Parse a JSON file (a UTF-8 BOM, as Windows editors write, is fine); exit with a message if broken."""
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except ValueError as e:
        sys.exit(f"{p}: not valid JSON ({e})")
    except OSError as e:
        sys.exit(f"{p}: can't read ({e})")


def load_market(name_or_path):
    try:
        p = paths.find_market(name_or_path)
    except FileNotFoundError as e:
        sys.exit(str(e))
    return read_json_file(p)


def apply_overrides(market, overrides):
    attrs = {a["key"]: a for a in market["attributes"]}
    for key, values in overrides.get("set", {}).items():
        if key not in attrs:
            sys.exit(f"Override for unknown attribute '{key}'")
        attrs[key]["values"] = dict(values)
    for key, mults in overrides.get("multiply", {}).items():
        if key not in attrs:
            sys.exit(f"Override for unknown attribute '{key}'")
        for v, m in mults.items():
            attrs[key]["values"][v] = attrs[key]["values"].get(v, 0) * m


def weights_for(attr, persona, rules):
    w = dict(attr["values"])
    for rule in rules:
        if attr["key"] not in rule["then"]:
            continue
        if all(persona.get(k) == v for k, v in rule["if"].items()):
            for v, m in rule["then"][attr["key"]].items():
                if v in w:
                    w[v] *= m
    return w


def draw(rng, weights):
    items = [(k, v) for k, v in weights.items() if v > 0]
    total = sum(v for _, v in items)
    r = rng.uniform(0, total)
    for k, v in items:
        r -= v
        if r <= 0:
            return k
    return items[-1][0]


def sample_one(rng, market):
    persona = {}
    for attr in market["attributes"]:
        persona[attr["key"]] = draw(rng, weights_for(attr, persona, market["rules"]))
    # Second pass: rules whose condition is sampled after their target get a chance to apply.
    for attr in market["attributes"]:
        others = {k: v for k, v in persona.items() if k != attr["key"]}
        persona[attr["key"]] = draw(rng, weights_for(attr, others, market["rules"]))
    return persona


def ensure_coverage(rng, personas, market, locked):
    """Make sure every value with non-zero weight appears at least once."""
    for attr in market["attributes"]:
        key = attr["key"]
        wanted = [v for v, w in attr["values"].items() if w > 0]
        if len(personas) < len(wanted) * 2:
            continue
        for value in wanted:
            counts = Counter(p[key] for p in personas)
            if counts[value]:
                continue
            most_common = counts.most_common(1)[0][0]
            candidates = [p for p in personas if p[key] == most_common and (key, id(p)) not in locked]
            if candidates:
                chosen = rng.choice(candidates)
                chosen[key] = value
                locked.add((key, id(chosen)))


def view_profile_for(rng, device):
    """Which captured screen this persona sees (see devices.py)."""
    if device == "tablet":
        return "tablet"
    if device == "desktop_laptop":
        return "laptop" if rng.random() < 0.65 else "desktop"
    return "mobile"


def enrich(rng, i, persona, market, mode):
    gender = persona.get("gender", "female")
    names = market.get("names", {})
    name = rng.choice(names.get(gender) or names.get("female") or ["Alex"])
    band = persona.get("age_band", "25-34")
    lo, hi = AGE_RANGES.get(band, (25, 40))
    place_key = persona.get("location_tier") or persona.get("region")
    city = rng.choice(market.get("cities", {}).get(place_key) or [market.get("default_city", "their city")])
    occupation = rng.choice(market.get("occupations", {}).get(band) or [market.get("default_occupation", "working adult")])

    attention = ATTENTION[persona.get("patience", "medium")]
    if persona.get("accessibility_need") == "adhd_easily_distracted" or persona.get("context") == "in_a_hurry":
        attention = max(2, attention - 1)

    device = persona.get("device", "")
    persona.update({
        "id": f"p{i:03d}",
        "name": name,
        "age": rng.randint(lo, hi),
        "city": city,
        "occupation": occupation,
        "view_profile": view_profile_for(rng, device),
        "attention_budget_screens": attention,
        "entry_page": ENTRY_PAGE.get(persona.get("traffic_source"), "home"),
    })
    persona["card"] = persona_card(persona, market, mode)
    return persona


BROWSING_ONLY = ("device", "network", "context", "traffic_source", "patience", "accessibility_need")


def phrase(market, key, value):
    """Readable text for an attribute value: market-specific phrases, then built-ins, then plain text."""
    custom = market.get("phrases", {}).get(key, {})
    if value in custom:
        return custom[value]
    if value in PHRASES.get(key, {}):
        return PHRASES[key][value]
    return f"{key.replace('_', ' ').capitalize()}: {str(value).replace('_', ' ')}."


CARD_HANDLED = {"age_band", "gender", "location_tier", "region", "income", "device", "network", "context",
                "traffic_source", "intent", "aesthetic_taste", "patience", "accessibility_need"}


def persona_card(p, market, mode="site"):
    pronoun = {"female": "She", "male": "He"}.get(p.get("gender"), "They")
    gender_label = {"female": "woman", "male": "man"}.get(p.get("gender"), "non-binary person")
    place = p["city"] + (f" ({p['location_tier'].replace('_', ' ')})" if "location_tier" in p else "")
    income = f" {p['income'].replace('_', ' ').capitalize()} income." if "income" in p else ""
    lines = [f"{p['name']}, {p['age']}, {gender_label}, {p['occupation']} in {place}.{income}"]
    # Device/network/context and arrival are written independently: custom markets may omit any of them.
    if mode == "site" and "device" in p:
        how = f"Browsing on {phrase(market, 'device', p['device']).rstrip('.')}"
        if "network" in p:
            how += f" over {phrase(market, 'network', p['network']).rstrip('.')}"
        if "context" in p:
            how += f", {phrase(market, 'context', p['context']).rstrip('.')}"
        lines.append(how + ".")
    intent = phrase(market, "intent", p["intent"]).rstrip(".") if "intent" in p else ""
    if mode == "site" and "traffic_source" in p:
        lines.append(f"{pronoun} {TRAFFIC_PHRASE.get(p['traffic_source'], 'arrived')}" + (f" and is {intent}." if intent else "."))
    elif intent:
        lines.append(f"Mindset: {intent}.")
    if "aesthetic_taste" in p:
        lines.append(f"Likes {phrase(market, 'aesthetic_taste', p['aesthetic_taste']).rstrip('.')}.")
    # Every other sampled attribute, in market order (this is what makes custom markets work).
    for attr in market["attributes"]:
        k = attr["key"]
        if k in p and k not in CARD_HANDLED:
            lines.append(phrase(market, k, p[k]))
    if mode == "site" and p.get("view_profile") in ("tablet", "laptop", "desktop"):
        lines.append({"tablet": "Screen: a tablet held upright (820x1180).", "laptop": "Screen: a laptop with a 1366x768 browser window.",
                      "desktop": "Screen: a big 1920x1080 monitor."}[p["view_profile"]])
    if mode == "site" and "patience" in p:
        lines.append(f"Patience: {p['patience']} (looks at about {p['attention_budget_screens']} screens before deciding to stay or leave).")
    if mode == "site" and p.get("accessibility_need", "none") != "none":
        lines.append(phrase(market, "accessibility_need", p["accessibility_need"]))
    return " ".join(l for l in lines if l)


def ensure_screens(rng, personas, market, minimum):
    """Guarantee enough tablet/laptop/desktop reviewers; phone-heavy markets would otherwise leave PC layouts untested.

    Capped at 10% of the panel per screen type, so small panels keep most of their phone users."""
    per_screen = min(minimum, max(1, len(personas) // 10))
    for prof, device in (("tablet", "tablet"), ("laptop", "desktop_laptop"), ("desktop", "desktop_laptop")):
        have = [p for p in personas if p["view_profile"] == prof]
        # Prefer donors whose rare values won't vanish: skip personas holding the only copy of a value.
        counts = {k: Counter(p.get(k) for p in personas) for k in ("network", "context", "accessibility_need")}
        donors = [p for p in personas if p["view_profile"] == "mobile"
                  and all(counts[k][p.get(k)] > 1 for k in counts if k in p)]
        rng.shuffle(donors)
        for p in donors[:max(0, per_screen - len(have))]:
            p["device"], p["view_profile"] = device, prof
            if device == "desktop_laptop":
                if p.get("network") in ("slow_3g", "patchy_4g"):
                    p["network"] = "fast_wifi"
                if p.get("context") == "on_commute":
                    p["context"] = "relaxed_at_home"
            p["card"] = persona_card(p, market, "site")


def pick_live(personas, keys, k):
    """Greedy farthest-point selection: the k personas most different from each other."""
    if k <= 0:
        return []
    def rarity(p):
        return sum(1 / counts[key][p[key]] for key in keys)
    counts = {key: Counter(p[key] for p in personas) for key in keys}
    # One walker per screen type first (phone, tablet, laptop, desktop), then the most different personas.
    chosen = []
    for prof in ("mobile", "laptop", "tablet", "desktop"):
        group = [p for p in personas if p.get("view_profile") == prof and p not in chosen]
        if group and len(chosen) < k:
            chosen.append(max(group, key=rarity))
    if not chosen:
        chosen = [max(personas, key=rarity)]
    while len(chosen) < min(k, len(personas)):
        def min_dist(p):
            return min(sum(p[key] != c[key] for key in keys) for c in chosen)
        rest = [p for p in personas if p not in chosen]
        chosen.append(max(rest, key=lambda p: (min_dist(p), rarity(p))))
    return chosen


def main():
    cfg = paths.config_or_exit()
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="Run directory")
    ap.add_argument("--mode", choices=["site", "concept"], default="site")
    ap.add_argument("--market", default=cfg["market"], help="Market name or path to a market JSON")
    ap.add_argument("--n", type=int, default=cfg["n"])
    ap.add_argument("--batch-size", type=int, default=cfg["batch_size"])
    ap.add_argument("--live", type=int, default=cfg["live"], help="How many personas walk the live site in a real browser")
    ap.add_argument("--seed", type=int, default=cfg["seed"])
    ap.add_argument("--min-per-screen", type=int, default=cfg["min_per_screen"],
                    help="Site mode: at least this many personas per screen type (tablet, laptop, desktop), converted from phone users")
    ap.add_argument("--overrides", help="JSON file with weight overrides")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    market = load_market(args.market)
    if args.overrides:
        apply_overrides(market, read_json_file(Path(args.overrides).expanduser()))
    if args.mode == "concept":
        market["attributes"] = [a for a in market["attributes"] if a["key"] not in BROWSING_ONLY]
        args.live = 0
    keys = [a["key"] for a in market["attributes"]]

    personas, seen = [], set()
    attempts = 0
    while len(personas) < args.n and attempts < args.n * 50:
        attempts += 1
        p = sample_one(rng, market)
        sig = tuple(p[k] for k in keys)
        if sig in seen:
            continue
        seen.add(sig)
        personas.append(p)
    ensure_coverage(rng, personas, market, set())
    personas = [enrich(rng, i + 1, p, market, args.mode) for i, p in enumerate(personas)]

    if args.mode == "site" and "device" in keys:
        ensure_screens(rng, personas, market, args.min_per_screen)
    live = pick_live(personas, keys, args.live)
    live_ids = [p["id"] for p in live]
    for p in personas:
        p["mode"] = "live" if p["id"] in live_ids else "panel"

    # Panel batches share a device profile so a batch reviews one set of screenshots.
    batches = []
    for profile in (("concept",) if args.mode == "concept" else ("mobile", "tablet", "laptop", "desktop")):
        group = [p["id"] for p in personas if p["mode"] == "panel" and (args.mode == "concept" or p["view_profile"] == profile)]
        for j in range(0, len(group), args.batch_size):
            batches.append({"batch_id": f"b{len(batches) + 1:02d}", "profile": profile,
                            "persona_ids": group[j:j + args.batch_size]})

    run = paths.run_dir_arg(args.run)
    run.mkdir(parents=True, exist_ok=True)
    (run / "personas.json").write_text(json.dumps(personas, indent=1, ensure_ascii=False), encoding="utf-8")
    (run / "batches.json").write_text(json.dumps({"market": market["name"], "mode": args.mode, "attributes": keys, "panel": batches, "live": live_ids},
                                                 indent=1), encoding="utf-8")

    lines = [f"# Panel: {len(personas)} personas ({market['name']} market, seed {args.seed})", ""]
    for key in keys:
        c = Counter(p[key] for p in personas)
        lines.append(f"- **{key}**: " + ", ".join(f"{v} {n}" for v, n in c.most_common()))
    lines += ["", f"Live walkers: {', '.join(live_ids)}", ""]
    lines += [f"- {p['id']} [{p['mode']}/{p['view_profile']}] {p['card']}" for p in personas]
    (run / "personas.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {len(personas)} personas, {len(batches)} panel batches, {len(live_ids)} live walkers to {run}")
    for key in ("age_band", "device", "location_tier", "region", "accessibility_need"):
        if key in keys:
            c = Counter(p[key] for p in personas)
            print(f"  {key}: " + ", ".join(f"{v}={n}" for v, n in c.most_common()))


if __name__ == "__main__":
    main()
