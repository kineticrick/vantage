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
