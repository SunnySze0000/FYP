"""End-to-end research run. Each `run_*` function is one phase of the plan."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from eventlens.analysis import calibration, event_study, sanity, universe, wallets
from eventlens.config import Paths, get_paths
from eventlens.data import fomc, loaders
from eventlens.features.events import build_event_table
from eventlens.features.returns import single_ticker
from eventlens.reporting import ReportWriter
from eventlens.validation import checks

EQUITY_TICKERS = ("SPY", "QQQ", "IWM", "TLT", "DIA")


@dataclass
class Inputs:
    probabilities: pd.DataFrame
    calendar: pd.DataFrame
    prices: pd.DataFrame
    events: pd.DataFrame


def load_inputs(paths: Paths) -> Inputs:
    probabilities = loaders.load_probabilities(paths)
    calendar = fomc.calendar()
    return Inputs(
        probabilities=probabilities,
        calendar=calendar,
        prices=loaders.load_prices(paths),
        events=build_event_table(probabilities, calendar),
    )


def run_data_checks(inputs: Inputs, report: ReportWriter) -> None:
    report.section("1. Data checks", "Problems are reported, not silently repaired.")
    results = checks.run_probability_checks(inputs.probabilities, inputs.calendar)
    report.table("data_checks", checks.summarise(results), "Check summary")
    for result in results:
        if not result.passed:
            result.failures.to_csv(report.directory / f"data_check_{result.name}.csv", index=False)


def run_sanity(inputs: Inputs, report: ReportWriter) -> None:
    report.section("2. Sanity tests (known facts the pipeline must reproduce)")
    report.facts(sanity.decision_reconciliation(inputs.events))
    rows = []
    for ticker in _available_tickers(inputs.prices):
        series = single_ticker(inputs.prices, ticker)
        rows.append({"ticker": ticker, **sanity.fomc_day_volatility(series, inputs.calendar["announcement_date"])})
    report.table("fomc_day_volatility", pd.DataFrame(rows), "Squared standardised return on FOMC days vs placebo days")


def run_event_study(inputs: Inputs, report: ReportWriter) -> None:
    report.section("3. Event study: does Polymarket's pre-meeting view explain the reaction?")
    report.table("event_table", inputs.events, "One row per FOMC meeting")
    results = []
    for ticker in _available_tickers(inputs.prices):
        data = event_study.build_event_dataset(inputs.events, single_ticker(inputs.prices, ticker))
        results.append(event_study.test_hypotheses(data, ticker))
    report.table("event_study_tests", pd.concat(results, ignore_index=True), "Pre-registered hypotheses")
    report.table("power_analysis", event_study.power_table(), "Smallest detectable correlation (80% power)")


def run_calibration(inputs: Inputs, report: ReportWriter) -> None:
    report.section("4. Fed-market calibration and favourite rule")
    panel = calibration.market_day_panel(inputs.probabilities, inputs.calendar)
    report.table("fed_calibration", calibration.calibration_table(panel), "Price vs observed frequency")
    report.table("fed_brier_by_horizon", calibration.brier_by_horizon(panel), "Brier score by days to event")
    report.table("fed_favourite_rule", calibration.favourite_strategy_grid(panel),
                 "Buy the favourite and hold to resolution (1 cent cost)")
    report.table("fed_favourite_rule_time_split", calibration.chronological_split_check(panel, 30, 0.80, 0.95),
                 "Robustness: 80-95% favourites 30 days out, earlier vs later meetings")


def run_wallets(paths: Paths, inputs: Inputs, report: ReportWriter) -> None:
    report.section("5. Smart wallets (June 2026 Fed event, all participants)")
    trades = loaders.load_wallet_trades(paths)
    final_yes = (
        inputs.probabilities.drop_duplicates("market_id")
        .assign(market_id=lambda frame: frame["market_id"].astype(str))
        .set_index("market_id")["final_outcome"].to_dict()
    )
    hourly, daily = wallets.price_bars(trades, "1h"), wallets.price_bars(trades, "1D")
    trades = wallets.add_resolution_pnl(wallets.add_markouts(trades, hourly), final_yes)
    for label, sample, windows, min_trades in (
        ("all", trades, wallets.DEFAULT_WINDOWS, 20),
        ("contested", wallets.contested(trades), wallets.CONTESTED_WINDOWS, 5),
    ):
        _wallet_block(label, sample, windows, min_trades, hourly, daily, report)


def _wallet_block(label, trades, windows, min_trades, hourly, daily, report) -> None:
    formation, test = wallets.split_periods(trades, windows)
    formation_scores = wallets.wallet_scores(formation, "markout_24h_usd")
    rows = []
    for target in ("markout_24h_usd", "markout_1h_usd", "resolution_pnl_usd"):
        test_scores = wallets.wallet_scores(test, target)
        estimate, table = wallets.persistence(formation_scores, test_scores, min_trades)
        rows.append({"sample": label, "test_target": target, **estimate})
        report.table(f"wallet_{label}_quintiles_{target}", table,
                     f"[{label}] test-period results by formation-score quintile, target {target}")
    report.table(f"wallet_{label}_persistence", pd.DataFrame(rows),
                 f"[{label}] Does formation skill predict test skill? (min {min_trades} trades each period)")
    groups = wallets.assign_groups(formation_scores, min_trades)
    report.table(f"wallet_{label}_profiles", wallets.wallet_profiles(test, groups), f"[{label}] Group trading style (medians)")
    report.table(f"wallet_{label}_flow_signal", wallets.flow_signal(test, daily, groups),
                 f"[{label}] Daily net flow vs next-day price change")
    copies = [wallets.follow_with_delay(test, hourly, groups, group, 1, hold, 0.005)
              for group in ("top", "middle", "bottom") for hold in (24, 72)]
    report.table(f"wallet_{label}_copy_trading", pd.DataFrame(copies), f"[{label}] Copy trades 1h later (0.5 cent cost)")


def run_universe(paths: Paths, report: ReportWriter) -> None:
    report.section("6. Cross-market calibration (Polymarket universe)")
    if not universe.has_universe_data(paths):
        report.lines += ["_Skipped: run the collectors first (see README)._", ""]
        return
    panel = universe.build_panel(paths)
    report.table("universe_coverage", universe.coverage(panel), "Markets collected")
    report.table("universe_calibration", universe.calibration_by_bucket(panel), "Calibration by price bucket")
    report.table("universe_longshot_rule", universe.walk_forward_rule(panel), "Favourite/longshot rule, walk-forward by month")


def _available_tickers(prices: pd.DataFrame) -> list[str]:
    present = set(prices["ticker"].unique())
    return [ticker for ticker in EQUITY_TICKERS if ticker in present]


def run_all(paths: Paths | None = None) -> ReportWriter:
    paths = paths or get_paths()
    report = ReportWriter(paths.reports, "EventLens research results")
    inputs = load_inputs(paths)
    run_data_checks(inputs, report)
    run_sanity(inputs, report)
    run_event_study(inputs, report)
    run_calibration(inputs, report)
    run_wallets(paths, inputs, report)
    run_universe(paths, report)
    report.write()
    return report
