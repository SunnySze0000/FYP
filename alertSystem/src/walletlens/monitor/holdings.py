"""D1 · Portfolio import: turn any US large stock or ETF ticker into a set of checked links to event bets.

Layer 1  direct mention   company name, ticker and a few well-known executives, matched in bet questions
Layer 2  via sector       Yahoo sector / industry (stocks) or a hand-made ETF table -> topic groups
Layer 3  history check    keep a group link only if the holding's own hourly moves were larger than usual
                          in past jump hours of that group (research data, every group is tested)
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from walletlens import logs
from walletlens.monitor import APP_VERSION
from walletlens.polymarket import yahoo
from walletlens.polymarket.http import get_json

log = logs.get("monitor.holdings")
SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"
US_EXCHANGES = {"NMS", "NYQ", "NGM", "NCM", "PCX", "ASE", "BTS", "NYS", "NAS", "CBO", "PNK"}
GROUPS = ("rates", "macro", "trade_china", "energy_mideast", "war_europe", "crypto", "ai_tech", "us_politics")
WEAK = {"us_politics"}

# hand-made table for common ETFs (Yahoo gives no sector for funds)
ETF_GROUPS = {
    **{s: ("macro", "trade_china", "rates") for s in ("SPY", "VOO", "IVV", "VTI", "SPLG", "ITOT", "SCHB", "RSP", "DIA")},
    **{s: ("ai_tech", "trade_china", "macro") for s in ("QQQ", "QQQM", "VGT", "XLK", "XLC")},
    **{s: ("ai_tech", "trade_china") for s in ("SMH", "SOXX", "SOXL")},
    **{s: ("rates", "macro") for s in ("TLT", "IEF", "SHY", "BND", "AGG", "GOVT", "TLH", "VGLT", "BIL", "SGOV", "TIP", "LQD", "HYG")},
    **{s: ("energy_mideast", "war_europe", "macro") for s in ("GLD", "IAU", "GLDM", "SGOL", "SLV")},
    **{s: ("energy_mideast", "war_europe") for s in ("USO", "BNO", "XLE", "VDE", "XOP", "OIH")},
    **{s: ("rates", "macro") for s in ("XLF", "KRE", "KBE", "VFH")},
    **{s: ("war_europe", "energy_mideast") for s in ("ITA", "XAR", "PPA")},
    **{s: ("crypto",) for s in ("IBIT", "FBTC", "GBTC", "BITO", "ARKB", "ETHA", "ETHE", "BITB")},
    **{s: ("trade_china",) for s in ("FXI", "KWEB", "MCHI", "ASHR", "EEM", "VWO", "IEMG")},
    **{s: ("war_europe", "macro") for s in ("EZU", "VGK", "IEUR", "FEZ")},
    **{s: ("macro", "rates") for s in ("IWM", "VB", "IJR", "UUP", "VNQ", "XLU", "XLRE")},
}
INDUSTRY_GROUPS = [            # (pattern in industry, groups) - checked before the sector table
    (r"semiconductor", ("ai_tech", "trade_china")),
    (r"oil|gas|coal|uranium", ("energy_mideast", "war_europe")),
    (r"gold|silver|precious", ("energy_mideast", "war_europe", "macro")),
    (r"aerospace|defense", ("war_europe", "energy_mideast")),
    (r"bank|credit|mortgage|insurance|capital markets|asset management", ("rates", "macro")),
    (r"software|internet|information technology|computer|electronic", ("ai_tech",)),
    (r"auto", ("trade_china", "macro")),
    (r"airline|travel|lodging|leisure|cruise", ("energy_mideast", "macro")),
    (r"reit|real estate", ("rates",)),
    (r"utilities", ("rates",)),
]
SECTOR_GROUPS = {
    "Technology": ("ai_tech", "trade_china"), "Communication Services": ("ai_tech",),
    "Energy": ("energy_mideast", "war_europe"), "Financial Services": ("rates", "macro"),
    "Consumer Cyclical": ("macro", "trade_china"), "Consumer Defensive": ("macro",), "Healthcare": ("macro",),
    "Industrials": ("macro", "trade_china"), "Basic Materials": ("trade_china", "macro"),
    "Utilities": ("rates",), "Real Estate": ("rates",),
}
EXECUTIVES = {"TSLA": ["musk", "elon"], "META": ["zuckerberg"], "AAPL": ["tim cook"], "NVDA": ["jensen huang", "huang"],
              "MSFT": ["nadella"], "AMZN": ["bezos", "jassy"], "MSTR": ["saylor"], "GOOGL": ["pichai", "alphabet", "google"],
              "GOOG": ["pichai", "alphabet", "google"], "BRK-B": ["buffett", "berkshire"], "JPM": ["dimon"],
              "COIN": ["armstrong", "coinbase"], "PLTR": ["karp", "palantir"]}
COMMON_WORDS = {"all", "it", "a", "on", "be", "now", "big", "key", "see", "low", "ever", "well", "next", "open", "real", "fast",
                "life", "post", "play", "true", "gold", "one", "ai", "go", "so", "us", "win", "best", "fun"}
NAME_SUFFIX = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|ltd|plc|holdings?|group|class [a-z]|the|n\.?v|s\.?a|"
                         r"common stock|ordinary shares|adr|etf|trust|fund|shares)\b\.?", re.I)


# --------------------------------------------------------------------------- layer 0: what is it?
def resolve(symbol: str, fetch=get_json) -> dict:
    symbol = symbol.strip().upper()
    info = {"symbol": symbol, "name": symbol, "type": None, "sector": None, "industry": None, "exchange": None}
    try:
        payload = fetch(SEARCH, {"q": symbol, "quotesCount": 6, "newsCount": 0})
        match = next((q for q in payload.get("quotes", []) if str(q.get("symbol", "")).upper() == symbol), None)
        if match:
            info.update(name=match.get("longname") or match.get("shortname") or symbol, type=match.get("quoteType"),
                        sector=match.get("sector"), industry=match.get("industry"), exchange=match.get("exchange"))
    except Exception as error:                        # noqa: BLE001
        log.warning("search %s failed: %s", symbol, error)
    if info["type"] is None and symbol in ETF_GROUPS:
        info["type"] = "ETF"
    if symbol.endswith("-USD"):
        info["type"], info["exchange"] = "CRYPTOCURRENCY", "CCC"
    return info


def supported(info: dict) -> tuple[bool, str]:
    if info["type"] == "CRYPTOCURRENCY":
        return True, ""
    if info["type"] not in ("EQUITY", "ETF"):
        return False, "Not found as a US stock or ETF"
    if info["exchange"] and info["exchange"] not in US_EXCHANGES:
        return False, "Only US listings are supported in this version"
    return True, ""


# --------------------------------------------------------------------------- layer 2: sector -> groups
def candidate_groups(info: dict) -> tuple[list[str], str]:
    s = info["symbol"]
    if info["type"] == "CRYPTOCURRENCY" or s in {"COIN", "MSTR", "MARA", "RIOT", "HOOD"}:
        return ["crypto"], "crypto"
    if s in ETF_GROUPS:
        return list(ETF_GROUPS[s]), "ETF table"
    industry = (info.get("industry") or "").lower()
    for pattern, groups in INDUSTRY_GROUPS:
        if re.search(pattern, industry):
            return list(groups), f"industry: {info['industry']}"
    if info.get("sector") in SECTOR_GROUPS:
        return list(SECTOR_GROUPS[info["sector"]]), f"sector: {info['sector']}"
    if info["type"] == "ETF":
        return ["macro"], "ETF not in table (assumed broad market)"
    return ["macro"], "no sector data (assumed broad market)"


# --------------------------------------------------------------------------- layer 1: direct mention
def mention_terms(info: dict) -> list[str]:
    terms = []
    if info["type"] == "EQUITY":
        name = NAME_SUFFIX.sub(" ", info.get("name") or "")
        name = re.sub(r"[^A-Za-z0-9&\-. ]", " ", name).strip()
        words = [w for w in name.split() if len(w) > 1]
        if words and words[0].lower() not in COMMON_WORDS and len(words[0]) >= 3:
            terms.append(words[0].lower())
        if len(words) >= 2:
            terms.append(" ".join(words[:2]).lower())
        sym = info["symbol"].lower()
        if len(sym) >= 3 and sym not in COMMON_WORDS:
            terms.append(sym)
    terms += EXECUTIVES.get(info["symbol"], [])
    return sorted(set(terms))


def mentions(question: str, terms: list[str]) -> bool:
    text = str(question).lower()
    return any(re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", text) for t in terms)


# --------------------------------------------------------------------------- layer 3: history check
def hourly_history(symbol: str, fetch=get_json) -> list[tuple[int, float]]:
    rows = yahoo.bars(yahoo.chart(symbol, "60m", "730d", fetch), 3600)
    return [(end, close) for _, end, close in rows]


def history_check(bars: list[tuple[int, float]], jumps: pd.DataFrame, seed: int = 7, draws: int = 1000) -> dict:
    """Per topic group: the holding's |hourly return| in that group's past jump hours vs normal (same hour of
    day). Returns effect (1.0 = normal -> effect 0), 90% CI by day bootstrap and the number of jump hours."""
    if len(bars) < 200:
        return {}
    ends = np.array([b[0] for b in bars], dtype=np.int64)
    closes = np.array([b[1] for b in bars], dtype=float)
    same = np.r_[False, np.diff(ends) == 3600]
    r = np.abs(np.r_[np.nan, np.diff(np.log(closes))])
    ok = same & np.isfinite(r)
    ends, r = ends[ok], r[ok]
    hod = (ends // 3600) % 24
    norm = pd.Series(r).groupby(hod).transform("mean").to_numpy()
    y = np.where(norm > 0, r / norm, np.nan)
    day = ends // 86_400
    rng = np.random.default_rng(seed)
    out = {}
    for group, g in jumps.groupby("group"):
        jt = np.sort(g["ts"].unique())
        hit = np.searchsorted(jt, ends, side="right") > np.searchsorted(jt, ends - 3600, side="right")
        n = int(hit.sum())
        if n < 5:
            out[group] = {"effect": None, "low": None, "high": None, "jump_hours": n}
            continue
        uniq, inv = np.unique(day, return_inverse=True)
        sh = np.bincount(inv, weights=np.where(hit, y, 0), minlength=len(uniq))
        ch = np.bincount(inv, weights=hit.astype(float), minlength=len(uniq))
        so = np.bincount(inv, weights=np.where(~hit, y, 0), minlength=len(uniq))
        co = np.bincount(inv, weights=(~hit).astype(float), minlength=len(uniq))
        boots = []
        for _ in range(draws):
            w = np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq))
            boots.append((w @ sh) / max(w @ ch, 1) - (w @ so) / max(w @ co, 1))
        eff = float(np.nanmean(y[hit]) - np.nanmean(y[~hit]))
        out[group] = {"effect": eff, "low": float(np.quantile(boots, 0.05)), "high": float(np.quantile(boots, 0.95)),
                      "jump_hours": n}
    return out


MIN_JUMP_HOURS = 15


def decide_links(candidates: list[str], history: dict) -> dict:
    """Only candidate groups (layers 1-2) are tested; history alone never adds a link.

    confirmed: history 90% CI above 0 | likely: positive but uncertain (the pooled research effect, D6, supports it) |
    untested: fewer than 15 past jump hours | weak: US politics (D6) | dropped: no effect in the holding's history.
    Adding links from history alone was tried and rejected: jump hours cluster in market-wide busy hours, so
    almost every asset looked linked to crypto markets (docs/07).
    """
    links = {}
    for group in candidates:
        h = history.get(group) or {}
        eff, low, n = h.get("effect"), h.get("low"), h.get("jump_hours", 0)
        if group in WEAK:
            links[group] = "weak"
        elif eff is None or n < MIN_JUMP_HOURS:
            links[group] = "untested"
        elif low is not None and low > 0:
            links[group] = "confirmed"
        else:
            links[group] = "likely" if eff > 0 else "dropped"
    return links


def build_profile(symbol: str, jumps: pd.DataFrame, fetch=get_json, history=None) -> dict:
    info = resolve(symbol, fetch)
    ok, reason = supported(info)
    profile = {"symbol": info["symbol"], "info": info, "version": APP_VERSION,
               "checked_at": datetime.now(timezone.utc).isoformat(), "supported": ok, "reason": reason}
    if not ok:
        return profile
    candidates, why = candidate_groups(info)
    try:
        bars = history if history is not None else hourly_history(info["symbol"], fetch)
    except Exception as error:                        # noqa: BLE001
        log.warning("history %s failed: %s", symbol, error)
        bars = []
    hist = history_check(bars, jumps)
    links = decide_links(candidates, hist)
    r = np.abs(np.diff(np.log([c for _, c in bars]))) if len(bars) > 2 else np.array([])
    profile.update(candidates=candidates, candidate_reason=why, terms=mention_terms(info), history=hist, links=links,
                   history_bars=len(bars), normal_abs_r=float(np.nanmean(r)) if len(r) else None,
                   big_threshold=float(np.nanquantile(r, 0.8)) if len(r) > 20 else None)
    return profile


def active_groups(profile: dict) -> dict[str, bool]:
    """group -> reliable? (confirmed, likely and untested are reliable; weak links are shown but never raise the level)."""
    return {g: s in ("confirmed", "likely", "untested") for g, s in (profile.get("links") or {}).items() if s != "dropped"}


def jump_ratio(profile: dict) -> float | None:
    """Average 'moves x times normal in jump hours' over the holding's reliable groups."""
    vals = [h["effect"] for g, h in (profile.get("history") or {}).items()
            if h.get("effect") is not None and active_groups(profile).get(g)]
    return 1 + float(np.mean(vals)) if vals else None


def _finite(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))
