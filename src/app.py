"""
全场基金监测 — 统一 Web 界面（全场扫描 + 盯盘提醒）。
"""

import json
import logging
import os
import queue
import sys
import threading
from datetime import datetime, date
from pathlib import Path

os.environ.setdefault("NO_PROXY", "eastmoney.com,*.eastmoney.com")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, Response, render_template, request, jsonify
from src.screener import scan, _EM_API, _EM_HEADERS, _NO_PROXY
from src.fetcher_watch import fetch_quote
from src.rules import evaluate
from src.notifier import desktop_done
from src.storage import init_db, save_price_snapshot, already_alerted_today, mark_alerted
import requests

app = Flask(__name__, template_folder=str(PROJECT_ROOT / "templates"))

WATCHLIST_FILE = PROJECT_ROOT / "data" / "watchlist.json"

# ============================================================
# 自选列表管理
# ============================================================


def _load_watchlist() -> list:
    if WATCHLIST_FILE.exists():
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_watchlist(data: list) -> None:
    WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# 扫描状态管理
# ============================================================

_scan_state = {
    "running": False,
    "done": False,
    "progress": 0,
    "total": 0,
    "found": 0,
    "results": [],
    "started_at": "",
    "error": "",
}
_progress_queue: queue.Queue = queue.Queue()


class _ScanHandler(logging.Handler):
    def emit(self, record):
        msg = self.format(record)
        _progress_queue.put({"type": "log", "text": msg})
        if "进度:" in msg:
            try:
                parts = msg.split("进度:")[1].strip()
                done_str = parts.split("/")[0].strip()
                total_str = parts.split("/")[1].split(",")[0].strip()
                _scan_state["progress"] = int(done_str)
                _scan_state["total"] = int(total_str)
                found_str = parts.split("已发现")[1].split("只")[0].strip()
                _scan_state["found"] = int(found_str)
            except (ValueError, IndexError):
                pass


_scan_logger = logging.getLogger("scan_ui")
_scan_logger.setLevel(logging.INFO)
_scan_logger.addHandler(_ScanHandler())


def _run_scan_async():
    global _scan_state
    _scan_state.update(running=True, done=False, error="", results=[], found=0)
    _scan_state["started_at"] = datetime.now().strftime("%H:%M:%S")
    _progress_queue.put({"type": "start"})
    try:
        results = scan(max_workers=10, candidate_per_type=60, output_top=50)
        _scan_state["results"] = results
        _scan_state["found"] = len(results)
        _progress_queue.put({"type": "done", "found": len(results)})
    except Exception as e:
        _scan_state["error"] = str(e)
        _progress_queue.put({"type": "error", "text": str(e)})
    finally:
        _scan_state.update(running=False, done=True)


# ============================================================
# 工具函数
# ============================================================


def _lookup_fund_name(code: str, ftype: str) -> str:
    """根据基金代码自动查询名称（多重策略）。"""
    if ftype == "etf":
        try:
            import akshare as ak
            df = ak.fund_etf_spot_em()
            row = df[df["代码"] == code]
            if not row.empty:
                return str(row.iloc[0]["名称"])
        except Exception:
            pass
    else:
        # 策略1：东方财富搜索
        try:
            resp = requests.get(
                "https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx",
                params={"m": 1, "key": code},
                timeout=10,
                proxies=_NO_PROXY,
            )
            data = resp.json()
            for f in data.get("Datas", []):
                if f.get("CODE") == code:
                    name = f.get("NAME", "")
                    if name:
                        return name
        except Exception:
            pass
        # 策略2：从排名数据中按代码查找
        try:
            import akshare as ak
            import pandas as pd
            for ftype_name in ["股票型", "混合型", "指数型", "债券型"]:
                df = ak.fund_open_fund_rank_em(symbol=ftype_name)
                row = df[df["基金代码"] == code]
                if not row.empty:
                    return str(row.iloc[0]["基金简称"])
        except Exception:
            pass
    return code


# ============================================================
# 路由 — 页面
# ============================================================


@app.after_request
def _no_cache(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/")
def index():
    return render_template("index.html")


# ============================================================
# 路由 — 全场扫描
# ============================================================


@app.route("/api/scan", methods=["POST"])
def api_scan():
    if _scan_state["running"]:
        return {"ok": False, "error": "扫描正在进行中"}
    threading.Thread(target=_run_scan_async, daemon=True).start()
    return {"ok": True}


@app.route("/api/status")
def api_status():
    return {k: _scan_state[k] for k in ("running", "done", "progress", "total", "found", "error", "started_at")}


@app.route("/api/progress")
def api_progress():
    def stream():
        while True:
            try:
                msg = _progress_queue.get(timeout=2)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg["type"] in ("done", "error"):
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
    return Response(stream(), mimetype="text/event-stream")


@app.route("/api/results")
def api_results():
    return {"results": _scan_state["results"]}


# ============================================================
# 路由 — 盯盘列表
# ============================================================


@app.route("/api/watchlist")
def api_watchlist():
    return {"funds": _load_watchlist()}


@app.route("/api/watchlist/add", methods=["POST"])
def api_watchlist_add():
    data = request.get_json()
    code = data.get("code", "").strip()
    name = data.get("name", "").strip()
    ftype = data.get("type", "open_fund")
    alert_below = data.get("alert_below")
    daily_drop_pct = data.get("daily_drop_pct")
    if not code:
        return {"ok": False, "error": "请输入基金代码"}
    wl = _load_watchlist()
    if any(f["code"] == code for f in wl):
        return {"ok": False, "error": "该基金已在列表中"}
    # 如果用户没填名称，自动查询
    if not name:
        name = _lookup_fund_name(code, ftype)
    wl.append({
        "code": code, "name": name, "type": ftype,
        "alert_below": alert_below, "daily_drop_pct": daily_drop_pct,
    })
    _save_watchlist(wl)
    return {"ok": True, "funds": wl, "auto_name": name}


@app.route("/api/watchlist/remove", methods=["POST"])
def api_watchlist_remove():
    code = request.get_json().get("code", "")
    wl = _load_watchlist()
    wl = [f for f in wl if f["code"] != code]
    _save_watchlist(wl)
    return {"ok": True, "funds": wl}


@app.route("/api/watchlist/check", methods=["POST"])
def api_watchlist_check():
    """手动检查所有自选基金，返回每只基金的当前价格和触发状态。"""
    init_db()
    wl = _load_watchlist()
    if not wl:
        return {"ok": True, "results": [], "message": "自选列表为空"}
    results = []
    need_save = False
    for fund in wl:
        code = fund["code"]
        name = fund.get("name") or code
        ftype = fund.get("type", "open_fund")
        alert_below = fund.get("alert_below")
        daily_drop_pct = fund.get("daily_drop_pct")
        # 如果名称没解析过（等于代码），再尝试查一次并回写
        if name == code or not name.strip():
            resolved = _lookup_fund_name(code, ftype)
            if resolved != code:
                name = resolved
                fund["name"] = name
                need_save = True
        try:
            quote = fetch_quote(code, ftype)
            if quote is None:
                results.append({"code": code, "name": name, "error": "获取数据失败"})
                continue
            if not quote.name:
                quote.name = name
            save_price_snapshot(code, quote.name, ftype, quote.current_price, quote.price_date)
            result = evaluate(quote, alert_below=alert_below, daily_drop_pct=daily_drop_pct)
            results.append({
                "code": code,
                "name": quote.name,
                "current_price": quote.current_price,
                "price_date": quote.price_date,
                "prev_price": quote.prev_price,
                "fund_type": ftype,
                "triggered": result.triggered,
                "reasons": result.reasons,
                "alert_below": alert_below,
            })
            if result.triggered:
                if not already_alerted_today(code):
                    mark_alerted(code, quote.name, "; ".join(result.reasons))
        except Exception as e:
            results.append({"code": code, "name": name, "error": str(e)})
    if need_save:
        _save_watchlist(wl)
    desktop_done(sum(1 for r in results if r.get("triggered")))
    return {"ok": True, "results": results}


@app.route("/api/fund-detail/<code>")
def api_fund_detail(code):
    try:
        params = {"fundCode": code, "pageIndex": 1, "pageSize": 20}
        resp = requests.get(_EM_API, params=params, headers=_EM_HEADERS, timeout=15, proxies=_NO_PROXY)
        data = resp.json()
        items = (data.get("Data") or {}).get("LSJZList", [])
        nav_data = [{"date": it["FSRQ"], "nav": float(it["DWJZ"])} for it in items[:30]]
        return {"ok": True, "data": list(reversed(nav_data))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
# 启动
# ============================================================


def main():
    import webbrowser
    init_db()
    port = 8080
    print(f"\n   基金监测已启动: http://localhost:{port}\n   浏览器将自动打开\n")
    webbrowser.open(f"http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
