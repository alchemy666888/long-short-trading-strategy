import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

from backtest_vectorized import run_backtest

BARS_PER_YEAR = int(252 * 78)


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
    bar_returns = equity.pct_change().dropna()
    total_return = (equity.iloc[-1] / equity.iloc[0]) - 1.0
    ann_return = _annualized_return(total_return, len(bar_returns))
    ann_vol = bar_returns.std() * np.sqrt(BARS_PER_YEAR) if len(bar_returns) > 1 else np.nan
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


def _decision(base: BacktestSummary, stress_15: BacktestSummary, stress_20: BacktestSummary) -> str:
    if base.total_return_pct > 0 and stress_15.total_return_pct > 0 and stress_20.total_return_pct > 0:
        return "deploy_candidate"
    if base.total_return_pct > 0 and (stress_15.total_return_pct > 0 or stress_20.total_return_pct > 0):
        return "refine"
    return "abandon"


def write_report_files(output_dir: Path, make_plots: bool) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    base = run_backtest()["equity"]
    stress_15 = run_backtest(cost_multiplier=1.5)["equity"]
    stress_20 = run_backtest(cost_multiplier=2.0, one_bar_delay=True)["equity"]

    s_base = compute_summary(base)
    s_15 = compute_summary(stress_15)
    s_20 = compute_summary(stress_20)
    decision = _decision(s_base, s_15, s_20)

    base.to_frame("equity").to_csv(output_dir / "equity.csv")
    stress_15.to_frame("equity").to_csv(output_dir / "equity_stress_1p5x.csv")
    stress_20.to_frame("equity").to_csv(output_dir / "equity_stress_2p0x_delay.csv")

    summary_json_path = output_dir / "summary.json"
    with summary_json_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "hypothesis": "Vol-normalized multi-horizon momentum with correlation-aware pairing can survive friction stress.",
                "base": asdict(s_base),
                "stress_1p5x": asdict(s_15),
                "stress_2p0x_delay": asdict(s_20),
                "decision": decision,
            },
            f,
            indent=2,
        )

    summary_md_path = output_dir / "summary.md"
    with summary_md_path.open("w", encoding="utf-8") as f:
        f.write("# Backtest Summary (v3)\n\n")
        f.write("## 1. Hypothesis\n")
        f.write("Vol-normalized multi-horizon momentum with correlation-aware pairing can survive conservative friction stress.\n\n")
        f.write("## 2. Rules snapshot\n")
        f.write("- 20/60/120 log-return z-score momentum blend with EWMA vol normalization.\n")
        f.write("- Quartile long/short candidates, correlation-aware pairing.\n")
        f.write("- ATR(20) risk: stop 1.25x, target 2.25x, rebalance 10:00/12:00/14:00 ET.\n")
        f.write("- Stress tests include 1.5x cost and 2.0x + one-bar delay.\n\n")
        f.write("## 3. Headline metrics\n\n")
        for name, s in (("Base", s_base), ("Stress 1.5x", s_15), ("Stress 2.0x + delay", s_20)):
            f.write(f"### {name}\n")
            f.write(f"- Total return: {s.total_return_pct:.2f}%\n")
            f.write(f"- Sharpe: {s.sharpe:.3f}\n")
            f.write(f"- Max drawdown: {s.max_drawdown_pct:.2f}%\n")
        f.write("\n## 4. Decision\n")
        f.write(f"**{decision}**\n")

    generated = {"summary_json": str(summary_json_path), "summary_md": str(summary_md_path), "equity_csv": str(output_dir / "equity.csv")}

    if make_plots:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(12, 5))
        base.plot(ax=ax, lw=1.1, label="Base")
        stress_15.plot(ax=ax, lw=1.0, label="Stress 1.5x")
        stress_20.plot(ax=ax, lw=1.0, label="Stress 2.0x + delay")
        ax.legend()
        ax.set_title("Equity Curves")
        fig.tight_layout()
        eq_png = output_dir / "equity_curve.png"
        fig.savefig(eq_png, dpi=150)
        plt.close(fig)
        generated["equity_png"] = str(eq_png)

    return generated


def default_output_dir() -> Path:
    ts = pd.Timestamp.now(tz="US/Eastern").strftime("%Y%m%d_%H%M%S")
    return Path("data") / "reports" / ts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run backtest and generate report files.")
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
