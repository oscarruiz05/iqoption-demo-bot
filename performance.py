"""Métricas y puerta estadística para historiales de opciones binarias."""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class PerformanceReport:
    trades: int
    wins: int
    losses: int
    ties: int
    pnl: float
    win_rate: float
    average_win: float
    average_loss: float
    break_even_win_rate: float
    expectancy: float
    profit_factor: float
    max_drawdown: float
    wilson_low: float
    validated: bool
    reasons: tuple[str, ...]


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if trials <= 0:
        return 0.0, 1.0
    probability = successes / trials
    denominator = 1 + z * z / trials
    center = (probability + z * z / (2 * trials)) / denominator
    margin = z * math.sqrt(
        probability * (1 - probability) / trials + z * z / (4 * trials * trials)
    ) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def analyze_pnls(
    pnls: Iterable[float],
    *,
    minimum_trades: int = 200,
    minimum_edge: float = 0.02,
) -> PerformanceReport:
    values = [float(value) for value in pnls]
    wins = [value for value in values if value > 0]
    losses = [-value for value in values if value < 0]
    ties = len(values) - len(wins) - len(losses)
    decisive = len(wins) + len(losses)
    average_win = sum(wins) / len(wins) if wins else 0.0
    average_loss = sum(losses) / len(losses) if losses else 0.0
    win_rate = len(wins) / decisive if decisive else 0.0
    break_even = (
        average_loss / (average_win + average_loss)
        if average_win > 0 and average_loss > 0
        else 1.0
    )
    wilson_low, _ = wilson_interval(len(wins), decisive)

    equity = peak = max_drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    gross_profit = sum(wins)
    gross_loss = sum(losses)
    profit_factor = gross_profit / gross_loss if gross_loss else math.inf if gross_profit else 0.0
    reasons = []
    if len(values) < minimum_trades:
        reasons.append(f"muestra insuficiente: {len(values)}/{minimum_trades} operaciones")
    if sum(values) <= 0:
        reasons.append("PnL acumulado no positivo")
    if wilson_low <= break_even + minimum_edge:
        reasons.append(
            "el límite inferior de acierto no supera el punto de equilibrio "
            f"más el margen ({wilson_low:.2%} <= {break_even + minimum_edge:.2%})"
        )

    return PerformanceReport(
        trades=len(values), wins=len(wins), losses=len(losses), ties=ties,
        pnl=sum(values), win_rate=win_rate, average_win=average_win,
        average_loss=average_loss, break_even_win_rate=break_even,
        expectancy=sum(values) / len(values) if values else 0.0,
        profit_factor=profit_factor, max_drawdown=max_drawdown,
        wilson_low=wilson_low, validated=not reasons, reasons=tuple(reasons),
    )


def read_trade_pnls(
    path: Path,
    *,
    strategy: str | None = None,
    strategy_version: str | None = None,
) -> list[float]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as file:
        rows = csv.DictReader(file)
        return [
            float(row["pnl"])
            for row in rows
            if row.get("pnl", "") != ""
            and (strategy is None or row.get("strategy") == strategy)
            and (strategy_version is None or row.get("strategy_version") == strategy_version)
        ]


def format_report(report: PerformanceReport) -> str:
    factor = "infinito" if math.isinf(report.profit_factor) else f"{report.profit_factor:.2f}"
    verdict = "VALIDADA" if report.validated else "NO VALIDADA"
    lines = [
        f"Estado: {verdict}",
        f"Operaciones: {report.trades} ({report.wins} ganadas, {report.losses} perdidas, {report.ties} empates)",
        f"PnL: {report.pnl:.2f} | esperanza/operación: {report.expectancy:.4f}",
        f"Acierto: {report.win_rate:.2%} | equilibrio: {report.break_even_win_rate:.2%}",
        f"Límite inferior 95% del acierto: {report.wilson_low:.2%}",
        f"Profit factor: {factor} | drawdown máximo: {report.max_drawdown:.2f}",
    ]
    lines.extend(f"- {reason}" for reason in report.reasons)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evalúa si el historial demuestra una ventaja estadística.")
    parser.add_argument("path", nargs="?", default="trades.csv")
    parser.add_argument("--strategy", choices=("trend", "support_channel"))
    parser.add_argument("--version", help="Versión exacta de estrategia, por ejemplo trend-v2")
    parser.add_argument("--minimum-trades", type=int, default=200)
    parser.add_argument("--minimum-edge", type=float, default=0.02)
    args = parser.parse_args()
    report = analyze_pnls(
        read_trade_pnls(
            Path(args.path), strategy=args.strategy, strategy_version=args.version
        ),
        minimum_trades=args.minimum_trades,
        minimum_edge=args.minimum_edge,
    )
    print(format_report(report))


if __name__ == "__main__":
    main()
