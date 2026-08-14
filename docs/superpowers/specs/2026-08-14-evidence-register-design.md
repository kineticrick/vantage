# Evidence Register — Design

**Date:** 2026-08-14
**Status:** Design — pending user review
**Project root:** `/home/kineticrick/code/python/vantage`

## 1. Purpose

Vantage has now run three empirical studies and produced two findings documents.
Their results contradict things the analyst finds intuitively compelling — most
sharply, that a stock's return "accelerating" says nothing useful about its
future, even though a fluent, well-evidenced narrative can always be built from
one.

Nothing currently carries those results into the analyst's reasoning. The
findings live in `docs/`, which the analyst never reads. Left alone, the next
brief will confidently rediscover a refuted idea, because the idea is genuinely
persuasive and only the data says otherwise.

This unit gives the analyst a memory of what has actually been tested.

### Success criteria
- The weekly analyst and the chat analyst both receive, on every run, the list of
  claims that have been tested against this universe, with verdicts and the
  evidence behind them.
- Adding a claim after a future study is editing one YAML file — no code change.
- The analyst does not present a refuted claim as an insight, and when asked
  about one, can say what was tested and what was found.
- The analyst does not overcorrect into reflexive dismissal of untested ideas.

### Non-goal
This does not change what the analyst *sees* about any ticker (that is the
descriptive term-structure project) and does not change how new claims get
tested (that is the backtest-practice project). This unit only carries settled
results into the prompt.

## 2. Architecture

Three pieces, following the pattern `config/interests.yaml` already establishes:
hand-written YAML in `config/`, loaded by both `run_weekly.py` and
`vantage/chat_context.py`, rendered into the prompt.

### 2.1 `config/evidence.yaml` (new) — the data

```yaml
# Claims tested empirically against this universe. Append after each study.
universe: >
  913 US large- and mid-cap tickers (S&P 500 + Nasdaq-100 + S&P 400),
  2016-08-15 to 2026-08-13, 102 formation dates at 21-trading-day steps,
  forward horizons of 1, 3 and 6 months.

limits:
  - Survivorship bias — the universe is today's index membership, so companies
    removed or delisted over the decade are invisible.
  - Overlapping forward windows — effective sample is roughly 102 / 34 / 17
    independent observations at 1 / 3 / 6 months, not 102.
  - One market regime, one country, no transaction costs or position sizing.
  - Nothing tested here reaches conventional statistical significance in either
    direction. "Refuted" means "failed to demonstrate an edge", not "proven
    harmful".

claims:
  - id: acceleration-beats-12m
    claim: >
      Ranking by return acceleration (recent annualized pace above long-run
      pace) identifies future outperformers better than ranking by trailing
      12-month return.
    verdict: refuted
    tested: 2026-08-13
    evidence: >
      36 of 36 paired estimates negative across 6 parameter variants and 3
      horizons. Median forward return, accelerating vs 12-month leaders:
      +2.06% vs +2.43% at 1 month, +3.92% vs +7.73% at 3 months, +8.19% vs
      +12.12% at 6 months. The accelerating cohort lost on 54-65 of 102 dates
      in every configuration.
    implication: >
      Do not rank, sort, filter or gate on the trajectory score. The term
      structure is still fact worth describing; it carries no forward claim.
    finding: docs/superpowers/findings/2026-08-13-momentum-backtest.md
```

Four further entries follow the same shape and are specified in §3.

**Schema.** Required per claim: `id` (kebab-case, unique), `claim`, `verdict`,
`tested` (ISO date), `evidence`, `implication`, `finding` (repo-relative path).
Optional: `universe`, overriding the top-level value for a claim tested against
a different dataset.

**Verdict vocabulary:** exactly `refuted`, `supported`, `inconclusive`. A fourth
value is a schema error, not a new category invented in passing.

Top-level `universe` and `limits` are stated once rather than repeated per
claim, because every current claim shares them and repetition invites drift.

### 2.2 `vantage/evidence.py` (new) — the unit

```python
@dataclass
class Claim:
    id: str
    claim: str
    verdict: str
    tested: str
    evidence: str
    implication: str
    finding: str
    universe: str | None = None

@dataclass
class Evidence:
    universe: str = ""
    limits: list = field(default_factory=list)
    claims: list = field(default_factory=list)

    def render(self) -> str: ...
    def by_verdict(self, verdict) -> list: ...

def load_evidence(config_dir) -> Evidence
```

`load_evidence` reads `config_dir / "evidence.yaml"`. A missing file, unreadable
file, malformed YAML, or non-mapping payload yields an empty `Evidence` — never
an exception, matching how `interests.yaml` already degrades. A claim missing a
required key is skipped rather than failing the whole load, so one bad entry
cannot silence the register; the skip is logged.

`render()` produces the prompt block:

```
=== Evidence register — claims tested against this universe ===
Universe: 913 US large- and mid-cap tickers ...
Limits applying to every claim below:
  - Survivorship bias — ...
  - ...

[REFUTED] Ranking by return acceleration identifies future outperformers
  better than ranking by trailing 12-month return.  (tested 2026-08-13)
  Evidence: 36 of 36 paired estimates negative ...
  Implication: Do not rank, sort, filter or gate on the trajectory score ...
  Source: docs/superpowers/findings/2026-08-13-momentum-backtest.md
```

An empty `Evidence` renders as the empty string, so consumers can concatenate
unconditionally.

### 2.3 Wiring — three touch points

- **`vantage/analyst.py`** — `build_prompt(signal_set, portfolio_context,
  interests, evidence=None)` gains an evidence section before the user's
  interest overlay. `evidence=None` renders nothing, keeping existing tests
  meaningful.
- **`vantage/chat_context.py`** — `ChatContext` gains an `evidence` field;
  `load_chat_context` loads it; `render()` includes the block.
- **`run_weekly.py`** — loads the register alongside `interests.yaml` and passes
  it through.
- **`vantage/persona.py`** — gains the standing instruction in §4.

Cost is roughly 500 tokens per prompt for five claims. That is small against a
64k-token budget, and it is the whole point of the unit.

## 3. The seeded claims

Five entries, from the two findings documents. Values below are the ones to
ship; they are drawn from the findings, not recomputed here.

1. **`acceleration-beats-12m`** — `refuted`, tested 2026-08-13. As shown in §2.1.

2. **`fade-flag-predicts-underperformance`** — `refuted`, tested 2026-08-13.
   Evidence: fading names versus the universe, paired per date, −0.04 / +0.09 /
   −0.02 percentage points at 1 / 3 / 6 months, winning 54 / 47 / 52 of 102
   dates; non-monotonic and positive at 3 months. Implication: a "fading" label
   is not a sell or avoid signal; do not ship the label.

3. **`trajectory-discriminates-within-leaders`** — `refuted`, tested 2026-08-14.
   Evidence: among the top 30 by trailing 12-month return, the higher-trajectory
   half beat the lower half by −0.36 / +0.81 / −0.92 percentage points, winning
   50 / 54 / 50 of 102 dates, signs unstable across horizons. Implication: even
   conditional on a stock already being a leader, trajectory does not identify
   which leaders do better. This was the original motivating question.

4. **`sector-breadth-predicts-sector-returns`** — `refuted`, tested 2026-08-14.
   Evidence: tickers in the top-3 sectors by accelerating share versus the
   bottom-3, −0.22 / −0.77 / −0.58 percentage points, 48 / 45 / 45 of 102 dates;
   ranking sectors by median score instead gave +0.23 / −0.35 / +0.01, 53 / 47 /
   51. Implication: sector breadth is descriptive dispersion, not a theme
   predictor; do not use it to order or select brief items.

5. **`12m-rank-beats-universe`** — `supported`, tested 2026-08-13 and replicated
   2026-08-14. Evidence: the 12-month leader cohort beat the plain universe by
   +1.43 / +4.62 / +9.01 percentage points paired, winning 59 / 71 / 69 of 102
   dates; an independent top-30 construction replicated it at +1.55 / +2.92 /
   +6.10, winning 65 / 65 / 73. This is the only comparison in 66 that clears
   its band. Implication: the existing 12-month screen is the one validated
   component; do not displace it.
   **Caveat carried in the entry itself:** both backtests rank by trailing
   12-month return, whereas `vantage/screener.py` selects by a `ret_12m >= 1.0`
   threshold. The validated result belongs to ranking-by-12-month-return as a
   principle, not to the exact selection the dashboard performs.

Including the one supported claim is deliberate. A register of nothing but
refutations teaches the analyst that measurement only ever destroys ideas.

## 4. The persona instruction

This is the part most likely to be got wrong, because it has two opposite
failure modes. Too weak and the analyst keeps producing compelling acceleration
narratives. Too strong and it becomes reflexively dismissive of everything,
which is worse — the user loses a thinking partner and gains a sceptic that
contributes nothing.

Text to add to `ANALYST_PERSONA`:

```
EVIDENCE DISCIPLINE. You are given an evidence register: claims about this
market universe that have been tested empirically, each with a verdict and the
data behind it. Treat those verdicts as settled for this universe unless new
data is presented.
- Never present a refuted claim as an insight or as a reason to act.
- When the user raises one, say plainly what was tested and what was found,
  and point at the finding document.
- A refuted claim does not make its underlying data worthless. Return term
  structure is still fact worth describing; it simply carries no forward
  claim. Describe it, and say so.
- Absence of evidence is not evidence of absence. These tests had limited
  power and stated limits. An untested idea is still worth reasoning about —
  do not become reflexively dismissive, and do not treat "not measured" as
  "false".
```

## 5. Error handling

- Missing, unreadable, or malformed `evidence.yaml` yields an empty register;
  the pipeline runs and the prompt simply omits the block.
- A claim missing a required key is skipped with a log line; other claims load.
- An unknown `verdict` value renders the claim with its verdict shown verbatim
  and is reported by the schema test (§6) rather than silently normalized.
- `render()` on an empty register returns `""`.

## 6. Testing

- Load: a well-formed file produces the expected claims, universe and limits.
- Degradation: missing file, unreadable file, malformed YAML, non-mapping
  payload, and a `claims` value that is not a list each yield an empty register
  without raising.
- Partial data: a claim missing a required key is skipped while its siblings
  load.
- Render: the block contains each claim's verdict, text, evidence, implication
  and source; an empty register renders `""`.
- Wiring: `build_prompt` includes the block when given a register and is
  unchanged when given `None`; `ChatContext.render()` includes it.
- **Shipped-config integrity**, the test that matters most for maintenance: the
  real `config/evidence.yaml` parses, every entry carries every required key,
  every `verdict` is one of the three permitted values, every `id` is unique,
  and **every `finding:` path exists on disk**. Without that last assertion the
  register accumulates dead links to evidence nobody can check.

## 7. Out of scope

- Surfacing return term structure to the user (separate project).
- Codifying pre-registered backtesting as standard practice (separate project).
- An `untested` verdict for open questions — easy to add later, speculative now.
- A `check_evidence` chat tool. The register is small enough to include in the
  prompt wholesale; a tool call would add latency for no coverage.
- Deriving the register automatically from the findings documents.
