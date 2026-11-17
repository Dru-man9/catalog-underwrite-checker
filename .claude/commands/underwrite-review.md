---
description: Run the full underwrite review (analyze, draft, verify)
---

Run the `underwrite-vs-actual` skill end to end:

1. Run the analysis script and read its JSON output.
2. Draft `out/report.md` and `out/claims.json` following the skill's format.
3. Invoke the `checker` subagent on the draft.
4. If the verdict is REJECTED, fix the draft and re-run the checker. Repeat until APPROVED.
5. Reply with the final report and the checker's verdict.

$ARGUMENTS
