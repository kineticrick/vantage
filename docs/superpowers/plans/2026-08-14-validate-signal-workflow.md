# Validate-Signal Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make pre-registered backtesting the default path for a new signal — an invocable workflow plus a library the next study imports instead of importing its predecessor.

**Architecture:** The shared backtest primitives move out of `tools/backtest_momentum.py` into `tools/backtest_core.py`; both existing studies import from there, keeping only their own cohort definitions. A reproduction test pins the published findings against the real snapshot so a refactor of those primitives cannot silently invalidate them. A project skill encodes the workflow and the specific errors this project made.

**Tech Stack:** Python 3.14, pandas, pytest; markdown for the skill.

**Spec:** `docs/superpowers/specs/2026-08-14-validate-signal-workflow-design.md`

## Global Constraints

- Run everything with the project venv: `.venv/bin/python`, `.venv/bin/pytest`.
- **No new runtime dependencies.**
- **No behavior change.** This project touches no pipeline code, no prompt, no dashboard, and does not alter `config/evidence.yaml`'s contents. Do not modify anything under `vantage/`.
- **The extraction is a pure move.** Function bodies are relocated verbatim, not rewritten, reformatted or "improved" in transit. A behavior change here would silently alter two published studies.
- `tools/` is not a package. Both existing tools resolve imports by inserting `tools/` on `sys.path`; follow that established pattern rather than introducing a new one.
- **`run_backtest` returns integer horizon keys** (`out["paired"][21]`), while `cache/history/backtest-results.json` has them stringified by `json.dumps`. Use int keys when calling the function, string keys when reading the artifact.
- Full suite baseline before starting: **334 tests passing** (`.venv/bin/pytest -q`).

---

### Task 1: Extract the shared primitives

**Files:**
- Create: `tools/backtest_core.py`
- Modify: `tools/backtest_momentum.py`, `tools/backtest_conditional.py`
- Test: `tests/test_backtest_core.py`

**Interfaces:**
- Produces, from `tools/backtest_core.py`:
  - `WINDOW_DAYS`, `MAX_PLAUSIBLE_RETURN`
  - `formation_positions(n_rows, lookback=252, forward=126, step=21)`
  - `metrics_at(values, pos)`
  - `forward_return(values, pos, horizon)`
  - `paired_stats(periods, horizon, a, b) -> dict`
- `tools/backtest_momentum.py` re-exports these by importing them, so existing test modules that import them from there keep working untouched.

- [ ] **Step 1: Write the failing test**

Create `tests/test_backtest_core.py`:

```python
import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from backtest_core import (MAX_PLAUSIBLE_RETURN, WINDOW_DAYS,
                           formation_positions, forward_return, metrics_at,
                           paired_stats)

def _ramp(n, daily):
    return 100.0 * np.cumprod(np.full(n, 1.0 + daily))

def test_windows_and_guard_are_the_published_values():
    assert WINDOW_DAYS == {"ret_1m": 21, "ret_3m": 63, "ret_6m": 126, "ret_12m": 252}
    assert MAX_PLAUSIBLE_RETURN == 10.0

def test_formation_positions_boundaries():
    pos = formation_positions(700, lookback=252, forward=126, step=21)
    assert pos[0] == 252
    assert max(pos) <= 700 - 126 - 1
    assert formation_positions(200, lookback=252, forward=126) == []

def test_metrics_at_measures_backwards():
    vals = _ramp(400, 0.001)
    m = metrics_at(vals, 399)
    assert set(m) == set(WINDOW_DAYS)
    assert m["ret_12m"] == pytest.approx(1.001 ** 252 - 1, rel=1e-9)

def test_metrics_at_returns_none_without_history():
    assert metrics_at(_ramp(100, 0.001), 99) is None

def test_forward_return_looks_ahead_and_stops_at_the_end():
    vals = _ramp(400, 0.002)
    assert forward_return(vals, 100, 63) == pytest.approx(1.002 ** 63 - 1, rel=1e-9)
    assert forward_return(vals, 399, 63) is None

def test_paired_stats_pairs_per_period():
    periods = [{"forward": {21: {"a": 0.10, "b": 0.04}}},
               {"forward": {21: {"a": 0.02, "b": 0.05}}},
               {"forward": {21: {"a": 0.06, "b": 0.01}}}]
    out = paired_stats(periods, 21, "a", "b")
    assert out["periods"] == 3
    assert out["wins"] == 2
    assert out["median_diff"] == pytest.approx(0.05)

def test_paired_stats_skips_periods_missing_either_side():
    periods = [{"forward": {21: {"a": 0.10, "b": None}}},
               {"forward": {21: {"a": 0.02, "b": 0.05}}}]
    assert paired_stats(periods, 21, "a", "b")["periods"] == 1

def test_studies_still_expose_the_primitives():
    # backtest_momentum re-exports them, so existing test modules that import
    # from it keep working after the move.
    import backtest_momentum as bm
    for name in ("WINDOW_DAYS", "formation_positions", "metrics_at",
                 "forward_return", "paired_stats"):
        assert hasattr(bm, name), name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_backtest_core.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest_core'`

If `test_paired_stats_pairs_per_period` or `test_paired_stats_skips_periods_missing_either_side` fails **after** the move for a reason other than the import, stop and report: it means `paired_stats`' contract is not what this test assumes, and the test — not the function — must be corrected against the real implementation.

- [ ] **Step 3: Do the extraction**

Create `tools/backtest_core.py` with this docstring, then **move the six definitions verbatim** from `tools/backtest_momentum.py` (`WINDOW_DAYS` and `MAX_PLAUSIBLE_RETURN` at lines 24-25, `formation_positions` at 28, `metrics_at` at 36, `forward_return` at 53, `paired_stats` at 140), preserving their bodies and comments exactly:

```python
"""Primitives shared by every backtest in this project.

A study defines its own cohorts; these are the parts every study needs and
none should reimplement — where the formation dates fall, how a trailing
window is measured, how a forward return is taken, and how two cohorts are
compared per date.

That last one is not optional. Comparing two separately aggregated statistics
produced three wrong conclusions in this project's own history; `paired_stats`
computes per-date differences and aggregates those. See
.claude/skills/validate-signal/SKILL.md.
"""
```

It needs `import numpy as np` (used by `metrics_at`, `forward_return` and `paired_stats`).

In `tools/backtest_momentum.py`, delete those six definitions and add, alongside the existing `sys.path` shim:

```python
from backtest_core import (MAX_PLAUSIBLE_RETURN, WINDOW_DAYS,  # noqa: F401
                           formation_positions, forward_return, metrics_at,
                           paired_stats)
```

The `# noqa: F401` is deliberate — several are re-exports for existing importers rather than direct uses.

In `tools/backtest_conditional.py`, change its existing import from `backtest_momentum` to `backtest_core`. Leave everything else in both files alone: `run_period`, `COHORTS`, `PAIRS`, `run_backtest`, `SWEEP` and `main` stay where they are.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_backtest_core.py tests/test_backtest_momentum.py tests/test_backtest_conditional.py -q`
Expected: PASS. **The two existing suites must pass with zero edits** — they are the regression guard on the move. If either needs a change, the extraction was not a pure move; stop and report.

- [ ] **Step 5: Run the full suite and commit**

Run: `.venv/bin/pytest -q` → expect 334 + 8 = 342.

```bash
git add tools/backtest_core.py tools/backtest_momentum.py \
        tools/backtest_conditional.py tests/test_backtest_core.py
git commit -m "refactor(tools): extract shared backtest primitives to backtest_core"
```

---

### Task 2: Pin the published findings

The test that makes the extraction safe. Both study suites run on synthetic fixtures; the real numbers live only in two markdown documents and in git-ignored JSON, so nothing currently notices if a refactor changes them.

**Files:**
- Create: `tests/test_published_findings.py`

**Interfaces:**
- Consumes: `backtest_momentum.run_backtest`, `vantage.momentum.MomentumParams`.

- [ ] **Step 1: Write the test**

Create `tests/test_published_findings.py`:

```python
"""The published findings must still reproduce.

Extracting shared primitives is exactly the change that could alter a published
result with nothing noticing: both study suites run on synthetic fixtures, and
the real numbers live only in docs/superpowers/findings/ and in git-ignored
JSON. This runs the momentum backtest against the real snapshot and asserts the
headline figures from
docs/superpowers/findings/2026-08-13-momentum-backtest.md.

Skips when cache/history/ is absent — that directory is git-ignored, so a fresh
clone has no snapshot. It must skip, never silently pass.
"""
import glob
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

SNAPSHOTS = sorted(glob.glob(str(REPO / "cache" / "history" / "prices-*.parquet")))
needs_snapshot = pytest.mark.skipif(
    not SNAPSHOTS, reason="no price snapshot in cache/history (git-ignored)")


@pytest.fixture(scope="module")
def baseline():
    import pandas as pd
    from backtest_momentum import run_backtest
    from vantage.momentum import MomentumParams
    prices = pd.read_parquet(SNAPSHOTS[-1]).sort_index()
    return run_backtest(prices, MomentumParams())


@needs_snapshot
def test_formation_date_count(baseline):
    assert baseline["periods"] == 102


@needs_snapshot
def test_published_aggregate_spreads(baseline):
    # "the 12-month-leader cohort outperformed the accelerating cohort by
    #  -0.37 percentage points at 1 month, -3.81pp at 3 months, -3.93pp at
    #  6 months"  — findings §1. Note: horizon keys are ints from the
    #  function, strings only after json.dumps.
    spreads = baseline["spread_vs_leaders"]
    assert spreads[21] == pytest.approx(-0.0037, abs=5e-5)
    assert spreads[63] == pytest.approx(-0.0381, abs=5e-5)
    assert spreads[126] == pytest.approx(-0.0393, abs=5e-5)


@needs_snapshot
def test_published_paired_medians(baseline):
    # The paired figures are a different statistic from the aggregate spreads
    # above and are published separately. Pinning both is deliberate: a change
    # that made them agree would be as much a regression as one that moved
    # either.
    paired = baseline["paired"]
    expected = {21: -0.0121, 63: -0.0141, 126: -0.0531}
    wins = {21: 42, 63: 44, 126: 38}
    for horizon, med in expected.items():
        cell = paired[horizon]["accelerating-leaders"]
        assert cell["median_diff"] == pytest.approx(med, abs=5e-5)
        assert cell["wins"] == wins[horizon]
        assert cell["periods"] == 102


@needs_snapshot
def test_the_headline_conclusion_still_holds(baseline):
    # The finding's entire claim: the acceleration score loses to the 12-month
    # rank at every horizon, on both statistics.
    assert all(v < 0 for v in baseline["spread_vs_leaders"].values())
    assert all(baseline["paired"][h]["accelerating-leaders"]["median_diff"] < 0
               for h in (21, 63, 126))
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/pytest tests/test_published_findings.py -q -rs`

Expected: 4 passed, taking roughly 25 seconds (one `run_backtest` over 102 formation dates and ~900 tickers, shared across the four tests by the module-scoped fixture).

If the snapshot is absent it must report 4 **skipped** with the reason shown by `-rs` — confirm that by temporarily renaming `cache/history/` and re-running, then rename it back. Report both outcomes.

If any figure fails, **do not adjust the expected value**. Stop and report: either the extraction changed behavior, or a published finding is wrong, and both need a human decision.

- [ ] **Step 3: Run the full suite and commit**

Run: `.venv/bin/pytest -q` → expect 346. Note the total wall time and report it; the suite was ~6 seconds before this test.

```bash
git add tests/test_published_findings.py
git commit -m "test: pin the published momentum findings against the real snapshot"
```

---

### Task 3: The workflow skill and the README

**Files:**
- Create: `.claude/skills/validate-signal/SKILL.md`
- Modify: `README.md`

- [ ] **Step 1: Write the skill**

Create `.claude/skills/validate-signal/SKILL.md`. Frontmatter first:

```markdown
---
name: validate-signal
description: Use when proposing, evaluating, or shipping any new market signal, score, ranking or filter in Vantage — walks pre-registration, cohort design with a control, paired comparison, multiple-comparisons accounting, the findings document, and the evidence-register entry.
---
```

Then the body. Write it as instructions to whoever is doing the work, and keep every step's justification tied to something that actually happened in this repository — that specificity is the point, and generic statistical advice would not have prevented any of these:

1. **Write the hypothesis down and commit it before running anything.** State what would count as success and what would count as failure, in advance. The 2026-08-14 follow-up study could not prove pre-registration from the repository alone — its hypotheses lived in a dispatch message — and had to disclose that in its own finding. Commit the design first so the claim is checkable.

2. **Define a control that represents current behavior.** "The new score returned +8%" means nothing. The entire momentum result is the comparison against the trailing-12-month rank Vantage already ships. Without a control a study produces a number, not an answer.

3. **Compare paired, per formation date. Never subtract two separately aggregated statistics.** A difference of medians is not the median of differences. This produced three wrong conclusions in this project — two written by the coordinator, one *inside the section that had just diagnosed the error*. `backtest_core.paired_stats` does it correctly; use it.

4. **Count every comparison, and put the multiple-comparisons exposure beside any nominally significant result**, not in a footnote. Across two studies, 66 comparisons produced 3 nominally significant results — exactly the chance expectation.

5. **State the effective sample size.** Overlapping forward windows mean 102 formation dates at 21-day steps are not 102 independent observations: closer to 34 at 3 months and 17 at 6 months. Report the standard error at the honest N.

6. **Include a positive control** so a null is informative — but say precisely what it licenses. Detecting a large, low-noise effect does not establish power for the smaller one under test.

7. **Write the finding, caveats stated plainly** — survivorship bias, market regime, transaction costs, and any way the study's cohorts differ from what the product actually ships. A negative result is a successful outcome and is written as the headline, not softened, and not rescued by hunting the parameter sweep for a flattering variant.

8. **Append an entry to `config/evidence.yaml`** with `finding:` pointing at the document. This is the step that makes the study change anything: the analyst inherits the verdict on every run. `tests/test_evidence_config.py` will fail if the cited document does not exist.

Close with pointers: `tools/backtest_core.py` for the primitives,
`tools/backtest_momentum.py` and `tools/backtest_conditional.py` as worked
examples, `docs/superpowers/findings/` for what a finished finding looks like,
and `tests/test_published_findings.py` as the reason not to change those
numbers casually.

- [ ] **Step 2: Verify the skill's factual claims**

Every claim the skill makes about this repository must be true. Check each against the source before committing, and report what you verified:

- the 2026-08-14 finding does disclose its unverifiable pre-registration
- 66 comparisons and 3 nominally significant results appear in the findings
- the effective-N figures (102 / 34 / 17) appear in the findings
- `paired_stats` lives in `backtest_core` after Task 1
- `tests/test_evidence_config.py` does assert cited findings exist on disk

If any claim does not check out, correct the skill rather than the source.

- [ ] **Step 3: Update the README**

Add a short paragraph to the tooling section: that `.claude/skills/validate-signal/` is the starting point for any new signal, that `tools/backtest_core.py` holds the shared primitives, and that `tests/test_published_findings.py` pins the published numbers. Do not restate the workflow — point at it.

- [ ] **Step 4: Run the full suite and commit**

Run: `.venv/bin/pytest -q` → expect 346, unchanged by this task.

```bash
git add .claude/skills/validate-signal/SKILL.md README.md
git commit -m "docs: validate-signal workflow skill"
```

---

## Self-Review Notes

Spec coverage against `docs/superpowers/specs/2026-08-14-validate-signal-workflow-design.md`:

- §2.1 the six names that move, the ones that stay, both studies importing from the library, `sys.path` pattern preserved → Task 1
- §2.2 reproduction test pinning both statistics with correct labels, skipif-guarded → Task 2
- §2.3 the eight workflow steps, each tied to a real incident → Task 3
- §2.4 README pointer → Task 3 Step 3
- §4 testing — existing suites unchanged as the regression guard, importability test, reproduction test, no test for the skill → Tasks 1, 2, 3
- §5 out of scope — no integrity test, no cohort DSL, no extraction of `analyze_conditional.py` — enforced by the Global Constraints and the file lists

Type consistency: `paired_stats`' return shape is used identically in Task 1's unit test and Task 2's reproduction test; horizon keys are ints in both, matching the live function rather than the JSON artifact.
