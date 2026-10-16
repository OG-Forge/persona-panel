The file is a JSON array with one object per persona, written in a single Write call. Keep every string short: this is data for counting, not prose. No markdown, no comments, valid JSON only.

```json
[
  {
    "id": "p001",
    "first_impression": "≤20 words, in the persona's own voice",
    "understood_offer": true,
    "seen": "home 1-3, product 1-2",
    "left_at": "product screen 2 (null if they stayed to the end)",
    "outcome": "buy | maybe | no",
    "scores": {"clarity": 3, "trust": 2, "appeal": 4, "ease": 3, "value": 3},
    "price_feel": "cheap | fair | pricey | too_expensive | unclear",
    "issues": [
      {"where": "product", "severity": "blocker | major | minor", "category": "trust",
       "what": "≤20 words: the problem as this persona experienced it", "fix": "≤15 words: concrete change",
       "shot": "the short id of the image that shows it (e.g. i03), a measured-check id like u004, a live walker's SCREENSHOT path, or null"}
    ],
    "liked": ["≤10 words"],
    "would_change_mind": "≤20 words: the single thing that would turn no/maybe into yes",
    "quote": "≤25 words, how they'd describe it to a friend"
  }
]
```

- `scores` are 1-5 (1 = terrible, 3 = okay, 5 = excellent) from this persona's point of view.
- `category` is one of: clarity, trust, price, navigation, performance, accessibility, content, visual, checkout, mobile, language, product, other.
- `where` is a page kind (home, product, collection, cart, checkout, policy, about, other) for sites, or an aspect (value_prop, pricing, name, audience_fit, feasibility, differentiation, other) for concepts.
- 0-4 issues per persona, most important first. An issue only this persona would hit is valuable; don't pad with generic ones.
- Use `null` for `left_at` when they didn't leave, and omit `seen` for concepts.
