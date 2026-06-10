"""
Agent 智能分析器 — 规则引擎 + 技术指标 → 结构化分析。
当前为 mock/规则模式，后续可接入 LLM 增强自然语言解释。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .fetcher_watch import fetch_history
from .fund_indicators import compute_indicators
from .agent_rules import evaluate_rules


@dataclass
class AnalysisRequest:
    code: str
    name: str = ""
    fund_type: str = "open_fund"
    current_price: float = 0.0
    cost_nav: Optional[float] = None     # 持仓成本
    buy_date: Optional[str] = None        # 买入日期 YYYY-MM-DD


def analyze(req: AnalysisRequest) -> Dict:
    """执行完整分析，返回结构化 JSON。"""

    # 1. 获取历史数据 + 计算技术指标
    hist = fetch_history(req.code, req.fund_type) if req.fund_type else None
    indicators = compute_indicators(hist) if hist is not None else {}

    if req.current_price > 0 and not indicators.get("current_nav"):
        indicators["current_nav"] = req.current_price

    # 2. 执行交易纪律规则
    result = evaluate_rules(
        current_nav=req.current_price or indicators.get("current_nav", 0),
        cost_nav=req.cost_nav,
        buy_date=req.buy_date,
        indicators=indicators,
    )

    # 3. 附加元信息
    result["fund_code"] = req.code
    result["fund_name"] = req.name
    result["model"] = "rule_engine"
    result["disclaimer"] = "仅做分析参考，不构成投资建议。Agent 不会直接给出买卖指令。"

    return result
