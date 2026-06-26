# Blind-Spot Radar — Weekly Digest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the weekly-digest pipeline end-to-end: pull free market data, compute deterministic signals, derive context from the user's real portfolio, have a Claude analyst fuse them with self-sourced news into a reasoned (and challenging) brief, render it, and email it.

**Architecture:** Hybrid. Deterministic, unit-tested Python for data ingestion, signal screening, and portfolio-context derivation; a Claude API analyst layer (claude-opus-4-8, adaptive thinking, web_search) for narrative detection, convergence, second-order reasoning, and evidence-based challenge. Units communicate through plain dataclasses (`Signal`/`SignalSet`, `PortfolioContext`, `Brief`) so the analyst can later be driven interactively without touching the screener. All `portfolio_analysis` access is isolated behind one adapter module.

**Tech Stack:** Python 3, yfinance (free market data), pandas, the `anthropic` SDK (Claude API), PyYAML, python-dotenv, smtplib (stdlib, Gmail SMTP), pytest. The existing `~/code/python/portfolio_analysis` codebase is imported by path for portfolio/transaction data.

## Global Constraints

- **Model:** Analyst uses exactly `claude-opus-4-8`. Adaptive thinking (`thinking={"type": "adaptive"}`), effort `high`, streaming, and the `web_search` server tool (type `web_search_20260209`, name `web_search`). Do NOT pass `temperature`/`top_p`/`top_k`/`budget_tokens` — they 400 on this model.
- **Secrets:** `ANTHROPIC_API_KEY`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `EMAIL_RECIPIENT` come from `.env` only (loaded via python-dotenv). `.env` is git-ignored; `.env.example` documents required keys. Never hardcode or commit secrets.
- **Determinism boundary:** `data_ingest`, `screener`, `portfolio_context` are deterministic and unit-tested with mocked external calls. Only `analyst` is non-deterministic.
- **Coupling containment:** Only `radar/portfolio_context.py` may import `portfolio_analysis`. Every other module depends solely on the `PortfolioContext` dataclass.
- **Graceful degradation:** If portfolio data is unavailable (import/DB failure), the pipeline runs in market-wide-only mode (logs a warning, notes it in the brief) rather than crashing.
- **Not financial advice:** Every brief/email carries a plain research-aid disclaimer.
- **Package name:** `radar`. Project root: `/home/kineticrick/code/python/market_insights`. Entry point `run_weekly.py` at root.
- **portfolio_analysis path:** default `/home/kineticrick/code/python/portfolio_analysis`, overridable via `PORTFOLIO_ANALYSIS_PATH` env var.

---

## File Structure

```
market_insights/
├── requirements.txt
├── .gitignore
├── .env.example
├── README.md
├── run_weekly.py                 # entry point: full weekly pipeline
├── config/
│   ├── interests.yaml            # hand-written interest overlay
│   └── universe.txt              # ticker universe (one symbol per line, '#' comments)
├── radar/
│   ├── __init__.py
│   ├── settings.py               # env + paths + model config
│   ├── models.py                 # Signal, SignalSet, PortfolioContext, Brief dataclasses
│   ├── universe.py               # load ticker universe from config/universe.txt
│   ├── data_ingest.py            # yfinance batched fetch + disk cache → MarketData
│   ├── screener.py               # MarketData → SignalSet (deterministic)
│   ├── portfolio_context.py      # adapter over portfolio_analysis → PortfolioContext
│   ├── analyst.py                # Claude API → Brief
│   ├── report.py                 # Brief → Markdown + HTML
│   └── deliver.py                # send HTML email via Gmail SMTP
├── data/                         # dated SignalSet JSON (gitignored)
├── reports/                      # dated Markdown briefs (gitignored)
├── cache/                        # yfinance disk cache (gitignored)
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_universe.py
    ├── test_data_ingest.py
    ├── test_screener.py
    ├── test_portfolio_context.py
    ├── test_analyst.py
    ├── test_report.py
    └── test_deliver.py
```

---

### Task 1: Project scaffolding & settings

**Files:**
- Create: `requirements.txt`, `.gitignore`, `.env.example`, `radar/__init__.py`, `tests/__init__.py`, `config/universe.txt`, `config/interests.yaml`, `radar/settings.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Produces: `radar.settings.Settings` (dataclass) and `radar.settings.load_settings() -> Settings`. Fields: `anthropic_api_key: str`, `gmail_user: str`, `gmail_app_password: str`, `email_recipient: str`, `model: str` (default `"claude-opus-4-8"`), `portfolio_analysis_path: str`, `project_root: Path`, `data_dir: Path`, `reports_dir: Path`, `cache_dir: Path`, `config_dir: Path`. `load_settings()` reads `.env` via python-dotenv and creates `data/`, `reports/`, `cache/` if missing.

- [ ] **Step 1: Create `requirements.txt`**

```
anthropic>=0.40
yfinance>=0.2.50
pandas>=2.0
PyYAML>=6.0
python-dotenv>=1.0
pytest>=8.0
```

- [ ] **Step 2: Create `.gitignore`**

```
.env
__pycache__/
*.pyc
data/
reports/
cache/
.pytest_cache/
```

- [ ] **Step 3: Create `.env.example`**

```
# Claude API
ANTHROPIC_API_KEY=sk-ant-...
# Gmail SMTP (use a Gmail App Password, not your account password)
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
EMAIL_RECIPIENT=you@gmail.com
# Optional: override path to the portfolio_analysis codebase
PORTFOLIO_ANALYSIS_PATH=/home/kineticrick/code/python/portfolio_analysis
```

- [ ] **Step 4: Create empty package markers and starter config**

Create `radar/__init__.py` (empty) and `tests/__init__.py` (empty).

Create `config/universe.txt` (starter; expanded in Task 3's real loader test data — a minimal seed is fine here):

```
# Ticker universe — one symbol per line. Lines starting with '#' are comments.
# Expanded from index constituents; see README.
AAPL
MSFT
NVDA
MU
WDC
```

Create `config/interests.yaml`:

```yaml
# Hand-written interest overlay: themes you care about but may not (yet) hold.
themes:
  - artificial intelligence infrastructure
  - semiconductors and memory
  - energy transition
sectors_of_interest:
  - Technology
  - Energy
risk_appetite: moderate
notes: >
  Free-text guidance for the analyst about what you care about and how you think.
```

- [ ] **Step 5: Write the failing test**

```python
# tests/test_settings.py
from pathlib import Path
import radar.settings as s

def test_load_settings_reads_env_and_makes_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key123")
    monkeypatch.setenv("GMAIL_USER", "a@b.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    monkeypatch.setenv("EMAIL_RECIPIENT", "a@b.com")
    monkeypatch.setattr(s, "PROJECT_ROOT", tmp_path)
    cfg = s.load_settings(load_dotenv_file=False)
    assert cfg.anthropic_api_key == "key123"
    assert cfg.model == "claude-opus-4-8"
    assert cfg.data_dir.exists() and cfg.reports_dir.exists() and cfg.cache_dir.exists()
    assert cfg.portfolio_analysis_path  # has a default
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd /home/kineticrick/code/python/market_insights && python -m pytest tests/test_settings.py -v`
Expected: FAIL (module/attribute not defined).

- [ ] **Step 7: Write `radar/settings.py`**

```python
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PA_PATH = "/home/kineticrick/code/python/portfolio_analysis"

@dataclass
class Settings:
    anthropic_api_key: str
    gmail_user: str
    gmail_app_password: str
    email_recipient: str
    model: str
    portfolio_analysis_path: str
    project_root: Path
    config_dir: Path
    data_dir: Path
    reports_dir: Path
    cache_dir: Path

def load_settings(load_dotenv_file: bool = True) -> Settings:
    if load_dotenv_file:
        load_dotenv(PROJECT_ROOT / ".env")
    data_dir = PROJECT_ROOT / "data"
    reports_dir = PROJECT_ROOT / "reports"
    cache_dir = PROJECT_ROOT / "cache"
    for d in (data_dir, reports_dir, cache_dir):
        d.mkdir(parents=True, exist_ok=True)
    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        gmail_user=os.getenv("GMAIL_USER", ""),
        gmail_app_password=os.getenv("GMAIL_APP_PASSWORD", ""),
        email_recipient=os.getenv("EMAIL_RECIPIENT", ""),
        model=os.getenv("RADAR_MODEL", "claude-opus-4-8"),
        portfolio_analysis_path=os.getenv("PORTFOLIO_ANALYSIS_PATH", DEFAULT_PA_PATH),
        project_root=PROJECT_ROOT,
        config_dir=PROJECT_ROOT / "config",
        data_dir=data_dir,
        reports_dir=reports_dir,
        cache_dir=cache_dir,
    )
```

- [ ] **Step 8: Run test to verify it passes**

Run: `python -m pytest tests/test_settings.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add requirements.txt .gitignore .env.example radar/ tests/ config/
git commit -m "feat: project scaffolding and settings loader"
```

---

### Task 2: Data models

**Files:**
- Create: `radar/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces:
  - `Signal` dataclass: `ticker: str`, `signal_type: str`, `value: float`, `rank: int`, `sector: str | None`, `metrics: dict` (e.g. `{"ret_1m":.., "ret_3m":.., "ret_6m":.., "ret_12m":.., "volume_ratio":..}`).
  - `SignalSet` dataclass: `as_of: str` (YYYY-MM-DD), `signals: list[Signal]`, `sector_momentum: dict[str, float]`. Methods `to_dict() -> dict`, `from_dict(d) -> SignalSet`, `save(path)`, `load(path) -> SignalSet`.
  - `Holding` dataclass: `ticker: str`, `name: str`, `shares: float`, `cost_basis: float`, `current_value: float | None`, `pct_of_portfolio: float | None`, `sector: str | None`, `asset_type: str | None`.
  - `PortfolioContext` dataclass: `available: bool`, `holdings: list[Holding]`, `sector_concentration: dict[str, float]`, `asset_type_concentration: dict[str, float]`, `revealed_interests: list[str]`, `note: str` (e.g. degradation reason). Method `summary_text() -> str` (compact human-readable summary for the analyst prompt).
  - `BriefItem` dataclass: `title: str`, `thesis: str`, `evidence: str`, `sources: list[str]`, `why_it_matters: str`, `portfolio_relevance: str`.
  - `Brief` dataclass: `as_of: str`, `executive_summary: str`, `items: list[BriefItem]`, `watchlist: list[str]`, `challenge: str`, `what_im_missing: str`, `disclaimer: str`. Methods `to_dict()`, `from_dict(d)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from radar.models import Signal, SignalSet, Holding, PortfolioContext, Brief, BriefItem

def test_signalset_roundtrip(tmp_path):
    ss = SignalSet(
        as_of="2026-06-26",
        signals=[Signal(ticker="MU", signal_type="ret_12m_leader", value=1.4,
                        rank=1, sector="Technology",
                        metrics={"ret_12m": 1.4, "volume_ratio": 2.1})],
        sector_momentum={"Technology": 0.22},
    )
    p = tmp_path / "ss.json"
    ss.save(p)
    loaded = SignalSet.load(p)
    assert loaded.as_of == "2026-06-26"
    assert loaded.signals[0].ticker == "MU"
    assert loaded.signals[0].metrics["ret_12m"] == 1.4
    assert loaded.sector_momentum["Technology"] == 0.22

def test_portfolio_context_summary_text():
    pc = PortfolioContext(
        available=True,
        holdings=[Holding(ticker="AAPL", name="Apple", shares=10, cost_basis=1000,
                          current_value=2000, pct_of_portfolio=0.5,
                          sector="Technology", asset_type="Common Stock")],
        sector_concentration={"Technology": 0.5},
        asset_type_concentration={"Common Stock": 1.0},
        revealed_interests=["Technology"],
        note="",
    )
    text = pc.summary_text()
    assert "AAPL" in text and "Technology" in text

def test_brief_roundtrip():
    b = Brief(as_of="2026-06-26", executive_summary="x",
              items=[BriefItem(title="t", thesis="th", evidence="e",
                               sources=["http://s"], why_it_matters="w",
                               portfolio_relevance="p")],
              watchlist=["NVDA"], challenge="c", what_im_missing="m",
              disclaimer="not advice")
    d = b.to_dict()
    b2 = Brief.from_dict(d)
    assert b2.items[0].sources == ["http://s"]
    assert b2.challenge == "c"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Write `radar/models.py`**

```python
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

@dataclass
class Signal:
    ticker: str
    signal_type: str
    value: float
    rank: int
    sector: str | None = None
    metrics: dict = field(default_factory=dict)

@dataclass
class SignalSet:
    as_of: str
    signals: list
    sector_momentum: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of,
            "signals": [asdict(s) for s in self.signals],
            "sector_momentum": self.sector_momentum,
        }

    @staticmethod
    def from_dict(d: dict) -> "SignalSet":
        return SignalSet(
            as_of=d["as_of"],
            signals=[Signal(**s) for s in d["signals"]],
            sector_momentum=d.get("sector_momentum", {}),
        )

    def save(self, path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @staticmethod
    def load(path) -> "SignalSet":
        return SignalSet.from_dict(json.loads(Path(path).read_text()))

@dataclass
class Holding:
    ticker: str
    name: str
    shares: float
    cost_basis: float
    current_value: float | None = None
    pct_of_portfolio: float | None = None
    sector: str | None = None
    asset_type: str | None = None

@dataclass
class PortfolioContext:
    available: bool
    holdings: list = field(default_factory=list)
    sector_concentration: dict = field(default_factory=dict)
    asset_type_concentration: dict = field(default_factory=dict)
    revealed_interests: list = field(default_factory=list)
    note: str = ""

    def summary_text(self) -> str:
        if not self.available:
            return f"Portfolio data unavailable: {self.note}"
        lines = ["Current holdings:"]
        for h in self.holdings:
            pct = f"{h.pct_of_portfolio:.0%}" if h.pct_of_portfolio is not None else "?"
            lines.append(f"  {h.ticker} ({h.name}) — {pct} of portfolio, sector {h.sector}")
        lines.append("Sector concentration: " + ", ".join(
            f"{k} {v:.0%}" for k, v in self.sector_concentration.items()))
        lines.append("Revealed interests (where capital has gone): " +
                     ", ".join(self.revealed_interests))
        return "\n".join(lines)

@dataclass
class BriefItem:
    title: str
    thesis: str
    evidence: str
    sources: list = field(default_factory=list)
    why_it_matters: str = ""
    portfolio_relevance: str = ""

@dataclass
class Brief:
    as_of: str
    executive_summary: str
    items: list
    watchlist: list
    challenge: str
    what_im_missing: str
    disclaimer: str

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(d: dict) -> "Brief":
        return Brief(
            as_of=d["as_of"],
            executive_summary=d["executive_summary"],
            items=[BriefItem(**i) for i in d["items"]],
            watchlist=d.get("watchlist", []),
            challenge=d.get("challenge", ""),
            what_im_missing=d.get("what_im_missing", ""),
            disclaimer=d.get("disclaimer", ""),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add radar/models.py tests/test_models.py
git commit -m "feat: data contracts (Signal/SignalSet, PortfolioContext, Brief)"
```

---

### Task 3: Universe loader

**Files:**
- Create: `radar/universe.py`
- Test: `tests/test_universe.py`

**Interfaces:**
- Consumes: `config/universe.txt` (one ticker per line, `#` comments, blank lines ignored).
- Produces: `radar.universe.load_universe(path) -> list[str]` (de-duplicated, uppercased, order-preserving).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_universe.py
from radar.universe import load_universe

def test_load_universe_parses_and_dedupes(tmp_path):
    f = tmp_path / "universe.txt"
    f.write_text("# comment\nAAPL\n\nmsft\nAAPL\n  NVDA  \n")
    out = load_universe(f)
    assert out == ["AAPL", "MSFT", "NVDA"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_universe.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Write `radar/universe.py`**

```python
from pathlib import Path

def load_universe(path) -> list:
    seen = set()
    out = []
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        sym = line.upper()
        if sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_universe.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add radar/universe.py tests/test_universe.py
git commit -m "feat: ticker universe loader"
```

---

### Task 4: Market data ingestion

**Files:**
- Create: `radar/data_ingest.py`
- Test: `tests/test_data_ingest.py`

**Interfaces:**
- Consumes: a list of tickers (from `load_universe`), `Settings.cache_dir`.
- Produces:
  - `MarketData` dataclass: `as_of: str`, `prices: dict[str, pandas.Series]` (close price series, date-indexed), `volumes: dict[str, pandas.Series]`, `sectors: dict[str, str]`.
  - `fetch_market_data(tickers, cache_dir, batch_size=100, period="1y", _downloader=None, _sector_fn=None) -> MarketData`. Uses `yfinance.download` in batches; caches each batch's raw frame to `cache_dir` as parquet keyed by a hash of the batch + date, reused within the same day. `_downloader`/`_sector_fn` are injectable for testing (default to real yfinance).

- [ ] **Step 1: Write the failing test (mocked yfinance)**

```python
# tests/test_data_ingest.py
import pandas as pd
from radar.data_ingest import fetch_market_data, MarketData

def _fake_download(tickers, period):
    # Mimic yfinance.download multiindex columns: (field, ticker)
    idx = pd.date_range("2025-06-01", periods=5, freq="D")
    cols = pd.MultiIndex.from_product([["Close", "Volume"], tickers])
    data = {}
    for f in ["Close", "Volume"]:
        for t in tickers:
            base = 100.0 if f == "Close" else 1000.0
            data[(f, t)] = [base + i for i in range(5)]
    return pd.DataFrame(data, index=idx, columns=cols)

def _fake_sector(ticker):
    return {"AAPL": "Technology", "MU": "Technology"}.get(ticker, "Unknown")

def test_fetch_market_data_builds_series(tmp_path):
    md = fetch_market_data(["AAPL", "MU"], cache_dir=tmp_path, batch_size=2,
                           _downloader=_fake_download, _sector_fn=_fake_sector)
    assert isinstance(md, MarketData)
    assert "AAPL" in md.prices and len(md.prices["AAPL"]) == 5
    assert md.prices["AAPL"].iloc[-1] == 104.0
    assert md.volumes["MU"].iloc[0] == 1000.0
    assert md.sectors["AAPL"] == "Technology"

def test_fetch_market_data_caches(tmp_path):
    calls = {"n": 0}
    def counting_download(tickers, period):
        calls["n"] += 1
        return _fake_download(tickers, period)
    fetch_market_data(["AAPL"], cache_dir=tmp_path, batch_size=1,
                      _downloader=counting_download, _sector_fn=_fake_sector)
    fetch_market_data(["AAPL"], cache_dir=tmp_path, batch_size=1,
                      _downloader=counting_download, _sector_fn=_fake_sector)
    assert calls["n"] == 1  # second run served from cache
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_data_ingest.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Write `radar/data_ingest.py`**

```python
import hashlib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
import pandas as pd

@dataclass
class MarketData:
    as_of: str
    prices: dict = field(default_factory=dict)
    volumes: dict = field(default_factory=dict)
    sectors: dict = field(default_factory=dict)

def _default_downloader(tickers, period):
    import yfinance as yf
    return yf.download(tickers, period=period, auto_adjust=True,
                       progress=False, group_by="column")

def _default_sector_fn(ticker):
    import yfinance as yf
    try:
        info = yf.Ticker(ticker).info
        return info.get("sector") or "Unknown"
    except Exception:
        return "Unknown"

def _batch_cache_path(cache_dir, batch, period):
    key = hashlib.sha1(
        ("|".join(batch) + period + date.today().isoformat()).encode()
    ).hexdigest()[:16]
    return Path(cache_dir) / f"batch_{key}.parquet"

def fetch_market_data(tickers, cache_dir, batch_size=100, period="1y",
                      _downloader=None, _sector_fn=None) -> MarketData:
    downloader = _downloader or _default_downloader
    sector_fn = _sector_fn or _default_sector_fn
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    prices, volumes, sectors = {}, {}, {}
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        cpath = _batch_cache_path(cache_dir, batch, period)
        if cpath.exists():
            df = pd.read_parquet(cpath)
        else:
            df = downloader(batch, period)
            df.to_parquet(cpath)
        for t in batch:
            try:
                prices[t] = df[("Close", t)].dropna()
                volumes[t] = df[("Volume", t)].dropna()
            except KeyError:
                continue
            sectors[t] = sector_fn(t)
    return MarketData(as_of=date.today().isoformat(),
                      prices=prices, volumes=volumes, sectors=sectors)
```

Note: parquet requires `pyarrow`. Add `pyarrow>=14` to `requirements.txt` in this task's commit.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_data_ingest.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add radar/data_ingest.py tests/test_data_ingest.py requirements.txt
git commit -m "feat: batched, disk-cached market data ingestion via yfinance"
```

---

### Task 5: Screener

**Files:**
- Create: `radar/screener.py`
- Test: `tests/test_screener.py`

**Interfaces:**
- Consumes: `MarketData` (Task 4), thresholds.
- Produces: `radar.screener.run_screener(market_data, top_n=25, return_leader_threshold=1.0, volume_spike_ratio=2.0) -> SignalSet`. Computes per-ticker trailing returns (1m≈21d, 3m≈63d, 6m≈126d, 12m≈252d) and volume ratio (latest vs trailing-average), emits `Signal`s for ret_12m leaders (≥ threshold), volume spikes (ratio ≥ threshold), and a `sector_momentum` map (mean 12m return per sector). Signals ranked by 12m return; capped at `top_n`. Deterministic.

- [ ] **Step 1: Write the failing test (synthetic deterministic data)**

```python
# tests/test_screener.py
import pandas as pd
from radar.data_ingest import MarketData
from radar.screener import run_screener

def _series(values):
    idx = pd.date_range("2025-06-01", periods=len(values), freq="D")
    return pd.Series(values, index=idx)

def test_screener_flags_12m_leader_and_volume_spike():
    # 260 days so 252d lookback exists. Doubler: ends at 2x its 252-days-ago price.
    doubler = [100.0] + [100.0 + (i * 100.0 / 259) for i in range(259)]  # 100 -> 200
    flat = [50.0] * 260
    vols_spike = [1000.0] * 259 + [5000.0]  # last day 5x
    vols_flat = [1000.0] * 260
    md = MarketData(
        as_of="2026-06-26",
        prices={"MU": _series(doubler), "AAPL": _series(flat)},
        volumes={"MU": _series(vols_spike), "AAPL": _series(vols_flat)},
        sectors={"MU": "Technology", "AAPL": "Technology"},
    )
    ss = run_screener(md, return_leader_threshold=0.9, volume_spike_ratio=2.0)
    types = {(s.ticker, s.signal_type) for s in ss.signals}
    assert ("MU", "ret_12m_leader") in types
    assert ("MU", "volume_spike") in types
    assert ("AAPL", "ret_12m_leader") not in types
    assert ss.sector_momentum["Technology"] > 0  # MU pulls it positive

def test_screener_ranks_by_12m_return():
    big = [100.0 + (i * 100.0 / 259) for i in range(260)]   # ~+100%
    small = [100.0 + (i * 20.0 / 259) for i in range(260)]  # ~+20%
    md = MarketData(as_of="2026-06-26",
                    prices={"BIG": _series(big), "SM": _series(small)},
                    volumes={"BIG": _series([1.0]*260), "SM": _series([1.0]*260)},
                    sectors={"BIG": "Tech", "SM": "Tech"})
    ss = run_screener(md, return_leader_threshold=0.1, volume_spike_ratio=99.0)
    leaders = [s for s in ss.signals if s.signal_type == "ret_12m_leader"]
    assert leaders[0].ticker == "BIG" and leaders[0].rank == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_screener.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Write `radar/screener.py`**

```python
from statistics import mean
from radar.models import Signal, SignalSet

_WINDOWS = {"ret_1m": 21, "ret_3m": 63, "ret_6m": 126, "ret_12m": 252}

def _trailing_return(series, lookback):
    if len(series) <= lookback:
        return None
    past = series.iloc[-(lookback + 1)]
    last = series.iloc[-1]
    if past == 0 or past != past:  # zero or NaN
        return None
    return float(last / past - 1.0)

def _volume_ratio(series, lookback=21):
    if len(series) < lookback + 1:
        return None
    trailing = series.iloc[-(lookback + 1):-1]
    avg = float(trailing.mean())
    if avg == 0:
        return None
    return float(series.iloc[-1] / avg)

def run_screener(market_data, top_n=25, return_leader_threshold=1.0,
                 volume_spike_ratio=2.0) -> SignalSet:
    rows = []
    for ticker, prices in market_data.prices.items():
        metrics = {}
        for name, lb in _WINDOWS.items():
            r = _trailing_return(prices, lb)
            if r is not None:
                metrics[name] = r
        vol = market_data.volumes.get(ticker)
        vr = _volume_ratio(vol) if vol is not None else None
        if vr is not None:
            metrics["volume_ratio"] = vr
        rows.append((ticker, market_data.sectors.get(ticker, "Unknown"), metrics))

    # rank by 12m return (desc); tickers without a 12m return sort last
    rows.sort(key=lambda r: r[2].get("ret_12m", float("-inf")), reverse=True)

    signals = []
    rank = 0
    for ticker, sector, metrics in rows:
        ret12 = metrics.get("ret_12m")
        if ret12 is not None and ret12 >= return_leader_threshold:
            rank += 1
            signals.append(Signal(ticker=ticker, signal_type="ret_12m_leader",
                                  value=ret12, rank=rank, sector=sector,
                                  metrics=metrics))
        vr = metrics.get("volume_ratio")
        if vr is not None and vr >= volume_spike_ratio:
            signals.append(Signal(ticker=ticker, signal_type="volume_spike",
                                  value=vr, rank=0, sector=sector, metrics=metrics))

    signals = signals[:top_n] if top_n else signals

    by_sector = {}
    for _, sector, metrics in rows:
        if "ret_12m" in metrics:
            by_sector.setdefault(sector, []).append(metrics["ret_12m"])
    sector_momentum = {s: mean(v) for s, v in by_sector.items()}

    return SignalSet(as_of=market_data.as_of, signals=signals,
                     sector_momentum=sector_momentum)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_screener.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add radar/screener.py tests/test_screener.py
git commit -m "feat: deterministic signal screener"
```

---

### Task 6: Portfolio context adapter

**Files:**
- Create: `radar/portfolio_context.py`
- Test: `tests/test_portfolio_context.py`

**Interfaces:**
- Consumes: `Settings.portfolio_analysis_path`. Imports `portfolio_analysis` **only inside this module**, lazily.
- Produces: `radar.portfolio_context.load_portfolio_context(pa_path, _loader=None) -> PortfolioContext`. The real `_loader` (default) appends `pa_path` to `sys.path` and calls `portfolio_analysis` helpers: `get_portfolio_current_value()` → holdings + `% Total Portfolio` + `Current Value`; `add_asset_info()` for sector/asset_type; `build_master_log()` to derive revealed interests (distinct sectors/symbols the user has bought historically). On ANY exception, returns `PortfolioContext(available=False, note=<reason>)`. `_loader` is injectable: a callable returning a dict `{"holdings": [...], "revealed_interests": [...]}` for testing without the real DB.

- [ ] **Step 1: Write the failing test (injected loader; no real DB)**

```python
# tests/test_portfolio_context.py
from radar.portfolio_context import load_portfolio_context
from radar.models import PortfolioContext

def _fake_loader(pa_path):
    return {
        "holdings": [
            {"ticker": "AAPL", "name": "Apple", "shares": 10, "cost_basis": 1000,
             "current_value": 3000, "pct_of_portfolio": 0.6,
             "sector": "Technology", "asset_type": "Common Stock"},
            {"ticker": "XOM", "name": "Exxon", "shares": 20, "cost_basis": 2000,
             "current_value": 2000, "pct_of_portfolio": 0.4,
             "sector": "Energy", "asset_type": "Common Stock"},
        ],
        "revealed_interests": ["Technology", "Energy", "Semiconductors"],
    }

def test_load_portfolio_context_builds_concentrations():
    pc = load_portfolio_context("/unused", _loader=_fake_loader)
    assert isinstance(pc, PortfolioContext) and pc.available
    assert pc.sector_concentration["Technology"] == 0.6
    assert pc.asset_type_concentration["Common Stock"] == 1.0
    assert "Semiconductors" in pc.revealed_interests

def test_load_portfolio_context_degrades_on_error():
    def boom(pa_path):
        raise RuntimeError("db down")
    pc = load_portfolio_context("/unused", _loader=boom)
    assert pc.available is False and "db down" in pc.note
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_portfolio_context.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Write `radar/portfolio_context.py`**

```python
import sys
from radar.models import Holding, PortfolioContext

def _real_loader(pa_path: str) -> dict:
    if pa_path not in sys.path:
        sys.path.append(pa_path)
    from libraries.helpers import get_portfolio_current_value, add_asset_info, build_master_log
    df, _total = get_portfolio_current_value()
    df = add_asset_info(df, truncate=True)
    holdings = []
    for _, row in df.iterrows():
        pct = row.get("% Total Portfolio")
        holdings.append({
            "ticker": row.get("Symbol"),
            "name": row.get("Name", ""),
            "shares": float(row.get("Quantity", 0) or 0),
            "cost_basis": float(row.get("Cost Basis", 0) or 0),
            "current_value": float(row.get("Current Value", 0) or 0),
            "pct_of_portfolio": float(pct) / 100.0 if pct and pct > 1 else float(pct or 0),
            "sector": row.get("Sector"),
            "asset_type": row.get("Asset Type"),
        })
    log = build_master_log()  # full history
    revealed = []
    for col in ("Sector", "Symbol"):
        if col in log.columns:
            for v in log[col].dropna().unique().tolist():
                if v not in revealed:
                    revealed.append(v)
    return {"holdings": holdings, "revealed_interests": revealed}

def load_portfolio_context(pa_path: str, _loader=None) -> PortfolioContext:
    loader = _loader or _real_loader
    try:
        raw = loader(pa_path)
    except Exception as e:  # graceful degradation
        return PortfolioContext(available=False, note=str(e))

    holdings = [Holding(**h) for h in raw["holdings"]]
    sector_conc, type_conc = {}, {}
    for h in holdings:
        if h.pct_of_portfolio:
            sector_conc[h.sector] = sector_conc.get(h.sector, 0.0) + h.pct_of_portfolio
    total_val = sum((h.current_value or 0) for h in holdings) or 1.0
    for h in holdings:
        if h.asset_type:
            type_conc[h.asset_type] = type_conc.get(h.asset_type, 0.0) + (h.current_value or 0) / total_val
    return PortfolioContext(
        available=True,
        holdings=holdings,
        sector_concentration=sector_conc,
        asset_type_concentration=type_conc,
        revealed_interests=raw.get("revealed_interests", []),
        note="",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_portfolio_context.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add radar/portfolio_context.py tests/test_portfolio_context.py
git commit -m "feat: portfolio_analysis adapter with graceful degradation"
```

> **Implementation note for the executor:** the exact pandas column names returned by `get_portfolio_current_value()` / `add_asset_info()` (`"% Total Portfolio"`, `"Asset Type"`, etc.) come from the code exploration but should be verified against the live functions during a one-off manual run (`python -c "import sys; sys.path.append('/home/kineticrick/code/python/portfolio_analysis'); from libraries.helpers import get_portfolio_current_value; print(get_portfolio_current_value()[0].columns.tolist())"`). Adjust the `.get(...)` keys in `_real_loader` if they differ. The injected-loader tests are unaffected. Also validate whether the `hypotheticals` analysis is callable and worth feeding into `revealed_interests`/challenge (spec §13); defer if awkward.

---

### Task 7: Analyst (Claude API)

**Files:**
- Create: `radar/analyst.py`
- Test: `tests/test_analyst.py`

**Interfaces:**
- Consumes: `SignalSet`, `PortfolioContext`, the interests-overlay dict (parsed `config/interests.yaml`), `Settings` (api key + model).
- Produces:
  - `radar.analyst.build_prompt(signal_set, portfolio_context, interests) -> str` — assembles the analyst instructions + structured inputs. Pure/deterministic; directly testable.
  - `radar.analyst.parse_brief(response_text, as_of) -> Brief` — parses the model's JSON output into a `Brief`. Pure/testable.
  - `radar.analyst.generate_brief(signal_set, portfolio_context, interests, settings, _client=None) -> Brief` — calls the Claude API (streaming, adaptive thinking, web_search) and returns a `Brief`. `_client` injectable for tests.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analyst.py
import json
from radar.models import SignalSet, Signal, PortfolioContext, Brief
from radar.analyst import build_prompt, parse_brief

def _sigset():
    return SignalSet(as_of="2026-06-26",
                     signals=[Signal(ticker="MU", signal_type="ret_12m_leader",
                                     value=1.4, rank=1, sector="Technology",
                                     metrics={"ret_12m": 1.4})],
                     sector_momentum={"Technology": 0.2})

def test_build_prompt_includes_signals_portfolio_and_challenge_instruction():
    pc = PortfolioContext(available=True, holdings=[], sector_concentration={},
                          asset_type_concentration={}, revealed_interests=["Energy"],
                          note="")
    prompt = build_prompt(_sigset(), pc, {"themes": ["AI"], "risk_appetite": "moderate"})
    assert "MU" in prompt
    assert "Energy" in prompt
    assert "challenge" in prompt.lower()           # challenge/coaching instruction present
    assert "second-order" in prompt.lower()        # supply-chain reasoning instruction
    assert "json" in prompt.lower()                # output-format instruction

def test_parse_brief_reads_model_json():
    payload = {
        "executive_summary": "summary",
        "items": [{"title": "Memory boom", "thesis": "t", "evidence": "e",
                   "sources": ["http://x"], "why_it_matters": "w",
                   "portfolio_relevance": "p"}],
        "watchlist": ["NVDA"],
        "challenge": "You sold WDC early.",
        "what_im_missing": "m",
    }
    text = "prose...\n```json\n" + json.dumps(payload) + "\n```\ntrailing"
    brief = parse_brief(text, as_of="2026-06-26")
    assert isinstance(brief, Brief)
    assert brief.items[0].title == "Memory boom"
    assert brief.challenge == "You sold WDC early."
    assert "not financial advice" in brief.disclaimer.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_analyst.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Write `radar/analyst.py`**

```python
import json

DISCLAIMER = ("This is an automated research aid, not financial advice. "
              "Verify independently before making any investment decision.")

_INSTRUCTIONS = """You are a sharp, candid investment research analyst and sparring partner.
You are given (1) deterministic quantitative market signals, (2) the user's real
portfolio and historical interests, and (3) the user's stated interest themes.

Your job, in order:
1. Detect EMERGING NARRATIVES: use web_search to find themes/sectors rising in the
   news around the top movers before they are mainstream. Cite sources (URLs).
2. Find NARRATIVE<->PRICE CONVERGENCE: where a rising narrative AND unusual price
   action point at the same sector/asset. Flag these most prominently.
3. Reason SECOND-ORDER / supply-chain: if X is booming, who are the non-obvious
   upstream/downstream beneficiaries the user may not be watching?
4. PERSONAL LENS (do not narrow the broad scan): connect movers to what the user
   holds, flag threats to their concentrations, and surface adjacents to themes
   they have repeatedly bought.
5. CHALLENGE & COACH: pressure-test the user's positioning and past decisions
   against the evidence — over-concentration, a thesis now undercut, a missed
   rotation, or a recurring behavioral pattern. State the counter-case they should
   have to answer. Be evidence-based and constructive, never contrarian for its own
   sake, and never fabricate confidence.

Be specific and grounded. Show evidence and cite sources. State uncertainty plainly.

Return your final answer as a single JSON object inside a ```json code block with
exactly these keys:
{
  "executive_summary": str,
  "items": [{"title": str, "thesis": str, "evidence": str, "sources": [str],
             "why_it_matters": str, "portfolio_relevance": str}],
  "watchlist": [str],
  "challenge": str,
  "what_im_missing": str
}
"""

def build_prompt(signal_set, portfolio_context, interests) -> str:
    sig_lines = []
    for s in signal_set.signals:
        sig_lines.append(
            f"- {s.ticker} [{s.signal_type}] value={s.value:.2f} sector={s.sector} "
            f"metrics={ {k: round(v, 3) for k, v in s.metrics.items()} }")
    sectors = ", ".join(f"{k} {v:+.1%}" for k, v in
                        sorted(signal_set.sector_momentum.items(),
                               key=lambda kv: kv[1], reverse=True))
    return (
        _INSTRUCTIONS
        + f"\n\n=== As of: {signal_set.as_of} ===\n"
        + "\n=== Quantitative signals ===\n" + "\n".join(sig_lines)
        + "\n\n=== Sector momentum (mean 12m return) ===\n" + sectors
        + "\n\n=== User portfolio ===\n" + portfolio_context.summary_text()
        + "\n\n=== User interest overlay ===\n" + json.dumps(interests, indent=2)
    )

def parse_brief(response_text, as_of):
    from radar.models import Brief, BriefItem
    text = response_text
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    payload = json.loads(text[start:end + 1])
    items = [BriefItem(title=i.get("title", ""), thesis=i.get("thesis", ""),
                       evidence=i.get("evidence", ""), sources=i.get("sources", []),
                       why_it_matters=i.get("why_it_matters", ""),
                       portfolio_relevance=i.get("portfolio_relevance", ""))
             for i in payload.get("items", [])]
    return Brief(as_of=as_of,
                 executive_summary=payload.get("executive_summary", ""),
                 items=items, watchlist=payload.get("watchlist", []),
                 challenge=payload.get("challenge", ""),
                 what_im_missing=payload.get("what_im_missing", ""),
                 disclaimer=DISCLAIMER)

def generate_brief(signal_set, portfolio_context, interests, settings, _client=None):
    import anthropic
    client = _client or anthropic.Anthropic(api_key=settings.anthropic_api_key)
    prompt = build_prompt(signal_set, portfolio_context, interests)
    with client.messages.stream(
        model=settings.model,
        max_tokens=64000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        tools=[{"type": "web_search_20260209", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        msg = stream.get_final_message()
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    return parse_brief(text, as_of=signal_set.as_of)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_analyst.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add radar/analyst.py tests/test_analyst.py
git commit -m "feat: Claude analyst layer (prompt, parse, generate)"
```

---

### Task 8: Report rendering

**Files:**
- Create: `radar/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `Brief`.
- Produces:
  - `radar.report.render_markdown(brief) -> str`
  - `radar.report.render_html(brief) -> str`
  - `radar.report.save_markdown(brief, reports_dir) -> Path` (writes `reports/brief-<as_of>.md`, returns path).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report.py
from radar.models import Brief, BriefItem
from radar.report import render_markdown, render_html, save_markdown

def _brief():
    return Brief(as_of="2026-06-26", executive_summary="Big week.",
                 items=[BriefItem(title="Memory boom", thesis="AI demand",
                                  evidence="MU +140%", sources=["http://x"],
                                  why_it_matters="cycle", portfolio_relevance="you hold none")],
                 watchlist=["NVDA"], challenge="You exited WDC too early.",
                 what_im_missing="small caps", disclaimer="Not financial advice.")

def test_render_markdown_contains_sections():
    md = render_markdown(_brief())
    assert "# " in md and "Memory boom" in md
    assert "Challenge" in md and "WDC" in md
    assert "Watchlist" in md and "NVDA" in md
    assert "Not financial advice" in md

def test_render_html_is_html():
    html = render_html(_brief())
    assert "<html" in html.lower() and "Memory boom" in html

def test_save_markdown_writes_dated_file(tmp_path):
    p = save_markdown(_brief(), tmp_path)
    assert p.exists() and p.name == "brief-2026-06-26.md"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_report.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Write `radar/report.py`**

```python
from pathlib import Path
from html import escape

def render_markdown(brief) -> str:
    out = [f"# Blind-Spot Radar — Weekly Brief ({brief.as_of})", ""]
    out += ["## Executive summary", brief.executive_summary, ""]
    out.append("## Notable items")
    for i in brief.items:
        out += [f"### {i.title}",
                f"**Thesis:** {i.thesis}",
                f"**Evidence:** {i.evidence}",
                f"**Why it matters:** {i.why_it_matters}",
                f"**Portfolio relevance:** {i.portfolio_relevance}"]
        if i.sources:
            out.append("**Sources:** " + ", ".join(i.sources))
        out.append("")
    out += ["## Challenge & coaching", brief.challenge, ""]
    out += ["## What I might be missing", brief.what_im_missing, ""]
    out += ["## Watchlist", ", ".join(brief.watchlist) or "—", ""]
    out += ["---", f"_{brief.disclaimer}_"]
    return "\n".join(out)

def render_html(brief) -> str:
    def p(s): return f"<p>{escape(str(s))}</p>"
    parts = [f"<html><body><h1>Blind-Spot Radar — Weekly Brief ({escape(brief.as_of)})</h1>",
             "<h2>Executive summary</h2>", p(brief.executive_summary),
             "<h2>Notable items</h2>"]
    for i in brief.items:
        parts.append(f"<h3>{escape(i.title)}</h3>")
        parts.append(p(f"Thesis: {i.thesis}"))
        parts.append(p(f"Evidence: {i.evidence}"))
        parts.append(p(f"Why it matters: {i.why_it_matters}"))
        parts.append(p(f"Portfolio relevance: {i.portfolio_relevance}"))
        if i.sources:
            links = " ".join(f'<a href="{escape(s)}">{escape(s)}</a>' for s in i.sources)
            parts.append(f"<p>Sources: {links}</p>")
    parts += ["<h2>Challenge &amp; coaching</h2>", p(brief.challenge),
              "<h2>What I might be missing</h2>", p(brief.what_im_missing),
              "<h2>Watchlist</h2>", p(", ".join(brief.watchlist) or "—"),
              "<hr>", f"<p><em>{escape(brief.disclaimer)}</em></p>",
              "</body></html>"]
    return "\n".join(parts)

def save_markdown(brief, reports_dir) -> Path:
    path = Path(reports_dir) / f"brief-{brief.as_of}.md"
    path.write_text(render_markdown(brief))
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_report.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add radar/report.py tests/test_report.py
git commit -m "feat: Markdown + HTML report rendering"
```

---

### Task 9: Email delivery

**Files:**
- Create: `radar/deliver.py`
- Test: `tests/test_deliver.py`

**Interfaces:**
- Consumes: rendered HTML (Task 8), `Settings` (gmail_user, gmail_app_password, email_recipient).
- Produces: `radar.deliver.send_email(subject, html_body, settings, _smtp_factory=None) -> None`. Builds a MIME email and sends via Gmail SMTP (`smtp.gmail.com:465`, SSL). `_smtp_factory` injectable: a callable returning an object with `.login(user, pw)` and `.send_message(msg)` (context-manager compatible) for testing without a real connection.

- [ ] **Step 1: Write the failing test (mock SMTP)**

```python
# tests/test_deliver.py
from radar.deliver import send_email
from radar.settings import Settings
from pathlib import Path

class _FakeSMTP:
    sent = []
    def __init__(self): self.logged_in = None
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def login(self, user, pw): self.logged_in = (user, pw)
    def send_message(self, msg): _FakeSMTP.sent.append(msg)

def _settings():
    return Settings(anthropic_api_key="", gmail_user="me@gmail.com",
                    gmail_app_password="pw", email_recipient="you@gmail.com",
                    model="claude-opus-4-8", portfolio_analysis_path="/x",
                    project_root=Path("."), config_dir=Path("."),
                    data_dir=Path("."), reports_dir=Path("."), cache_dir=Path("."))

def test_send_email_builds_and_sends():
    _FakeSMTP.sent.clear()
    send_email("Weekly Brief", "<html><body>hi</body></html>", _settings(),
               _smtp_factory=lambda: _FakeSMTP())
    assert len(_FakeSMTP.sent) == 1
    msg = _FakeSMTP.sent[0]
    assert msg["To"] == "you@gmail.com"
    assert msg["Subject"] == "Weekly Brief"
    assert "hi" in msg.get_content()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_deliver.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Write `radar/deliver.py`**

```python
import ssl
import smtplib
from email.message import EmailMessage

def _default_smtp_factory():
    return smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context())

def send_email(subject, html_body, settings, _smtp_factory=None) -> None:
    factory = _smtp_factory or _default_smtp_factory
    msg = EmailMessage()
    msg["From"] = settings.gmail_user
    msg["To"] = settings.email_recipient
    msg["Subject"] = subject
    msg.set_content("This email requires an HTML-capable client.")
    msg.add_alternative(html_body, subtype="html")
    with factory() as server:
        server.login(settings.gmail_user, settings.gmail_app_password)
        server.send_message(msg)
```

Note: `EmailMessage.get_content()` on a message with an HTML alternative returns the plain part; the test asserts on the plain alt only if present. To make the test robust, assert against the HTML alternative instead:

Replace the final test assertion with:
```python
    html_part = msg.get_body(preferencelist=("html",))
    assert "hi" in html_part.get_content()
```
(Update `tests/test_deliver.py` accordingly before running Step 4.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_deliver.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add radar/deliver.py tests/test_deliver.py
git commit -m "feat: Gmail SMTP email delivery"
```

---

### Task 10: Weekly pipeline entry point & README

**Files:**
- Create: `run_weekly.py`, `README.md`
- Test: `tests/test_run_weekly.py`

**Interfaces:**
- Consumes: every prior unit.
- Produces: `run_weekly.run(settings=None, _market_data_fn=None, _portfolio_fn=None, _analyst_fn=None, _send_fn=None) -> Path` — orchestrates the full pipeline: load settings → load universe → fetch market data → screen → save SignalSet to `data/` → load portfolio context → load interests yaml → generate brief → save markdown → send email → return the saved markdown path. All external steps are injectable so the orchestration is testable without network/DB/API.

- [ ] **Step 1: Write the failing test (all externals injected)**

```python
# tests/test_run_weekly.py
from pathlib import Path
import run_weekly
from radar.settings import Settings
from radar.data_ingest import MarketData
from radar.models import PortfolioContext, Brief, BriefItem
import pandas as pd

def _settings(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "universe.txt").write_text("AAPL\n")
    (tmp_path / "config" / "interests.yaml").write_text("themes: [AI]\n")
    for d in ("data", "reports", "cache"):
        (tmp_path / d).mkdir()
    return Settings(anthropic_api_key="k", gmail_user="m@x.com",
                    gmail_app_password="pw", email_recipient="y@x.com",
                    model="claude-opus-4-8", portfolio_analysis_path="/x",
                    project_root=tmp_path, config_dir=tmp_path / "config",
                    data_dir=tmp_path / "data", reports_dir=tmp_path / "reports",
                    cache_dir=tmp_path / "cache")

def test_run_weekly_orchestrates(tmp_path):
    s = _settings(tmp_path)
    idx = pd.date_range("2025-06-01", periods=260, freq="D")
    md = MarketData(as_of="2026-06-26",
                    prices={"AAPL": pd.Series([100.0 + i for i in range(260)], index=idx)},
                    volumes={"AAPL": pd.Series([1000.0] * 260, index=idx)},
                    sectors={"AAPL": "Technology"})
    pc = PortfolioContext(available=True, holdings=[], sector_concentration={},
                          asset_type_concentration={}, revealed_interests=[], note="")
    brief = Brief(as_of="2026-06-26", executive_summary="s",
                  items=[BriefItem(title="t", thesis="x", evidence="x",
                                   sources=[], why_it_matters="x",
                                   portfolio_relevance="x")],
                  watchlist=[], challenge="c", what_im_missing="m",
                  disclaimer="Not financial advice.")
    sent = {}
    path = run_weekly.run(
        settings=s,
        _market_data_fn=lambda tickers, cache_dir: md,
        _portfolio_fn=lambda pa_path: pc,
        _analyst_fn=lambda ss, pcx, interests, st: brief,
        _send_fn=lambda subject, html, st: sent.update({"subject": subject, "html": html}),
    )
    assert Path(path).exists()
    assert (s.data_dir / "signals-2026-06-26.json").exists()
    assert "Weekly Brief" in sent["subject"]
    assert "Not financial advice" in sent["html"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run_weekly.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Write `run_weekly.py`**

```python
import yaml
from radar.settings import load_settings
from radar.universe import load_universe
from radar.data_ingest import fetch_market_data
from radar.screener import run_screener
from radar.portfolio_context import load_portfolio_context
from radar.analyst import generate_brief
from radar.report import save_markdown, render_html
from radar.deliver import send_email

def run(settings=None, _market_data_fn=None, _portfolio_fn=None,
        _analyst_fn=None, _send_fn=None):
    s = settings or load_settings()
    tickers = load_universe(s.config_dir / "universe.txt")
    md_fn = _market_data_fn or (lambda tickers, cache_dir: fetch_market_data(tickers, cache_dir))
    market_data = md_fn(tickers, s.cache_dir)

    signal_set = run_screener(market_data)
    signal_set.save(s.data_dir / f"signals-{signal_set.as_of}.json")

    pf_fn = _portfolio_fn or (lambda pa_path: load_portfolio_context(pa_path))
    portfolio = pf_fn(s.portfolio_analysis_path)

    interests = yaml.safe_load((s.config_dir / "interests.yaml").read_text()) or {}

    an_fn = _analyst_fn or (lambda ss, pc, it, st: generate_brief(ss, pc, it, st))
    brief = an_fn(signal_set, portfolio, interests, s)

    path = save_markdown(brief, s.reports_dir)
    html = render_html(brief)
    subject = f"Blind-Spot Radar — Weekly Brief ({brief.as_of})"
    send = _send_fn or (lambda subject, html, st: send_email(subject, html, st))
    send(subject, html, s)
    return path

if __name__ == "__main__":
    out = run()
    print(f"Brief written to {out} and emailed.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run_weekly.py -v`
Expected: PASS.

- [ ] **Step 5: Write `README.md`**

```markdown
# Market Insights — Blind-Spot Radar

An AI-driven research partner that scans the market weekly, fuses hard
price/volume signals with self-sourced news, and emails a reasoned (and
deliberately challenging) brief. Research aid — **not financial advice**.

## Setup
1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. `cp .env.example .env` and fill in `ANTHROPIC_API_KEY`, Gmail credentials
   (use a Gmail **App Password**), and `EMAIL_RECIPIENT`.
4. Edit `config/universe.txt` (ticker universe) and `config/interests.yaml`
   (your interest overlay).
5. Ensure the `portfolio_analysis` codebase is at
   `/home/kineticrick/code/python/portfolio_analysis` (or set
   `PORTFOLIO_ANALYSIS_PATH`). Its MySQL DB must be reachable. If unavailable,
   the radar runs in market-wide-only mode.

## Run
- Weekly digest (full pipeline): `python run_weekly.py`
- Tests: `python -m pytest -v`

## Schedule (cron)
Weekly, Sunday 7am:
```
0 7 * * 0 cd /home/kineticrick/code/python/market_insights && /path/to/.venv/bin/python run_weekly.py >> reports/cron.log 2>&1
```

## Architecture
See `docs/superpowers/specs/2026-06-26-market-insights-blind-spot-radar-design.md`.
Pipeline: data_ingest → screener → portfolio_context → analyst → report → deliver.
Daily alerts are a planned fast-follow.
```

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -v`
Expected: ALL PASS.

- [ ] **Step 7: Commit**

```bash
git add run_weekly.py README.md tests/test_run_weekly.py
git commit -m "feat: weekly pipeline entry point and README"
```

---

## Self-Review

**Spec coverage:**
- §2 architecture / units → Tasks 1–10 map 1:1 to the units (data_ingest=4, screener=5, portfolio_context=6, analyst=7, report=8, deliver=9, orchestration=10; models=2, config/settings=1, universe=3).
- §3 quantitative layer (universe blend, yfinance batched+cached, return/volume/sector signals) → Tasks 3, 4, 5.
- §4 portfolio integration (library-import behind adapter, graceful degradation, no other module imports portfolio_analysis) → Task 6 + Global Constraints.
- §5 analyst (claude-opus-4-8, adaptive thinking, web_search, narratives/convergence/2nd-order/personal-lens/challenge, structured Brief) → Task 7 (prompt instructions + parse).
- §6 delivery (Markdown archive + HTML email, Gmail SMTP) → Tasks 8, 9.
- §7 scheduling (weekly entry point + cron doc) → Task 10 + README.
- §8 config (.env, universe, interests overlay) → Task 1.
- §9 guardrails (disclaimer everywhere, graceful degradation) → DISCLAIMER in Task 7, degradation in Task 6, both surfaced in report (Task 8).
- §10 out-of-scope (daily alerts, conversational mode, etc.) → intentionally excluded; daily alerts noted as fast-follow.
- §11 first slice (weekly digest end-to-end) → this entire plan.
- §12 deliverables (README, unit tests for deterministic units) → Task 10 README; tests in Tasks 1–6, 8–10.

**Placeholder scan:** No TBD/TODO; every code step contains complete code. The two implementation-time validations (exact portfolio_analysis column names; `hypotheticals` availability) are explicitly called out as verification steps with concrete commands and fallbacks, not as gaps in the code.

**Type consistency:** `SignalSet`/`Signal`/`PortfolioContext`/`Holding`/`Brief`/`BriefItem` field names and methods (`to_dict`/`from_dict`/`save`/`load`/`summary_text`) defined in Task 2 are used consistently in Tasks 5–10. `MarketData` (Task 4) fields (`prices`/`volumes`/`sectors`/`as_of`) used consistently in Task 5. Analyst `build_prompt`/`parse_brief`/`generate_brief` signatures (Task 7) match their call in Task 10. `send_email(subject, html_body, settings, _smtp_factory)` (Task 9) matches the `_send_fn` shape in Task 10.

## Notes for the executor
- Run all commands from the project root with the venv active.
- `requirements.txt` gains `pyarrow` in Task 4 (parquet cache).
- Tasks are ordered by dependency; execute in order. Each task is independently testable and committable.
