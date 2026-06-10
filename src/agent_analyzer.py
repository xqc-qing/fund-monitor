"""
Agent 智能分析器 — 规则引擎 + 可选 LLM 增强。
设置 LLM_API_KEY 环境变量可启用 LLM 自然语言分析，不设则使用纯规则引擎。
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

# 尝试加载 .env 文件
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
_NO_PROXY = {"http": None, "https": None}

from .fetcher_watch import fetch_history
from .fund_indicators import compute_indicators
from .agent_rules import evaluate_rules


@dataclass
class AnalysisRequest:
    code: str
    name: str = ""
    fund_type: str = "open_fund"
    current_price: float = 0.0
    cost_nav: Optional[float] = None
    buy_date: Optional[str] = None


def _enhance_with_llm(rule_result: Dict) -> Optional[str]:
    """用 LLM 生成自然语言总结。失败时返回 None，不影响规则引擎结果。"""
    if not LLM_API_KEY:
        return None

    prompt = f"""你是一个基金分析助手。请用中文根据以下结构化数据，生成一段 3-5 句的分析总结。

规则引擎输出：
{json.dumps(rule_result, ensure_ascii=False, indent=2)}

要求：
1. 简要总结当前基金状态
2. 如果触发风险规则，说明风险重点
3. 如果出现买入信号，判断信号强弱
4. 不要直接说"买入"或"卖出"，只做分析和提醒
5. 语气客观、克制、专业
"""
    try:
        resp = requests.post(
            f"{LLM_API_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "temperature": 0.3,
            },
            timeout=20,
            proxies=_NO_PROXY,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        logger.warning("LLM API 返回 %s: %s", resp.status_code, resp.text[:100])
    except Exception:
        logger.exception("LLM 调用失败，回退到规则引擎模式")
    return None


def analyze(req: AnalysisRequest) -> Dict:
    """执行完整分析，返回结构化 JSON。如果配置了 LLM_API_KEY，会用 LLM 增强自然语言输出。"""

    # 1. 获取历史数据 + 计算技术指标
    hist = fetch_history(req.code, req.fund_type) if req.fund_type else None
    indicators = compute_indicators(hist) if hist is not None else {}

    if req.current_price > 0 and not indicators.get("current_nav"):
        indicators["current_nav"] = req.current_price

    # 2. 执行交易纪律规则（确定性）
    result = evaluate_rules(
        current_nav=req.current_price or indicators.get("current_nav", 0),
        cost_nav=req.cost_nav,
        buy_date=req.buy_date,
        indicators=indicators,
    )

    # 3. 附加元信息
    result["fund_code"] = req.code
    result["fund_name"] = req.name

    # 4. 尝试 LLM 增强
    if LLM_API_KEY:
        llm_text = _enhance_with_llm(result)
        if llm_text:
            result["summary"] = llm_text
            result["model"] = f"rule_engine + {LLM_MODEL}"
        else:
            result["model"] = "rule_engine (LLM failed, fallback)"
    else:
        result["model"] = "rule_engine"

    result["disclaimer"] = "仅做分析参考，不构成投资建议。Agent 不会直接给出买卖指令。"
    return result
