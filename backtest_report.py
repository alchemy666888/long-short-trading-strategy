from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from backtest_vectorized import run_backtest
from long_short_config import (
    STRESS_LIQUIDITY_HAIRCUT,
    STRESS_MISSING_DATA_RATIO,
    STRESS_SHORT_BORROW_BPS_PER_DAY,
)

BARS_PER_YEAR = 252


@dataclass
class BacktestSummary:
    start: str
    end: str
    bars: int
    start_equity: float
    end_equity: float
    total_return_pct: float
    annualized_return_pct: float
    annualized_volatility_pct: float
    sharpe: float
    max_drawdown_pct: float
    max_drawdown_at: str


def _annualized_return(total_return: float, bars: int) -> float:
    if bars <= 0:
        return np.nan
    return (1.0 + total_return) ** (BARS_PER_YEAR / bars) - 1.0


def compute_summary(equity: pd.Series) -> BacktestSummary:
    equity = equity.dropna()
    daily_returns = equity.pct_change(fill_method=None).dropna()

    total_return = (equity.iloc[-1] / equity.iloc[0]) - 1.0
    ann_return = _annualized_return(total_return, len(daily_returns))
    ann_vol = daily_returns.std() * np.sqrt(BARS_PER_YEAR) if len(daily_returns) > 1 else np.nan
    sharpe = ann_return / ann_vol if ann_vol and not np.isnan(ann_vol) else np.nan

    running_max = equity.cummax()
    drawdown = (equity / running_max) - 1.0

    return BacktestSummary(
        start=str(equity.index[0]),
        end=str(equity.index[-1]),
        bars=int(len(equity)),
        start_equity=float(equity.iloc[0]),
        end_equity=float(equity.iloc[-1]),
        total_return_pct=float(total_return * 100.0),
        annualized_return_pct=float(ann_return * 100.0) if not np.isnan(ann_return) else np.nan,
        annualized_volatility_pct=float(ann_vol * 100.0) if not np.isnan(ann_vol) else np.nan,
        sharpe=float(sharpe) if not np.isnan(sharpe) else np.nan,
        max_drawdown_pct=float(drawdown.min() * 100.0),
        max_drawdown_at=str(drawdown.idxmin()),
    )


def _acceptance_checks(
    base: BacktestSummary,
    stress_15: BacktestSummary,
    stress_20_delay: BacktestSummary,
    median_turnover_pct: float,
) -> Dict[str, bool]:
    checks = {
        "base_sharpe_ge_0_9": bool(base.sharpe >= 0.9 if not np.isnan(base.sharpe) else False),
        "base_maxdd_le_12pct": bool(base.max_drawdown_pct >= -12.0 if not np.isnan(base.max_drawdown_pct) else False),
        "stress_1p5x_sharpe_ge_0_4": bool(stress_15.sharpe >= 0.4 if not np.isnan(stress_15.sharpe) else False),
        "stress_2p0x_delay_non_negative_total_return": bool(
            stress_20_delay.total_return_pct >= 0.0 if not np.isnan(stress_20_delay.total_return_pct) else False
        ),
        "median_daily_turnover_le_35pct": bool(median_turnover_pct <= 35.0),
    }
    return checks


def _decision(checks: Dict[str, bool], base: BacktestSummary, stress_15: BacktestSummary) -> str:
    passed = sum(1 for v in checks.values() if v)
    if passed == len(checks):
        return "deploy"
    if base.total_return_pct > 0 and stress_15.total_return_pct > 0:
        return "refine"
    return "abandon"


def _run_scenarios() -> Tuple[Dict[str, Dict], Dict[str, BacktestSummary]]:
    scenario_params = {
        "base": {
            "cost_multiplier": 1.0,
            "one_day_delay": False,
            "missing_data_ratio": 0.0,
            "liquidity_haircut": 1.0,
            "short_borrow_bps_per_day": 0.0,
        },
        "stress_1p5x": {
            "cost_multiplier": 1.5,
            "one_day_delay": False,
            "missing_data_ratio": 0.0,
            "liquidity_haircut": 1.0,
            "short_borrow_bps_per_day": 0.0,
        },
        "stress_2p0x_delay": {
            "cost_multiplier": 2.0,
            "one_day_delay": True,
            "missing_data_ratio": 0.0,
            "liquidity_haircut": 1.0,
            "short_borrow_bps_per_day": 0.0,
        },
        "stress_missing_data": {
            "cost_multiplier": 1.0,
            "one_day_delay": False,
            "missing_data_ratio": STRESS_MISSING_DATA_RATIO,
            "liquidity_haircut": 1.0,
            "short_borrow_bps_per_day": 0.0,
        },
        "stress_liquidity": {
            "cost_multiplier": 1.0,
            "one_day_delay": False,
            "missing_data_ratio": 0.0,
            "liquidity_haircut": STRESS_LIQUIDITY_HAIRCUT,
            "short_borrow_bps_per_day": 0.0,
        },
        "stress_borrow_funding": {
            "cost_multiplier": 1.0,
            "one_day_delay": False,
            "missing_data_ratio": 0.0,
            "liquidity_haircut": 1.0,
            "short_borrow_bps_per_day": STRESS_SHORT_BORROW_BPS_PER_DAY,
        },
    }

    results: Dict[str, Dict] = {}
    summaries: Dict[str, BacktestSummary] = {}

    for name, params in scenario_params.items():
        res = run_backtest(**params)
        results[name] = res
        summaries[name] = compute_summary(res["equity"])

    return results, summaries


def write_report_files(output_dir: Path, make_plots: bool) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    results, summaries = _run_scenarios()
    base_diag = results["base"]["diagnostics"]

    median_turnover_pct = float(base_diag.get("turnover", {}).get("median_daily_turnover_pct", np.nan))
    checks = _acceptance_checks(
        base=summaries["base"],
        stress_15=summaries["stress_1p5x"],
        stress_20_delay=summaries["stress_2p0x_delay"],
        median_turnover_pct=median_turnover_pct,
    )
    decision = _decision(checks, summaries["base"], summaries["stress_1p5x"])

    generated = {}

    for scenario, result in results.items():
        equity_path = output_dir / f"equity_{scenario}.csv"
        result["equity"].to_frame("equity").to_csv(equity_path)
        generated[f"equity_{scenario}"] = str(equity_path)

    base_returns = results["base"]["daily_returns"].rename("daily_return")
    daily_returns_path = output_dir / "daily_returns.csv"
    monthly_returns_path = output_dir / "monthly_returns.csv"
    base_returns.to_frame().to_csv(daily_returns_path)
    base_returns.resample("ME").sum().to_frame("monthly_return").to_csv(monthly_returns_path)
    generated["daily_returns"] = str(daily_returns_path)
    generated["monthly_returns"] = str(monthly_returns_path)

    summary_json_path = output_dir / "summary.json"
    summary_json = {
        "strategy_version": "v5",
        "hypothesis": "Weekly-regime plus daily trend/reversal scoring with 4H staged execution can preserve net edge under friction and turnover constraints.",
        "scenarios": {name: asdict(summary) for name, summary in summaries.items()},
        "acceptance_checks": checks,
        "decision": decision,
        "diagnostics": {
            "regime_state_attribution": base_diag.get("regime_attribution", {}),
            "turnover": base_diag.get("turnover", {}),
            "execution": base_diag.get("execution", {}),
            "breadth": {
                k: v
                for k, v in base_diag.get("breadth", {}).items()
                if k != "history"
            },
            "cost_drag": base_diag.get("cost_drag", {}),
            "risk_events": {
                "count": base_diag.get("risk_events", {}).get("count", 0),
                "by_type": base_diag.get("risk_events", {}).get("by_type", {}),
            },
            "data_quality": base_diag.get("quality", {}),
        },
    }

    summary_json_path.write_text(json.dumps(summary_json, indent=2), encoding="utf-8")
    generated["summary_json"] = str(summary_json_path)

    summary_md_path = output_dir / "summary.md"
    with summary_md_path.open("w", encoding="utf-8") as f:
        f.write("# Backtest Summary (v5)\n\n")
        f.write("## 1. Hypothesis\n")
        f.write(
            "Weekly-regime plus daily trend/reversal scoring with 4H staged execution can preserve net edge under friction and turnover constraints.\n\n"
        )

        f.write("## 2. Scenarios\n")
        for name in [
            "base",
            "stress_1p5x",
            "stress_2p0x_delay",
            "stress_missing_data",
            "stress_liquidity",
            "stress_borrow_funding",
        ]:
            s = summaries[name]
            f.write(f"### {name}\n")
            f.write(f"- Total return: {s.total_return_pct:.2f}%\n")
            f.write(f"- Sharpe: {s.sharpe:.3f}\n")
            f.write(f"- Max drawdown: {s.max_drawdown_pct:.2f}%\n")

        f.write("\n## 3. Regime-State Attribution (Base)\n")
        for state, metrics in base_diag.get("regime_attribution", {}).items():
            f.write(f"### {state}\n")
            f.write(f"- Total return: {metrics.get('total_return_pct', float('nan')):.2f}%\n")
            f.write(f"- Sharpe: {metrics.get('sharpe', float('nan')):.3f}\n")
            f.write(f"- Max drawdown: {metrics.get('max_drawdown_pct', float('nan')):.2f}%\n")

        turnover = base_diag.get("turnover", {})
        f.write("\n## 4. Turnover Decomposition (Base)\n")
        f.write(f"- Raw turnover (avg daily): {turnover.get('avg_raw_turnover', 0.0) * 100.0:.2f}%\n")
        f.write(f"- Turnover after no-trade band (avg daily): {turnover.get('avg_turnover_after_band', 0.0) * 100.0:.2f}%\n")
        f.write(f"- Throttled turnover (avg daily): {turnover.get('avg_throttled_turnover', 0.0) * 100.0:.2f}%\n")
        f.write(f"- Median daily turnover: {turnover.get('median_daily_turnover_pct', 0.0):.2f}%\n")

        execution = base_diag.get("execution", {})
        f.write("\n## 5. Execution Diagnostics (Base)\n")
        counts = execution.get("counts", {})
        f.write(f"- Executed trades: {counts.get('executed', 0)}\n")
        f.write(f"- Deferred trades: {counts.get('deferred', 0)}\n")
        f.write(f"- Canceled trades: {counts.get('canceled', 0)}\n")
        f.write("- Avg slippage (bps) by quality bucket:\n")
        for bucket, value in execution.get("avg_slippage_bps_by_bucket", {}).items():
            if value is None or np.isnan(value):
                f.write(f"  - {bucket}: n/a\n")
            else:
                f.write(f"  - {bucket}: {value:.2f}\n")

        breadth = base_diag.get("breadth", {})
        f.write("\n## 6. Breadth and Eligibility (Base)\n")
        f.write(f"- Average active assets: {breadth.get('average_active_assets', 0.0):.2f}\n")
        f.write(f"- Average active categories: {breadth.get('average_active_categories', 0.0):.2f}\n")
        f.write(f"- Mean max-category share: {breadth.get('max_category_share_mean', 0.0):.2f}\n")

        cost_drag = base_diag.get("cost_drag", {})
        f.write("\n## 7. Cost Drag by Asset Class (Base)\n")
        for cls, amount in cost_drag.get("by_asset_class", {}).items():
            f.write(f"- {cls}: ${amount:,.2f}\n")

        risk = base_diag.get("risk_events", {})
        f.write("\n## 8. Risk Event Ledger (Base)\n")
        f.write(f"- Total risk events: {risk.get('count', 0)}\n")
        for event, n in risk.get("by_type", {}).items():
            f.write(f"- {event}: {n}\n")

        f.write("\n## 9. Acceptance Gate and Decision\n")
        for check_name, passed in checks.items():
            f.write(f"- {check_name}: {'PASS' if passed else 'FAIL'}\n")
        f.write(f"\n**Decision: {decision}**\n")

    generated["summary_md"] = str(summary_md_path)

    if make_plots:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(12, 5))
        for scenario in ["base", "stress_1p5x", "stress_2p0x_delay", "stress_missing_data", "stress_liquidity", "stress_borrow_funding"]:
            results[scenario]["equity"].plot(ax=ax, lw=1.0, label=scenario)
        ax.legend(loc="best")
        ax.set_title("v5 Scenario Equity Curves")
        fig.tight_layout()
        eq_png = output_dir / "equity_curve.png"
        fig.savefig(eq_png, dpi=150)
        plt.close(fig)
        generated["equity_curve_png"] = str(eq_png)

    return generated


def default_output_dir() -> Path:
    ts = pd.Timestamp.now(tz="US/Eastern").strftime("%Y%m%d_%H%M%S")
    return Path("data") / "reports" / ts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run v5 backtest scenario matrix and generate report bundle.")
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--no-plots", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir) if args.output_dir else default_output_dir()
    generated = write_report_files(output_dir=out_dir, make_plots=not args.no_plots)

    print(f"Report generated in: {out_dir}")
    for key, value in generated.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
