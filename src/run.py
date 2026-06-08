"""
全场基金扫描 — 主运行脚本。
双击 启动扫描.bat 即可运行。
"""

import logging
import sys
from pathlib import Path
from datetime import datetime

import yaml

# 项目路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.screener import scan, format_report
from src.notifier import desktop_done


def main():
    # 日志
    data_dir = PROJECT_ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(data_dir / "scan.log", encoding="utf-8"),
        ],
    )

    # 读配置
    config_path = PROJECT_ROOT / "config" / "settings.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        scan_cfg = config.get("scan", {})
    else:
        scan_cfg = {}

    print()
    print("=" * 50)
    print("  全场基金低点扫描")
    print(f"  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("  扫描范围: 股票型 + 指数型基金")
    print("  预计耗时: 1-3 分钟")
    print("=" * 50)
    print()

    # 执行扫描
    result = scan(
        max_workers=scan_cfg.get("max_workers", 15),
        candidate_per_type=scan_cfg.get("candidate_per_type", 80),
        output_top=scan_cfg.get("output_top", 40),
    )

    # 生成报告
    report = format_report(result)
    print()
    print(report)

    # 保存到文件
    report_path = data_dir / "扫描结果.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n结果已保存到: {report_path}")

    # 桌面通知
    desktop_done(len(result))

    print("\n按任意键关闭窗口...")


if __name__ == "__main__":
    main()
