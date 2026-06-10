"""
技术指标计算 — 基于基金历史净值数据。
"""

from datetime import date, datetime
from typing import List, Dict, Optional
import pandas as pd


def compute_indicators(hist_df: pd.DataFrame, settings: Optional[Dict] = None) -> Dict:
    """从历史净值 DataFrame 计算各项指标。settings 可为低点阈值参数。"""
    s = settings or {}
    lookback_days = int(s.get("lowPointLookbackDays", 30))
    near_low_pct = float(s.get("nearLowPointThresholdPercent", 3))

    # 交易日换算：约 22 个交易日/月
    trading_days_30 = max(5, round(lookback_days * 22 / 30))
    trading_days_90 = trading_days_30 * 3
    if hist_df.empty or len(hist_df) < 5:
        return _empty_indicators()

    nav_col = "单位净值"
    navs = hist_df[nav_col].dropna()
    if len(navs) < 5:
        return _empty_indicators()

    current = float(navs.iloc[-1] if len(navs) > 0 else 0)

    # 近期涨跌幅
    def _pct_change(n: int) -> Optional[float]:
        if len(navs) <= n:
            return None
        old = float(navs.iloc[-(n + 1)])
        return round((current - old) / old * 100, 2) if old else None

    change_7d = _pct_change(5)       # ~5个交易日
    change_30d = _pct_change(trading_days_30)
    change_90d = _pct_change(trading_days_90)

    # 近期最高/最低
    has_30d = len(navs) >= trading_days_30
    has_90d = len(navs) >= trading_days_90
    high_30d = float(navs.iloc[-trading_days_30:].max()) if has_30d else current
    low_30d = float(navs.iloc[-trading_days_30:].min()) if has_30d else current
    high_90d = float(navs.iloc[-trading_days_90:].max()) if has_90d else current
    low_90d = float(navs.iloc[-trading_days_90:].min()) if has_90d else current

    # 是否处于阶段低位（当前价格在低点阈值范围内）
    near_month_low = (current - low_30d) / low_30d * 100 <= near_low_pct if low_30d > 0 and has_30d else False
    near_quarter_low = (current - low_90d) / low_90d * 100 <= near_low_pct if low_90d > 0 and has_90d else False

    # 距离高低点的距离
    dist_to_month_high = round((high_30d - current) / current * 100, 2) if current > 0 else None
    dist_to_month_low = round((current - low_30d) / low_30d * 100, 2) if low_30d > 0 else None

    return {
        "current_nav": current,
        "change_7d": change_7d,
        "change_30d": change_30d,
        "change_90d": change_90d,
        "high_30d": high_30d,
        "low_30d": low_30d,
        "high_90d": high_90d,
        "low_90d": low_90d,
        "near_month_low": near_month_low,
        "near_quarter_low": near_quarter_low,
        "dist_to_month_high": dist_to_month_high,
        "dist_to_month_low": dist_to_month_low,
    }


def _empty_indicators() -> Dict:
    return {
        "current_nav": 0, "change_7d": None, "change_30d": None, "change_90d": None,
        "high_30d": 0, "low_30d": 0, "high_90d": 0, "low_90d": 0,
        "near_month_low": False, "near_quarter_low": False,
        "dist_to_month_high": None, "dist_to_month_low": None,
    }
