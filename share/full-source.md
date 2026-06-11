# 基金监测 — 完整源码审查

请审查以下文件，找出为什么用户反馈"界面显示旧模型、分析来源不显示"。

## 用户期望

- AI 设置中模型字段可手动输入任意模型名（如 deepseek-v4-pro）
- 选择 DeepSeek 时 baseUrl 自动填 https://api.deepseek.com
- 预设模型：deepseek-v4-flash, deepseek-v4-pro
- Agent 分析卡片显示：分析来源、使用模型、判断基础、使用规则

## 页面在 http://127.0.0.1:8080

## 文件 1: templates/index.html (关键前端)

请复制 https://github.com/xqc-qing/fund-monitor/blob/master/templates/index.html 的内容

## 文件 2: src/agent_analyzer.py (Agent 分析后端)

请复制 https://github.com/xqc-qing/fund-monitor/blob/master/src/agent_analyzer.py 的内容

## 文件 3: src/app.py (Flask 路由)

请复制 https://github.com/xqc-qing/fund-monitor/blob/master/src/app.py 的内容

## 验证命令

```bash
# 启动
cd "D:\全场基金监测"
python src/app.py

# 验证页面
curl -s http://127.0.0.1:8080 | grep -o 'id="aiModel"[^>]*'

# 验证 API
curl -s -X POST http://127.0.0.1:8080/api/agent/analyze \
  -H "Content-Type: application/json" \
  -d '{"code":"110022","llm_config":{"provider":"deepseek","model":"deepseek-v4-pro","key":"sk-test","enableAIAnalysis":true}}' | python -m json.tool | grep -E "model_|analysis_|source_"
```

## 仓库地址

https://github.com/xqc-qing/fund-monitor

请克隆或直接查看 master 分支最新代码。
