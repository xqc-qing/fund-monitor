"""
交易纪律规则引擎 — 确定性规则，不依赖 LLM。
"""

from datetime import date, datetime
from typing import Dict, List, Optional


def evaluate_rules(
    *,
    current_nav: float,
    cost_nav: Optional[float] = None,
    buy_date: Optional[str] = None,
    indicators: Optional[Dict] = None,
) -> Dict:
    """根据交易纪律输出结构化规则判断。"""

    indicators = indicators or {}

    # ---- 收益率计算 ----
    current_return: Optional[float] = None
    if cost_nav and cost_nav > 0:
        current_return = round((current_nav - cost_nav) / cost_nav * 100, 2)

    # ---- 持有天数 ----
    hold_days: Optional[int] = None
    if buy_date:
        try:
            buy = datetime.strptime(buy_date[:10], "%Y-%m-%d").date()
            hold_days = (date.today() - buy).days
        except (ValueError, TypeError):
            pass

    # ---- 风险规则 ----
    risk_rules: List[str] = []
    risk_level = "低"

    if current_return is not None:
        if current_return >= 15:
            risk_rules.append("收益率已达标 15%，进入止盈观察区")
            risk_level = "中"
        if current_return <= -8:
            risk_rules.append("跌幅超过 8%，需要复盘持仓逻辑")
            risk_level = "中"
        if current_return <= -12:
            risk_rules.append("跌幅超过 12%，建议停止加仓")
            risk_level = "高"
        if current_return <= -15:
            risk_rules.append("跌幅超过 15%，买入逻辑可能已失效，重新评估")
            risk_level = "高"

    # 持有期风险
    if hold_days is not None and hold_days < 7:
        risk_rules.append(f"持有仅 {hold_days} 天，C类基金短期赎回费较高，不宜频繁操作")

    # 阶段低位提醒
    if indicators.get("near_month_low"):
        risk_rules.append("处于近30日低点区域，可能还有下探空间")
    if indicators.get("near_quarter_low") and not indicators.get("near_month_low"):
        risk_rules.append("处于近90日低点区域，可观察是否止跌企稳")

    # ---- 买入信号 ----
    buy_signals: List[str] = []
    buy_level = "无"

    if indicators.get("near_month_low") and indicators.get("near_quarter_low"):
        buy_signals.append("同时处于30日和90日低点区域")
        buy_level = "强"
    elif indicators.get("near_month_low"):
        buy_signals.append("处于30日低点区域")
        buy_level = "中"
    elif indicators.get("near_quarter_low"):
        buy_signals.append("处于90日低点区域")
        buy_level = "弱"

    change_30d = indicators.get("change_30d")
    if change_30d is not None and change_30d <= -10:
        buy_signals.append(f"近30日跌幅较大 ({change_30d:.2f}%)，恐慌性下跌阶段")
        if buy_level == "无":
            buy_level = "弱"

    # ---- 止盈信号 ----
    take_profit = {
        "target_return": "15%",
        "current_return": f"{current_return}%" if current_return is not None else "未知",
        "distance_to_target": None,
        "triggered": False,
    }
    if current_return is not None:
        distance = round(15 - current_return, 2)
        take_profit["distance_to_target"] = f"{distance}%"
        take_profit["triggered"] = current_return >= 15

    # ---- 当前状态判定 ----
    if current_return is not None and current_return >= 15:
        current_status = "接近止盈"
    elif buy_level in ("中", "强"):
        current_status = "接近买点"
    elif current_return is not None and cost_nav and cost_nav > 0:
        current_status = "持有"
    else:
        current_status = "观察"

    # ---- 建议动作 ----
    if risk_level == "高":
        suggested_action = "复盘 — 触发高风险规则，建议重新评估"
    elif current_return is not None and current_return >= 15:
        suggested_action = "考虑止盈 — 已接近目标收益率"
    elif buy_level == "强":
        suggested_action = "可观察买入 — 处于阶段低位，但需确认止跌"
    elif buy_level == "中":
        suggested_action = "继续观察 — 接近买点区域"
    elif hold_days is not None and hold_days < 7:
        suggested_action = "暂不操作 — 注意C类基金短期赎回费"
    else:
        suggested_action = "继续观察 — 暂无明显信号"

    # ---- 一句话总结 ----
    parts = []
    if current_return is not None:
        parts.append(f"当前收益率 {current_return:+.2f}%")
    if hold_days is not None:
        parts.append(f"持有 {hold_days} 天")
    if parts:
        summary_text = "，".join(parts) + "。"
    else:
        summary_text = "持仓数据不完整，请补充成本与买入日期。"

    summary = f"{current_status} | " + summary_text
    if risk_level != "低":
        summary += f" 风险等级: {risk_level}。"

    # ---- 推理原因 ----
    reasoning = risk_rules + buy_signals
    if not reasoning:
        reasoning = ["暂无特殊信号，基金处于正常波动范围。"]

    return {
        "summary": summary,
        "current_status": current_status,
        "buy_signal": {
            "level": buy_level,
            "reason": "；".join(buy_signals) if buy_signals else "无买入信号",
        },
        "take_profit_signal": take_profit,
        "risk_signal": {
            "level": risk_level,
            "triggered_rules": risk_rules,
        },
        "suggested_action": suggested_action,
        "reasoning": reasoning,
        "indicators": {
            "current_return": current_return,
            "hold_days": hold_days,
            "change_30d": indicators.get("change_30d"),
            "change_90d": indicators.get("change_90d"),
            "near_month_low": indicators.get("near_month_low"),
            "near_quarter_low": indicators.get("near_quarter_low"),
        },
    }
