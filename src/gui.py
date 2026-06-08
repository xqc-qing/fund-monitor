"""
全场基金监测 — 原生桌面窗口（Edge WebView2 引擎，零浏览器痕迹）。
"""

import sys
import threading
import time
from pathlib import Path

# 隐藏控制台窗口（使用 python.exe 而非 pythonw.exe，因为 webview 需要控制台子系统）
if sys.platform == "win32":
    import ctypes
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass  # 非控制台模式启动时不报错

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    import webview
    from src.app import app

    # 后台启动 Flask
    def start_flask():
        app.run(host="127.0.0.1", port=8080, debug=False, use_reloader=False)

    threading.Thread(target=start_flask, daemon=True).start()

    # 等 Flask 就绪
    import urllib.request
    for _ in range(10):
        try:
            urllib.request.urlopen("http://127.0.0.1:8080")
            break
        except Exception:
            time.sleep(0.5)

    # 纯原生窗口：内嵌 Edge WebView2，无浏览器进程，无地址栏，无任何多余元素
    window = webview.create_window(
        title="基金监测",
        url="http://127.0.0.1:8080",
        width=1200,
        height=800,
        min_size=(900, 600),
        resizable=True,
        confirm_close=True,
    )
    webview.start(gui="edgechromium")


if __name__ == "__main__":
    main()
