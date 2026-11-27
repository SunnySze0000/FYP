"""V6 · 5-minute bars for every research asset and every portfolio holding (Yahoo keeps only the last 60 days).

Merges into data/raw/prices_5m/<SYMBOL>.csv (start_ts, end_ts, close), so every rerun extends the history.
Usage: python scripts/v6_download_5m.py [project root]   (TEMPORARY entry point: tonight_v5v6.bat, see H2)"""
import sys, csv, json, time
from pathlib import Path
root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from walletlens.config import ASSET_GROUPS, EventsConfig
from walletlens.polymarket import yahoo

symbols = {s for v in ASSET_GROUPS.values() for s in v} | set(EventsConfig().extra_assets)
portfolio = root / "data" / "app" / "portfolio.json"
if portfolio.exists():
    symbols |= set(json.loads(portfolio.read_text(encoding="utf-8")).get("holdings", []))
out = root / "data" / "raw" / "prices_5m"; out.mkdir(parents=True, exist_ok=True)
for sym in sorted(symbols):
    path = out / f"{sym.replace('^', '_')}.csv"
    old = {}
    if path.exists():
        with open(path, newline="") as f:
            old = {int(r["start_ts"]): (int(r["end_ts"]), float(r["close"])) for r in csv.DictReader(f)}
    try:
        bars = yahoo.bars(yahoo.chart(sym, "5m", "60d"), 300)
    except Exception as error:      # noqa: BLE001 - one failure must not stop the rest
        print(f"{sym:8s} FAILED: {error}"); continue
    before = len(old)
    for s, e, c in bars:
        old[s] = (e, c)
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["start_ts", "end_ts", "close"])
        for s in sorted(old):
            w.writerow([s, *old[s]])
    print(f"{sym:8s} {len(bars):6d} bars downloaded, {len(old) - before:6d} new, {len(old):6d} total")
    time.sleep(1)
print("V6 done:", out)
