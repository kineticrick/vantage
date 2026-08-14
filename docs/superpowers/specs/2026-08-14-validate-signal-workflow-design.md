# Validate-Signal Workflow — Design

**Date:** 2026-08-14
**Status:** Design — pending user review
**Project root:** `/home/kineticrick/code/python/vantage`

## 1. Purpose

Vantage has now tested three market hypotheses and refuted all three. The
process that produced those results was invented twice and improvised once. It
worked — but it lives in the conversation that produced it, not in the
repository, and the next person to propose a signal will rebuild it from
scratch or, more likely, skip it.

This makes the process the default: an invocable workflow that encodes what to
do, plus a library the next study imports instead of importing its predecessor.

### Success criteria
- Proposing a new signal has an obvious, invocable starting point that walks the
  full path from hypothesis to evidence-register entry.
- The workflow names the specific errors this project actually made, not generic
  statistical advice.
- A third study imports its primitives from a library, not from
  `tools/backtest_momentum.py`.
- Refactoring those primitives cannot silently invalidate a published finding.

### Non-goal
This does not change any pipeline behavior, any analyst prompt, or the evidence
register's contents. It is process and refactoring only.

## 2. Architecture

Three units.

### 2.1 `tools/backtest_core.py` (new) — the shared primitives

`tools/backtest_conditional.py` already imports `formation_positions`,
`forward_return`, `metrics_at` and `paired_stats` from
`tools/backtest_momentum.py`. The reuse is real; only its address is wrong — a
study should not be the library its successor depends on.

**Moves to `backtest_core.py`**, unchanged:

| Name | Currently at |
|---|---|
| `WINDOW_DAYS` | `backtest_momentum.py:24` |
| `MAX_PLAUSIBLE_RETURN` | `:25` |
| `formation_positions` | `:28` |
| `metrics_at` | `:36` |
| `forward_return` | `:53` |
| `paired_stats` | `:140` |

**Stays in `backtest_momentum.py`:** `run_period`, `COHORTS`, `PAIRS`,
`run_backtest`, `SWEEP`, `main`. These are that study's cohort definitions and
its sweep — the part where its thinking lives, and the part a different study
would legitimately write differently.

Both studies import the primitives from `backtest_core`. Their existing test
suites are the regression guard and must pass unchanged.

`tools/` is not a package; both existing tools already resolve imports by
inserting `tools/` on `sys.path`, and `backtest_core` follows that established
pattern rather than introducing a new one.

### 2.2 Reproduction test — the guard that matters

Extracting shared primitives is exactly the change that could alter a published
result without any test noticing: both studies' suites run on synthetic
fixtures, and their real numbers live only in two findings documents and in
git-ignored JSON.

Add a test that runs the momentum backtest against the real snapshot and asserts
the published headline still reproduces. Both statistics are published and both
must be pinned, **labelled correctly** — an earlier draft of this spec called the
first set "paired," which is precisely the conflation §2.3 step 3 exists to
prevent:

- baseline **aggregate**-median spreads (`spread_vs_leaders`) of
  **−0.37pp / −3.81pp / −3.93pp** at 21 / 63 / 126 days
- baseline **paired** accelerating-minus-leaders medians of
  **−1.21pp / −1.41pp / −5.31pp** over 102 formation dates
- all **36 of 36** sweep×horizon aggregate spreads negative

as stated in `docs/superpowers/findings/2026-08-13-momentum-backtest.md`. Pinning
both is deliberate: the two differ by design, and a refactor that silently made
them agree would be as much a regression as one that changed either.

Guarded with `pytest.mark.skipif` on the presence of
`cache/history/prices-*.parquet`, which is git-ignored — the test must **skip**,
never silently pass, when the snapshot is absent. It is slow enough to matter, so
it is marked and skippable, but it runs by default when the data is there.

This is the same discipline the momentum study's own false-positive test uses:
point the code at real data that already exists in the repository rather than
only at inputs invented alongside it.

### 2.3 `.claude/skills/validate-signal/SKILL.md` (new) — the workflow

An invocable skill. Its value is that it names the errors this project made,
which generic advice would not have prevented.

The workflow it encodes:

1. **Write the hypothesis down and commit it before running anything.** State
   what would count as success and what would count as failure. The follow-up
   study could not prove pre-registration from the repository alone — its
   hypotheses lived in a dispatch message — and had to disclose that in its own
   finding. Commit the design first so the claim is checkable.

2. **Define a control that represents current behavior.** "The new score
   returned +8%" means nothing. The entire momentum result is the comparison
   against the trailing-12-month rank Vantage already ships. Without a control
   a study cannot produce a usable answer, only a number.

3. **Compare paired, per formation date. Never subtract two separately
   aggregated statistics.** A difference of medians is not the median of
   differences. This error produced three wrong conclusions in this project —
   two of them written by the coordinator, one of them inside the very section
   that had just diagnosed the error. Compute per-date differences, then
   aggregate.

4. **Count every comparison, and report the exposure beside any nominally
   significant result** — not in a footnote. Across two studies, 66 comparisons
   produced 3 nominally significant results, which is exactly the chance
   expectation.

5. **State the effective sample size.** Overlapping forward windows mean 102
   formation dates at 21-day steps are not 102 independent observations —
   closer to 34 at a 3-month horizon and 17 at 6 months.

6. **Include a positive control.** A null from an instrument with no
   demonstrated sensitivity is uninformative. But say precisely what the control
   licenses: detecting a large, low-noise effect does not establish power for
   the smaller one under test.

7. **Write the finding, with its caveats stated plainly** — survivorship bias,
   regime, transaction costs, and any way the study's cohorts differ from what
   the product actually ships. A negative result is a successful outcome and is
   written as the headline, not softened.

8. **Append an entry to `config/evidence.yaml`**, with `finding:` pointing at
   the document. The analyst then inherits the verdict on every run, which is
   the only step that makes the study change anything.

The skill points at `tools/backtest_core.py` for the primitives, at the two
existing studies as worked examples, and at
`docs/superpowers/findings/` for what a finished finding looks like.

### 2.4 README

A short pointer from the tooling section: what the skill is, when to invoke it,
and that `backtest_core.py` is where a new study starts.

## 3. Error handling

- The reproduction test skips — with a reason — when the snapshot is absent. It
  never passes silently.
- No runtime behavior changes, so there are no new failure modes in the
  pipeline, the dashboard, or the analyst.

## 4. Testing

- Both existing study test suites pass unchanged after the extraction. This is
  the primary regression guard and requires no new assertions.
- A small test that `backtest_core`'s public names are importable from it, so a
  future edit cannot quietly move one back.
- The reproduction test in §2.2.
- No test for the skill: it is a document. Its correctness is that its claims
  about this project are true, which is checked in review against the findings.

## 5. Out of scope

- Any change to pipeline behavior, prompts, or the evidence register's contents.
- An integrity test linking findings documents to register entries. Worth
  building the first time a study is run and then forgotten; speculative now.
- A generalized cohort DSL. Cohort definitions are where a study's reasoning
  lives; abstracting them would make the next study harder to follow, not
  easier.
- Extracting `tools/analyze_conditional.py`'s significance helpers. They were
  written for one study's reporting and have no second caller yet.
