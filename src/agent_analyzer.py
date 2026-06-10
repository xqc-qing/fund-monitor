"""
Agent 智能分析器 — LLM 主导分析 + 规则引擎兜底。
配置 LLM_API_KEY 后由大模型主做分析；
不配置或调用失败时自动退回规则引擎。
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

# 加载 .env 文件
try:
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        with open(_env_path, encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip())
except Exception:
    pass

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.openai.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")

from .fetcher_watch import fetch_history
from .fund_indicators import compute_indicators
from .agent_rules import evaluate_rules

# ============================================================
# 交易纪律（注入 LLM prompt）
# ============================================================

TRADING_DISCIPLINE = """
用户交易纪律：
1. 偏好在阶段低点一次性买入，主要买 C 类基金
2. 目标止盈：相对买入成本上涨 15%
3. 买入后跌 8%：需要复盘
4. 跌 12%：提示停止加仓
5. 跌 15%：判断买入逻辑是否失效
6. 持有不足 7 天：提醒 C 类基金赎回费
7. 当前价格接近近 30/90 日低点：提示可能进入观察区
8. 你不能直接说"必须买入"或"必须卖出"，只能给出分析、风险和动作建议
"""

OUTPUT_SCHEMA = """
输出一个 JSON 对象（不要 markdown 代码块，只输出纯 JSON）：
{
  "summary": "一句话总结当前状态",
  "current_status": "观察 / 接近买点 / 持有 / 接近止盈 / 需要复盘",
  "buy_signal": {"level": "无 / 弱 / 中 / 强", "reason": "原因"},
  "take_profit_signal": {"target_return": "15%", "current_return": "当前收益率%", "distance_to_target": "距离目标%", "triggered": true/false},
  "risk_signal": {"level": "低 / 中 / 高", "triggered_rules": ["触发的规则"]},
  "suggested_action": "建议操作（观察/复盘/考虑止盈/暂不操作）",
  "reasoning": ["原因1", "原因2", "原因3"]
}
"""


@dataclass
class AnalysisRequest:
    code: str
    name: str = ""
    fund_type: str = "open_fund"
    current_price: float = 0.0
    cost_nav: Optional[float] = None
    buy_date: Optional[str] = None


def _llm_analyze(req: AnalysisRequest, indicators: Dict, llm_config: Optional[Dict] = None) -> Optional[Dict]:
    """用 LLM 做完整分析，返回结构化 JSON。失败返回 None。"""
    # 优先用请求参数中的配置，否则用环境变量
    key = (llm_config or {}).get("key") or LLM_API_KEY
    base = (llm_config or {}).get("base") or LLM_API_BASE
    model = (llm_config or {}).get("model") or LLM_MODEL
    if not key:
        return None

    # 计算当前收益率
    current_return = "无持仓成本"
    if req.cost_nav and req.cost_nav > 0 and req.current_price > 0:
        ret = round((req.current_price - req.cost_nav) / req.cost_nav * 100, 2)
        current_return = f"{ret}%"

    # 持有天数
    hold_days = "未知"
    if req.buy_date:
        from datetime import date, datetime
        try:
            buy = datetime.strptime(str(req.buy_date)[:10], "%Y-%m-%d").date()
            hold_days = str((date.today() - buy).days)
        except Exception:
            pass

    prompt = f"""你是基金分析助手，请根据以下数据对这只基金做分析。

## 基金数据
- 代码: {req.code}
- 名称: {req.name}
- 当前净值: {req.current_price}
- 持仓成本: {req.cost_nav or '未知'}
- 当前收益率: {current_return}
- 买入日期: {req.buy_date or '未知'}
- 持有天数: {hold_days}
- 近7日涨跌: {indicators.get('change_7d', '未知')}%
- 近30日涨跌: {indicators.get('change_30d', '未知')}%
- 近90日涨跌: {indicators.get('change_90d', '未知')}%
- 近30日高点: {indicators.get('high_30d', '未知')}
- 近30日低点: {indicators.get('low_30d', '未知')}
- 近90日高点: {indicators.get('high_90d', '未知')}
- 近90日低点: {indicators.get('low_90d', '未知')}
- 是否阶段低位: {'是' if indicators.get('near_quarter_low') else '否'}

{TRADING_DISCIPLINE}

{OUTPUT_SCHEMA}
"""
    try:
        resp = requests.post(
            f"{base}/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是基金分析助手。只输出 JSON，不要 markdown 代码块，不要额外解释。"},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 800,
                "temperature": 0.3,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            logger.warning("LLM API 返回 %s: %s", resp.status_code, resp.text[:100])
            return None

        content = resp.json()["choices"][0]["message"]["content"].strip()
        # 清理可能的 markdown 代码块
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content[:-3]
        result = json.loads(content)
        if isinstance(result, dict) and "summary" in result:
            return result
    except json.JSONDecodeError:
        logger.warning("LLM 返回非 JSON，回退规则引擎。内容: %s", content[:200])
    except Exception:
        logger.exception("LLM 调用失败，回退规则引擎")
    return None


def analyze(req: AnalysisRequest, llm_config: Optional[Dict] = None) -> Dict:
    """执行分析：优先 LLM → 失败则规则引擎。"""

    # 1. 获取历史数据 + 计算技术指标
    hist = fetch_history(req.code, req.fund_type) if req.fund_type else None
    indicators = compute_indicators(hist) if hist is not None else {}
    if req.current_price > 0 and not indicators.get("current_nav"):
        indicators["current_nav"] = req.current_price

    # 2. 计算持仓收益率（供 LLM 和规则引擎共用）
    current_return = None
    if req.cost_nav and req.cost_nav > 0 and req.current_price > 0:
        current_return = round((req.current_price - req.cost_nav) / req.cost_nav * 100, 2)

    # 3. 规则引擎兜底结果
    rule_result = evaluate_rules(
        current_nav=req.current_price or indicators.get("current_nav", 0),
        cost_nav=req.cost_nav,
        buy_date=req.buy_date,
        indicators=indicators,
    )

    # 4. 尝试 LLM 分析
    llm_result = _llm_analyze(req, indicators, llm_config)

    # 5. 合并结果
    if llm_result:
        result = {
            "fund_code": req.code,
            "fund_name": req.name,
            "model": f"llm ({LLM_MODEL})",
            "summary": llm_result.get("summary", rule_result["summary"]),
            "current_status": llm_result.get("current_status", rule_result["current_status"]),
            "buy_signal": llm_result.get("buy_signal", rule_result["buy_signal"]),
            "take_profit_signal": llm_result.get("take_profit_signal", rule_result["take_profit_signal"]),
            "risk_signal": llm_result.get("risk_signal", rule_result["risk_signal"]),
            "suggested_action": llm_result.get("suggested_action", rule_result["suggested_action"]),
            "reasoning": llm_result.get("reasoning", rule_result["reasoning"]),
            "disclaimer": "仅做分析参考，不构成投资建议。Agent 不会直接给出买卖指令。",
        }
    else:
        result = {
            **rule_result,
            "fund_code": req.code,
            "fund_name": req.name,
            "model": "rule_engine (未配置 LLM 或调用失败)",
            "disclaimer": "仅做分析参考，不构成投资建议。Agent 不会直接给出买卖指令。",
        }

    return result
