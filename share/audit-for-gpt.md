# 基金监测项目 — 外部审查报告

## 如何验证

```bash
cd "D:\全场基金监测"
python src/app.py
# 浏览器打开 http://127.0.0.1:8080
```

## 当前需求（未解决）

1. AI 设置面板里，模型字段应该是文本输入框（可手动输入任意模型名，如 deepseek-v4-pro），不是下拉 select
2. 选择 DeepSeek 时，baseUrl 自动填 `https://api.deepseek.com`，模型预设为 deepseek-v4-flash 和 deepseek-v4-pro
3. Agent 分析卡片必须显示分析来源（AI/规则/兜底）、使用模型、判断基础

## 关键文件

- `templates/index.html` — 前端全部代码
- `src/agent_analyzer.py` — Agent 分析后端
- `src/app.py` — Flask 路由
- `src/gui.py` — 桌面窗口入口
- `启动.vbs` — 启动脚本

## 实际页面验证

```bash
curl -s http://127.0.0.1:8080 | grep "aiModel" | head -3
# 应该是: <input id="aiModel" type="text" ...>
# 不应该是: <select id="aiModel">

curl -s http://127.0.0.1:8080 | grep "deepseek-v4-pro"
# 应该能找到

curl -s http://127.0.0.1:8080 | grep "deepseek-chat"
# 不应该找到
```

## API 验证

```bash
curl -s -X POST http://127.0.0.1:8080/api/agent/analyze \
  -H "Content-Type: application/json" \
  -d '{"code":"110022","llm_config":{"provider":"deepseek","model":"deepseek-v4-pro","key":"sk-test","enableAIAnalysis":true}}' | python -m json.tool
```

## 仓库

https://github.com/xqc-qing/fund-monitor
