# Assumptions (change these, then update scripts/underwrite_check.py to match)

| Assumption | Value | Why |
|---|---|---|
| Below-underwrite threshold | cumulative % of underwrite < 90% | Flags catalogs meaningfully behind plan; 10% cushion for normal variance |
| Watch threshold | trailing-3-month % < 85% while cumulative >= 90% | Catches catalogs that look fine overall but are deteriorating now |
| Underwrite curve | `projected_t = r0 * (1 - decay)^t` | Simple exponential decay; real underwriting is more detailed |
| Duplicate handling | exact (catalog, month, revenue) duplicates dropped and reported | Common statement-ingestion error |
| Ranking | by dollar gap, not percent | A 70% catalog with big revenue matters more than a 70% small one |

All figures are synthetic. These are illustrative defaults, not real underwriting standards.
