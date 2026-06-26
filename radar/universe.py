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
