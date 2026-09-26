"""
MC 工具箱 · 打包脚本
功能：将 mod.py 打包为单个、无黑色控制台窗口的 Windows exe
用法：双击运行，或在命令行执行  python 打包.py
"""

import os
import sys
import subprocess
import shutil
import json

HERE = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "MC工具箱"
ENTRY = "mod.py"
ENTRY_PATH = os.path.join(HERE, ENTRY)


def step(msg):
    print(f"\n{'='*48}\n  {msg}\n{'='*48}")


def fail(msg):
    print(f"\n[错误] {msg}")
    input("\n按回车键退出...")
    sys.exit(1)


def main():
    # 0. 检查主程序
    if not os.path.isfile(ENTRY_PATH):
        fail(f"未找到 {ENTRY}，请把 打包.py 与 mod.py 放在同一文件夹")

    # 1. 检查 Python
    step("步骤 1/3  检查 Python 环境")
    try:
        ver = sys.version_info
        print(f"  Python {ver.major}.{ver.minor}.{ver.micro}")
        if ver < (3, 8):
            fail("需要 Python 3.8 及以上版本")
    except Exception:
        fail("无法获取 Python 版本")

    # 2. 安装依赖
    step("步骤 2/3  安装/更新依赖")
    for pkg in ("pyinstaller", "customtkinter"):
        print(f"  正在安装 {pkg} ...")
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "--upgrade", pkg],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            print(r.stdout)
            print(r.stderr)
            fail(f"{pkg} 安装失败，请检查网络后重试")

    # 3. 清理旧构建产物
    for name in ("build", "dist", f"{APP_NAME}.spec"):
        full = os.path.join(HERE, name)
        if os.path.isdir(full):
            shutil.rmtree(full)
        elif os.path.isfile(full):
            os.remove(full)

    # 4. 执行打包
    step("步骤 3/3  开始打包（可能需要 1~3 分钟，请耐心等待）")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--onefile",        # 单个 exe
        "--windowed",       # 无黑色控制台窗口
        "--clean",
        "--noconfirm",
        ENTRY,
    ]
    print("  执行命令：", " ".join(cmd), "\n")
    result = subprocess.run(cmd)

    if result.returncode != 0:
        fail("打包失败，请查看上方日志")

    # 5. 校验输出
    exe = os.path.join(HERE, "dist", f"{APP_NAME}.exe")
    if not os.path.isfile(exe):
        fail("未生成 exe，请检查 dist 目录")

    mb = os.path.getsize(exe) / (1024 * 1024)
    step("打包成功！")
    print(f"  文件：{exe}")
    print(f"  大小：{mb:.1f} MB")
    print(f"\n  双击该 exe 即可运行，无黑色控制台窗口。")
    print(f"  程序会在 exe 同目录自动生成 mc_toolbox_config.json 记录路径。")

    input("\n按回车键退出...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[已取消]")
        sys.exit(0)
