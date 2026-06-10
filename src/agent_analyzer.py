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
LLM_MODEL = os.environ.get("LLM_MODEL", "")
LLM_LAST_ERROR = ""  # 最近一次 LLM 调用失败的具体原因

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


def _llm_analyze(req: AnalysisRequest, indicators: Dict, llm_config: Optional[Dict] = None, trade_settings: Optional[Dict] = None) -> Optional[Dict]:
    """用 LLM 做完整分析，返回结构化 JSON。失败返回 None。"""
    global LLM_LAST_ERROR
    # 优先用请求参数中的配置，否则用环境变量
    cfg = llm_config or {}
    key = cfg.get("key") or LLM_API_KEY
    base = cfg.get("base") or LLM_API_BASE
    model = cfg.get("model") or LLM_MODEL
    temperature = float(cfg.get("temperature", 0.3))
    max_tokens = int(cfg.get("maxTokens", 800))
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

    # 交易纪律（优先用传入的，否则默认值）
    from .agent_rules import DEFAULT_TRADE_SETTINGS
    trade = {**DEFAULT_TRADE_SETTINGS, **(trade_settings or {})}
    trade_desc = f"""- 止盈目标: {trade['targetTakeProfitPercent']}%
- 复盘线: {trade['reviewLossPercent']}%
- 停止加仓线: {trade['stopAddingLossPercent']}%
- 逻辑失效线: {trade['logicFailureLossPercent']}%
- C类最短持有: {trade['minHoldingDaysForCFund']}天
- 买入方式: {trade['buyStyle']}
- 基金类型: {trade['fundType']}"""

    prompt = f"""你是基金分析助手，请根据以下数据对这只基金做分析。分析时必须严格按交易纪律判断。

## 交易纪律
{trade_desc}

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
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=30,
        )
        if resp.status_code == 401 or resp.status_code == 403:
            LLM_LAST_ERROR = "API Key 错误"
            logger.warning("LLM API 认证失败: %s", resp.status_code)
            return None
        if resp.status_code == 404:
            LLM_LAST_ERROR = "baseUrl 错误或模型不存在"
            logger.warning("LLM API 404: %s", resp.status_code)
            return None
        if resp.status_code != 200:
            LLM_LAST_ERROR = f"接口请求失败 (HTTP {resp.status_code})"
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
            LLM_LAST_ERROR = ""
            return result
        LLM_LAST_ERROR = "AI 返回格式异常，未包含 summary"
    except requests.ConnectionError:
        LLM_LAST_ERROR = "接口请求失败：无法连接"
        logger.warning("LLM 连接失败: %s", base)
    except requests.Timeout:
        LLM_LAST_ERROR = "接口请求超时"
        logger.warning("LLM 请求超时: %s", base)
    except json.JSONDecodeError:
        LLM_LAST_ERROR = "AI 返回非 JSON 格式"
        logger.warning("LLM 返回非 JSON，回退规则引擎。内容: %s", content[:200])
    except Exception:
        LLM_LAST_ERROR = "接口请求失败"
        logger.exception("LLM 调用失败，回退规则引擎")
    return None


def analyze(req: AnalysisRequest, llm_config: Optional[Dict] = None, trade_settings: Optional[Dict] = None) -> Dict:
    """执行分析：优先 LLM → 失败则规则引擎。可传入 trade_settings 覆盖默认交易纪律。"""

    cfg = llm_config or {}
    provider = cfg.get("provider", "")
    user_model = cfg.get("model")
    model_used = user_model if user_model else LLM_MODEL

    # DEBUG: model 全链路追踪
    logger.info("[Agent] backend_received_model=%s  llm_request_model=%s  model_used_in_result=%s",
                repr(user_model), repr(model_used), repr(model_used))
    llm_enabled = cfg.get("enableAIAnalysis", True) if "enableAIAnalysis" in cfg else True
    key = cfg.get("key") or LLM_API_KEY

    # 1. 获取历史数据 + 计算技术指标（传入交易设置以使用用户配置的阈值）
    hist = fetch_history(req.code, req.fund_type) if req.fund_type else None
    indicators = compute_indicators(hist, settings=trade_settings) if hist is not None else {}
    if req.current_price > 0 and not indicators.get("current_nav"):
        indicators["current_nav"] = req.current_price

    # 2. 计算持仓收益率
    current_return = None
    if req.cost_nav and req.cost_nav > 0 and req.current_price > 0:
        current_return = round((req.current_price - req.cost_nav) / req.cost_nav * 100, 2)

    # 3. 规则引擎兜底结果（传入用户交易设置）
    rule_result = evaluate_rules(
        current_nav=req.current_price or indicators.get("current_nav", 0),
        cost_nav=req.cost_nav,
        buy_date=req.buy_date,
        indicators=indicators,
        settings=trade_settings,
    )

    # 4. 收集启用的规则（中文可读格式，含实际阈值）
    from .agent_rules import DEFAULT_TRADE_SETTINGS
    trade = {**DEFAULT_TRADE_SETTINGS, **(trade_settings or {})}
    tp = trade.get("targetTakeProfitPercent", 15)
    review = trade.get("reviewLossPercent", -8)
    stop_add = trade.get("stopAddingLossPercent", -12)
    logic_fail = trade.get("logicFailureLossPercent", -15)
    min_days = trade.get("minHoldingDaysForCFund", 7)
    lookback = trade.get("lowPointLookbackDays", 30)
    near_low = trade.get("nearLowPointThresholdPercent", 3)

    rules_used = []
    if trade.get("enableTakeProfitReminder", True):
        rules_used.append(f"{tp}%止盈")
    if trade.get("enableRiskReminder", True):
        rules_used.extend([f"{review}%复盘", f"{stop_add}%停止加仓", f"{logic_fail}%逻辑失效"])
    if trade.get("enableRedemptionFeeReminder", True):
        rules_used.append(f"C类基金持有{min_days}天")

    # 5. 决定分析来源
    analysis_source = "rules"
    source_label = "交易纪律规则"
    basis = "仅根据交易纪律规则判断"
    fallback_reason = ""
    llm_used = False
    llm_result = None

    if llm_enabled:
        if not key:
            analysis_source = "rules"
            source_label = "交易纪律规则"
            basis = "仅根据交易纪律规则判断"
            fallback_reason = "API Key 未配置"
        elif not (cfg.get("model") or LLM_MODEL):
            analysis_source = "rules"
            source_label = "交易纪律规则"
            basis = "仅根据交易纪律规则判断"
            fallback_reason = "模型名缺失"
        else:
            llm_result = _llm_analyze(req, indicators, llm_config, trade_settings)
            if llm_result:
                analysis_source = "ai"
                source_label = "AI 分析"
                basis = "AI 分析 + 交易纪律规则"
                llm_used = True
            else:
                analysis_source = "fallback"
                source_label = "规则兜底"
                basis = "AI 调用失败，已改用交易纪律规则判断"
                fallback_reason = LLM_LAST_ERROR or "AI 请求失败，已使用交易纪律规则判断"
    else:
        analysis_source = "rules"
        source_label = "交易纪律规则"
        basis = "仅根据交易纪律规则判断"
        fallback_reason = "AI 未启用"

    analysis_mode = basis  # 兼容旧字段

    # 6. 合并结果
    if llm_result:
        result = {
            "fund_code": req.code,
            "fund_name": req.name,
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
            "disclaimer": "仅做分析参考，不构成投资建议。Agent 不会直接给出买卖指令。",
        }

    # 注入分析来源元数据
    result["analysis_source"] = analysis_source
    result["source_label"] = source_label
    result["analysis_mode"] = analysis_mode
    result["basis"] = basis
    result["provider"] = provider
    result["model_requested"] = user_model or ""   # 用户在前端输入的原始模型名
    result["model_used"] = model_used               # 实际发送给 API 的模型名
    result["llm_used"] = llm_used
    result["fallback_reason"] = fallback_reason
    result["rules_used"] = rules_used
    result["ok"] = True

    return result
