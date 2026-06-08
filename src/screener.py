"""
全场基金扫描器 — 找出接近一年最低点的支付宝基金。
"""

import os
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict

# 绕过 Windows 系统代理（127.0.0.1:7897），否则 AKShare 无法访问东方财富
os.environ["NO_PROXY"] = "eastmoney.com,*.eastmoney.com"

import akshare as ak
import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ============================================================
# 第一步：获取候选基金列表（按近1年收益最差排序）
# ============================================================


def _get_ranked_funds(fund_type: str, top_n: int = 80) -> pd.DataFrame:
    """获取某类基金，按近1年收益从低到高排序，取最差的 top_n 只。"""
    try:
        df = ak.fund_open_fund_rank_em(symbol=fund_type)
        df["近1年"] = pd.to_numeric(df["近1年"], errors="coerce")
        df["单位净值"] = pd.to_numeric(df["单位净值"], errors="coerce")
        df = df.dropna(subset=["近1年", "单位净值"])
        # 排除净值异常的（可能是拆分/折算）
        df = df[df["单位净值"] > 0.01]
        df = df.sort_values("近1年")
        return df.head(top_n)
    except Exception:
        logger.exception("获取 %s 排名失败", fund_type)
        return pd.DataFrame()


# ============================================================
# 第二步：获取单只基金的1年历史净值
# ============================================================

_EM_API = "https://api.fund.eastmoney.com/f10/lsjz"
_EM_HEADERS = {"Referer": "https://fundf10.eastmoney.com/"}
# 绕过 Windows 系统代理（127.0.0.1:7897），直接访问东方财富
_NO_PROXY = {"http": None, "https": None}


def _fetch_fund_history(code: str, pages: int = 5) -> pd.DataFrame:
    """获取一只基金近半年的净值历史（并发分页，每页20条）。"""
    all_rows = []
    try:

        def _fetch_page(page: int):
            params = {"fundCode": code, "pageIndex": page, "pageSize": 20, "startDate": "", "endDate": ""}
            resp = requests.get(_EM_API, params=params, headers=_EM_HEADERS, timeout=15, proxies=_NO_PROXY)
            resp.raise_for_status()
            data = resp.json()
            if data.get("ErrCode") != 0:
                return []
            result = data.get("Data")
            if result is None:
                return []
            items = result.get("LSJZList", [])
            return [{"净值日期": it["FSRQ"], "单位净值": float(it["DWJZ"])} for it in items]

        # 小并发请求所有页
        with ThreadPoolExecutor(max_workers=3) as pool:
            page_results = list(pool.map(_fetch_page, range(1, pages + 1)))
        for rows in page_results:
            all_rows.extend(rows)

        if not all_rows:
            return pd.DataFrame()
        df = pd.DataFrame(all_rows)
        df["单位净值"] = pd.to_numeric(df["单位净值"], errors="coerce")
        return df.dropna()
    except Exception:
        return pd.DataFrame()


# ============================================================
# 第三步：计算距离1年低点的距离
# ============================================================


def _calc_distance(hist: pd.DataFrame) -> dict:
    """计算当前净值距离1年最低点的百分比。"""
    low_1y = hist["单位净值"].min()
    current = hist["单位净值"].iloc[0]  # 最新一天
    distance_pct = round((current - low_1y) / low_1y * 100, 2)
    low_date = hist.loc[hist["单位净值"].idxmin(), "净值日期"]
    current_date = hist["净值日期"].iloc[0]
    return {
        "current_nav": current,
        "low_1y": low_1y,
        "distance_pct": distance_pct,
        "low_date": str(low_date)[:10],
        "nav_date": str(current_date)[:10],
    }


# ============================================================
# 主流程：扫描
# ============================================================


def scan(
    max_workers: int = 8,
    candidate_per_type: int = 80,
    output_top: int = 40,
) -> List[Dict]:
    """
    扫描全市场支付宝基金，找出最接近1年低点的基金。

    返回按 distance_pct 升序排列的结果列表。
    """
    logger.info("=== 全场基金扫描开始 ===")

    # 1. 收集候选基金
    candidates = pd.DataFrame()
    for ftype in ["股票型", "指数型"]:
        df = _get_ranked_funds(ftype, top_n=candidate_per_type)
        if not df.empty:
            df["类型"] = ftype
            candidates = pd.concat([candidates, df], ignore_index=True)
            logger.info("%s: 入选 %d 只候选", ftype, len(df))

    if candidates.empty:
        logger.error("没有找到候选基金")
        return []

    # 去重
    candidates = candidates.drop_duplicates(subset=["基金代码"])
    logger.info("候选基金合计 %d 只，开始获取历史净值...", len(candidates))

    # 2. 并发获取历史净值
    results = []
    codes = candidates["基金代码"].tolist()
    names = dict(zip(candidates["基金代码"], candidates["基金简称"]))
    types = dict(zip(candidates["基金代码"], candidates["类型"]))

    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_fund_history, code): code for code in codes}
        for future in as_completed(futures):
            code = futures[future]
            done += 1
            try:
                hist = future.result()
                if hist.empty or len(hist) < 20:
                    continue
                info = _calc_distance(hist)
                # 只看确实接近低点的（距离 < 10%）
                if info["distance_pct"] <= 10:
                    results.append({
                        "code": code,
                        "name": names.get(code, ""),
                        "type": types.get(code, ""),
                        **info,
                    })
                if done % 20 == 0:
                    logger.info("进度: %d/%d, 已发现 %d 只接近低点", done, len(codes), len(results))
            except Exception:
                pass

    logger.info("扫描完成: %d 只基金距离1年低点在10%%以内", len(results))

    # 3. 按距离低点排序
    results.sort(key=lambda x: x["distance_pct"])
    return results[:output_top]


# ============================================================
# 输出格式化
# ============================================================


def format_report(results: List[Dict]) -> str:
    """把扫描结果格式化为可读报告。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "=" * 70,
        f"  全场基金低点扫描报告 — {now}",
        "  数据来源: 东方财富 | 仅展示距离1年最低点 10% 以内的基金",
        "=" * 70,
        "",
        f"{'排名':<4} {'代码':<8} {'名称':<20} {'当前净值':<10} {'1年最低':<10} {'距低点%':<8} {'低点日期':<10} {'类型':<6}",
        "-" * 70,
    ]

    for i, r in enumerate(results, 1):
        name = r["name"][:18] if len(r["name"]) > 18 else r["name"]
        lines.append(
            f"{i:<4} {r['code']:<8} {name:<20} "
            f"{r['current_nav']:<10.4f} {r['low_1y']:<10.4f} "
            f"{r['distance_pct']:<8.2f}% {r['low_date']:<10} {r['type']:<6}"
        )

    lines.extend([
        "",
        "-" * 70,
        "风险提示: 接近低点不代表一定会涨，基金投资有风险，决策需谨慎。",
        f"共发现 {len(results)} 只接近1年低点的基金。",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = scan()
    report = format_report(result)
    print(report)
