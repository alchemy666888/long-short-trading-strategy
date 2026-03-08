from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from ablation_runner import run_ablation_suite
from backtest_vectorized import run_backtest
from long_short_config import (
    STRESS_LIQUIDITY_HAIRCUT,
    STRESS_MISSING_DATA_RATIO,
    STRESS_SHORT_BORROW_BPS_PER_DAY,
    STRATEGY_VERSION,
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


def _json_default(obj):
    if isinstance(obj, (pd.Timestamp, pd.Timedelta)):
        return str(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return str(obj)


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


def _scenario_params() -> Dict[str, Dict]:
    return {
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


def _run_scenarios(strategy_version: str) -> Tuple[Dict[str, Dict], Dict[str, BacktestSummary]]:
    results: Dict[str, Dict] = {}
    summaries: Dict[str, BacktestSummary] = {}

    for name, params in _scenario_params().items():
        res = run_backtest(
            strategy_version=strategy_version,
            analysis_ablation=None,
            persist_analysis_artifacts=False,
            **params,
        )
        results[name] = res
        summaries[name] = compute_summary(res["equity"])

    return results, summaries


def _worst_fold_monthly_return(returns: pd.Series) -> float:
    monthly = returns.resample("ME").sum().dropna()
    if monthly.empty:
        return np.nan
    return float(monthly.min() * 100.0)


def _acceptance_checks_v5(
    base: BacktestSummary,
    stress_15: BacktestSummary,
    stress_20_delay: BacktestSummary,
    median_turnover_pct: float,
) -> Dict[str, bool]:
    return {
        "base_sharpe_ge_0_9": bool(base.sharpe >= 0.9 if not np.isnan(base.sharpe) else False),
        "base_maxdd_le_12pct": bool(base.max_drawdown_pct >= -12.0 if not np.isnan(base.max_drawdown_pct) else False),
        "stress_1p5x_sharpe_ge_0_4": bool(stress_15.sharpe >= 0.4 if not np.isnan(stress_15.sharpe) else False),
        "stress_2p0x_delay_non_negative_total_return": bool(
            stress_20_delay.total_return_pct >= 0.0 if not np.isnan(stress_20_delay.total_return_pct) else False
        ),
        "median_daily_turnover_le_35pct": bool(median_turnover_pct <= 35.0),
    }


def _acceptance_checks_v6(
    v6_summaries: Dict[str, BacktestSummary],
    v5_summaries: Dict[str, BacktestSummary],
    base_overlay_high_q_share: float,
    v6_worst_fold_pct: float,
    v5_worst_fold_pct: float,
) -> Dict[str, bool]:
    base_v6 = v6_summaries["base"]
    base_v5 = v5_summaries["base"]
    stress_v6 = v6_summaries["stress_1p5x"]
    stress_v5 = v5_summaries["stress_1p5x"]

    sharpe_uplift = (
        base_v6.sharpe - base_v5.sharpe
        if (not np.isnan(base_v6.sharpe) and not np.isnan(base_v5.sharpe))
        else np.nan
    )
    stress_sharpe_uplift = (
        stress_v6.sharpe - stress_v5.sharpe
        if (not np.isnan(stress_v6.sharpe) and not np.isnan(stress_v5.sharpe))
        else np.nan
    )

    checks = {
        "oos_sharpe_uplift_ge_0p20": bool(sharpe_uplift >= 0.20 if not np.isnan(sharpe_uplift) else False),
        "max_drawdown_not_worse_than_v5": bool(base_v6.max_drawdown_pct >= base_v5.max_drawdown_pct),
        "cost_stress_sharpe_uplift_ge_0p10": bool(stress_sharpe_uplift >= 0.10 if not np.isnan(stress_sharpe_uplift) else False),
        "overlay_contrib_high_q_ge_60pct": bool(base_overlay_high_q_share >= 0.60 if not np.isnan(base_overlay_high_q_share) else False),
        "worst_fold_not_worse_than_v5": bool(v6_worst_fold_pct >= v5_worst_fold_pct)
        if (not np.isnan(v6_worst_fold_pct) and not np.isnan(v5_worst_fold_pct))
        else False,
    }
    return checks


def _decision(strategy_version: str, checks: Dict[str, bool], base: BacktestSummary, reference_base: BacktestSummary | None = None) -> str:
    passed = sum(1 for v in checks.values() if v)
    if passed == len(checks):
        return "deploy"

    if strategy_version == "v5":
        return "refine" if base.total_return_pct > 0 else "abandon"

    if reference_base is not None and not np.isnan(base.sharpe) and not np.isnan(reference_base.sharpe):
        if base.total_return_pct > 0 and base.sharpe >= reference_base.sharpe:
            return "refine"
    return "abandon"


def _write_scenario_csvs(output_dir: Path, strategy_version: str, results: Dict[str, Dict]) -> Dict[str, str]:
    generated: Dict[str, str] = {}
    for scenario, result in results.items():
        equity_path = output_dir / f"equity_{strategy_version}_{scenario}.csv"
        result["equity"].to_frame("equity").to_csv(equity_path)
        generated[f"equity_{scenario}"] = str(equity_path)

    returns = results["base"]["daily_returns"].rename("daily_return")
    daily_returns_path = output_dir / f"daily_returns_{strategy_version}.csv"
    monthly_returns_path = output_dir / f"monthly_returns_{strategy_version}.csv"
    returns.to_frame().to_csv(daily_returns_path)
    returns.resample("ME").sum().to_frame("monthly_return").to_csv(monthly_returns_path)

    generated["daily_returns"] = str(daily_returns_path)
    generated["monthly_returns"] = str(monthly_returns_path)
    return generated


def write_report_files(output_dir: Path, make_plots: bool, strategy_version: str, run_ablation: bool = True) -> Dict[str, str]:
    strategy_version = strategy_version.lower().strip()
    if strategy_version not in {"v5", "v6"}:
        raise ValueError(f"Unsupported strategy version: {strategy_version}")

    output_dir.mkdir(parents=True, exist_ok=True)

    results, summaries = _run_scenarios(strategy_version=strategy_version)
    generated = _write_scenario_csvs(output_dir=output_dir, strategy_version=strategy_version, results=results)

    base_diag = results["base"]["diagnostics"]
    median_turnover_pct = float(base_diag.get("turnover", {}).get("median_daily_turnover_pct", np.nan))

    comparison = {}
    if strategy_version == "v5":
        checks = _acceptance_checks_v5(
            base=summaries["base"],
            stress_15=summaries["stress_1p5x"],
            stress_20_delay=summaries["stress_2p0x_delay"],
            median_turnover_pct=median_turnover_pct,
        )
        decision = _decision(strategy_version, checks, summaries["base"])
    else:
        v5_results, v5_summaries = _run_scenarios(strategy_version="v5")
        base_overlay_high_q_share = float(base_diag.get("analysis", {}).get("overlay_high_q_share", np.nan))

        v6_worst_fold = _worst_fold_monthly_return(results["base"]["daily_returns"])
        v5_worst_fold = _worst_fold_monthly_return(v5_results["base"]["daily_returns"])

        checks = _acceptance_checks_v6(
            v6_summaries=summaries,
            v5_summaries=v5_summaries,
            base_overlay_high_q_share=base_overlay_high_q_share,
            v6_worst_fold_pct=v6_worst_fold,
            v5_worst_fold_pct=v5_worst_fold,
        )
        decision = _decision(strategy_version, checks, summaries["base"], reference_base=v5_summaries["base"])

        comparison = {
            "v5_base": asdict(v5_summaries["base"]),
            "v6_base": asdict(summaries["base"]),
            "base_sharpe_uplift": (
                summaries["base"].sharpe - v5_summaries["base"].sharpe
                if (not np.isnan(summaries["base"].sharpe) and not np.isnan(v5_summaries["base"].sharpe))
                else np.nan
            ),
            "stress_1p5x_sharpe_uplift": (
                summaries["stress_1p5x"].sharpe - v5_summaries["stress_1p5x"].sharpe
                if (not np.isnan(summaries["stress_1p5x"].sharpe) and not np.isnan(v5_summaries["stress_1p5x"].sharpe))
                else np.nan
            ),
            "overlay_high_q_share": base_overlay_high_q_share,
            "worst_fold_monthly_return_pct": {
                "v6": v6_worst_fold,
                "v5": v5_worst_fold,
            },
        }

    if strategy_version == "v6":
        overlay_table = results["base"].get("overlay_table", pd.DataFrame())
        idea_table = results["base"].get("idea_table", pd.DataFrame())

        overlay_path = output_dir / "overlay_table_v6.csv"
        idea_path = output_dir / "idea_table_v6.csv"
        if not overlay_table.empty:
            overlay_table.to_csv(overlay_path)
            generated["overlay_table"] = str(overlay_path)
        if not idea_table.empty:
            idea_table.to_csv(idea_path, index=False)
            generated["idea_table"] = str(idea_path)

    ablation_payload = {}
    if run_ablation and strategy_version == "v6":
        ablation_payload = run_ablation_suite()

    summary_json_path = output_dir / "summary.json"
    summary_json = {
        "strategy_version": strategy_version,
        "leverage_multiplier": base_diag.get("leverage_multiplier"),
        "scenarios": {name: asdict(summary) for name, summary in summaries.items()},
        "acceptance_checks": checks,
        "decision": decision,
        "comparison": comparison,
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
            "analysis": base_diag.get("analysis", {}),
        },
        "ablation": ablation_payload,
    }

    summary_json_path.write_text(json.dumps(summary_json, indent=2, default=_json_default), encoding="utf-8")
    generated["summary_json"] = str(summary_json_path)

    summary_md_path = output_dir / "summary.md"
    with summary_md_path.open("w", encoding="utf-8") as f:
        f.write(f"# Backtest Summary ({strategy_version})\n\n")
        f.write("## 1. Scenario Overview\n")
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

        if comparison:
            f.write("\n## 2. v6 vs v5 Comparison\n")
            f.write(f"- Base Sharpe uplift: {comparison.get('base_sharpe_uplift', float('nan')):.3f}\n")
            f.write(f"- Stress 1.5x Sharpe uplift: {comparison.get('stress_1p5x_sharpe_uplift', float('nan')):.3f}\n")
            f.write(f"- Overlay high-Q contribution share: {comparison.get('overlay_high_q_share', float('nan')):.3f}\n")

        f.write("\n## 3. Acceptance Checks\n")
        for check_name, passed in checks.items():
            f.write(f"- {check_name}: {'PASS' if passed else 'FAIL'}\n")

        f.write(f"\n**Decision: {decision}**\n")

    generated["summary_md"] = str(summary_md_path)

    if make_plots:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(12, 5))
        for scenario in [
            "base",
            "stress_1p5x",
            "stress_2p0x_delay",
            "stress_missing_data",
            "stress_liquidity",
            "stress_borrow_funding",
        ]:
            results[scenario]["equity"].plot(ax=ax, lw=1.0, label=scenario)
        ax.legend(loc="best")
        ax.set_title(f"{strategy_version} scenario equity curves")
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
    parser = argparse.ArgumentParser(description="Run backtest scenario matrix and generate report bundle.")
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument("--strategy-version", choices=["v5", "v6"], default=STRATEGY_VERSION)
    parser.add_argument("--skip-ablation", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir) if args.output_dir else default_output_dir()
    generated = write_report_files(
        output_dir=out_dir,
        make_plots=not args.no_plots,
        strategy_version=args.strategy_version,
        run_ablation=not args.skip_ablation,
    )

    print(f"Report generated in: {out_dir}")
    for key, value in generated.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
