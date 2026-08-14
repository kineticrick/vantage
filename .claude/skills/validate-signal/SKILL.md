---
name: validate-signal
description: Use when proposing, evaluating, or shipping any new market signal, score, ranking or filter in Vantage — walks pre-registration, cohort design with a control, paired comparison, multiple-comparisons accounting, the findings document, and the evidence-register entry.
---

# Validating a new market signal

`config/evidence.yaml` currently holds five tested claims: four refuted —
does the acceleration score beat 12-month rank, does the fade flag predict
underperformance, does trajectory discriminate among leaders, does sector
breadth predict sector returns — and one supported, that ranking by trailing
12-month return beats the plain universe. The register is not a list of
failures; it is a record of what has and hasn't held up, and step 8 below
adds to that same file regardless of which way a new study comes out. The
process that produced these results, across two studies, was invented twice
and improvised a third time, and it produced three separate wrong
conclusions along the way (see step 3). Follow the steps below instead of
rebuilding the process from scratch or skipping it.

## 1. Write the hypothesis down and commit it before running anything

State what would count as success and what would count as failure, in
advance, and commit that design before looking at any result. The
2026-08-14 follow-up study (`docs/superpowers/findings/2026-08-14-conditional-and-sector-breadth.md`)
could not prove its own pre-registration from the repository alone — its
hypotheses were fixed in a dispatch message, not a committed design doc —
and had to disclose that gap explicitly in its own finding (§1,
"Disclosure — 'pre-registered' is not verifiable from this repository").
Commit the design first so the claim is checkable by the next reader, not
just asserted by you.

## 2. Define a control that represents current behavior

"The new score returned +8%" means nothing on its own. The entire momentum
finding is the comparison against the trailing-12-month rank Vantage already
ships — the control *is* the result. Without a control, a study produces a
number, not an answer.

## 3. Compare paired, per formation date. Never subtract two separately aggregated statistics

A difference of medians is not the median of differences. This produced
three wrong published conclusions in this project's own history — two
written by the coordinator, and the third *inside the section that had just
finished diagnosing the first two* (see the "Correction note" and §2–§4 of
`docs/superpowers/findings/2026-08-13-momentum-backtest.md`). `paired_stats`
in `tools/backtest_core.py` does this correctly: it computes the per-date
differences first and aggregates those, and reports hit rate and dispersion
alongside the point estimate. Use it; do not re-derive the arithmetic.

## 4. Count every comparison, and put the multiple-comparisons exposure beside any nominally significant result

Not in a footnote — next to the number. Across the two studies run so far,
66 comparisons were reported (33 from the parent study, 33 from the
follow-up) and exactly 3 came out nominally significant — all three
belonging to the same comparison (ranking by trailing 12-month return
against the plain universe), which is exactly the chance expectation at
conventional thresholds (`docs/superpowers/findings/2026-08-14-conditional-and-sector-breadth.md`,
§5). Neither of the follow-up's two hits clears a Bonferroni threshold over
its own 33 tests. State that arithmetic wherever a result is reported as
significant, not below the fold.

## 5. State the effective sample size

Overlapping forward windows mean formation dates stepped 21 trading days
apart, measured against horizons up to 126 days, are not independent: 102
formation dates are closer to 34 independent observations at the 3-month
horizon and 17 at the 6-month horizon (both findings documents, "Statistical
power" / §2). Report standard error at the honest N, not at 102.

## 6. Include a positive control so a null is informative — but say precisely what it licenses

A null from an instrument with no demonstrated sensitivity is not
informative. The 2026-08-14 study added `leaders_top30 − universe` as a
positive control and it worked — a large, low-noise effect, clearly
detected. But detecting that effect does **not** establish power for the
much smaller effect actually under test: the study's own §5.1 states the
control's dispersion is 4- to 13-fold better than the primary comparison's,
and is explicit that the control demonstrates the harness isn't broken, not
that the study could have seen a small real effect if one were there. Say
what your control proves and stop there.

## 7. Write the finding, caveats stated plainly

Survivorship bias, market regime, transaction costs, and any way the
study's cohorts differ from what the product actually ships (e.g. both
findings note their `leaders`/`leaders_top30` cohort is a pure rank, not the
`ret_12m >= 1.0` threshold `vantage/screener.py` actually applies — do not
let a study's control be silently reread as a description of production
behavior). A negative result is a successful outcome and belongs in the
headline, stated plainly — not softened, and not rescued by hunting the
parameter sweep for a flattering variant.

## 8. Append an entry to `config/evidence.yaml`

With a `finding:` key pointing at the document you just wrote. This is the
step that makes the study change anything: `vantage/evidence.py` loads the
register into both the weekly brief and the chat analyst, so this is how
the analyst inherits the verdict on every future run. `tests/test_evidence_config.py`
asserts every cited finding path exists on disk, so a broken pointer fails
the suite rather than silently rotting.

## Pointers

- `tools/backtest_core.py` — the shared primitives (`WINDOW_DAYS`,
  `MAX_PLAUSIBLE_RETURN`, `formation_positions`, `metrics_at`,
  `forward_return`, `paired_stats`). Start a new study here: import from this
  module rather than reimplementing cohort formation or comparison logic.
  `tools/` is not a package — insert `tools/` onto `sys.path` the way both
  existing studies do, rather than adding an `__init__.py`.
- `tools/backtest_momentum.py` and `tools/backtest_conditional.py` — worked
  examples. The first is the original study with its own cohort definitions
  and a parameter sweep; the second is the pre-registered follow-up that
  reused the primitives and added two new experiments.
- `docs/superpowers/findings/` — what a finished finding looks like,
  including how to disclose a correction rather than silently editing it out.
- `tests/test_published_findings.py` — runs the momentum backtest against the
  real snapshot and asserts the published headline figures still reproduce.
  It is the reason not to change `tools/backtest_core.py` or
  `tools/backtest_momentum.py` in a way that casually moves those numbers.
