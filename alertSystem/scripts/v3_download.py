"""V3 · download sector volatility gauges (60-minute bars, 730 days) to data/raw/vol_gauges.csv. Run on the laptop."""
import sys, csv, time
from pathlib import Path
root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from walletlens.polymarket import yahoo

GAUGES = ["^OVX", "^GVZ", "^MOVE", "^VXFXI", "^VXN", "^VIX"]
out = root / "data" / "raw" / "vol_gauges.csv"; out.parent.mkdir(parents=True, exist_ok=True)
rows = []
for g in GAUGES:
    try:
        bars = yahoo.bars(yahoo.chart(g, "60m", "730d"), 3600)
        rows += [(g, s, e, c) for s, e, c in bars]
        print(f"{g:8s} {len(bars):6d} bars")
    except Exception as error:      # noqa: BLE001
        print(f"{g:8s} FAILED: {error}")
    time.sleep(1)
with open(out, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["symbol", "start_ts", "end_ts", "close"]); w.writerows(rows)
print("saved", out, len(rows), "rows")
