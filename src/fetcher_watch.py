"""
数据获取模块 — 基于 AKShare + 东方财富 REST API 获取基金净值与价格。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)


def _get_pd():
    import pandas as pd
    return pd


def _get_requests():
    import requests
    return requests


def _get_ak():
    """惰性导入 akshare，用于 ETF 行情获取。"""
    import akshare as ak
    return ak


# ============================================================
# 数据模型
# ============================================================


@dataclass
class FundQuote:
    code: str
    name: str
    fund_type: str  # "etf" | "open_fund"
    current_price: float
    price_date: str  # YYYY-MM-DD 或带时间的字符串
    prev_price: Optional[float] = None  # 前一日价格/净值，用于计算日涨跌


# ============================================================
# 场外开放式基金（使用东方财富 REST API，避免 py_mini_racer JS 引擎不稳定）
# ============================================================

_EM_FUND_API = "https://api.fund.eastmoney.com/f10/lsjz"
_EM_HEADERS = {"Referer": "https://fundf10.eastmoney.com/"}
_NO_PROXY = {"http": None, "https": None}


def _fetch_open_fund_nav(code: str) -> Optional[FundQuote]:
    """获取场外基金最新单位净值（东方财富 REST API）。"""
    try:
        req = _get_requests()
        params = {"fundCode": code, "pageIndex": 1, "pageSize": 2, "startDate": "", "endDate": ""}
        resp = req.get(_EM_FUND_API, params=params, headers=_EM_HEADERS, timeout=15, proxies=_NO_PROXY)
        resp.raise_for_status()
        data = resp.json()
        if data.get("ErrCode") != 0:
            logger.warning("场外基金 %s API 返回错误: %s", code, data.get("ErrMsg"))
            return None
        result = data.get("Data")
        if result is None:
            logger.warning("场外基金 %s 返回数据为空", code)
            return None
        items = result.get("LSJZList", [])
        if not items:
            logger.warning("场外基金 %s 返回空数据", code)
            return None

        latest = items[0]
        nav = float(latest["DWJZ"])
        nav_date = latest["FSRQ"]

        prev_nav = None
        if len(items) >= 2:
            prev_nav = float(items[1]["DWJZ"])

        return FundQuote(
            code=code,
            name="",
            fund_type="open_fund",
            current_price=nav,
            price_date=nav_date,
            prev_price=prev_nav,
        )
    except Exception:
        logger.exception("获取场外基金 %s 净值失败", code)
        return None


def _fetch_open_fund_history(code: str, days: int = 365) -> "pd.DataFrame":
    """获取场外基金历史净值（东方财富 REST API，分页获取，每页20条）。"""
    try:
        req = _get_requests()
        pd = _get_pd()
        pages_needed = max(1, days // 20 + 1)
        all_rows = []
        for page in range(1, pages_needed + 1):
            params = {"fundCode": code, "pageIndex": page, "pageSize": 20, "startDate": "", "endDate": ""}
            resp = req.get(_EM_FUND_API, params=params, headers=_EM_HEADERS, timeout=20, proxies=_NO_PROXY)
            resp.raise_for_status()
            data = resp.json()
            if data.get("ErrCode") != 0:
                break
            result = data.get("Data")
            if result is None:
                break
            items = result.get("LSJZList", [])
            if not items:
                break
            for it in items:
                all_rows.append({"净值日期": it["FSRQ"], "单位净值": float(it["DWJZ"])})
        if not all_rows:
            return pd.DataFrame()
        df = pd.DataFrame(all_rows)
        df["净值日期"] = pd.to_datetime(df["净值日期"])
        df["单位净值"] = pd.to_numeric(df["单位净值"], errors="coerce")
        return df.sort_values("净值日期")
    except Exception:
        logger.exception("获取场外基金 %s 历史净值失败", code)
        return _get_pd().DataFrame()


# ============================================================
# 场内 ETF
# ============================================================


def _fetch_etf_price(code: str) -> Optional[FundQuote]:
    """获取 ETF 最新交易价格，基于 AKShare fund_etf_spot_em。"""
    try:
        df = _get_ak().fund_etf_spot_em()
        if df is None or df.empty:
            logger.warning("ETF 行情数据为空")
            return None

        row = df[df["代码"] == code]
        if row.empty:
            logger.warning("未找到 ETF 代码 %s", code)
            return None

        row = row.iloc[0]
        price = float(row["最新价"])
        price_date = str(row.get("时间", "")) or str(date.today())

        prev_close = None
        if "昨收" in row.index:
            try:
                prev_close = float(row["昨收"])
            except (ValueError, TypeError):
                pass

        return FundQuote(
            code=code,
            name=str(row.get("名称", "")),
            fund_type="etf",
            current_price=price,
            price_date=price_date,
            prev_price=prev_close,
        )
    except Exception:
        logger.exception("获取 ETF %s 价格失败", code)
        return None


def _fetch_etf_history(code: str, days: int = 365) -> "pd.DataFrame":
    """获取 ETF 历史日线数据。"""
    try:
        end = date.today().strftime("%Y%m%d")
        start = (date.today() - timedelta(days=days + 10)).strftime("%Y%m%d")
        df = _get_ak().fund_etf_hist_em(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
        if df is None or df.empty:
            return _get_pd().DataFrame()
        df["日期"] = _get_pd().to_datetime(df["日期"])
        df["收盘"] = _get_pd().to_numeric(df["收盘"], errors="coerce")
        return df.sort_values("日期")
    except Exception:
        logger.exception("获取 ETF %s 历史行情失败", code)
        return _get_pd().DataFrame()


# ============================================================
# 统一入口
# ============================================================


def fetch_quote(code: str, fund_type: str) -> Optional[FundQuote]:
    """根据基金类型获取最新报价。"""
    if fund_type == "etf":
        return _fetch_etf_price(code)
    elif fund_type == "open_fund":
        return _fetch_open_fund_nav(code)
    else:
        logger.error("未知基金类型: %s", fund_type)
        return None


def fetch_history(code: str, fund_type: str, days: int = 365) -> "pd.DataFrame":
    """根据基金类型获取历史数据。"""
    if fund_type == "etf":
        return _fetch_etf_history(code, days)
    elif fund_type == "open_fund":
        return _fetch_open_fund_history(code, days)
    else:
        logger.error("未知基金类型: %s", fund_type)
        return _get_pd().DataFrame()
