# Project Jury backlog

Improvements found in the first real runs (ledgerline full review, doorknock one-reviewer review, TaskWrite one-on-one, 2026-11-13). Ordered by priority within each section.

**Suggested order:** 1 to 4 first (small), then 5, 8 and 9 together (they decide whether true claims survive), then 12 (eval set), then deploy (28).

## 1. Bugs found in real runs

- [x] **1. Dotfiles can't be cited.** `verifier.py` uses `ev.ref.lstrip("./")`, which strips every leading dot, so `.github/workflows/tests.yml` and `.gitignore` always fail. Use `removeprefix("./")` and add a test. Seen in the TaskWrite chat: a true CI claim dropped twice.
- [x] **2. Verdicts lost to the token cap.** Ledgerline's 4 verdicts failed with `BudgetExceeded` after the debate. Reserve budget for round 3 plus the summary; end the debate early when the remainder can't cover it.
- [x] **3. Empty debate turns accepted.** The Product manager's last ledgerline turn had an empty message. Require a minimum length on `DebateTurn.message`.
- [x] **4. Cost estimate about 2x too low.** A real review is ~17 calls x ~45k tokens = ~770k tokens, not 370k. Update the Cost section in `CLAUDE.md`.

## 2. What the reviewers get to see

- [x] **5. Smarter file picking.** Rank app code (`src/`, `app/`, `server*`) and UI pages above tooling (`eval/`, `scripts/`, `mockups/`, `docs/`); stop alphabetical tie-breaks. Ledgerline's brief had 7 `eval/` scripts but no front-end.
- [ ] **6. Persona-aware briefs.** Shared core plus a few persona-specific files (UI pages for the UX designer, routes and config for the Senior engineer).
- [ ] **7. Smaller brief.** ~120k characters (~40k tokens) per call is costly; summarise lower-priority files to cut it roughly in half.
- [x] **8. Citable file tree.** Allow evidence like "no lockfile exists" against the brief's file list (`kind: tree`).
- [x] **9. Looser quote matching.** Tolerate small differences in quotes while still rejecting invented ones.
- [ ] **10. Debate tools.** Build `read_file` and `search_repo`; needs the full repo stored, not just the brief.
- [ ] **11. Branch awareness.** Let ingestion pick a branch, or note when other branches differ (doorknock's deploy config is only on `byok`).

## 3. Review quality and honesty

- [ ] **12. Eval set.** 3 to 5 known repos (good, weak, misleading README) to check the panel can praise as well as criticise. Rerun after prompt or model changes.
- [ ] **13. Check reasoning, not just quotes.** The verifier confirms a quote exists, not that the point drawn from it is right. Add a cheap second-pass check.
- [ ] **14. Real debate when everyone agrees.** On ledgerline all four started "unsure" and nobody challenged anyone. Nudge one reviewer to argue the other side.
- [ ] **15. Builder answers as evidence.** Make the user's answers citable, marked as coming from the builder.

## 4. Product features

- [ ] **16. Live website review.** Headless browser capture plus a vision model into a citable site log.
- [ ] **17. Video demo log** (milestone 7).
- [ ] **18. Talk to the room mid-debate.** Router supports it; the page only allows it after the review ends.
- [ ] **19. Re-run a failed round from the page.** Ledgerline's verdicts had to be re-run with a script.
- [ ] **20. More personas:** investor, security reviewer, developer panel.
- [ ] **21. Shareable report.** Export a finished review as a page or PDF.
- [ ] **22. Compare runs.** Review again after fixes and show which verdicts moved.

## 5. Cost and models

- [x] **23. Model fallback.** Switch to the next free model when one is rate-limited upstream (Gemma was, on 2026-11-13).
- [x] **24. Show quota before starting.** "This review needs ~17 requests, you have N left."
- [ ] **25. Prompt caching.** The brief is identical across calls; caching roughly halves cost on paid models.
- [ ] **26. Paid tiers.** Bring-your-own-key and a "deep review" mode.

## 6. Engineering

- [x] **27. CI for Jury itself.** It flagged missing CI on all three reviewed projects and has none.
- [ ] **28. Push to GitHub, then deploy.** Docker plus a free host (SQLite resets there).
- [ ] **29. Phone width and accessibility pass** on the web page.
- [ ] **30. One chat store.** The CLI chat writes to `jury.sqlite`, the web chat to `jury_app.sqlite`.
