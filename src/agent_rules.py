"""
交易纪律规则引擎 — 确定性规则，所有阈值可配置。
"""

from datetime import date, datetime
from typing import Dict, List, Optional

# 默认交易纪律
DEFAULT_TRADE_SETTINGS = {
    "targetTakeProfitPercent": 15,
    "reviewLossPercent": -8,
    "stopAddingLossPercent": -12,
    "logicFailureLossPercent": -15,
    "minHoldingDaysForCFund": 7,
    "lowPointLookbackDays": 30,
    "nearLowPointThresholdPercent": 3,
    "buyStyle": "一次性买入",
    "fundType": "C类基金",
    "enableTakeProfitReminder": True,
    "enableRiskReminder": True,
    "enableRedemptionFeeReminder": True,
}


def evaluate_rules(
    *,
    current_nav: float,
    cost_nav: Optional[float] = None,
    buy_date: Optional[str] = None,
    indicators: Optional[Dict] = None,
    settings: Optional[Dict] = None,
) -> Dict:
    """根据交易纪律输出结构化规则判断。settings 为可选的交易纪律覆盖配置。"""

    indicators = indicators or {}
    s = {**DEFAULT_TRADE_SETTINGS, **(settings or {})}  # 合并默认 + 用户配置

    # ---- 收益率计算 ----
    current_return: Optional[float] = None
    if cost_nav and cost_nav > 0:
        current_return = round((current_nav - cost_nav) / cost_nav * 100, 2)

    # ---- 持有天数 ----
    hold_days: Optional[int] = None
    if buy_date:
        try:
            buy = datetime.strptime(str(buy_date)[:10], "%Y-%m-%d").date()
            hold_days = (date.today() - buy).days
        except (ValueError, TypeError):
            pass

    # ---- 风险规则 ----
    risk_rules: List[str] = []
    risk_level = "低"

    tp_target = s["targetTakeProfitPercent"]
    review_line = s["reviewLossPercent"]
    stop_add_line = s["stopAddingLossPercent"]
    logic_fail_line = s["logicFailureLossPercent"]
    holding_min = s["minHoldingDaysForCFund"]
    near_threshold = s["nearLowPointThresholdPercent"]

    if current_return is not None:
        if s["enableTakeProfitReminder"] and current_return >= tp_target:
            risk_rules.append(f"收益率已达标 {tp_target}%，进入止盈观察区")
            risk_level = "中"
        if s["enableRiskReminder"] and current_return <= review_line:
            risk_rules.append(f"跌幅超过 {abs(review_line)}%，需要复盘持仓逻辑")
            risk_level = "中"
        if s["enableRiskReminder"] and current_return <= stop_add_line:
            risk_rules.append(f"跌幅超过 {abs(stop_add_line)}%，建议停止加仓")
            risk_level = "高"
        if s["enableRiskReminder"] and current_return <= logic_fail_line:
            risk_rules.append(f"跌幅超过 {abs(logic_fail_line)}%，买入逻辑可能已失效，重新评估")
            risk_level = "高"

    if s["enableRedemptionFeeReminder"] and hold_days is not None and hold_days < holding_min:
        risk_rules.append(f"持有仅 {hold_days} 天，C类基金短期赎回费较高，不宜频繁操作")

    # 阶段低位提醒
    if s["enableRiskReminder"]:
        if indicators.get("near_month_low"):
            risk_rules.append(f"处于近30日低点区域（距低点<{near_threshold}%），可能还有下探空间")
        elif indicators.get("near_quarter_low"):
            risk_rules.append(f"处于近90日低点区域，可观察是否止跌企稳")

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
        "target_return": f"{tp_target}%",
        "current_return": f"{current_return}%" if current_return is not None else "未知",
        "distance_to_target": None,
        "triggered": False,
    }
    if current_return is not None:
        distance = round(tp_target - current_return, 2)
        take_profit["distance_to_target"] = f"{distance}%"
        take_profit["triggered"] = current_return >= tp_target

    # ---- 当前状态判定 ----
    if current_return is not None and current_return >= tp_target:
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
    elif current_return is not None and current_return >= tp_target:
        suggested_action = "考虑止盈 — 已接近目标收益率"
    elif buy_level == "强":
        suggested_action = "可观察买入 — 处于阶段低位，但需确认止跌"
    elif buy_level == "中":
        suggested_action = "继续观察 — 接近买点区域"
    elif s["enableRedemptionFeeReminder"] and hold_days is not None and hold_days < holding_min:
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
