# 全场基金监测

全市场基金低点扫描 + 盯盘提醒桌面应用，帮你发现接近一年最低点的基金并盯住自选标的。

## 主要功能

### 全场扫描
- 扫描全市场股票型 + 指数型基金
- 并发获取历史净值，找出距一年低点 10% 以内的基金
- 按距离低点百分比排名展示
- 一键收藏到盯盘列表
- 基金代码点击跳转天天基金详情页

### 我的盯盘
- 自定义自选基金列表
- 只输入代码即可自动查询基金名称
- 设定目标价位和日跌幅提醒
- 一键检查当前净值与触发状态
- 触发提醒的基金红色高亮
- 数据本地持久化，关闭不丢失

## 快速开始

### 环境要求
- Windows 10/11
- Python 3.11+

### 安装
```bash
git clone https://github.com/xqc-qing/fund-monitor.git
cd fund-monitor
pip install -r requirements.txt
```

### 运行
双击 `启动.vbs` 或运行：
```bash
python src/gui.py
```

## 技术栈
- **后端**: Python + Flask
- **桌面窗口**: pywebview (Edge WebView2)
- **数据源**: AKShare + 东方财富 REST API
- **存储**: SQLite + JSON

## 项目结构
```
├── src/
│   ├── gui.py           # 桌面窗口入口
│   ├── app.py           # Flask 服务端
│   ├── screener.py       # 全场扫描引擎
│   ├── fetcher_watch.py  # 盯盘数据获取
│   ├── rules.py          # 提醒规则判断
│   ├── storage.py        # SQLite 存储
│   └── notifier.py       # 桌面通知
├── templates/
│   └── index.html        # Web 界面
├── config/
│   └── settings.yaml     # 扫描参数配置
├── 启动.vbs              # 一键启动（无命令行窗口）
└── requirements.txt
```

## 免责声明
仅作价格提醒，不构成投资建议。基金投资有风险，决策需谨慎。
