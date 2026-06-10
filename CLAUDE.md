# 基金监测 — 项目知识库

## 项目概况
Python/Flask + pywebview 桌面基金监测应用，纯原生 HTML/CSS/JS 前端。

## 启动方式
- 桌面窗口: 双击 `启动.vbs` → 隐式调用 `python src/gui.py`
- 浏览器: `python src/app.py` → http://localhost:8080

## 每次修改后必须执行

1. `python verify.py` — 语法 + 导入 + 安全 + 配置
2. 如果修改了前端: `curl -s http://127.0.0.1:8080 | grep <改动的元素>` 验证实际返回
3. 检查运行进程: `netstat -ano | grep :8080` 确认没有旧进程残留
4. 自检分析: 为什么原来的筛查流程没发现这个问题？

## 上次修改缺少的检查项（教训）
- 没有验证运行态（disk file vs served HTML）→ 必须 `curl` 抓取实际页面
- 没有检查运行进程数量（旧进程残留导致新代码不生效）→ 必须 `netstat -ano | grep :8080`
- 没有检查用户实际使用的启动方式（启动.vbs vs python src/app.py）→ 必须验证启动.vbs
- 杀进程后没检查 WebView2 残留 → 必须 `tasklist | grep msedgewebview2`
