#!/usr/bin/env python3
"""Consolidated analysis: IQR, density plots, WAR vs salary, Pearson correlation.
Reads trade_war_by_year.json and war_value_by_year.json directly.
Requires: matplotlib, numpy, scipy
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy import stats

# Configure matplotlib for headless use
import os
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplcache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load_trade_interest(path: Path) -> list[dict]:
    """Load trade data and extract interest rate fields."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for r in data:
        if "," not in r.get("date", ""):
            continue
        yr = int(r["date"].split(",")[-1].strip())
        rows.append({
            "year": yr,
            "interest_rate": r.get("interest_rate"),
            "interest_rate_salary_adjusted": r.get("interest_rate_salary_adjusted"),
        })
    return rows


def load_war_value(path: Path) -> list[dict]:
    """Load war_value_by_year data."""
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_label(x: float) -> str:
    """Format axis label as -.3, -.2, 0, .1, .2, ..."""
    if x == 0:
        return "0"
    if 0 < x < 1:
        return f".{round(x * 10)}"
    if -1 < x < 0:
        return f"-.{round(abs(x) * 10)}"
    return str(x)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="IQR, density plots, WAR vs salary, Pearson correlation."
    )
    parser.add_argument(
        "--trade-war",
        type=Path,
        default=Path("trade_war_by_year.json"),
        help="Path to trade_war_by_year.json",
    )
    parser.add_argument(
        "--war-value",
        type=Path,
        default=Path("war_value_by_year.json"),
        help="Path to war_value_by_year.json",
    )
    args = parser.parse_args()

    # Load data
    trade_rows = []
    war_rows = []
    if args.trade_war.exists():
        trade_rows = load_trade_interest(args.trade_war)
    if args.war_value.exists():
        war_rows = load_war_value(args.war_value)

    # --- IQR of interest rates ---
    if trade_rows:
        ir = np.array([r["interest_rate"] for r in trade_rows if r["interest_rate"] is not None])
        ir_adj = np.array([
            r["interest_rate_salary_adjusted"]
            for r in trade_rows
            if r["interest_rate_salary_adjusted"] is not None
        ])
        print("--- Interest rate (raw WAR) ---")
        p25, p50, p75 = np.percentile(ir, [25, 50, 75])
        print(f"25th: {p25:.4f}  50th: {p50:.4f}  75th: {p75:.4f}  IQR: {p75 - p25:.4f}  N: {len(ir)}")
        print("--- Interest rate (salary-adjusted) ---")
        p25, p50, p75 = np.percentile(ir_adj, [25, 50, 75])
        print(f"25th: {p25:.4f}  50th: {p50:.4f}  75th: {p75:.4f}  IQR: {p75 - p25:.4f}  N: {len(ir_adj)}")

    # --- Pearson correlation: WAR vs Salary ---
    if war_rows and "war" in war_rows[0] and "salary" in war_rows[0]:
        wars = np.array([r["war"] for r in war_rows])
        salaries = np.array([r["salary"] for r in war_rows])
        valid = (salaries > 0) & np.isfinite(wars) & np.isfinite(salaries)
        if valid.sum() > 1:
            r = np.corrcoef(wars[valid], salaries[valid])[0, 1]
            print("--- Pearson correlation (WAR vs Salary) ---")
            print(f"r = {r:.4f}  N = {valid.sum()}")

    # --- Density: interest_rate (raw WAR) ---
    if trade_rows:
        ir = np.array([r["interest_rate"] for r in trade_rows if r["interest_rate"] is not None])
        if len(ir) > 1:
            kde = stats.gaussian_kde(ir)
            x_plot = np.linspace(-5, 5, 200)
            dens = kde(x_plot)
            fig, ax = plt.subplots(figsize=(800 / 120, 600 / 120), dpi=120)
            ax.fill_between(x_plot, dens, alpha=0.3, color=(0.2, 0.4, 0.8))
            ax.plot(x_plot, dens, color="darkblue", lw=2)
            ax.set_xlim(-5, 5)
            ax.set_xlabel("Interest rate")
            ax.set_ylabel("Density")
            ax.set_title("Density of trade interest rates (raw WAR)")
            ticks = np.arange(-5, 5.1, 0.5)
            ax.set_xticks(ticks)
            ax.set_xticklabels([fmt_label(x) for x in ticks])
            fig.tight_layout()
            fig.savefig("interest_density_raw.png")
            plt.close()
            print("Saved interest_density_raw.png")

    # --- Density: interest_rate_salary_adjusted ---
    if trade_rows:
        ir_adj = np.array([
            r["interest_rate_salary_adjusted"]
            for r in trade_rows
            if r["interest_rate_salary_adjusted"] is not None
        ])
        if len(ir_adj) > 1:
            kde = stats.gaussian_kde(ir_adj)
            x_plot = np.linspace(-5, 5, 200)
            dens = kde(x_plot)
            fig, ax = plt.subplots(figsize=(800 / 120, 600 / 120), dpi=120)
            ax.fill_between(x_plot, dens, alpha=0.3, color=(0.2, 0.4, 0.8))
            ax.plot(x_plot, dens, color="darkblue", lw=2)
            ax.set_xlim(-5, 5)
            ax.set_xlabel("Interest rate")
            ax.set_ylabel("Density")
            ax.set_title("Density of trade interest rates (salary-adjusted)")
            ticks = np.arange(-5, 5.1, 0.5)
            ax.set_xticks(ticks)
            ax.set_xticklabels([fmt_label(x) for x in ticks])
            fig.tight_layout()
            fig.savefig("interest_density_salary_adjusted.png")
            plt.close()
            print("Saved interest_density_salary_adjusted.png")

    # --- Density (full range, 20 ticks): interest_rate (raw WAR) ---
    if trade_rows:
        ir = np.array([r["interest_rate"] for r in trade_rows if r["interest_rate"] is not None])
        if len(ir) > 1:
            kde = stats.gaussian_kde(ir)
            x_min, x_max = ir.min(), ir.max()
            x_pad = max(0.1 * (x_max - x_min), 0.1)
            x_lo, x_hi = x_min - x_pad, x_max + x_pad
            x_plot = np.linspace(x_lo, x_hi, 500)
            dens = kde(x_plot)
            fig, ax = plt.subplots(figsize=(800 / 120, 600 / 120), dpi=120)
            ax.fill_between(x_plot, dens, alpha=0.3, color=(0.2, 0.4, 0.8))
            ax.plot(x_plot, dens, color="darkblue", lw=2)
            ax.set_xlim(x_lo, x_hi)
            ax.set_xlabel("Interest rate")
            ax.set_ylabel("Density")
            ax.set_title("Density of trade interest rates (raw WAR, full range)")
            ticks = np.linspace(x_lo, x_hi, 20)
            ax.set_xticks(ticks)
            ax.set_xticklabels([f"{x:.2g}" for x in ticks])
            fig.tight_layout()
            fig.savefig("interest_density_raw_full_range.png")
            plt.close()
            print("Saved interest_density_raw_full_range.png")

    # --- Density (full range, 20 ticks): interest_rate_salary_adjusted ---
    if trade_rows:
        ir_adj = np.array([
            r["interest_rate_salary_adjusted"]
            for r in trade_rows
            if r["interest_rate_salary_adjusted"] is not None
        ])
        if len(ir_adj) > 1:
            kde = stats.gaussian_kde(ir_adj)
            x_min, x_max = ir_adj.min(), ir_adj.max()
            x_pad = max(0.1 * (x_max - x_min), 0.1)
            x_lo, x_hi = x_min - x_pad, x_max + x_pad
            x_plot = np.linspace(x_lo, x_hi, 500)
            dens = kde(x_plot)
            fig, ax = plt.subplots(figsize=(800 / 120, 600 / 120), dpi=120)
            ax.fill_between(x_plot, dens, alpha=0.3, color=(0.2, 0.4, 0.8))
            ax.plot(x_plot, dens, color="darkblue", lw=2)
            ax.set_xlim(x_lo, x_hi)
            ax.set_xlabel("Interest rate")
            ax.set_ylabel("Density")
            ax.set_title("Density of trade interest rates (salary-adjusted, full range)")
            ticks = np.linspace(x_lo, x_hi, 20)
            ax.set_xticks(ticks)
            ax.set_xticklabels([f"{x:.2g}" for x in ticks])
            fig.tight_layout()
            fig.savefig("interest_density_salary_adjusted_full_range.png")
            plt.close()
            print("Saved interest_density_salary_adjusted_full_range.png")

    # --- WAR vs Salary: linear scale ---
    if war_rows and "war" in war_rows[0] and "salary" in war_rows[0]:
        wars = np.array([r["war"] for r in war_rows])
        salaries = np.array([r["salary"] for r in war_rows])
        fig, ax = plt.subplots(figsize=(800 / 120, 600 / 120), dpi=120)
        ax.scatter(salaries, wars, alpha=0.3, c=(0.2, 0.4, 0.8), s=16)
        valid = salaries > 0
        if valid.sum() > 1:
            coeffs = np.polyfit(salaries[valid], wars[valid], 1)
            xseq = np.linspace(salaries.min(), salaries.max(), 200)
            ax.plot(xseq, np.polyval(coeffs, xseq), "r-", lw=2)
        ax.set_xlabel("Salary ($)")
        ax.set_ylabel("WAR")
        ax.set_title("WAR vs Salary (linear)")
        fig.tight_layout()
        fig.savefig("war_vs_salary_linear.png")
        plt.close()
        print("Saved war_vs_salary_linear.png")

    # --- WAR vs Salary: log scale ---
    if war_rows and "war" in war_rows[0] and "salary" in war_rows[0]:
        wars = np.array([r["war"] for r in war_rows])
        salaries = np.array([r["salary"] for r in war_rows])
        valid = salaries > 0
        if valid.sum() > 1:
            fig, ax = plt.subplots(figsize=(800 / 120, 600 / 120), dpi=120)
            ax.scatter(salaries, wars, alpha=0.3, c=(0.2, 0.4, 0.8), s=16)
            ax.set_xscale("log")
            coeffs = np.polyfit(np.log(salaries[valid]), wars[valid], 1)
            xseq = np.logspace(
                np.log10(salaries[valid].min()),
                np.log10(salaries[valid].max()),
                200,
            )
            ax.plot(xseq, np.polyval(coeffs, np.log(xseq)), "r-", lw=2)
            ax.set_xlabel("Salary ($)")
            ax.set_ylabel("WAR")
            ax.set_title("WAR vs Salary (log scale)")
            fig.tight_layout()
            fig.savefig("war_vs_salary_log.png")
            plt.close()
            print("Saved war_vs_salary_log.png")


if __name__ == "__main__":
    main()
