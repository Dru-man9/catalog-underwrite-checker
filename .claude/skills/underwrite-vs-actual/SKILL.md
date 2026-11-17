---
name: underwrite-vs-actual
description: Compare each catalog's actual revenue to its underwritten projection, flag underperformers, and draft a short commentary. Use when asked to review portfolio performance, check catalogs against underwrite, or run the monthly underwrite review.
---

# Underwrite vs. Actual

## Steps
1. Run `python scripts/generate_data.py` only if `data/portfolio.db` does not exist.
2. Run `python scripts/underwrite_check.py` and read the JSON. This is your ONLY source of numbers.
3. Report data-quality issues first (`data_quality.duplicate_rows_dropped`). State what was dropped.
4. Build the report in the format below. Rank by `dollar_gap` (largest shortfall first).
5. For each BELOW_UNDERWRITE or WATCH catalog, write one line: the figure, then a driver
   *hypothesis* labeled "possible:" or "unknown". Never state a cause as fact.
6. Write every number you cite into `out/claims.json` as
   `[{"catalog": "<name>", "metric": "<metric>", "value": <number>}]`.
   Metrics: `pct_of_underwrite`, `trailing3_pct`, `dollar_gap`, `actual_total`, `underwritten_total`.
7. Invoke the `checker` subagent. Fix and re-verify until it reports all figures verified.

## Output format (`out/report.md`)
```
# Underwrite Review - as of <as_of>
**Data quality:** <issues, or "no issues found">
**Summary:** <n_below> below underwrite, <n_watch> on watch, total gap $<total>

| Catalog | % of UW | Trailing 3M % | $ Gap | Status |
|---|---|---|---|---|
...flagged catalogs only, ranked by $ gap...

## Commentary
<one line per flagged catalog: figure + "possible: ..." or "unknown">

## Recommended next actions
<2-4 concrete actions, e.g., request distributor statements for X, re-check metadata for Y>
```

## Don'ts
- Don't round, recompute, or estimate any figure.
- Don't list OK catalogs in the table (mention the count only).
- Don't claim a cause the data cannot show.
