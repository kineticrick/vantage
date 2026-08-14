# Evidence Register Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Vantage analyst a memory of which market claims have been empirically tested, so it stops presenting refuted-but-persuasive ideas as insight.

**Architecture:** A hand-written YAML register in `config/`, a small pure loader/renderer unit, and two consumers. It follows the pattern `config/interests.yaml` already establishes. `generate_brief` loads the register itself from `settings.config_dir`, so `run_weekly.py` and its dependency-injection seam are untouched; `conversation.py` already calls `ChatContext.render()`, so the chat analyst inherits the block with no change there either.

**Tech Stack:** Python 3.14, PyYAML (already a dependency), pytest.

**Spec:** `docs/superpowers/specs/2026-08-14-evidence-register-design.md`

## Global Constraints

- Run everything with the project venv: `.venv/bin/python`, `.venv/bin/pytest`.
- **No new runtime dependencies.** `yaml` is already used by `run_weekly.py` and `chat_context.py`.
- **Degrade, never raise.** A missing, unreadable, or malformed `evidence.yaml` yields an empty register and the pipeline runs normally — matching how `interests.yaml` is already handled.
- All file reads use `encoding="utf-8"`.
- **Do not modify** `vantage/screener.py`, `vantage/momentum.py`, `vantage/models.py`, `vantage/report.py`, `run_weekly.py`, `vantage/data_ingest.py`, or anything under `vantage/web/` or `tools/`. This project touches `vantage/evidence.py` (new), `config/evidence.yaml` (new), `vantage/analyst.py`, `vantage/chat_context.py`, `vantage/persona.py`, and tests.
- Verdict vocabulary is exactly `refuted`, `supported`, `inconclusive`.
- Full suite baseline before starting: **251 tests passing** (`.venv/bin/pytest -q`).

---

### Task 1: The register unit

**Files:**
- Create: `vantage/evidence.py`
- Test: `tests/test_evidence.py`

**Interfaces:**
- Consumes: `yaml` (stdlib-adjacent, already a dependency).
- Produces:
  - `VERDICTS = ("refuted", "supported", "inconclusive")`
  - `REQUIRED_KEYS = ("id", "claim", "verdict", "tested", "evidence", "implication", "finding")`
  - `Claim(id, claim, verdict, tested, evidence, implication, finding, universe=None)`
  - `Evidence(universe="", limits=[], claims=[])` with `.render() -> str` and `.by_verdict(verdict) -> list`
  - `load_evidence(config_dir) -> Evidence`

- [ ] **Step 1: Write the failing test**

Create `tests/test_evidence.py`:

```python
import pytest
import yaml
from vantage.evidence import (VERDICTS, REQUIRED_KEYS, Claim, Evidence,
                              load_evidence)

_CLAIM = {
    "id": "acceleration-beats-12m",
    "claim": "Ranking by return acceleration beats ranking by 12-month return.",
    "verdict": "refuted",
    "tested": "2026-08-13",
    "evidence": "36 of 36 paired estimates negative.",
    "implication": "Do not rank on the trajectory score.",
    "finding": "docs/superpowers/findings/2026-08-13-momentum-backtest.md",
}

def _write(tmp_path, payload):
    (tmp_path / "evidence.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    return tmp_path

def test_loads_claims_universe_and_limits(tmp_path):
    _write(tmp_path, {"universe": "913 tickers", "limits": ["survivorship bias"],
                      "claims": [_CLAIM]})
    ev = load_evidence(tmp_path)
    assert ev.universe == "913 tickers"
    assert ev.limits == ["survivorship bias"]
    assert len(ev.claims) == 1
    assert ev.claims[0].id == "acceleration-beats-12m"
    assert ev.claims[0].verdict == "refuted"
    assert ev.claims[0].universe is None

def test_missing_file_yields_empty_register(tmp_path):
    ev = load_evidence(tmp_path)
    assert ev.claims == [] and ev.universe == "" and ev.limits == []

def test_malformed_yaml_yields_empty_register(tmp_path):
    (tmp_path / "evidence.yaml").write_text("claims: [oops: :", encoding="utf-8")
    assert load_evidence(tmp_path).claims == []

@pytest.mark.parametrize("payload", ["just a string", ["a", "list"], None])
def test_non_mapping_payload_yields_empty_register(tmp_path, payload):
    (tmp_path / "evidence.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    assert load_evidence(tmp_path).claims == []

def test_claims_not_a_list_yields_no_claims(tmp_path):
    _write(tmp_path, {"claims": {"id": "x"}})
    assert load_evidence(tmp_path).claims == []

def test_claim_missing_a_required_key_is_skipped_siblings_survive(tmp_path):
    broken = {k: v for k, v in _CLAIM.items() if k != "implication"}
    broken["id"] = "broken"
    _write(tmp_path, {"claims": [broken, _CLAIM]})
    ev = load_evidence(tmp_path)
    assert [c.id for c in ev.claims] == ["acceleration-beats-12m"]

def test_claim_with_empty_required_value_is_skipped(tmp_path):
    empty = dict(_CLAIM, id="empty-evidence", evidence="")
    _write(tmp_path, {"claims": [empty, _CLAIM]})
    assert [c.id for c in load_evidence(tmp_path).claims] == ["acceleration-beats-12m"]

def test_yaml_date_is_coerced_to_string(tmp_path):
    # An unquoted ISO date in YAML parses to datetime.date, which must not
    # reach the prompt as a repr.
    (tmp_path / "evidence.yaml").write_text(
        "claims:\n"
        "  - id: d\n"
        "    claim: c\n"
        "    verdict: refuted\n"
        "    tested: 2026-08-13\n"
        "    evidence: e\n"
        "    implication: i\n"
        "    finding: f.md\n", encoding="utf-8")
    assert load_evidence(tmp_path).claims[0].tested == "2026-08-13"

def test_per_claim_universe_override_is_kept(tmp_path):
    _write(tmp_path, {"universe": "default",
                      "claims": [dict(_CLAIM, universe="a different dataset")]})
    assert load_evidence(tmp_path).claims[0].universe == "a different dataset"

def test_by_verdict_filters():
    a = Claim("a", "c", "refuted", "d", "e", "i", "f")
    b = Claim("b", "c", "supported", "d", "e", "i", "f")
    ev = Evidence(claims=[a, b])
    assert [c.id for c in ev.by_verdict("supported")] == ["b"]
    assert ev.by_verdict("inconclusive") == []

def test_render_contains_every_field_of_every_claim(tmp_path):
    _write(tmp_path, {"universe": "913 tickers", "limits": ["survivorship bias"],
                      "claims": [_CLAIM]})
    text = load_evidence(tmp_path).render()
    assert "REFUTED" in text
    assert "913 tickers" in text
    assert "survivorship bias" in text
    assert "Ranking by return acceleration" in text
    assert "36 of 36 paired estimates negative." in text
    assert "Do not rank on the trajectory score." in text
    assert "2026-08-13-momentum-backtest.md" in text

def test_render_flattens_block_scalars(tmp_path):
    wrapped = dict(_CLAIM, claim="a claim\nwrapped over\nthree lines\n")
    _write(tmp_path, {"claims": [wrapped]})
    text = load_evidence(tmp_path).render()
    assert "a claim wrapped over three lines" in text

def test_render_of_empty_register_is_empty_string():
    assert Evidence().render() == ""

def test_verdict_vocabulary_is_exactly_three():
    assert set(VERDICTS) == {"refuted", "supported", "inconclusive"}
    assert "finding" in REQUIRED_KEYS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_evidence.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'vantage.evidence'`

- [ ] **Step 3: Write the implementation**

Create `vantage/evidence.py`:

```python
"""What has actually been tested about this market universe.

The analyst finds some ideas compelling that the data does not support — most
sharply, that a stock's returns "accelerating" says anything useful about its
future. The findings live in docs/, which the analyst never reads. This carries
them into the prompt so a refuted idea is not rediscovered every week.

Hand-maintained: append an entry to config/evidence.yaml after each study.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

VERDICTS = ("refuted", "supported", "inconclusive")
REQUIRED_KEYS = ("id", "claim", "verdict", "tested", "evidence", "implication",
                 "finding")


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

    def by_verdict(self, verdict) -> list:
        return [c for c in self.claims if c.verdict == verdict]

    def render(self) -> str:
        """The block injected into analyst prompts. Empty register -> ''."""
        if not self.claims:
            return ""
        out = ["=== Evidence register — claims tested against this universe ==="]
        if self.universe:
            out.append(f"Universe: {_flat(self.universe)}")
        if self.limits:
            out.append("Limits applying to every claim below:")
            out += [f"  - {_flat(x)}" for x in self.limits]
        for c in self.claims:
            out.append("")
            out.append(f"[{c.verdict.upper()}] {_flat(c.claim)}  (tested {c.tested})")
            if c.universe:
                out.append(f"  Universe: {_flat(c.universe)}")
            out.append(f"  Evidence: {_flat(c.evidence)}")
            out.append(f"  Implication: {_flat(c.implication)}")
            out.append(f"  Source: {c.finding}")
        return "\n".join(out)


def _flat(text) -> str:
    """YAML block scalars carry newlines; prompts read better on one line."""
    return " ".join(str(text).split())


def load_evidence(config_dir) -> Evidence:
    """Read config/evidence.yaml. Never raises; degrades to an empty register."""
    path = Path(config_dir) / "evidence.yaml"
    if not path.exists():
        return Evidence()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as e:
        logger.warning("evidence.yaml unreadable (%s); continuing without it", e)
        return Evidence()
    if not isinstance(raw, dict):
        return Evidence()

    entries = raw.get("claims")
    claims = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        missing = [k for k in REQUIRED_KEYS if not entry.get(k)]
        if missing:
            # One malformed entry must not silence the whole register.
            logger.warning("evidence claim %r missing %s; skipped",
                           entry.get("id", "?"), ", ".join(missing))
            continue
        claims.append(Claim(
            id=str(entry["id"]), claim=entry["claim"],
            verdict=str(entry["verdict"]), tested=str(entry["tested"]),
            evidence=entry["evidence"], implication=entry["implication"],
            finding=str(entry["finding"]),
            universe=entry.get("universe")))

    limits = raw.get("limits")
    return Evidence(universe=raw.get("universe") or "",
                    limits=list(limits) if isinstance(limits, list) else [],
                    claims=claims)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_evidence.py -q`
Expected: PASS (16 tests)

- [ ] **Step 5: Run the full suite and commit**

Run: `.venv/bin/pytest -q` → expect 251 + 16 = 267.

```bash
git add vantage/evidence.py tests/test_evidence.py
git commit -m "feat(evidence): register of empirically tested market claims"
```

---

### Task 2: The seeded register

The data is the deliverable here. Every figure must match the findings documents it cites — this file is what the analyst will believe.

**Files:**
- Create: `config/evidence.yaml`
- Test: `tests/test_evidence_config.py`

**Interfaces:**
- Consumes: `load_evidence`, `VERDICTS`, `REQUIRED_KEYS` from Task 1.
- Produces: the shipped register.

- [ ] **Step 1: Write the failing test**

Create `tests/test_evidence_config.py`:

```python
from pathlib import Path
import yaml
from vantage.evidence import VERDICTS, REQUIRED_KEYS, load_evidence

CONFIG = Path(__file__).resolve().parents[1] / "config"
REPO = Path(__file__).resolve().parents[1]

def test_shipped_register_parses_and_has_claims():
    ev = load_evidence(CONFIG)
    assert len(ev.claims) >= 5
    assert ev.universe and ev.limits

def test_every_claim_has_every_required_key():
    raw = yaml.safe_load((CONFIG / "evidence.yaml").read_text(encoding="utf-8"))
    for entry in raw["claims"]:
        missing = [k for k in REQUIRED_KEYS if not entry.get(k)]
        assert not missing, f"{entry.get('id')} missing {missing}"

def test_every_verdict_is_in_the_vocabulary():
    for c in load_evidence(CONFIG).claims:
        assert c.verdict in VERDICTS, f"{c.id} has verdict {c.verdict!r}"

def test_claim_ids_are_unique():
    ids = [c.id for c in load_evidence(CONFIG).claims]
    assert len(ids) == len(set(ids))

def test_every_cited_finding_exists_on_disk():
    # Without this the register accumulates citations to evidence nobody can
    # open, which is worse than having no register.
    for c in load_evidence(CONFIG).claims:
        assert (REPO / c.finding).exists(), f"{c.id} cites missing {c.finding}"

def test_register_records_at_least_one_supported_claim():
    # A register of nothing but refutations teaches the analyst that
    # measurement only ever destroys ideas. See the design spec, §3.
    assert load_evidence(CONFIG).by_verdict("supported")

def test_the_four_refuted_claims_are_present():
    ids = {c.id for c in load_evidence(CONFIG).by_verdict("refuted")}
    assert {"acceleration-beats-12m",
            "fade-flag-predicts-underperformance",
            "trajectory-discriminates-within-leaders",
            "sector-breadth-predicts-sector-returns"} <= ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_evidence_config.py -q`
Expected: FAIL — the register does not exist, so `load_evidence` returns empty and the first assertion fails.

- [ ] **Step 3: Write the register**

Create `config/evidence.yaml`. Copy the figures verbatim from the two findings documents; do not recompute or round them differently.

```yaml
# Claims tested empirically against this universe. Append an entry after each
# study. Loaded by vantage/evidence.py into both the weekly and chat analysts.
universe: >
  913 US large- and mid-cap tickers (S&P 500 + Nasdaq-100 + S&P 400),
  2016-08-15 to 2026-08-13, 102 formation dates at 21-trading-day steps,
  forward horizons of 1, 3 and 6 months.

limits:
  - Survivorship bias — the universe is today's index membership, so companies
    removed or delisted over the decade are invisible.
  - Overlapping forward windows — the effective sample is roughly 102 / 34 / 17
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
    tested: "2026-08-13"
    evidence: >
      36 of 36 paired estimates negative across 6 parameter variants and 3
      horizons. Median forward return, accelerating versus 12-month leaders:
      +2.06% vs +2.43% at 1 month, +3.92% vs +7.73% at 3 months, +8.19% vs
      +12.12% at 6 months. The accelerating cohort lost on 54 to 65 of 102
      dates in every configuration.
    implication: >
      Do not rank, sort, filter or gate on the trajectory score. The return
      term structure is still fact worth describing; it carries no forward
      claim.
    finding: docs/superpowers/findings/2026-08-13-momentum-backtest.md

  - id: fade-flag-predicts-underperformance
    claim: >
      Labelling a past winner "fading" when its recent pace decays identifies
      stocks that will underperform.
    verdict: refuted
    tested: "2026-08-13"
    evidence: >
      Fading names versus the universe, paired per date: -0.04, +0.09 and
      -0.02 percentage points at 1, 3 and 6 months, winning 54, 47 and 52 of
      102 dates. Non-monotonic and positive at 3 months.
    implication: >
      A "fading" label is not a sell or avoid signal. Do not ship the label,
      and do not treat a weak recent month as evidence a leader is done.
    finding: docs/superpowers/findings/2026-08-13-momentum-backtest.md

  - id: trajectory-discriminates-within-leaders
    claim: >
      Among stocks that are already 12-month leaders, trajectory identifies
      which of those leaders will do better.
    verdict: refuted
    tested: "2026-08-14"
    evidence: >
      Among the top 30 by trailing 12-month return, the higher-trajectory half
      beat the lower half by -0.36, +0.81 and -0.92 percentage points at 1, 3
      and 6 months, winning 50, 54 and 50 of 102 dates, with signs unstable
      across horizons.
    implication: >
      Even conditional on a stock already being a leader, trajectory does not
      say which leaders do better. This was the original motivating question;
      it does not work either.
    finding: docs/superpowers/findings/2026-08-14-conditional-and-sector-breadth.md

  - id: sector-breadth-predicts-sector-returns
    claim: >
      A sector where many names are accelerating at once is turning, and its
      constituents will outperform.
    verdict: refuted
    tested: "2026-08-14"
    evidence: >
      Tickers in the top-3 sectors by accelerating share versus the bottom-3:
      -0.22, -0.77 and -0.58 percentage points, winning 48, 45 and 45 of 102
      dates. Ranking sectors by median trajectory score instead gave +0.23,
      -0.35 and +0.01, winning 53, 47 and 51.
    implication: >
      Sector breadth is descriptive dispersion, not a theme predictor. Do not
      use it to order or select brief items.
    finding: docs/superpowers/findings/2026-08-14-conditional-and-sector-breadth.md

  - id: 12m-rank-beats-universe
    claim: >
      Ranking by trailing 12-month return selects stocks that outperform the
      broad universe.
    verdict: supported
    tested: "2026-08-13"
    evidence: >
      The 12-month leader cohort beat the plain universe by +1.43, +4.62 and
      +9.01 percentage points paired, winning 59, 71 and 69 of 102 dates; an
      independent top-30 construction replicated it at +1.55, +2.92 and +6.10,
      winning 65, 65 and 73. This is the only comparison of 66 across both
      studies that clears its band.
    implication: >
      The existing 12-month screen is the one validated component of this
      system. Do not displace it. Note the caveat: both backtests rank by
      trailing 12-month return, whereas vantage/screener.py selects by a
      ret_12m >= 1.0 threshold — the validated result belongs to
      ranking-by-12-month-return as a principle, not to the exact selection
      the dashboard performs.
    finding: docs/superpowers/findings/2026-08-13-momentum-backtest.md
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_evidence_config.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Eyeball the rendered block**

Run:

```bash
.venv/bin/python -c "
from vantage.evidence import load_evidence
print(load_evidence('config').render())"
```

Read the output. Confirm each claim reads as a complete sentence, no stray newlines survive inside a field, and the dates render as `2026-08-13` rather than a `datetime.date` repr. Report the character count — if the block exceeds roughly 4000 characters, say so, since it is prepended to every prompt.

- [ ] **Step 6: Run the full suite and commit**

Run: `.venv/bin/pytest -q` → expect 274.

```bash
git add config/evidence.yaml tests/test_evidence_config.py
git commit -m "feat(evidence): seed the register with five tested claims"
```

---

### Task 3: Wire it into both analysts

**Files:**
- Modify: `vantage/analyst.py` (`build_prompt`, `generate_brief`)
- Modify: `vantage/chat_context.py` (`ChatContext`, `load_chat_context`)
- Test: `tests/test_analyst.py`, `tests/test_chat_context.py`

**Interfaces:**
- Consumes: `load_evidence`, `Evidence` from Task 1.
- Produces:
  - `build_prompt(signal_set, portfolio_context, interests, evidence=None) -> str`
  - `generate_brief(signal_set, portfolio_context, interests, settings, _client=None, _evidence=None)`
  - `ChatContext(..., evidence=None)`

`run_weekly.py` is deliberately **not** modified: `generate_brief` loads the register from `settings.config_dir` itself, which preserves the existing `_analyst_fn` injection seam and its test fakes. `vantage/conversation.py` is also not modified — it already calls `ChatContext.render()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_analyst.py`:

```python
def test_build_prompt_without_evidence_omits_the_block():
    from vantage.analyst import build_prompt
    from vantage.models import SignalSet, Signal, PortfolioContext
    ss = SignalSet("2026-08-13", [Signal("MU", "ret_12m_leader", 6.3, 1)], {})
    p = build_prompt(ss, PortfolioContext(available=False, note="x"), {})
    assert "Evidence register" not in p

def test_build_prompt_includes_the_evidence_block():
    from vantage.analyst import build_prompt
    from vantage.evidence import Evidence, Claim
    from vantage.models import SignalSet, Signal, PortfolioContext
    ev = Evidence(universe="913 tickers", limits=["survivorship bias"], claims=[
        Claim("acceleration-beats-12m", "Acceleration beats 12m rank.",
              "refuted", "2026-08-13", "36 of 36 negative.",
              "Do not rank on it.", "docs/f.md")])
    ss = SignalSet("2026-08-13", [Signal("MU", "ret_12m_leader", 6.3, 1)], {})
    p = build_prompt(ss, PortfolioContext(available=False, note="x"), {}, ev)
    assert "Evidence register" in p
    assert "REFUTED" in p
    assert "Do not rank on it." in p

def test_generate_brief_loads_the_register_from_settings(tmp_path):
    # The register reaches the prompt without run_weekly passing it.
    import yaml
    from vantage.analyst import generate_brief
    from vantage.models import SignalSet, Signal, PortfolioContext
    (tmp_path / "evidence.yaml").write_text(yaml.safe_dump({"claims": [{
        "id": "x", "claim": "A tested claim.", "verdict": "refuted",
        "tested": "2026-08-13", "evidence": "e", "implication": "i",
        "finding": "f.md"}]}), encoding="utf-8")

    seen = {}
    class _FakeStream:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get_final_message(self):
            class M: content = [type("B", (), {"type": "text",
                "text": '```json\n{"executive_summary": "s", "items": [], '
                        '"watchlist": [], "challenge": "", '
                        '"what_im_missing": ""}\n```'})()]
            return M()
    class _FakeMessages:
        def stream(self, **kw):
            seen["prompt"] = kw["messages"][0]["content"]
            return _FakeStream()
    class _FakeClient:
        messages = _FakeMessages()

    class _S:
        anthropic_api_key = "k"; model = "m"; config_dir = tmp_path
    ss = SignalSet("2026-08-13", [Signal("MU", "ret_12m_leader", 6.3, 1)], {})
    generate_brief(ss, PortfolioContext(available=False, note="x"), {}, _S(),
                   _client=_FakeClient())
    assert "A tested claim." in seen["prompt"]
```

Append to `tests/test_chat_context.py`:

```python
def test_chat_context_renders_the_evidence_block():
    from vantage.chat_context import ChatContext
    from vantage.evidence import Evidence, Claim
    ev = Evidence(universe="913 tickers", claims=[
        Claim("id1", "A tested claim.", "refuted", "2026-08-13", "e",
              "Do not act on it.", "docs/f.md")])
    text = ChatContext(evidence=ev).render()
    assert "Evidence register" in text
    assert "Do not act on it." in text

def test_chat_context_without_evidence_renders_without_the_block():
    from vantage.chat_context import ChatContext
    assert "Evidence register" not in ChatContext().render()

def test_load_chat_context_loads_the_register(tmp_path, monkeypatch):
    import yaml
    from vantage.chat_context import load_chat_context
    from vantage.models import PortfolioContext
    for sub in ("config", "data", "reports"):
        (tmp_path / sub).mkdir()
    (tmp_path / "config" / "evidence.yaml").write_text(yaml.safe_dump({"claims": [{
        "id": "x", "claim": "A tested claim.", "verdict": "refuted",
        "tested": "2026-08-13", "evidence": "e", "implication": "i",
        "finding": "f.md"}]}), encoding="utf-8")

    class _S:
        config_dir = tmp_path / "config"
        data_dir = tmp_path / "data"
        reports_dir = tmp_path / "reports"
        portfolio_analysis_path = "/x"
    ctx = load_chat_context(_S(),
                            _portfolio_fn=lambda p: PortfolioContext(available=False, note="x"))
    assert ctx.evidence is not None
    assert "A tested claim." in ctx.render()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_analyst.py tests/test_chat_context.py -q`
Expected: FAIL — `build_prompt() takes 3 positional arguments but 4 were given`, and `ChatContext` has no `evidence` field.

- [ ] **Step 3: Write the implementation**

In `vantage/analyst.py`, add the import and thread the register through:

```python
from vantage.evidence import load_evidence
```

```python
def build_prompt(signal_set, portfolio_context, interests, evidence=None) -> str:
    ...
    block = evidence.render() if evidence is not None else ""
    return (
        _INSTRUCTIONS
        + f"\n\n=== As of: {signal_set.as_of} ===\n"
        + "\n=== Quantitative signals ===\n" + "\n".join(sig_lines)
        + "\n\n=== Sector momentum (mean 12m return) ===\n" + sectors
        + "\n\n=== User portfolio ===\n" + portfolio_context.summary_text()
        + (f"\n\n{block}" if block else "")
        + "\n\n=== User interest overlay ===\n" + json.dumps(interests, indent=2)
    )
```

```python
def generate_brief(signal_set, portfolio_context, interests, settings,
                   _client=None, _evidence=None):
    import anthropic
    client = _client or anthropic.Anthropic(api_key=settings.anthropic_api_key)
    # Loaded here rather than passed in, so run_weekly's injection seam is
    # untouched and the chat and weekly analysts read the same register.
    evidence = _evidence if _evidence is not None else load_evidence(settings.config_dir)
    prompt = build_prompt(signal_set, portfolio_context, interests, evidence)
    ...
```

In `vantage/chat_context.py`, add the import, the field, the render line, and the load:

```python
from vantage.evidence import load_evidence
```

```python
@dataclass
class ChatContext:
    portfolio: object = None
    signals: object = None
    interests: dict = field(default_factory=dict)
    brief: object = None
    evidence: object = None
```

In `render()`, after the interest-overlay line and before the brief section:

```python
        block = self.evidence.render() if self.evidence is not None else ""
        if block:
            parts.append(block)
```

In `load_chat_context`, before the return:

```python
    evidence = load_evidence(settings.config_dir)
```

and pass `evidence=evidence` into the returned `ChatContext`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_analyst.py tests/test_chat_context.py -q`
Expected: PASS

- [ ] **Step 5: Run the full suite and commit**

Run: `.venv/bin/pytest -q` → expect 280. If `tests/test_conversation.py` fails because a fake `ChatContext` is constructed positionally, add `evidence=None` — the field is last and defaulted, so this should not happen; investigate rather than reordering fields if it does.

```bash
git add vantage/analyst.py vantage/chat_context.py tests/
git commit -m "feat(evidence): serve the register to the weekly and chat analysts"
```

---

### Task 4: The persona instruction, docs, and end-to-end check

**Files:**
- Modify: `vantage/persona.py`
- Modify: `README.md`
- Test: `tests/test_persona.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_persona.py`:

```python
def test_persona_carries_evidence_discipline():
    from vantage.persona import ANALYST_PERSONA
    lowered = ANALYST_PERSONA.lower()
    assert "evidence register" in lowered
    # both failure modes must be addressed: crediting refuted claims, and
    # overcorrecting into blanket dismissal
    assert "refuted" in lowered
    assert "absence of evidence" in lowered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_persona.py -q`
Expected: FAIL on the first assertion.

- [ ] **Step 3: Add the instruction**

Append to `ANALYST_PERSONA` in `vantage/persona.py`, after the numbered duties and before the closing line:

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

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_persona.py -q` → PASS
Run: `.venv/bin/pytest -q` → expect 281.

- [ ] **Step 5: End-to-end check**

Confirm the block genuinely reaches both surfaces, using the real shipped register:

```bash
.venv/bin/python -c "
from vantage.settings import load_settings
from vantage.evidence import load_evidence
from vantage.chat_context import ChatContext
from vantage.analyst import build_prompt
from vantage.models import SignalSet, Signal, PortfolioContext
s = load_settings()
ev = load_evidence(s.config_dir)
print('claims loaded:', len(ev.claims))
print('supported:', [c.id for c in ev.by_verdict('supported')])
ss = SignalSet('2026-08-13', [Signal('MU','ret_12m_leader',6.3,1)], {})
p = build_prompt(ss, PortfolioContext(available=False, note='x'), {}, ev)
print('weekly prompt has block:', 'Evidence register' in p)
print('chat context has block:', 'Evidence register' in ChatContext(evidence=ev).render())
print('persona has discipline:', 'EVIDENCE DISCIPLINE' in p)
"
```

Expected: 5 claims, `['12m-rank-beats-universe']`, and `True` on all three. Report the actual output.

- [ ] **Step 6: Update the README**

Add a short subsection describing `config/evidence.yaml`: what it is, that both the weekly brief and the chat analyst read it, that entries are appended after each study, and that `tests/test_evidence_config.py` enforces the schema and that cited findings exist. Point at `docs/superpowers/findings/` for the studies themselves. Do not claim any change to what the analyst *shows* the user — this project only changes what it knows.

- [ ] **Step 7: Commit**

```bash
git add vantage/persona.py README.md tests/test_persona.py
git commit -m "feat(evidence): persona instruction and docs for the register"
```

---

## Self-Review Notes

Spec coverage against `docs/superpowers/specs/2026-08-14-evidence-register-design.md`:

- §2.1 schema, verdict vocabulary, top-level `universe`/`limits` → Task 2
- §2.2 `Claim`, `Evidence`, `load_evidence`, `render`, `by_verdict` → Task 1
- §2.3 wiring at three touch points, `run_weekly.py` untouched → Task 3
- §3 all five seeded claims with their figures and the threshold-vs-rank caveat → Task 2 Step 3
- §4 persona instruction with both failure modes → Task 4
- §5 error handling — missing, unreadable, malformed, non-mapping, partial claim, empty render → Task 1 tests
- §6 testing, including the shipped-config integrity test and the dead-link assertion → Tasks 1, 2
- §7 out of scope — no `untested` verdict, no chat tool, no auto-derivation — enforced by the Global Constraint file list

Type consistency: `Evidence` and `Claim` are defined in Task 1 and consumed unchanged in Tasks 2 and 3; `build_prompt`'s fourth parameter is `evidence` in both its definition and every call site.
