"""
统一检查脚本 — 对项目执行全面检查。
用法: python verify.py          # 完整检查
      python verify.py --quick  # 仅语法检查
      python verify.py --sec    # 仅安全检查
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"

ALL_SRC_FILES = sorted(SRC_DIR.glob("*.py"))

# Windows GBK-safe status markers
PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"
INFO = "[INFO]"


def _print(msg: str) -> None:
    """安全打印，处理 Windows GBK 编码问题。"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


def run_check(name: str, files: list) -> bool:
    """编译检查 Python 文件语法。"""
    _print(f"\n{'='*50}")
    _print(f"  {name}")
    _print(f"{'='*50}")
    all_ok = True
    for f in files:
        try:
            subprocess.run(
                [sys.executable, "-m", "py_compile", str(f)],
                capture_output=True, check=True,
            )
            status = f"{PASS} OK"
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode("utf-8", errors="replace").strip()
            _print(f"  {FAIL} {f.name}")
            _print(f"     {stderr}")
            all_ok = False
            continue
        if "--quick" not in sys.argv:
            _print(f"  {status}  {f.name}")
    return all_ok


def check_imports() -> bool:
    """检查关键模块能否正常导入（不执行 Flask 启动）。"""
    _print(f"\n{'='*50}")
    _print(f"  导入检查")
    _print(f"{'='*50}")
    import_check_scripts = {
        "agent_rules": "from src.agent_rules import evaluate_rules, DEFAULT_TRADE_SETTINGS",
        "fund_indicators": "from src.fund_indicators import compute_indicators",
        "agent_analyzer": "from src.agent_analyzer import AnalysisRequest, analyze",
        "rules": "from src.rules import evaluate",
        "storage": "from src.storage import init_db",
    }
    all_ok = True
    for name, code in import_check_scripts.items():
        try:
            subprocess.run(
                [sys.executable, "-c", f"import sys; sys.path.insert(0, '{PROJECT_ROOT}'); {code}"],
                capture_output=True, check=True, cwd=str(PROJECT_ROOT),
            )
            if "--quick" not in sys.argv:
                _print(f"  {PASS} OK  {name}")
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode("utf-8", errors="replace").strip()
            _print(f"  {FAIL} FAIL  {name}")
            _print(f"     {stderr}")
            all_ok = False
    return all_ok


def check_sensitive() -> bool:
    """检查是否有敏感信息泄漏。"""
    _print(f"\n{'='*50}")
    _print(f"  安全检查")
    _print(f"{'='*50}")
    ok = True

    # 1. .env 文件是否存在
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        _print(f"  {WARN} .env 文件存在 ({env_file.stat().st_size} bytes)")
        content = env_file.read_text(encoding="utf-8")
        if "sk-" in content:
            _print(f"  {WARN} .env 中包含疑似 API Key (sk-...) ，请勿提交到 git")
    else:
        _print(f"  {PASS} .env 不存在（安全）")

    # 2. 检查 .gitignore 是否包含 .env
    gitignore = PROJECT_ROOT / ".gitignore"
    if gitignore.exists():
        gi = gitignore.read_text(encoding="utf-8")
        if ".env" in gi:
            _print(f"  {PASS} .gitignore 已包含 .env")
        else:
            _print(f"  {FAIL} .gitignore 未包含 .env，有泄漏风险！")
            ok = False
    else:
        _print(f"  {WARN} 无 .gitignore 文件")
        ok = False

    # 3. 扫描 Python 源码中是否有硬编码 API Key
    suspicious = []
    for f in ALL_SRC_FILES:
        text = f.read_text(encoding="utf-8")
        for pattern, desc in [
            ("sk-", "疑似 OpenAI/DeepSeek API Key"),
            ("AKIA", "疑似 AWS Access Key"),
            ("ghp_", "疑似 GitHub Personal Token"),
            ("gho_", "疑似 GitHub OAuth Token"),
            ("glpat-", "疑似 GitLab Token"),
        ]:
            if pattern in text:
                suspicious.append(f"  {FAIL} {f.name}: {desc} ({pattern})")
    if suspicious:
        for s in suspicious:
            _print(s)
        ok = False
    else:
        if "--quick" not in sys.argv:
            _print(f"  {PASS} 未发现硬编码密钥")

    # 4. 检查 .gitignore 是否合理
    if gitignore.exists():
        gi = gitignore.read_text(encoding="utf-8")
        if "*.txt" in gi:
            _print(f"  {WARN} .gitignore 中 *.txt 过于宽泛，可能误伤文本文件")

    return ok


def check_config() -> bool:
    """检查配置文件和关键数据文件。"""
    _print(f"\n{'='*50}")
    _print(f"  配置检查")
    _print(f"{'='*50}")
    ok = True

    # .env.example 存在
    env_example = PROJECT_ROOT / ".env.example"
    if env_example.exists():
        _print(f"  {PASS} .env.example 存在")
    else:
        _print(f"  {WARN} 建议添加 .env.example 作为配置模板")
        ok = False

    # requirements.txt 存在
    req_file = PROJECT_ROOT / "requirements.txt"
    if req_file.exists():
        reqs = req_file.read_text(encoding="utf-8").strip().split("\n")
        reqs = [r for r in reqs if r.strip() and not r.strip().startswith("#")]
        _print(f"  {PASS} requirements.txt 存在 ({len(reqs)} 个依赖)")
    else:
        _print(f"  {WARN} 缺少 requirements.txt")
        ok = False

    # data 目录
    data_dir = PROJECT_ROOT / "data"
    if data_dir.exists():
        _print(f"  {PASS} data/ 目录存在")
    else:
        _print(f"  {INFO} data/ 目录将在首次运行时自动创建")

    return ok


def check_frontend() -> bool:
    """检查前端 HTML/JS 完整性。"""
    import re

    _print(f"\n{'='*50}")
    _print(f"  前端检查")
    _print(f"{'='*50}")

    index_path = PROJECT_ROOT / "templates" / "index.html"
    if not index_path.exists():
        _print(f"  {FAIL} templates/index.html 不存在")
        return False

    html = index_path.read_text(encoding="utf-8")

    # 1. 检查 script 标签
    script_m = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    if not script_m:
        _print(f"  {FAIL} 未找到 script 标签")
        return False

    js = script_m.group(1)

    # 2. 用 node.js 检查 JS 语法
    import subprocess, tempfile, os
    ok = True
    node_check = False
    try:
        fname = os.path.join(tempfile.gettempdir(), "_verify_page.js")
        with open(fname, "w", encoding="utf-8") as f:
            f.write(js)
        r = subprocess.run(["node", "--check", fname], capture_output=True)
        if r.returncode == 0:
            _print(f"  {PASS} JS 语法正确 (Node.js)")
            node_check = True
        else:
            _print(f"  {FAIL} JS 语法错误: {r.stderr.decode('utf-8', errors='replace')[:200]}")
            ok = False
    except FileNotFoundError:
        _print(f"  {INFO} Node.js 未安装，跳过 JS 语法检查")
    except Exception as e:
        _print(f"  {WARN} JS 语法检查失败: {e}")

    # 3. 检查 getElementById 引用的元素
    ids_in_js = set(re.findall(r"getElementById\(['\"](\w+)['\"]\)", js))
    missing = [eid for eid in ids_in_js if f'id="{eid}"' not in html]
    if missing:
        _print(f"  {FAIL} {len(missing)} 个 DOM 元素缺失: {missing}")
        ok = False
    else:
        if "--quick" not in sys.argv:
            _print(f"  {PASS} {len(ids_in_js)} 个 DOM 元素全部存在")

    # 4. 检查 localStorage 键
    ls_keys = set(re.findall(r"localStorage\.getItem\(['\"]([^'\"]+)['\"]\)", js))
    _print(f"  {INFO} localStorage 键: {', '.join(sorted(ls_keys))}")

    # 5. 检查关键功能元素
    critical = ["settingsPanel", "agentCard", "agentSourceBox", "aiModel",
                "aiProvider", "aiBase", "aiKey", "aiEnable"]
    missing_crit = [c for c in critical if f'id="{c}"' not in html]
    if missing_crit:
        _print(f"  {FAIL} 关键元素缺失: {missing_crit}")
        ok = False
    else:
        _print(f"  {PASS} {len(critical)} 个关键元素全部存在")

    return ok


def main():
    is_quick = "--quick" in sys.argv
    is_sec = "--sec" in sys.argv

    _print("=" * 50)
    _print("  基金监测 — 项目检查")
    _print(f"  路径: {PROJECT_ROOT}")
    _print(f"  模式: {'快速' if is_quick else '安全' if is_sec else '完整'}")
    _print("=" * 50)

    results = {}

    if is_sec:
        results["安全"] = check_sensitive()
    elif is_quick:
        results["语法"] = run_check("语法编译检查", ALL_SRC_FILES)
    else:
        results["语法"] = run_check("语法编译检查", ALL_SRC_FILES)
        results["导入"] = check_imports()
        results["安全"] = check_sensitive()
        results["配置"] = check_config()
        results["前端"] = check_frontend()

    # 汇总
    _print(f"\n{'='*50}")
    _print(f"  检查结果汇总")
    _print(f"{'='*50}")
    all_pass = True
    for name, ok in results.items():
        _print(f"  {PASS if ok else FAIL} {name}: {'通过' if ok else '失败'}")
        if not ok:
            all_pass = False

    if all_pass:
        _print(f"\n  {PASS} 全部检查通过")
        return 0
    else:
        _print(f"\n  {FAIL} 存在未通过的检查项，请修复后再提交")
        return 1


if __name__ == "__main__":
    sys.exit(main())
