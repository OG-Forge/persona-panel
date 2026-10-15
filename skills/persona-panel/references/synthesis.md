## Your job

Turn the persona panel's raw issues into a short, prioritised fix list for the owner. Read `issues_digest.md` and `aggregate.json` in the run folder in ONE turn. Don't open individual results unless a theme is ambiguous, and then open at most 3. Write `synthesis.json` in ONE Write call.

## Rules

- **Cluster by root cause, not by wording.** "Can't find COD", "no cash on delivery?" and "only prepaid?" are one theme. Aim for 6-14 themes and merge the long tail.
- **Every theme lists the exact `persona_ids` that raised it.** Counts are computed from these, so never estimate.
- **Rank by `impact`** (1-5): how many personas hit it, how severe it was, and whether it made them leave. A blocker hit by 8 people outranks a minor nit hit by 30.
- **Use the segment table** in aggregate.json to say who is most affected. For example: "tier-3, COD-only and first-time buyers: 70% of them raised it vs 15% of metro UPI users".
- **Be specific.** Each `fix` is a concrete change someone could ship ("Add a 'COD available' badge under the price on product pages"), not advice ("improve trust").
- **Be honest about noise.** If a theme comes from one persona and looks speculative, drop it or put it in `open_questions`.
- **Keep the quick wins:** high impact, low effort.

## synthesis.json

```json
{
  "headline": "One-sentence verdict a busy owner would read",
  "summary": ["3-5 sentences: the most important things the panel showed"],
  "themes": [
    {"title": "Short name", "severity": "critical | high | medium | low", "where": "product",
     "persona_ids": ["p004", "p017"], "who": "Segments most affected, with numbers",
     "evidence": "≤40 words: what personas saw or said", "fix": "Concrete change",
     "effort": "low | medium | high", "impact": 5}
  ],
  "quick_wins": ["Theme title", "..."],
  "strengths": [{"title": "What works", "persona_ids": ["p002"]}],
  "segment_insights": ["Sentence about how a segment reacted differently"],
  "open_questions": ["Things to validate with real customers"]
}
```
