from typing import Any

import numpy as np
import pandas as pd

from etf_lab.backtest.engine import BacktestResult


def metrics(result: BacktestResult, benchmark: BacktestResult | None = None) -> dict[str, Any]:
    curve = result.curve.set_index("timestamp")
    equity = curve.equity
    daily = equity.resample("1D").last().dropna()
    returns = daily.pct_change().dropna()
    years = (equity.index[-1] - equity.index[0]).total_seconds() / (365.25 * 86400)
    total = float(equity.iloc[-1] / equity.iloc[0] - 1)
    dd = equity / equity.cummax() - 1
    vol = float(returns.std(ddof=1) * np.sqrt(252)) if len(returns) >= 2 else None
    sharpe = (
        float(returns.mean() / returns.std() * np.sqrt(252))
        if (len(returns) >= 30 and returns.std() > 0)
        else None
    )
    downside = (
        float(np.sqrt(np.mean(np.minimum(returns.to_numpy(), 0) ** 2))) if len(returns) else 0
    )
    sortino = (
        float(returns.mean() / downside * np.sqrt(252)) if len(returns) >= 30 and downside else None
    )
    cagr = (1 + total) ** (1 / years) - 1 if years >= 1 and total > -1 else None
    pnl = result.trades.pnl if not result.trades.empty else pd.Series(dtype=float)
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    durations, start = [], equity.index[0]
    for ts, drawdown in dd.items():
        if drawdown == 0:
            start = ts
        durations.append((ts - start).total_seconds())
    costs = {
        k: float(result.fills[k].sum()) if not result.fills.empty else 0.0
        for k in ["commission", "fx_cost", "spread_cost", "slippage_cost"]
    }
    avgwin, avgloss = (
        float(wins.mean()) if len(wins) else None,
        float(losses.mean()) if len(losses) else None,
    )
    output: dict[str, Any] = {
        "total_return": total,
        "annualized_return": cagr,
        "CAGR": cagr,
        "annualized_volatility": vol,
        "Sharpe": sharpe,
        "Sortino": sortino,
        "Calmar": cagr / abs(float(dd.min())) if cagr is not None and dd.min() < 0 else None,
        "max_drawdown": float(dd.min()),
        "average_drawdown": float(dd.mean()),
        "drawdown_duration_seconds": max(durations),
        "number_of_trades": len(pnl),
        "trades_per_year": len(pnl) / years if years >= 1 else None,
        "win_rate": float((pnl > 0).mean()) if len(pnl) else None,
        "loss_rate": float((pnl < 0).mean()) if len(pnl) else None,
        "profit_factor": float(wins.sum() / -losses.sum()) if len(losses) else None,
        "expectancy": float(pnl.mean()) if len(pnl) else None,
        "average_win": avgwin,
        "average_loss": avgloss,
        "payoff_ratio": avgwin / -avgloss if avgwin is not None and avgloss else None,
        "average_holding_period_seconds": float(result.trades.holding_seconds.mean())
        if len(pnl)
        else None,
        "turnover": float(
            (result.fills.quantity * result.fills.price * result.fills.fx_rate).sum()
            / equity.mean()
        )
        if not result.fills.empty
        else 0,
        "exposure": float((curve.exposure / equity).mean()),
        "time_in_market": float((curve.exposure > 0).mean()),
        "cash_usage": float((1 - curve.cash / equity).mean()),
        "fees_paid": costs["commission"],
        **costs,
        "total_costs": sum(costs.values()),
        "open_positions": len(result.portfolio.positions),
        "warnings": [
            "Synthetic/offline examples do not establish edge.",
            "Trades count exit fills; partial liquidation can split a round trip.",
        ],
    }
    if len(returns) < 30:
        output["warnings"].append("Fewer than 30 daily returns: Sharpe/Sortino suppressed.")
    if years < 1:
        output["warnings"].append("Less than one year: CAGR/annualized return suppressed.")
    if benchmark is not None:
        b = (
            benchmark.curve.set_index("timestamp")
            .equity.resample("1D")
            .last()
            .dropna()
            .pct_change()
        )
        aligned = pd.concat([returns.rename("strategy"), b.rename("benchmark")], axis=1).dropna()
        output["benchmark_return"] = float(
            benchmark.curve.equity.iloc[-1] / benchmark.curve.equity.iloc[0] - 1
        )
        if len(aligned) >= 30 and aligned.benchmark.var() > 0 and aligned.strategy.std() > 0:
            beta = float(aligned.cov().to_numpy(dtype=float)[0, 1] / aligned.benchmark.var())
            output.update(
                beta=beta,
                alpha_approximation=float(
                    (aligned.strategy.mean() - beta * aligned.benchmark.mean()) * 252
                ),
                benchmark_correlation=float(aligned.corr().to_numpy(dtype=float)[0, 1]),
            )
        else:
            output.update(beta=None, alpha_approximation=None, benchmark_correlation=None)
    return output
