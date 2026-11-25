---
name: milestone-finish
description: Finish one POWERDESK development milestone with reproducible tests, risk checks, clear evidence and an honest completion report.
---

# Milestone finish checklist

1. Read milestone's acceptance gates and inspect changed files.
2. Run available formatter, linter, type checks and automated tests; record exact commands and outcomes.
3. Run specifically designed edge-case tests for UTC/DST, units, stale/missing data, financial reconciliation and safety controls as applicable.
4. Ensure all mock/fixture data is labeled and no live trade functionality is enabled.
5. Update README, changelog and the milestone status in roadmap.
6. Review diff for secrets, permissions, inaccurate financial claims and destructive automation.
7. Produce report: delivered; test pass/fail/skipped; measured evidence; blockers; risks; next bounded task.
8. Do not mark complete if critical checks fail or are unavailable; mark blocked/partial.
