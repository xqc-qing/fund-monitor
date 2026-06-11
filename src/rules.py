"""
规则引擎 — 判断基金价格是否触发提醒条件。
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List

from .fetcher_watch import FundQuote, fetch_history

logger = logging.getLogger(__name__)


@dataclass
class AlertResult:
    triggered: bool = False
    reasons: List[str] = field(default_factory=list)


# ============================================================
# 单条规则
# ============================================================


def _rule_below_target(quote: FundQuote, alert_below: Optional[float]) -> Optional[str]:
    """规则1：当前价格/净值 <= 一年低点。"""
    if alert_below is None:
        return None
    if quote.current_price <= alert_below:
        pct = (quote.current_price - alert_below) / alert_below * 100
        return f"低于一年低点 {alert_below:.4f}（当前 {quote.current_price:.4f}，差距 {pct:+.2f}%）"
    return None


def _rule_near_1y_low(
    quote: FundQuote,
    fund_type: str,
    low_1y_ratio: Optional[float],
) -> Optional[str]:
    """规则2：当前价格 <= 最近一年最低价 × ratio。"""
    if low_1y_ratio is None:
        return None

    hist = fetch_history(quote.code, fund_type, days=365)
    if hist.empty:
        logger.warning("无法获取 %s 历史数据，跳过1年低点规则", quote.code)
        return None

    if fund_type == "etf":
        col = "收盘"
    else:
        col = "单位净值"

    year_low = float(hist[col].min())
    threshold = year_low * low_1y_ratio

    if quote.current_price <= threshold:
        pct = (quote.current_price - year_low) / year_low * 100
        return (
            f"接近1年低点（1年最低 {year_low:.4f}，"
            f"×{low_1y_ratio:.2f} = {threshold:.4f}，"
            f"当前 {quote.current_price:.4f}，距低点 {pct:+.2f}%）"
        )
    return None


def _rule_daily_drop(quote: FundQuote, daily_drop_pct: Optional[float]) -> Optional[str]:
    """规则3：当日跌幅 <= 指定百分比（如 -3%）。"""
    if daily_drop_pct is None:
        return None
    if daily_drop_pct >= 0:
        logger.warning("daily_drop_pct 应为负数（如 -3），当前值 %s 不会触发", daily_drop_pct)
    if quote.prev_price is None:
        logger.info("%s 无前一日价格，跳过日跌幅规则", quote.code)
        return None
    if quote.prev_price == 0:
        return None

    change_pct = (quote.current_price - quote.prev_price) / quote.prev_price * 100
    if change_pct <= daily_drop_pct:
        return f"当日跌幅 {change_pct:+.2f}% <= {daily_drop_pct:+.2f}%"
    return None


# ============================================================
# 汇总判断
# ============================================================


def evaluate(
    quote: FundQuote,
    *,
    alert_below: Optional[float] = None,
    low_1y_ratio: Optional[float] = None,
    daily_drop_pct: Optional[float] = None,
) -> AlertResult:
    """对一条 FundQuote 依次执行所有已配置规则，返回触发原因列表。"""
    reasons: List[str] = []

    r = _rule_below_target(quote, alert_below)
    if r:
        reasons.append(r)

    r = _rule_near_1y_low(quote, quote.fund_type, low_1y_ratio)
    if r:
        reasons.append(r)

    r = _rule_daily_drop(quote, daily_drop_pct)
    if r:
        reasons.append(r)

    return AlertResult(triggered=len(reasons) > 0, reasons=reasons)
