"""
Minecraft 工具箱 — 存档备份 & 模组备份
CustomTkinter 深色主题 · 响应式布局 · 智能路径记忆
"""

import os
import sys
import string
import json
import threading
import shutil
from datetime import datetime
import customtkinter as ctk
from tkinter import filedialog, messagebox

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── 配色 ──────────────────────────────────────────
BG = "#0f1117"
SURFACE = "#1a1d27"
BORDER = "#2a2d3a"
ACCENT = "#6c8cff"
ACCENT_DIM = "#3d5099"
GREEN = "#34d399"
GREEN_HOV = "#059669"
RED = "#f87171"
TEXT = "#f1f5f9"
TEXT_SEC = "#94a3b8"
TEXT_DIM = "#64748b"

# ── 字体 ──────────────────────────────────────────
FONT_FAMILY = "Microsoft YaHei"

# ── 常量 ──────────────────────────────────────────
SKIP_DIRS = {
    "Windows", "$Recycle.Bin", "System Volume Information",
    "Recovery", "PerfLogs", "ProgramData",
    "Program Files", "Program Files (x86)",
    "msys64", "msys", "MinGW",
    ".git", "node_modules", ".venv", "__pycache__",
    "TaskTemp",
}
PCL2_EXES = {"Plain Craft Launcher 2.exe", "PCL2.exe", "Plain Craft Launcher.exe"}
INI_NAMES = ["PCL/Setup.ini", "PCL2/Setup.ini"]
INI_ENCODINGS = ["utf-8-sig", "utf-8", "gbk", "gb2312", "latin-1"]
NON_VERSION_DIRS = {"saves", "libraries", "assets", "natives", "mods"}
MAX_SCAN_DEPTH = 10
CONFIG_FILENAME = "mc_toolbox_config.json"


def _config_file():
    """JSON 配置保存在程序同目录下（打包后为 exe 所在目录）"""
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), CONFIG_FILENAME)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILENAME)


class Card(ctk.CTkFrame):
    """圆角卡片容器"""

    def __init__(self, master, **kw):
        super().__init__(master, fg_color=SURFACE, corner_radius=14,
                         border_width=1, border_color=BORDER, **kw)


class MCToolboxApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("MC 工具箱")
        self.geometry("640x560")
        self.minsize(520, 420)
        self.configure(fg_color=BG)

        # 共享状态
        self.versions_path = None
        self._scan_cancel = False
        self._scan_frame = None

        # 存档备份状态
        self.save_versions = []
        self.save_selected_version = None
        self.save_saves = []
        self.save_selected_save = None
        self.save_save_path = None

        # 模组备份状态
        self.mod_versions = []
        self.mod_selected_version = None
        self.mod_mods = []
        self.mod_selected_mods = []
        self.mod_save_path = None

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_tabbar()
        self._build_container()
        self._show_tab(0)

    # ══════════════════════════════════════════════
    #  布局系统
    # ══════════════════════════════════════════════
    def _build_tabbar(self):
        tabbar = ctk.CTkFrame(self, fg_color=BG)
        tabbar.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 0))
        tabbar.grid_columnconfigure((0, 1), weight=1)

        self.tab_btns = []
        for i, name in enumerate(["存档备份", "模组备份"]):
            btn = ctk.CTkButton(
                tabbar, text=name, height=38,
                font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
                corner_radius=10,
                fg_color=ACCENT if i == 0 else "transparent",
                border_width=1,
                border_color=ACCENT if i == 0 else BORDER,
                text_color="white" if i == 0 else TEXT_SEC,
                command=lambda idx=i: self._show_tab(idx)
            )
            btn.grid(row=0, column=i, padx=(0 if i == 0 else 6), sticky="ew")
            self.tab_btns.append(btn)

    def _build_container(self):
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.grid(row=1, column=0, sticky="nsew", padx=24, pady=(12, 16))
        self.container.grid_columnconfigure(0, weight=1)
        self.container.grid_rowconfigure(0, weight=1)
        self.page = None
        self.current_tab = 0

    def _show_tab(self, idx):
        self.current_tab = idx
        for i, btn in enumerate(self.tab_btns):
            active = (i == idx)
            btn.configure(
                fg_color=ACCENT if active else "transparent",
                border_color=ACCENT if active else BORDER,
                text_color="white" if active else TEXT_SEC
            )
        self._scan_cancel = True
        self._scan_frame = None
        if idx == 0:
            self._save_goto(1)
        else:
            self._mod_goto(1)

    def _new_page(self):
        """创建新页面，固定三行布局：标题区 / 内容区 / 导航栏"""
        if self.page:
            self._scan_frame = None
            self.page.destroy()
        pg = ctk.CTkFrame(self.container, fg_color="transparent")
        pg.grid(row=0, column=0, sticky="nsew")
        pg.grid_columnconfigure(0, weight=1)
        pg.grid_rowconfigure(1, weight=1)
        self.page = pg
        return pg

    def _title(self, pg, title, subtitle):
        """标题区固定在 row=0，副标题紧贴主标题"""
        hdr = ctk.CTkFrame(pg, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr, text=title, font=ctk.CTkFont(family=FONT_FAMILY, size=18, weight="bold"),
                     text_color=TEXT).grid(row=0, column=0, sticky="w", pady=(0, 2))
        ctk.CTkLabel(hdr, text=subtitle, font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                     text_color=TEXT_SEC).grid(row=1, column=0, sticky="w")

    def _nav_row(self, pg, on_back, on_next, next_text="下一步  →", next_enabled=True):
        """导航栏固定在 row=2，上一步左下角、下一步右下角"""
        nav = ctk.CTkFrame(pg, fg_color="transparent")
        nav.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        nav.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(nav, text="←  上一步", width=110, height=38,
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      font=ctk.CTkFont(family=FONT_FAMILY, size=12), text_color=TEXT_SEC,
                      corner_radius=10, command=on_back).grid(row=0, column=0, sticky="w")

        nxt = ctk.CTkButton(nav, text=next_text, width=150, height=38,
                            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
                            corner_radius=10, command=on_next,
                            state="normal" if next_enabled else "disabled")
        nxt.grid(row=0, column=2, sticky="e")
        return nxt

    def _make_content(self, pg):
        """创建内容容器（row=1），返回该容器"""
        content = ctk.CTkFrame(pg, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        return content

    # ── 通用选择页 ────────────────────────────────
    def _selection_page(self, title, subtitle, items, attr_name, on_validate, back_page):
        pg = self._new_page()
        self._title(pg, title, subtitle)

        scroll = ctk.CTkScrollableFrame(pg, fg_color=BG, corner_radius=12,
                                        border_width=1, border_color=BORDER)
        scroll.grid(row=1, column=0, sticky="nsew", pady=(0, 4))
        scroll.grid_columnconfigure(0, weight=1)

        btns = []

        def make_pick(item, btn_ref):
            def pick():
                setattr(self, attr_name, item)
                for b in btns:
                    b.configure(fg_color=BG, border_color=BORDER, text_color=TEXT)
                btn_ref.configure(fg_color=ACCENT_DIM, border_color=ACCENT, text_color="white")
                nxt.configure(state="normal")
            return pick

        for i, item in enumerate(items):
            b = ctk.CTkButton(scroll, text=f"  {item}", anchor="w",
                              height=40, font=ctk.CTkFont(family=FONT_FAMILY, size=13),
                              corner_radius=10, fg_color=BG,
                              border_width=1, border_color=BORDER,
                              text_color=TEXT, hover_color=ACCENT_DIM)
            b.grid(row=i, column=0, sticky="ew", padx=6, pady=3)
            b.configure(command=make_pick(item, b))
            btns.append(b)

        def go():
            if not getattr(self, attr_name):
                return
            next_page = on_validate()
            if next_page is not None:
                next_page()

        nxt = self._nav_row(pg, back_page, go, next_enabled=False)

    # ══════════════════════════════════════════════
    #  扫描与识别
    # ══════════════════════════════════════════════
    def _get_all_drives(self):
        if os.name == "nt":
            return [f"{c}:\\" for c in string.ascii_uppercase if os.path.isdir(f"{c}:\\")]
        return ["/"]

    def _parse_pcl2_ini(self, ini_path):
        for enc in INI_ENCODINGS:
            try:
                with open(ini_path, "r", encoding=enc) as f:
                    for line in f:
                        if line.startswith("LaunchFolderSelect:"):
                            return line.split(":", 1)[1].strip().strip('"')
            except (UnicodeDecodeError, PermissionError):
                continue
        return None

    def _scan_directory(self, base_dir):
        """递归扫描，收集所有可能的 versions 目录"""
        candidates = []
        base_depth = base_dir.rstrip(os.sep).count(os.sep)
        try:
            walker = os.walk(base_dir, topdown=True)
        except (PermissionError, OSError):
            return []

        for dirpath, dirnames, filenames in walker:
            if dirpath.count(os.sep) - base_depth > MAX_SCAN_DEPTH:
                dirnames.clear()
                continue

            # 剪枝：跳过系统目录和 PCL 临时目录
            dirnames[:] = [d for d in dirnames
                           if d not in SKIP_DIRS and not d.startswith("$")]

            if "tasktemp" in dirpath.lower():
                continue

            try:
                for fn in filenames:
                    if fn in PCL2_EXES:
                        for ini_rel in INI_NAMES:
                            ini = os.path.join(dirpath, ini_rel)
                            if os.path.isfile(ini):
                                val = self._parse_pcl2_ini(ini)
                                if val:
                                    mc = self._resolve_mc_path(dirpath, val)
                                    vp = os.path.join(mc, "versions")
                                    if os.path.isdir(vp):
                                        candidates.append(vp)
                        break

                if ".minecraft" in dirnames:
                    vp = os.path.join(dirpath, ".minecraft", "versions")
                    if os.path.isdir(vp):
                        candidates.append(vp)

                if "versions" in dirnames:
                    vp = os.path.join(dirpath, "versions")
                    if os.path.isdir(vp):
                        candidates.append(vp)

                if os.path.basename(dirpath).lower() == "versions":
                    candidates.append(dirpath)
            except (PermissionError, OSError):
                continue

        return candidates

    def _score_version_path(self, vp):
        """打分排序，分数越高越可能是真实游戏目录"""
        score = 0
        mc_dir = os.path.dirname(vp)

        if "tasktemp" in vp.lower():
            score -= 1000
        if "\\temp\\" in vp.lower() or vp.lower().startswith(os.path.expandvars("%TEMP%").lower()):
            score -= 500

        saves_dir = os.path.join(mc_dir, "saves")
        if os.path.isdir(saves_dir) and os.listdir(saves_dir):
            score += 50

        mods_dir = os.path.join(mc_dir, "mods")
        if os.path.isdir(mods_dir):
            try:
                if any(f.lower().endswith(".jar") for f in os.listdir(mods_dir)):
                    score += 30
            except (PermissionError, OSError):
                pass

        try:
            if any(os.path.isfile(os.path.join(vp, d, f"{d}.json"))
                   for d in os.listdir(vp) if os.path.isdir(os.path.join(vp, d))):
                score += 20
        except (PermissionError, OSError):
            pass

        user_home = os.path.expanduser("~").lower()
        if vp.lower().startswith(user_home):
            score += 10

        return score

    def _pick_best_version(self, candidates):
        if not candidates:
            return None
        candidates = list(dict.fromkeys(candidates))  # 去重保序
        return max(candidates, key=lambda p: self._score_version_path(p))

    # ── 配置文件 ─────────────────────────────────────
    def _load_saved_path(self):
        """读取同目录下配置，返回已保存的 versions_path（有效则返回，否则 None）"""
        cfg = _config_file()
        if not os.path.isfile(cfg):
            return None
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                saved = json.load(f).get("versions_path")
            if saved and os.path.isdir(saved):
                return saved
        except (json.JSONDecodeError, IOError, PermissionError):
            pass
        return None

    def _save_path_config(self, path, save_location=None):
        """将 versions_path 与 save_location 写入同目录配置"""
        try:
            cfg = _config_file()
            data = {"versions_path": path}
            if save_location:
                data["save_location"] = save_location
            # 保留已有的 save_location
            if os.path.isfile(cfg):
                try:
                    with open(cfg, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                    if "save_location" in existing and save_location is None:
                        data["save_location"] = existing["save_location"]
                except (json.JSONDecodeError, IOError):
                    pass
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except (IOError, PermissionError):
            pass

    def _load_save_location(self, versions_path):
        """读取上次保存的备份位置"""
        cfg = _config_file()
        try:
            if os.path.isfile(cfg):
                with open(cfg, "r", encoding="utf-8") as f:
                    return json.load(f).get("save_location")
        except (json.JSONDecodeError, IOError, PermissionError):
            pass
        return None

    def _clear_path_config(self):
        cfg = _config_file()
        try:
            if os.path.isfile(cfg):
                os.remove(cfg)
        except (IOError, PermissionError):
            pass

    def _resolve_mc_path(self, base, val):
        if val.startswith("$"):
            return os.path.join(base, val.lstrip("$").rstrip("\\").rstrip("/"))
        if os.path.isabs(val):
            return val
        return os.path.join(base, val)

    def _full_scan(self):
        all_candidates = []
        for drive in self._get_all_drives():
            if self._scan_cancel:
                return None
            try:
                results = self._scan_directory(drive)
                all_candidates.extend(results)
            except (PermissionError, OSError):
                continue
        if not all_candidates or self._scan_cancel:
            return None
        return self._pick_best_version(all_candidates)

    def _resolve_versions(self, d):
        """从用户选择的目录向上/向下解析出 versions 目录"""
        if os.path.basename(d).lower() == "versions":
            return d
        for sub in [os.path.join(d, "versions"), os.path.join(d, ".minecraft", "versions"),
                    os.path.join(d, ".minecraft")]:
            if os.path.isdir(sub):
                if os.path.basename(sub).lower() == "versions":
                    return sub
                return os.path.join(sub, "versions")

        for exe in PCL2_EXES:
            if os.path.isfile(os.path.join(d, exe)):
                for ini_rel in INI_NAMES:
                    ini = os.path.join(d, ini_rel)
                    if os.path.isfile(ini):
                        val = self._parse_pcl2_ini(ini)
                        if val:
                            vp = os.path.join(self._resolve_mc_path(d, val), "versions")
                            if os.path.isdir(vp):
                                return vp
        return None

    # ── 扫描 UI ───────────────────────────────────
    def _build_scan_ui(self, pg, on_set_path):
        """
        智能扫描 UI：
        - 有已保存且有效的路径 → 直接使用，不扫描
        - 否则启动全盘扫描
        """
        scan_frame = ctk.CTkFrame(pg, fg_color="transparent")
        scan_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        scan_frame.grid_columnconfigure(1, weight=1)
        self._scan_frame = scan_frame

        scan_bar = ctk.CTkProgressBar(scan_frame, width=200)
        scan_bar.grid(row=0, column=0, padx=(0, 12))
        scan_bar.start()

        ctk.CTkLabel(scan_frame, text="正在全盘扫描，请稍候...",
                     font=ctk.CTkFont(family=FONT_FAMILY, size=12), text_color=TEXT_SEC
                     ).grid(row=0, column=1, sticky="w")

        cancel_btn = ctk.CTkButton(scan_frame, text="跳过扫描", width=90, height=30,
                                   font=ctk.CTkFont(family=FONT_FAMILY, size=11), corner_radius=8,
                                   fg_color="transparent", border_width=1, border_color=BORDER,
                                   text_color=TEXT_DIM)

        def on_cancel():
            self._scan_cancel = True
            scan_frame.grid_remove()
            messagebox.showinfo("提示", "已跳过扫描，请手动选择 versions 文件夹")

        cancel_btn.configure(command=on_cancel)
        cancel_btn.grid(row=0, column=2, padx=(12, 0))

        # 尝试复用已保存路径
        saved_path = self._load_saved_path()
        if saved_path and os.path.isdir(saved_path):
            scan_bar.stop()
            scan_frame.grid_remove()
            self.versions_path = saved_path
            self._save_path_config(saved_path)
            on_set_path(saved_path)
            return

        self._scan_cancel = False

        def scan_worker():
            result = self._full_scan()
            self.after(0, lambda: on_scan_done(result))

        def on_scan_done(result):
            if not scan_frame.winfo_exists():
                return
            scan_bar.stop()
            scan_frame.grid_remove()
            if self._scan_cancel:
                return
            if result:
                self.versions_path = result
                self._save_path_config(result)
                on_set_path(result)
            else:
                messagebox.showwarning("提示", "未识别到版本文件夹，请手动选择")

        threading.Thread(target=scan_worker, daemon=True).start()

    # ══════════════════════════════════════════════
    #  通用路径选择页（存档 & 模组共用）
    # ══════════════════════════════════════════════
    def _build_path_page(self, subtitle, back_tab, filter_fn, next_goto):
        """构建"选择 versions 路径"页面，存档和模组共用"""
        pg = self._new_page()
        self._title(pg, "选择 versions 文件夹", subtitle)
        content = self._make_content(pg)

        # 路径输入框卡片
        card = Card(content)
        card.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        card.grid_columnconfigure(0, weight=1)

        entry = ctk.CTkEntry(card, height=40, corner_radius=10,
                             font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                             placeholder_text="  如 C:\\...\\.minecraft\\versions",
                             border_width=1, border_color=BORDER, fg_color=BG)
        entry.grid(row=0, column=0, sticky="ew", padx=14, pady=14)

        def set_path(d):
            self._scan_cancel = True
            self.versions_path = d
            entry.delete(0, "end")
            entry.insert(0, d)
            nxt.configure(state="normal")
            self._save_path_config(d)

        def browse():
            d = filedialog.askdirectory(title="选择 versions 文件夹")
            if not d:
                return
            resolved = self._resolve_versions(d)
            if resolved:
                set_path(resolved)
            else:
                messagebox.showerror("错误", "无法识别该目录下的 versions 文件夹")

        ctk.CTkButton(card, text="浏览文件夹", width=120, height=40,
                      font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                      corner_radius=10, fg_color=ACCENT, hover_color=ACCENT_DIM,
                      command=browse).grid(row=0, column=1, padx=(0, 14), pady=14)

        def go():
            if not self.versions_path:
                return
            if not os.path.isdir(self.versions_path):
                self._clear_path_config()
                self.versions_path = None
                entry.delete(0, "end")
                messagebox.showwarning("提示", "保存的路径已失效，请重新选择")
                return
            versions = filter_fn()
            if not versions:
                messagebox.showwarning("提示", "该目录下没有找到有效内容！")
                return
            next_goto(versions)

        nxt = self._nav_row(pg, lambda: self._show_tab(back_tab), go, next_enabled=False)
        self._build_scan_ui(content, set_path)
        return pg

    # ══════════════════════════════════════════════
    #  存档备份 — 数据
    # ══════════════════════════════════════════════
    def _has_real_save(self, path):
        try:
            for dp, _, fs in os.walk(path):
                if "level.dat" in fs:
                    return True
        except (PermissionError, OSError):
            pass
        return False

    def _filter_save_versions(self):
        if not self.versions_path or not os.path.isdir(self.versions_path):
            return []
        result = []
        try:
            for d in sorted(os.listdir(self.versions_path)):
                vp = os.path.join(self.versions_path, d)
                if not os.path.isdir(vp) or d in NON_VERSION_DIRS:
                    continue
                sd = os.path.join(vp, "saves")
                if not os.path.isdir(sd):
                    continue
                try:
                    for sn in os.listdir(sd):
                        sp = os.path.join(sd, sn)
                        if os.path.isdir(sp) and self._has_real_save(sp):
                            result.append(d)
                            break
                except (PermissionError, OSError):
                    pass
        except (PermissionError, OSError):
            pass
        return result

    def _load_saves(self):
        if not self.versions_path or not self.save_selected_version:
            return []
        sd = os.path.join(self.versions_path, self.save_selected_version, "saves")
        if not os.path.isdir(sd):
            return []
        try:
            return sorted(d for d in os.listdir(sd)
                          if os.path.isdir(os.path.join(sd, d))
                          and self._has_real_save(os.path.join(sd, d)))
        except (PermissionError, OSError):
            return []

    # ══════════════════════════════════════════════
    #  模组备份 — 数据
    # ══════════════════════════════════════════════
    def _filter_mod_versions(self):
        if not self.versions_path or not os.path.isdir(self.versions_path):
            return []
        result = []
        try:
            for d in sorted(os.listdir(self.versions_path)):
                vp = os.path.join(self.versions_path, d)
                if not os.path.isdir(vp) or d in NON_VERSION_DIRS:
                    continue
                mods_dir = os.path.join(vp, "mods")
                if os.path.isdir(mods_dir):
                    try:
                        if any(f.lower().endswith(".jar") for f in os.listdir(mods_dir)
                               if os.path.isfile(os.path.join(mods_dir, f))):
                            result.append(d)
                    except (PermissionError, OSError):
                        pass
        except (PermissionError, OSError):
            pass
        return result

    def _load_mods(self):
        if not self.versions_path or not self.mod_selected_version:
            return []
        mods_dir = os.path.join(self.versions_path, self.mod_selected_version, "mods")
        if not os.path.isdir(mods_dir):
            return []
        try:
            return [(f, os.path.getsize(os.path.join(mods_dir, f)) / (1024 * 1024))
                    for f in sorted(os.listdir(mods_dir))
                    if os.path.isfile(os.path.join(mods_dir, f)) and f.lower().endswith(".jar")]
        except (PermissionError, OSError):
            return []

    # ══════════════════════════════════════════════
    #  通用确认备份页
    # ══════════════════════════════════════════════
    def _build_confirm_page(self, title, info_pairs, source_dirs, back_page, done_message,
                             version=None, backup_type="save"):
        """
        通用确认 + 备份页。
        - info_pairs: [(标签, 值), ...] 显示的信息
        - source_dirs: list of (src, dst_name) 需要复制的源
        - back_page: 返回上一页的回调
        - done_message: 成功后的提示信息模板
        - version: 游戏版本号，用于创建版本子文件夹
        - backup_type: "save"（存档）或 "mod"（模组），决定命名规则
        """
        pg = self._new_page()
        self._title(pg, title, "核对信息后选择保存位置")

        content = self._make_content(pg)

        # 信息卡片
        card = Card(content)
        card.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        card.grid_columnconfigure(1, weight=1)

        for i, (label, val) in enumerate(info_pairs):
            ctk.CTkLabel(card, text=label, anchor="w",
                         font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                         text_color=TEXT_SEC).grid(row=i, column=0, sticky="w", padx=16, pady=8)
            ctk.CTkLabel(card, text=val, anchor="w",
                         font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
                         text_color=TEXT).grid(row=i, column=1, sticky="w", padx=(0, 16), pady=8)

        # 保存位置卡片
        loc_card = Card(content)
        loc_card.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        loc_card.grid_columnconfigure(0, weight=1)

        loc_frame = ctk.CTkFrame(loc_card, fg_color="transparent")
        loc_frame.grid(row=0, column=0, sticky="ew", padx=14, pady=14)
        loc_frame.grid_columnconfigure(0, weight=1)

        loc_entry = ctk.CTkEntry(loc_frame, height=40, corner_radius=10,
                                 font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                                 placeholder_text="  请选择一个文件夹...", state="readonly",
                                 border_width=1, border_color=BORDER, fg_color=BG)
        loc_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        # 进度区（独立容器，初始隐藏）
        progress_frame = ctk.CTkFrame(content, fg_color="transparent")
        pbar = ctk.CTkProgressBar(progress_frame)
        pbar.grid(row=0, column=0, sticky="ew", pady=(8, 4))
        plbl = ctk.CTkLabel(progress_frame, text="",
                            font=ctk.CTkFont(family=FONT_FAMILY, size=12))
        plbl.grid(row=1, column=0, sticky="w")

        # 默认保存位置：从 JSON 配置中读取（首次使用为空）
        _saved_loc = self._load_save_location(self.versions_path)
        if _saved_loc and os.path.isdir(_saved_loc):
            _base = _saved_loc
            setattr(self, "save_save_path" if backup_type == "save" else "mod_save_path", _base)
        else:
            _base = None

        def browse_loc():
            init = _base if _base else os.path.expanduser("~")
            d = filedialog.askdirectory(title="选择备份保存位置", initialdir=init)
            if d:
                setattr(self, "save_save_path" if backup_type == "save" else "mod_save_path", d)
                loc_entry.configure(state="normal")
                loc_entry.delete(0, "end")
                loc_entry.insert(0, d)
                loc_entry.configure(state="readonly")
                # 保存到 JSON
                if self.versions_path:
                    self._save_path_config(self.versions_path, save_location=d)

        ctk.CTkButton(loc_frame, text="选择位置", width=110, height=40,
                      font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                      corner_radius=10, fg_color=ACCENT, hover_color=ACCENT_DIM,
                      command=browse_loc).grid(row=0, column=1)

        # 如果已有保存位置则显示，否则留空
        if _base:
            loc_entry.configure(state="normal")
            loc_entry.insert(0, _base)
            loc_entry.configure(state="readonly")

        def do_backup():
            if backup_type == "save":
                sp = getattr(self, "save_save_path")
            else:
                sp = getattr(self, "mod_save_path")

            # 确保保存位置已写入 JSON
            if sp and self.versions_path:
                self._save_path_config(self.versions_path, save_location=sp)

            backup_btn.configure(state="disabled", text="备份中...")
            progress_frame.grid(row=2, column=0, sticky="ew")
            pbar.start()
            plbl.configure(text="正在复制文件，请稍候...", text_color=TEXT_SEC)

            def worker():
                try:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

                    # 目标根目录：选择的位置/MCsaves/版本名/
                    mc_saves_dir = os.path.join(sp, "MCsaves")
                    os.makedirs(mc_saves_dir, exist_ok=True)

                    if version:
                        ver_dir = os.path.join(mc_saves_dir, version)
                        os.makedirs(ver_dir, exist_ok=True)
                    else:
                        ver_dir = mc_saves_dir

                    total_size = 0
                    copied = 0
                    details = []

                    if backup_type == "save":
                        # 存档备份：每个存档复制为 "存档名_时间" 文件夹
                        for src, name_hint in source_dirs:
                            dst_name = f"{name_hint}_{ts}"
                            item_dst = os.path.join(ver_dir, dst_name)

                            if os.path.isdir(src):
                                shutil.copytree(src, item_dst)
                            else:
                                shutil.copy2(src, item_dst)

                            if os.path.isdir(item_dst):
                                for dp, _, fs in os.walk(item_dst):
                                    for f in fs:
                                        total_size += os.path.getsize(os.path.join(dp, f))
                            else:
                                total_size += os.path.getsize(item_dst)
                            copied += 1
                            details.append(os.path.basename(src))

                    else:
                        # 模组备份：先新建 "mods_时间" 文件夹，再把每个 jar 原样复制进去
                        dst_name = f"mods_{ts}"
                        item_dst = os.path.join(ver_dir, dst_name)
                        os.makedirs(item_dst, exist_ok=True)

                        for src, name_hint in source_dirs:
                            if os.path.isdir(src):
                                # 模组以文件夹形式存在时，整个复制进去
                                base = os.path.basename(src.rstrip(os.sep))
                                target = os.path.join(item_dst, base)
                                if os.path.exists(target):
                                    shutil.rmtree(target)
                                shutil.copytree(src, target)
                            else:
                                # 普通文件（.jar 等），原样复制到文件夹内，不改名
                                shutil.copy2(src, item_dst)

                            if os.path.isdir(src):
                                sz = 0
                                for dp, _, fs in os.walk(src):
                                    for f in fs:
                                        sz += os.path.getsize(os.path.join(dp, f))
                                total_size += sz
                            else:
                                total_size += os.path.getsize(src)
                            copied += 1
                            details.append(os.path.basename(src))

                    self.after(0, lambda: done(True, copied, total_size / (1024 * 1024), ver_dir, details))
                except Exception as e:
                    self.after(0, lambda: done(False, 0, 0, str(e), []))

            threading.Thread(target=worker, daemon=True).start()

        def done(ok, count, mb, dst, details):
            pbar.stop()
            progress_frame.grid_remove()
            if ok:
                plbl.configure(text=f"备份完成  {mb:.1f} MB",
                               text_color=GREEN,
                               font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"))
                backup_btn.configure(state="normal", text="再次备份")
                msg = done_message.format(count=count, mb=mb, dst=dst,
                                           details=", ".join(details) if details else "全部")
                messagebox.showinfo("备份成功", msg)
            else:
                plbl.configure(text=f"备份失败：{dst}", text_color=RED,
                               font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"))
                backup_btn.configure(state="normal", text="重新备份")

        # 导航栏
        nav = ctk.CTkFrame(pg, fg_color="transparent")
        nav.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        nav.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(nav, text="←  上一步", width=110, height=38,
                      fg_color="transparent", border_width=1, border_color=BORDER,
                      font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                      text_color=TEXT_SEC, corner_radius=10,
                      command=back_page).grid(row=0, column=0, sticky="w")

        backup_btn = ctk.CTkButton(nav, text="开始备份", width=160, height=40,
                                   font=ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
                                   fg_color=GREEN, hover_color=GREEN_HOV,
                                   corner_radius=10, command=do_backup, state="normal")
        backup_btn.grid(row=0, column=2, sticky="e")

    # ══════════════════════════════════════════════
    #  存档备份流程
    # ══════════════════════════════════════════════
    def _save_goto(self, n):
        {1: self._save_p1, 2: self._save_p2, 3: self._save_p3, 4: self._save_p4}[n]()

    def _save_p1(self):
        self._build_path_page(
            "定位你 Minecraft 的 versions 目录",
            back_tab=1,
            filter_fn=self._filter_save_versions,
            next_goto=lambda versions: (setattr(self, 'save_versions', versions) or self._save_goto(2))
        )

    def _save_p2(self):
        def on_validate():
            self.save_saves = self._load_saves()
            if not self.save_saves:
                messagebox.showwarning("提示", "该版本没有找到任何存档！")
                return None
            return self._save_p3

        self._selection_page(
            "选择游戏版本",
            f"共发现 {len(self.save_versions)} 个版本，点击选择",
            self.save_versions, "save_selected_version",
            on_validate, lambda: self._save_goto(1)
        )

    def _save_p3(self):
        pg = self._new_page()
        self._title(pg, "选择要备份的存档",
                    f"{self.save_selected_version}  ·  共 {len(self.save_saves)} 个存档")

        scroll = ctk.CTkScrollableFrame(pg, fg_color=BG, corner_radius=12,
                                        border_width=1, border_color=BORDER)
        scroll.grid(row=1, column=0, sticky="nsew", pady=(0, 4))
        scroll.grid_columnconfigure(0, weight=1)

        btns = []

        def make_pick(item, btn_ref):
            def pick():
                self.save_selected_save = item
                for b in btns:
                    b.configure(fg_color=BG, border_color=BORDER, text_color=TEXT)
                btn_ref.configure(fg_color=ACCENT_DIM, border_color=ACCENT, text_color="white")
                nxt.configure(state="normal")
            return pick

        for i, item in enumerate(self.save_saves):
            b = ctk.CTkButton(scroll, text=f"  {item}", anchor="w", height=40,
                              font=ctk.CTkFont(family=FONT_FAMILY, size=13), corner_radius=10,
                              fg_color=BG, border_width=1, border_color=BORDER,
                              text_color=TEXT, hover_color=ACCENT_DIM)
            b.grid(row=i, column=0, sticky="ew", padx=6, pady=3)
            b.configure(command=make_pick(item, b))
            btns.append(b)

        def go():
            if not self.save_selected_save:
                return
            self._save_goto(4)

        nxt = self._nav_row(pg, lambda: self._save_goto(2), go, next_enabled=False)

    def _save_p4(self):
        src = os.path.join(self.versions_path, self.save_selected_version,
                           "saves", self.save_selected_save)

        self._build_confirm_page(
            "确认并备份存档",
            info_pairs=[
                ("游戏版本", self.save_selected_version),
                ("存档名称", self.save_selected_save),
            ],
            source_dirs=[(src, self.save_selected_save)],
            back_page=lambda: self._save_goto(3),
            done_message="存档已备份！\n\n大小：{mb:.1f} MB\n位置：{dst}",
            version=self.save_selected_version,
            backup_type="save"
        )

    # ══════════════════════════════════════════════
    #  模组备份流程
    # ══════════════════════════════════════════════
    def _mod_goto(self, n):
        {1: self._mod_p1, 2: self._mod_p2, 3: self._mod_p3, 4: self._mod_p4}[n]()

    def _mod_p1(self):
        self._build_path_page(
            "定位你 Minecraft 的 versions 目录（模组备份）",
            back_tab=0,
            filter_fn=self._filter_mod_versions,
            next_goto=lambda versions: (setattr(self, 'mod_versions', versions) or self._mod_goto(2))
        )

    def _mod_p2(self):
        def on_validate():
            self.mod_mods = self._load_mods()
            if not self.mod_mods:
                messagebox.showwarning("提示", "该版本的 mods 文件夹中没有找到 .jar 模组文件！")
                return None
            return self._mod_p3

        self._selection_page(
            "选择游戏版本",
            f"共发现 {len(self.mod_versions)} 个版本（含 mods），点击选择",
            self.mod_versions, "mod_selected_version",
            on_validate, lambda: self._mod_goto(1)
        )

    def _mod_p3(self):
        pg = self._new_page()
        self._title(pg, "选择要备份的模组",
                    f"{self.mod_selected_version}  ·  共 {len(self.mod_mods)} 个模组")

        content = self._make_content(pg)
        content.grid_rowconfigure(1, weight=1)

        # 工具栏
        tool_frame = ctk.CTkFrame(content, fg_color="transparent")
        tool_frame.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        tool_frame.grid_columnconfigure(2, weight=1)

        count_lbl = ctk.CTkLabel(tool_frame, text=f"已选 {len(self.mod_mods)} / {len(self.mod_mods)}",
                                  font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
                                  text_color=ACCENT)
        count_lbl.grid(row=0, column=0, sticky="w")

        btn_frame = ctk.CTkFrame(tool_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=2, sticky="e")

        # 列表区
        scroll = ctk.CTkScrollableFrame(content, fg_color=BG, corner_radius=12,
                                        border_width=1, border_color=BORDER)
        scroll.grid(row=1, column=0, sticky="nsew", pady=(0, 4))
        scroll.grid_columnconfigure(0, weight=1)

        self.mod_selected_mods = [m[0] for m in self.mod_mods]
        check_vars = []

        def update_count():
            cnt = sum(1 for v in check_vars if v.get())
            count_lbl.configure(text=f"已选 {cnt} / {len(self.mod_mods)}")
            nxt_btn.configure(state="normal" if cnt > 0 else "disabled")

        for i, (fname, size_mb) in enumerate(self.mod_mods):
            row_f = ctk.CTkFrame(scroll, fg_color="transparent")
            row_f.grid(row=i, column=0, sticky="ew", padx=6, pady=2)
            row_f.grid_columnconfigure(1, weight=1)

            var = ctk.BooleanVar(value=True)
            check_vars.append(var)

            ctk.CTkCheckBox(row_f, text="", variable=var, width=24,
                            command=update_count).grid(row=0, column=0, padx=(4, 8))
            ctk.CTkLabel(row_f, text=fname, anchor="w",
                         font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                         text_color=TEXT).grid(row=0, column=1, sticky="ew")
            ctk.CTkLabel(row_f, text=f"{size_mb:.1f} MB",
                         font=ctk.CTkFont(family=FONT_FAMILY, size=11),
                         text_color=TEXT_DIM).grid(row=0, column=2, padx=(8, 4))

        def select_all():
            for v in check_vars:
                v.set(True)
            update_count()

        def select_none():
            for v in check_vars:
                v.set(False)
            update_count()

        def invert():
            for v in check_vars:
                v.set(not v.get())
            update_count()

        for col, (text, cmd) in enumerate([("全选", select_all), ("全不选", select_none), ("反选", invert)]):
            ctk.CTkButton(btn_frame, text=text, width=70, height=28,
                          font=ctk.CTkFont(family=FONT_FAMILY, size=11), corner_radius=8,
                          fg_color="transparent", border_width=1, border_color=BORDER,
                          text_color=TEXT_SEC, command=cmd).grid(row=0, column=col, padx=2)

        def go():
            self.mod_selected_mods = [self.mod_mods[i][0]
                                      for i, v in enumerate(check_vars) if v.get()]
            if not self.mod_selected_mods:
                return
            self._mod_goto(4)

        nxt_btn = self._nav_row(pg, lambda: self._mod_goto(2), go, next_enabled=True)

    def _mod_p4(self):
        src_dir = os.path.join(self.versions_path, self.mod_selected_version, "mods")

        # 构建源文件列表
        source_dirs = [(os.path.join(src_dir, fname), fname)
                       for fname in self.mod_selected_mods]

        self._build_confirm_page(
            "确认并备份模组",
            info_pairs=[
                ("游戏版本", self.mod_selected_version),
                ("模组数量", f"{len(self.mod_selected_mods)} 个"),
            ],
            source_dirs=source_dirs,
            back_page=lambda: self._mod_goto(3),
            done_message="模组已备份！\n\n数量：{count} 个\n大小：{mb:.1f} MB\n位置：{dst}",
            version=self.mod_selected_version,
            backup_type="mod"
        )


def main():
    app = MCToolboxApp()
    app.mainloop()


if __name__ == "__main__":
    main()
