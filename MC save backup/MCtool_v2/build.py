# -*- coding: utf-8 -*-
"""
MC工具箱 打包脚本
依赖：pip install pyinstaller
用法：python build.py
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(HERE, "mod.py")

# ---- 自动查找图标：ico.ico > app.ico > icon.ico ----
ICO = ""
for name in ("ico.ico", "app.ico", "icon.ico"):
    p = os.path.join(HERE, name)
    if os.path.exists(p):
        ICO = p
        break

# ---- 清理上次产物 ----
for d in ("build", "dist", os.path.join(HERE, "MC工具箱.spec")):
    if os.path.isdir(d):
        shutil.rmtree(d)
    elif os.path.exists(d):
        os.remove(d)

# ---- 组装 PyInstaller 命令 ----
cmd = [
    sys.executable, "-m", "pyinstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--noconsole",
    "--name", "MC工具箱",
    "--collect-submodules", "customtkinter",
    "--hidden-import", "customtkinter",
]
if ICO:
    cmd += ["--icon", ICO]
    print("[图标] %s" % os.path.basename(ICO))
else:
    print("[警告] 未找到 ico.ico / app.ico / icon.ico，将使用默认图标")

# 如有需要打包进 exe 的额外文件，在此追加，例如：
# cmd += ["--add-data", os.path.join(HERE, "描述.txt") + os.pathsep + "."]

cmd.append(MAIN)

print("[开始打包] %s" % MAIN)
rc = subprocess.call(cmd)

dist_exe = os.path.join(HERE, "dist", "MC工具箱.exe")
if rc == 0 and os.path.exists(dist_exe):
    # 把图标拷到 exe 同目录，供运行时 window iconbitmap 使用
    if ICO:
        shutil.copyfile(ICO, os.path.join(HERE, "dist", os.path.basename(ICO)))
    print("[SUCCESS] 打包成功 -> %s" % dist_exe)
    print("           可直接把 dist 目录下的 exe 发给用户")
else:
    print("[FAILED] 打包失败，请检查上面的报错信息")
    print("         常见问题：pip install pyinstaller")
    print("         customtkinter 缺失：已在命令中加 --collect-submodules customtkinter")
    sys.exit(1)
