# Writing a custom market profile

Use this when neither `india` nor `global` fits the audience: for example B2B buyers, parents of toddlers, college students, or wedding planners. Copy the shape of `data/markets/india.json` and save it as `RUN_DIR/market.json`, then pass `--market RUN_DIR/market.json`.

```json
{
  "name": "indian-parents-of-young-kids",
  "description": "Who this is and where the weights come from (be honest when they're guesses)",
  "currency": "₹",
  "attributes": [
    {"key": "age_band", "values": {"25-34": 55, "35-44": 40, "45-54": 5}},
    {"key": "gender", "values": {"female": 60, "male": 38, "nonbinary": 2}},
    {"key": "location_tier", "values": {"metro": 45, "tier2": 35, "tier3_small_town": 20}},
    {"key": "income", "values": {"low": 25, "middle": 50, "high": 25}},
    {"key": "kids", "values": {"one_toddler": 50, "two_kids": 35, "three_plus": 15}},
    {"key": "biggest_worry", "values": {"safety": 30, "cost": 30, "time": 25, "quality": 15}}
  ],
  "rules": [{"if": {"income": "low"}, "then": {"biggest_worry": {"cost": 2}}}],
  "phrases": {"kids": {"one_toddler": "Has one toddler at home."},
              "biggest_worry": {"cost": "Money is tight; every rupee is weighed."}},
  "cities": {"metro": ["Mumbai", "Pune"], "tier2": ["Indore"], "tier3_small_town": ["Hisar (HR)"]},
  "names": {"female": ["Priya"], "male": ["Rahul"], "nonbinary": ["Sam"]},
  "occupations": {"25-34": ["software engineer"], "35-44": ["shop owner"], "45-54": ["teacher"]}
}
```

## Rules

- Keep `age_band` (the bands in `AGE_RANGES`: 18-24, 25-34, 35-44, 45-54, 55+), `gender`, and either `location_tier` or `region`.
- Any extra attribute works. Give each value a `phrases` entry so persona cards read naturally; without one it prints as "Key: value".
- For **site** mode, keep `device`, `network`, `patience`, `traffic_source`, `context` and `accessibility_need` (copy them from india.json). The capture and screen plans depend on them.
- Use `rules` to keep combinations believable: low income makes iPhones rarer, older age lowers tech comfort, and so on.
- Prefer real numbers when you have them (the owner's analytics, a report) and say so in `description`.
- To tweak an existing market instead, write an overrides file (see the `sample_personas.py` docstring) rather than a new market.
