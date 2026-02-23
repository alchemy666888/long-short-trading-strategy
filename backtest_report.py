import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict

_MPL_CONFIG_DIR = Path(os.getenv("MPLCONFIGDIR", "/tmp/codex-mplconfig"))
_MPL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPL_CONFIG_DIR.resolve()))

import numpy as np
import pandas as pd

from backtest_vectorized import run_backtest


BARS_PER_DAY = 78  # 6.5 hours * 12 bars/hour
TRADING_DAYS_PER_YEAR = 252
BARS_PER_YEAR = BARS_PER_DAY * TRADING_DAYS_PER_YEAR


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
    if equity.empty:
        raise ValueError("Equity series is empty; cannot compute report.")

    bar_returns = equity.pct_change().dropna()
    total_return = (equity.iloc[-1] / equity.iloc[0]) - 1.0
    ann_return = _annualized_return(total_return, len(bar_returns))
    ann_vol = bar_returns.std() * np.sqrt(BARS_PER_YEAR) if len(bar_returns) > 1 else np.nan
    sharpe = (ann_return / ann_vol) if ann_vol and not np.isnan(ann_vol) else np.nan

    running_max = equity.cummax()
    drawdown = (equity / running_max) - 1.0
    max_dd = drawdown.min()
    max_dd_at = drawdown.idxmin()

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
        max_drawdown_pct=float(max_dd * 100.0) if not np.isnan(max_dd) else np.nan,
        max_drawdown_at=str(max_dd_at),
    )


def _format_number(x: float, digits: int = 2) -> str:
    if x is None or np.isnan(x):
        return "NaN"
    return f"{x:.{digits}f}"


def write_report_files(equity: pd.Series, output_dir: Path, make_plots: bool) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = compute_summary(equity)
    bar_returns = equity.pct_change()
    daily_equity = equity.resample("1D").last().dropna()
    daily_returns = daily_equity.pct_change().dropna()
    monthly_returns = daily_equity.resample("ME").last().pct_change().dropna()

    equity.to_frame("equity").to_csv(output_dir / "equity.csv")
    bar_returns.to_frame("bar_returns").to_csv(output_dir / "bar_returns.csv")
    daily_returns.to_frame("daily_returns").to_csv(output_dir / "daily_returns.csv")
    monthly_returns.to_frame("monthly_returns").to_csv(output_dir / "monthly_returns.csv")

    summary_json_path = output_dir / "summary.json"
    with summary_json_path.open("w", encoding="utf-8") as f:
        json.dump(asdict(summary), f, indent=2)

    summary_md_path = output_dir / "summary.md"
    with summary_md_path.open("w", encoding="utf-8") as f:
        f.write("# Backtest Summary\n\n")
        f.write("| Metric | Value |\n")
        f.write("| --- | --- |\n")
        f.write(f"| Start | {summary.start} |\n")
        f.write(f"| End | {summary.end} |\n")
        f.write(f"| Bars | {summary.bars} |\n")
        f.write(f"| Start Equity | {_format_number(summary.start_equity, 2)} |\n")
        f.write(f"| End Equity | {_format_number(summary.end_equity, 2)} |\n")
        f.write(f"| Total Return (%) | {_format_number(summary.total_return_pct, 2)} |\n")
        f.write(f"| Annualized Return (%) | {_format_number(summary.annualized_return_pct, 2)} |\n")
        f.write(f"| Annualized Volatility (%) | {_format_number(summary.annualized_volatility_pct, 2)} |\n")
        f.write(f"| Sharpe | {_format_number(summary.sharpe, 3)} |\n")
        f.write(f"| Max Drawdown (%) | {_format_number(summary.max_drawdown_pct, 2)} |\n")
        f.write(f"| Max Drawdown At | {summary.max_drawdown_at} |\n")

    generated = {
        "summary_json": str(summary_json_path),
        "summary_md": str(summary_md_path),
        "equity_csv": str(output_dir / "equity.csv"),
        "bar_returns_csv": str(output_dir / "bar_returns.csv"),
        "daily_returns_csv": str(output_dir / "daily_returns.csv"),
        "monthly_returns_csv": str(output_dir / "monthly_returns.csv"),
    }

    if make_plots:
        import matplotlib.pyplot as plt

        running_max = equity.cummax()
        drawdown = (equity / running_max) - 1.0

        plt.style.use("seaborn-v0_8")

        fig, ax = plt.subplots(figsize=(12, 5))
        equity.plot(ax=ax, lw=1.2, color="#0B6E4F")
        ax.set_title("Equity Curve")
        ax.set_ylabel("Portfolio Value")
        ax.set_xlabel("Time")
        fig.tight_layout()
        equity_png = output_dir / "equity_curve.png"
        fig.savefig(equity_png, dpi=160)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(12, 5))
        drawdown.plot(ax=ax, lw=1.2, color="#B22222")
        ax.set_title("Drawdown")
        ax.set_ylabel("Drawdown")
        ax.set_xlabel("Time")
        fig.tight_layout()
        drawdown_png = output_dir / "drawdown.png"
        fig.savefig(drawdown_png, dpi=160)
        plt.close(fig)

        generated["equity_png"] = str(equity_png)
        generated["drawdown_png"] = str(drawdown_png)

    return generated


def default_output_dir() -> Path:
    ts = pd.Timestamp.now(tz="US/Eastern").strftime("%Y%m%d_%H%M%S")
    return Path("data") / "reports" / ts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run backtest and generate report files.")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to store generated report files. Default: data/reports/<timestamp>",
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Skip generating PNG plots.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir) if args.output_dir else default_output_dir()

    equity_df = run_backtest()
    equity = equity_df["equity"]
    generated = write_report_files(
        equity=equity,
        output_dir=out_dir,
        make_plots=not args.no_plots,
    )

    print(f"Report generated in: {out_dir}")
    for key, value in generated.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
