"""
Minecraft 工具箱 — 存档备份 & 模组备份 & 存档配置
CustomTkinter 深色主题 · 响应式布局 · 智能路径记忆
"""

import os
import sys
import string
import json
import re
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


def _now_ts():
    """备份时间戳"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _dir_size(path):
    """计算目录总大小（字节）"""
    total = 0
    try:
        for dp, _, fs in os.walk(path):
            for f in fs:
                try:
                    total += os.path.getsize(os.path.join(dp, f))
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError):
        pass
    return total


def _center(win, width, height):
    """窗口居中"""
    win.update_idletasks()
    x = (win.winfo_screenwidth() // 2) - (width // 2)
    y = (win.winfo_screenheight() // 2) - (height // 2)
    win.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")


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

        # 存档配置状态
        self.cfg_saves_root = None          # MCsaves 根目录
        self.cfg_saved_saves = []           # [(name, version, src), ...]
        self.cfg_selected_items = []        # 本次选中的存档 [(name, version, src), ...]
        self.cfg_selected_save = None       # 选中的存档名
        self.cfg_selected_version = None    # 选中存档对应的版本
        self.cfg_selected_save_path = None  # 选中存档的完整路径

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
        tabbar.grid_columnconfigure((0, 1, 2), weight=1)

        self.tab_btns = []
        for i, name in enumerate(["存档备份", "模组备份", "存档配置"]):
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
        # 切 tab 时重置 cfg 跳转记忆，否则跨 tab 切回会命中早退而不显示
        self._cfg_last_page = None
        # 隐藏已失效的缓存页，避免后续复用拿到死引用
        for pg in getattr(self, '_pages', {}).values():
            if not pg.winfo_exists():
                continue
            pg.grid_remove()
        if idx == 0:
            self._save_goto(1)
        elif idx == 1:
            self._mod_goto(1)
        else:
            self._cfg_goto(1)

    def _new_page(self, key=None):
        """创建/复用页面。
        - key 为 None 时按原行为：销毁旧页面并新建（用于 save/mod 流程）；
        - key 非 None 时：若已存在同名页面则直接复用，只隐藏/显示，不重建 widget 树。
        这是消除卡顿最关键的一步：存档配置的三个步骤页面只构建一次。
        """
        if key is None:
            if self.page:
                # 若当前页是缓存页（cfg_xxx），销毁后必须从 _pages 移除，否则下次复用会拿到死引用
                pages = getattr(self, '_pages', None)
                if pages:
                    for k, v in list(pages.items()):
                        if v == self.page:
                            del pages[k]
                            break
                self._scan_frame = None
                self.page.destroy()
            pg = ctk.CTkFrame(self.container, fg_color="transparent")
            pg.grid(row=0, column=0, sticky="nsew")
            pg.grid_columnconfigure(0, weight=1)
            pg.grid_rowconfigure(1, weight=1)
            self.page = pg
            return pg

        # 复用模式：首次构建并缓存
        if not hasattr(self, '_pages'):
            self._pages = {}
        if key in self._pages:
            pg = self._pages[key]
            if pg.winfo_exists():
                self.page = pg
                # 把它从当前位置摘下再 grid 到顶层，确保其可见
                pg.grid(row=0, column=0, sticky="nsew")
                return pg
            # 缓存页已失效（被其他流程 destroy），移出并重建
            del self._pages[key]
        pg = ctk.CTkFrame(self.container, fg_color="transparent")
        pg.grid(row=0, column=0, sticky="nsew")
        pg.grid_columnconfigure(0, weight=1)
        pg.grid_rowconfigure(1, weight=1)
        self._pages[key] = pg
        self.page = pg
        return pg

    def _title(self, pg, title, subtitle):
        """标题区固定在 row=0，副标题紧贴主标题"""
        hdr = ctk.CTkFrame(pg, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr, text=title, font=ctk.CTkFont(family=FONT_FAMILY, size=18, weight="bold"),
                     text_color=TEXT).grid(row=0, column=0, sticky="w", pady=(0, 1))
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
        setattr(self, attr_name, None)

        def make_pick(item, btn_ref):
            def pick():
                setattr(self, attr_name, item)
                for b in btns:
                    b.configure(fg_color=BG, border_color=BORDER, text_color=TEXT)
                btn_ref.configure(fg_color=ACCENT_DIM, border_color=ACCENT, text_color="white")
                nxt.configure(state="normal")
            return pick

        def render_row(parent, i, item, update=False):
            rf = parent
            if update:
                btn = rf._btn
                btn.configure(text=f"  {item}", command=make_pick(item, btn))
                return
            rf.grid(row=i, column=0, sticky="ew", padx=6, pady=3)
            rf.grid_columnconfigure(0, weight=1)
            b = ctk.CTkButton(rf, text=f"  {item}", anchor="w",
                              height=40, font=ctk.CTkFont(family=FONT_FAMILY, size=13),
                              corner_radius=10, fg_color=BG,
                              border_width=1, border_color=BORDER,
                              text_color=TEXT, hover_color=ACCENT_DIM)
            b.grid(row=0, column=0, sticky="ew")
            b.configure(command=make_pick(item, b))
            rf._btn = b
            btns.append(b)

        self._build_list(scroll, items, render_row, "没有可选项")

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
        """递归扫描，收集所有可能的 versions 目录。
        性能优化：
        - 延迟 os.path.isdir 判定，只在确定候选后再查；
        - 提前缓存 sep / join / isdir，减少属性查找；
        - 命中 versions 目录后及时跳出当前分支，避免向下重复扫描。
        """
        candidates = []
        _isdir = os.path.isdir
        _join = os.path.join
        _basename = os.path.basename
        try:
            walker = os.walk(base_dir, topdown=True)
        except (PermissionError, OSError):
            return []

        base_depth = base_dir.rstrip(os.sep).count(os.sep)
        max_depth = MAX_SCAN_DEPTH
        skip = SKIP_DIRS
        exes = PCL2_EXES
        ini_names = INI_NAMES
        resolve = self._resolve_mc_path
        parse_ini = self._parse_pcl2_ini

        for dirpath, dirnames, filenames in walker:
            depth = dirpath.count(os.sep) - base_depth
            if depth > max_depth:
                del dirnames[:]
                continue

            # 剪枝：跳过系统目录 / 以 $ 开头的隐藏目录 / TaskTemp
            if "tasktemp" in dirpath.lower():
                continue
            dirnames[:] = [d for d in dirnames
                           if d[0] != "$" and d not in skip]

            try:
                lower_dirs = set(d.lower() for d in dirnames)
                found_here = False

                # 1) 命中 PCL2 启动器 EXE
                if any(fn in exes for fn in filenames):
                    for ini_rel in ini_names:
                        ini = _join(dirpath, ini_rel)
                        if _isdir(ini) or os.path.isfile(ini):
                            # ini 可能是文件也可能是目录
                            pass
                    for fn in filenames:
                        if fn in exes:
                            for ini_rel in ini_names:
                                ini = _join(dirpath, ini_rel)
                                if os.path.isfile(ini):
                                    val = parse_ini(ini)
                                    if val:
                                        vp = _join(resolve(dirpath, val), "versions")
                                        if _isdir(vp):
                                            candidates.append(vp)
                            break

                # 2) 命中 .minecraft / versions 子目录
                if "versions" in lower_dirs:
                    # 这里 lower_dirs 是已 lower 的，需精确匹配原始名
                    for d in dirnames:
                        if d.lower() == "versions":
                            candidates.append(_join(dirpath, d))
                            found_here = True
                            break
                elif ".minecraft" in lower_dirs:
                    for d in dirnames:
                        if d.lower() == ".minecraft":
                            vp = _join(dirpath, d, "versions")
                            if _isdir(vp):
                                candidates.append(vp)
                            break

                # 3) 当前目录本身就叫 versions
                if _basename(dirpath).lower() == "versions":
                    candidates.append(dirpath)
            except (PermissionError, OSError):
                continue

        return candidates

    def _score_version_path(self, vp):
        """打分排序，分数越高越可能是真实游戏目录。
        优化：每个 listdir 只调用一次并缓存结果，避免重复磁盘访问。
        """
        score = 0
        vp_l = vp.lower()
        if "tasktemp" in vp_l:
            score -= 1000
        temp = os.path.expandvars("%TEMP%").lower()
        if "\\temp\\" in vp_l or vp_l.startswith(temp):
            score -= 500

        mc_dir = os.path.dirname(vp)
        try:
            mc_children = os.listdir(mc_dir)
        except (PermissionError, OSError):
            mc_children = []
        mc_lower = {c.lower() for c in mc_children}

        if "saves" in mc_lower:
            try:
                if os.listdir(os.path.join(mc_dir, "saves")):
                    score += 50
            except (PermissionError, OSError):
                pass

        if "mods" in mc_lower:
            mods_dir = os.path.join(mc_dir, "mods")
            try:
                if any(f.lower().endswith(".jar") for f in os.listdir(mods_dir)):
                    score += 30
            except (PermissionError, OSError):
                pass

        try:
            for d in os.listdir(vp):
                sub = os.path.join(vp, d)
                if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, f"{d}.json")):
                    score += 20
                    break
        except (PermissionError, OSError):
            pass

        user_home = os.path.expanduser("~").lower()
        if vp_l.startswith(user_home):
            score += 10

        return score

    def _pick_best_version(self, candidates):
        if not candidates:
            return None
        candidates = list(dict.fromkeys(candidates))  # 去重保序
        return max(candidates, key=lambda p: self._score_version_path(p))

    # ── 配置文件 ─────────────────────────────────────
    def _load_json(self):
        """读取同目录下配置，返回 dict（无效时返回空 dict）"""
        cfg = _config_file()
        if not os.path.isfile(cfg):
            return {}
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except (json.JSONDecodeError, IOError, PermissionError):
            return {}

    def _save_json(self, versions_path=None, save_location=None):
        """将 versions_path 与 save_location 写入同目录配置（增量更新）"""
        cfg = _config_file()
        data = {}
        if os.path.isfile(cfg):
            try:
                with open(cfg, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
            except (json.JSONDecodeError, IOError):
                data = {}
        if versions_path is not None:
            data["versions_path"] = versions_path
        if save_location is not None:
            data["save_location"] = save_location
        try:
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except (IOError, PermissionError):
            pass

    def _load_saved_path(self):
        p = self._load_json().get("versions_path")
        if p and os.path.isdir(p):
            return p
        return None

    def _load_save_location(self):
        return self._load_json().get("save_location")

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

    # ── 存档/模组真实性判断 ───────────────────────
    def _has_level_dat(self, path):
        """判断是否含 level.dat（真正的 MC 存档）。首层命中即返回，避免无意义深递归。"""
        try:
            for dp, _, fs in os.walk(path):
                if "level.dat" in fs:
                    return True
        except (PermissionError, OSError):
            pass
        return False

    def _is_real_save(self, path):
        """判定是否为真实 MC 存档（必须含 level.dat）"""
        if not os.path.isdir(path):
            return False
        return self._has_level_dat(path)

    def _is_version_dir(self, path):
        """判断是否是真实版本目录（含 .jar）"""
        if not os.path.isdir(path):
            return False
        try:
            return any(f.lower().endswith(".jar")
                       for f in os.listdir(path) if os.path.isfile(os.path.join(path, f)))
        except (PermissionError, OSError):
            return False

    def _parse_version_string(self, s):
        """解析版本目录名，拆出版本号 + API。

        规则：
          - 先按分隔符 [-_/ ] 或大写字母边界切分；
          - 开头连续的数字/点组成「版本号」（如 1.21.1）；
          - 版本号之后出现 fabric / forge / neoforge / quilt / liteloader 等
            关键字，取第一个作为「API」，其后跟的数字（loader 版本）一律丢弃；
          - 返回 (version, api) 或 (None, None)。

        例：
          "1.21.1-Fabric 0.19.5"  -> ("1.21.1", "fabric")
          "1.21.1fabric"          -> ("1.21.1", "fabric")
          "1.20.1-forge-47.1.0"   -> ("1.20.1", "forge")
          "1.21.4"                -> ("1.21.4", None)
          "forge-1.20.1"          -> ("1.20.1", "forge")
        """
        if not s:
            return (None, None)
        s = s.strip()
        # 先把常见分隔符统一成空格，便于切分
        norm = re.sub(r'[-_/]', ' ', s)
        tokens = re.split(r'\s+', norm)

        api_kw = {"fabric", "forge", "neoforge", "neoforged", "quilt", "liteloader", "rift"}
        version = None
        api = None
        # 提取版本号（开头的数字.数字...）
        m = re.match(r'^(\d+(?:\.\d+)+)', s)
        if m:
            version = m.group(1)

        # 提取 API 关键字（允许紧跟版本号，如 1.21.1fabric）
        lower = s.lower()
        for kw in api_kw:
            if re.search(r'(?:^|[\s\-_/.])' + kw + r'[\s\-_.0-9]', lower) or lower.endswith(kw):
                api = kw
                break

        # 兜底：若版本号在前面被切出但没命中正则开头，用 token 拼
        if version is None:
            for t in tokens:
                mm = re.match(r'^(\d+(?:\.\d+)+)$', t)
                if mm:
                    version = mm.group(1)
                    break
        return (version, api)

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
            self._save_json(versions_path=saved_path)
            on_set_path(saved_path)
            return

        self._scan_cancel = False

        def scan_worker():
            result = self._full_scan()
            self.after(0, lambda: on_scan_done(result))

        def on_scan_done(result):
            def ui():
                if not scan_frame.winfo_exists():
                    return
                scan_bar.stop()
                scan_frame.grid_remove()
            self.after(0, ui)
            if self._scan_cancel:
                return
            if result:
                self.versions_path = result
                self._save_json(versions_path=result)
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
            self._save_json(versions_path=d)

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
    def _filter_versions(self, check_saves=True):
        """筛选有效版本目录（有 saves 或有 mods）"""
        if not self.versions_path or not os.path.isdir(self.versions_path):
            return []
        result = []
        try:
            for d in sorted(os.listdir(self.versions_path)):
                vp = os.path.join(self.versions_path, d)
                if not os.path.isdir(vp) or d in NON_VERSION_DIRS:
                    continue
                if check_saves:
                    sd = os.path.join(vp, "saves")
                    if not os.path.isdir(sd):
                        continue
                    try:
                        for sn in os.listdir(sd):
                            if self._is_real_save(os.path.join(sd, sn)):
                                result.append(d)
                                break
                    except (PermissionError, OSError):
                        pass
                else:
                    mods_dir = os.path.join(vp, "mods")
                    if not os.path.isdir(mods_dir):
                        continue
                    try:
                        if any(f.lower().endswith(".jar")
                               for f in os.listdir(mods_dir)
                               if os.path.isfile(os.path.join(mods_dir, f))):
                            result.append(d)
                    except (PermissionError, OSError):
                        pass
        except (PermissionError, OSError):
            pass
        return result

    def _filter_save_versions(self):
        return self._filter_versions(check_saves=True)

    def _filter_mod_versions(self):
        return self._filter_versions(check_saves=False)

    def _load_saves(self):
        if not self.versions_path or not self.save_selected_version:
            return []
        sd = os.path.join(self.versions_path, self.save_selected_version, "saves")
        if not os.path.isdir(sd):
            return []
        try:
            return sorted(d for d in os.listdir(sd) if self._is_real_save(os.path.join(sd, d)))
        except (PermissionError, OSError):
            return []

    # ══════════════════════════════════════════════
    #  模组备份 — 数据
    # ══════════════════════════════════════════════
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

        _saved_loc = self._load_save_location()
        save_path_attr = "save_save_path" if backup_type == "save" else "mod_save_path"
        _base = _saved_loc if _saved_loc and os.path.isdir(_saved_loc) else None
        setattr(self, save_path_attr, _base)

        def browse_loc():
            init = _base if _base else os.path.expanduser("~")
            d = filedialog.askdirectory(title="选择备份保存位置", initialdir=init)
            if d:
                setattr(self, save_path_attr, d)
                loc_entry.configure(state="normal")
                loc_entry.delete(0, "end")
                loc_entry.insert(0, d)
                loc_entry.configure(state="readonly")
                if self.versions_path:
                    self._save_json(self.versions_path, d)

        ctk.CTkButton(loc_frame, text="选择位置", width=110, height=40,
                      font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                      corner_radius=10, fg_color=ACCENT, hover_color=ACCENT_DIM,
                      command=browse_loc).grid(row=0, column=1)

        if _base:
            loc_entry.configure(state="normal")
            loc_entry.insert(0, _base)
            loc_entry.configure(state="readonly")

        def do_backup():
            sp = getattr(self, save_path_attr)
            if not sp:
                messagebox.showwarning("提示", "请先选择保存位置")
                return

            if self.versions_path:
                self._save_json(self.versions_path, sp)

            backup_btn.configure(state="disabled", text="备份中...")
            progress_frame.grid(row=2, column=0, sticky="ew")
            pbar.start()
            plbl.configure(text="正在复制文件，请稍候...", text_color=TEXT_SEC)

            def worker():
                try:
                    ts = _now_ts()
                    mc_saves_dir = os.path.join(sp, "MCsaves")
                    os.makedirs(mc_saves_dir, exist_ok=True)

                    ver_dir = os.path.join(mc_saves_dir, version) if version else mc_saves_dir
                    os.makedirs(ver_dir, exist_ok=True)

                    total_size = 0
                    copied = 0
                    details = []

                    if backup_type == "save":
                        for src, name_hint in source_dirs:
                            item_dst = os.path.join(ver_dir, f"{name_hint}_{ts}")
                            shutil.copytree(src, item_dst)
                            total_size += _dir_size(item_dst)
                            copied += 1
                            details.append(os.path.basename(src))
                    else:
                        item_dst = os.path.join(ver_dir, f"mods_{ts}")
                        os.makedirs(item_dst, exist_ok=True)
                        for src, name_hint in source_dirs:
                            if os.path.isdir(src):
                                target = os.path.join(item_dst, os.path.basename(src.rstrip(os.sep)))
                                if os.path.exists(target):
                                    shutil.rmtree(target)
                                shutil.copytree(src, target)
                                total_size += _dir_size(src)
                            else:
                                shutil.copy2(src, item_dst)
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
        self.save_selected_save = None

        def make_pick(item, btn_ref):
            def pick():
                self.save_selected_save = item
                for b in btns:
                    b.configure(fg_color=BG, border_color=BORDER, text_color=TEXT)
                btn_ref.configure(fg_color=ACCENT_DIM, border_color=ACCENT, text_color="white")
                nxt.configure(state="normal")
            return pick

        def render_row(parent, i, item, update=False):
            if update:
                btn = parent._btn
                btn.configure(text=f"  {item}", command=make_pick(item, btn))
                return
            rf = parent
            rf.grid(row=i, column=0, sticky="ew", padx=6, pady=3)
            rf.grid_columnconfigure(0, weight=1)
            b = ctk.CTkButton(rf, text=f"  {item}", anchor="w", height=40,
                              font=ctk.CTkFont(family=FONT_FAMILY, size=13), corner_radius=10,
                              fg_color=BG, border_width=1, border_color=BORDER,
                              text_color=TEXT, hover_color=ACCENT_DIM)
            b.grid(row=0, column=0, sticky="ew")
            b.configure(command=make_pick(item, b))
            rf._btn = b
            btns.append(b)

        self._build_list(scroll, self.save_saves, render_row, "该版本没有找到存档")

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

    def _cfg_import_saves(self, paths, target_version=None):
        """
        将外部存档文件夹导入到当前 MCsaves 目录。
        - 要求目标含 level.dat，否则视为无效
        - 默认归类到「未命名」版本子目录；target_version 指定时导入到对应版本
        - 导入完成后刷新列表并回到对应步骤
        """
        if not self.cfg_saves_root or not os.path.isdir(self.cfg_saves_root):
            messagebox.showwarning("提示", "请先在第 1 步确认 MCsaves 目录")
            return

        imported, failed = [], []
        ver_name = target_version or "未命名"
        ver_dir = os.path.join(self.cfg_saves_root, ver_name)
        os.makedirs(ver_dir, exist_ok=True)

        for p in paths:
            p = p.strip()
            if not p or not os.path.isdir(p):
                failed.append(os.path.basename(p) if p else "空路径")
                continue
            if not self._has_level_dat(p):
                failed.append(os.path.basename(p.rstrip(os.sep)) or p)
                continue
            try:
                name = os.path.basename(p.rstrip(os.sep))
                dst = os.path.join(ver_dir, name)
                if os.path.exists(dst):
                    dst = os.path.join(ver_dir, f"{name}_{_now_ts()}")
                shutil.copytree(p, dst)
                imported.append(name)
            except Exception as e:
                failed.append(f"{os.path.basename(p)}: {e}")

        if imported:
            messagebox.showinfo("导入成功",
                                f"成功导入 {len(imported)} 个存档到「{ver_name}」：\n" + "\n".join(imported))
        if failed:
            messagebox.showwarning("部分失败",
                                   "以下项目未能导入（非有效存档）：\n" + "\n".join(failed))

        # 刷新后回到对应步骤
        self.cfg_versions = self._cfg_list_versions(self.cfg_saves_root)
        if target_version:
            self.cfg_selected_version = target_version
            self._cfg_goto(2)
        else:
            self._cfg_goto(1)

    def _cfg_scan_saves_root(self):
        """
        从 JSON 读取 MCsaves 根目录，自动解析。
        优先级：配置中的 save_location -> 配置中的 versions_path 的父级 -> None
        """
        data = self._load_json()
        base = data.get("save_location")
        if not base or not os.path.isdir(base):
            vp = data.get("versions_path")
            if vp and os.path.isdir(vp):
                base = os.path.dirname(vp)
        if not base or not os.path.isdir(base):
            return None
        candidate = os.path.join(base, "MCsaves")
        return candidate if os.path.isdir(candidate) else None

    def _cfg_list_versions(self, root):
        """列出 MCsaves 下的一级版本目录，返回 [(name, count), ...]"""
        versions = []
        try:
            for name in sorted(os.listdir(root)):
                d = os.path.join(root, name)
                if not os.path.isdir(d):
                    continue
                cnt = sum(1 for child in os.listdir(d)
                          if os.path.isdir(os.path.join(d, child))
                          and self._is_real_save(os.path.join(d, child)))
                versions.append((name, cnt))
        except (PermissionError, OSError):
            pass
        return versions

    def _cfg_list_saves_in(self, ver_dir):
        """列出某版本目录下的真实存档，返回 [(name, src), ...]"""
        result = []
        if not ver_dir or not os.path.isdir(ver_dir):
            return result
        try:
            for name in sorted(os.listdir(ver_dir)):
                src = os.path.join(ver_dir, name)
                if os.path.isdir(src) and self._is_real_save(src):
                    display = re.sub(r"_\d{8}_\d{6}$", "", name)
                    result.append((display, src))
        except (PermissionError, OSError):
            pass
        return result

    def _build_list(self, scroll, items, render_row, empty_text):
        """统一渲染可滚动列表，行级复用，避免反复销毁重建整棵 widget 树。

        注意：CTkScrollableFrame 的 winfo_children() 包含内部 _parent_frame、
        canvas、scrollbar 等私有控件，绝不能直接拿来当行容器用。这里改为
        把行容器显式挂到 scroll._rows 上，由调用方在首次构建时负责预建。
        """
        # 清理非行类子控件（首次进入时可能残留的上一次 empty 提示等）
        rows = getattr(scroll, '_rows', None)
        if rows is None:
            rows = []
            scroll._rows = rows

        if not items:
            # 空态：隐藏所有已有行
            for rf in rows:
                rf.grid_remove()
            tag = '_empty_lbl'
            if not hasattr(scroll, tag):
                setattr(scroll, tag, ctk.CTkLabel(
                    scroll, text=empty_text,
                    font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                    text_color=TEXT_SEC))
            getattr(scroll, tag).grid(row=0, column=0, padx=14, pady=30)
            return []

        # 有数据时移除空态提示
        _e = getattr(scroll, '_empty_lbl', None)
        if _e is not None:
            _e.grid_forget()

        for i, item in enumerate(items):
            if i < len(rows):
                rf = rows[i]
                rf.grid(row=i, column=0)          # 复用：恢复位置
                render_row(rf, i, item, update=True)
            else:
                rf = ctk.CTkFrame(scroll, fg_color="transparent")
                rf.grid(row=i, column=0, sticky="ew")
                rows.append(rf)
                render_row(rf, i, item, update=False)
        # 多余行隐藏（数量减少时复用，不销毁）
        for j in range(len(items), len(rows)):
            rows[j].grid_remove()
        return items


    # ══════════════════════════════════════════════
    #  存档配置流程（Tab 3）
    # ══════════════════════════════════════════════
    def _cfg_goto(self, n):
        # 注意：这里不缓存「上次页」来做早退——跨 tab 切回时该开关会导致页面永远不显示。
        # 页面复用由 _new_page 基于 _pages 字典管理，此处每次都正常跳转。
        self._cfg_last_page = None
        {1: self._cfg_p1, 2: self._cfg_p2, 3: self._cfg_p3}[n]()


    def _cfg_p1(self):
        """第 1 步：定位 MCsaves 目录并列出版本"""
        pg = self._new_page(key="cfg_p1")
        self._title(pg, "定位 MCsaves 目录",
                    "读取配置，列出 MCsaves 下的所有版本目录")

        content = self._make_content(pg)
        content.grid_rowconfigure(3, weight=1)  # 列表卡弹性

        # 信息卡片
        card = Card(content)
        card.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        card.grid_columnconfigure(1, weight=1)

        row = 0
        ctk.CTkLabel(card, text="配置状态", anchor="w",
                     font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                     text_color=TEXT_SEC).grid(row=row, column=0, sticky="w", padx=16, pady=10)
        status_lbl = ctk.CTkLabel(card, text="正在读取配置...", anchor="w",
                                  font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
                                  text_color=TEXT)
        status_lbl.grid(row=row, column=1, sticky="w", padx=(0, 16), pady=10)
        row += 1

        ctk.CTkLabel(card, text="MCsaves 目录", anchor="w",
                     font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                     text_color=TEXT_SEC).grid(row=row, column=0, sticky="w", padx=16, pady=10)
        path_lbl = ctk.CTkLabel(card, text="—", anchor="w",
                                font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                                text_color=TEXT_SEC)
        path_lbl.grid(row=row, column=1, sticky="w", padx=(0, 16), pady=10)

        # 手动指定区
        manual_card = Card(content)
        manual_card.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        manual_card.grid_columnconfigure(0, weight=1)

        manual_frame = ctk.CTkFrame(manual_card, fg_color="transparent")
        manual_frame.grid(row=0, column=0, sticky="ew", padx=14, pady=14)
        manual_frame.grid_columnconfigure(0, weight=1)

        manual_entry = ctk.CTkEntry(manual_frame, height=40, corner_radius=10,
                                    font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                                    placeholder_text="  配置无效时，可手动指定 MCsaves 目录",
                                    border_width=1, border_color=BORDER, fg_color=BG)
        manual_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        def browse_manual():
            d = filedialog.askdirectory(title="选择 MCsaves 目录")
            if d:
                manual_entry.delete(0, "end")
                manual_entry.insert(0, d)
                apply_root(d, from_manual=True)

        ctk.CTkButton(manual_frame, text="浏览 MCsaves", width=130, height=40,
                      font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                      corner_radius=10, fg_color=ACCENT, hover_color=ACCENT_DIM,
                      command=browse_manual).grid(row=0, column=1)

        # 版本列表卡
        list_card = Card(content)
        list_card.grid(row=3, column=0, sticky="nsew", pady=(0, 4))
        list_card.grid_columnconfigure(0, weight=1)
        list_card.grid_rowconfigure(1, weight=1)

        hdr_frame = ctk.CTkFrame(list_card, fg_color="transparent")
        hdr_frame.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        hdr_frame.grid_columnconfigure(1, weight=1)

        tip_lbl = ctk.CTkLabel(hdr_frame, text="未发现 MCsaves 目录",
                                font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                                text_color=TEXT_SEC)
        tip_lbl.grid(row=0, column=0, sticky="w")

        scroll = ctk.CTkScrollableFrame(list_card, fg_color=BG, corner_radius=12,
                                        border_width=1, border_color=BORDER)
        scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_rowconfigure(1000, weight=1)

        self.cfg_selected_version = None

        def render_row(parent, i, item, update=False):
            name, cnt = item
            rf = parent
            if update:
                # 复用模式：只更新已有控件的文本，不重建 widget
                for c in rf.winfo_children():
                    if isinstance(c, ctk.CTkLabel):
                        c.configure(text=f"{cnt} 个存档" if cnt else "空",
                                    text_color=GREEN if cnt else TEXT_DIM)
                    elif isinstance(c, ctk.CTkButton):
                        c.configure(text=f"  {name}")
                return
            rf.grid(row=i, column=0, sticky="ew", padx=6, pady=3)
            rf.grid_columnconfigure(0, weight=1)

            # 右侧标签：单独占一列，不与按钮重叠
            badge_text = f"{cnt} 个存档" if cnt else "空"
            badge = ctk.CTkLabel(rf, text=badge_text,
                                 font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
                                 text_color=GREEN if cnt else TEXT_DIM,
                                 fg_color="transparent", corner_radius=8)
            badge.grid(row=0, column=1, sticky="e", padx=(6, 8))

            btn = ctk.CTkButton(rf, text=f"  {name}", anchor="w", height=40,
                                font=ctk.CTkFont(family=FONT_FAMILY, size=13),
                                corner_radius=10, fg_color=BG,
                                border_width=1, border_color=BORDER,
                                text_color=TEXT, hover_color=ACCENT_DIM)
            btn.grid(row=0, column=0, sticky="ew")

            def pick(n=name, b=btn):
                self.cfg_selected_version = n
                for rf in getattr(scroll, '_rows', []):
                    c0 = rf.winfo_children()[0]
                    if isinstance(c0, ctk.CTkButton):
                        c0.configure(fg_color=BG, border_color=BORDER, text_color=TEXT)
                b.configure(fg_color=ACCENT_DIM, border_color=ACCENT, text_color="white")
                nxt.configure(state="normal")

            btn.configure(command=pick)

        # 一次性缓存：目录 -> 版本清单，避免重复扫描
        self._cfg_versions_cache = getattr(self, '_cfg_versions_cache', {})

        def apply_root(root, from_manual=False):
            if not root or not os.path.isdir(root):
                messagebox.showerror("错误", "指定的目录不存在或无效")
                return
            self.cfg_saves_root = root
            # 优先用缓存，避免每次切回第 1 步都重新 listdir
            if root in self._cfg_versions_cache:
                versions = self._cfg_versions_cache[root]
            else:
                versions = self._cfg_list_versions(root)
                self._cfg_versions_cache[root] = versions
            self.cfg_versions = versions
            tip_lbl.configure(
                text=f"共 {len(versions)} 个版本目录，选择一个进入下一步"
                if versions else "该目录不是有效的 MCsaves 目录（无子目录）")
            self._build_list(scroll, versions, render_row,
                             "未找到版本目录" + ("，请手动指定有效目录" if from_manual else ""))
            nxt.configure(state="disabled")
            self.cfg_selected_version = None

        # 自动检测
        def detect():
            root = self._cfg_scan_saves_root()
            if root:
                status_lbl.configure(text="✓ 配置有效", text_color=GREEN)
                path_lbl.configure(text=root, text_color=TEXT)
                apply_root(root)
            else:
                status_lbl.configure(text="✗ 未找到 MCsaves 目录", text_color=RED)
                path_lbl.configure(text="—", text_color=TEXT_SEC)
                tip_lbl.configure(text="请在下方手动指定 MCsaves 目录，或先去「存档备份」做一次备份")

        self.after(50, detect)

        def go():
            if self.cfg_selected_version:
                self._cfg_goto(2)
                return
            manual = manual_entry.get().strip()
            if manual and os.path.isdir(manual):
                apply_root(manual, from_manual=True)

        nxt = self._nav_row(pg, lambda: self._show_tab(0), go, next_enabled=False)

    def _cfg_p2(self):
        """第 2 步：列出所选版本下的存档，可多选。
        关键优化：
        - 不再调用 _cfg_list_saves（os.walk 全递归），改为只读一级子目录；
        - 列表行复用 _build_list，避免反复创建/销毁 widget；
        - 列表卡高度随内容自适应（封顶 320px），移除死高度导致的内部分页卡顿。
        """
        ver = self.cfg_selected_version
        ver_dir = os.path.join(self.cfg_saves_root, ver) if ver else None

        pg = self._new_page(key="cfg_p2")
        self._title(pg, f"版本：{ver}",
                    f"来源：{self.cfg_saves_root}")

        content = self._make_content(pg)

        # 工具栏
        tool_frame = ctk.CTkFrame(content, fg_color="transparent")
        tool_frame.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        tool_frame.grid_columnconfigure(2, weight=1)

        saves = self._cfg_list_saves_in(ver_dir) if ver_dir else []
        count_lbl = ctk.CTkLabel(tool_frame,
                                 text=f"共 {len(saves)} 个存档",
                                 font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
                                 text_color=ACCENT)
        count_lbl.grid(row=0, column=0, sticky="w")

        # 列表卡：自适应高度，封顶 320 避免长列表一次性重绘
        list_card = Card(content)
        list_card.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        list_card.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(list_card, fg_color=BG, corner_radius=12,
                                        border_width=1, border_color=BORDER)
        scroll.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        scroll.grid_columnconfigure(0, weight=1)

        check_vars = []

        def update_count():
            cnt = sum(1 for v in check_vars if v.get())
            count_lbl.configure(text=f"已选 {cnt} / {len(saves)}")

        def render_row(parent, i, item, update=False):
            name, src = item
            rf = parent
            if update:
                for c in rf.winfo_children():
                    if isinstance(c, ctk.CTkLabel):
                        c.configure(text=name)
                        break
                return
            rf.grid(row=i, column=0, sticky="ew", padx=4, pady=1)
            rf.grid_columnconfigure(1, weight=1)

            var = ctk.BooleanVar(value=False)
            check_vars.append(var)
            ctk.CTkCheckBox(rf, text="", variable=var, width=24,
                            command=update_count).grid(row=0, column=0, padx=(4, 8), pady=4)
            ctk.CTkLabel(rf, text=name, anchor="w",
                         font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                         text_color=TEXT).grid(row=0, column=1, sticky="ew")

        self._build_list(scroll, saves, render_row, "该版本下没有有效存档（需含 level.dat）")

        # 动态计算列表卡高度（内容自适应，避免死高度引发重绘）
        disp = min(len(saves), 7)
        list_card.configure(height=max(56, disp * 44 + 16) if saves else 90)

        def go():
            if not check_vars:
                return
            selected = [(saves[i][0], ver, saves[i][1])
                        for i, v in enumerate(check_vars) if v.get()]
            if not selected:
                messagebox.showinfo("提示", "请至少选择一个存档")
                return
            self.cfg_selected_items = selected
            self._cfg_goto(3)

        # 手动导入按钮（紧贴列表下方）
        manual_frame = ctk.CTkFrame(content, fg_color="transparent")
        manual_frame.grid(row=2, column=0, sticky="ew", pady=(0, 0))
        manual_frame.grid_columnconfigure(0, weight=1)

        def browse_import():
            d = filedialog.askdirectory(title="选择要导入的存档文件夹")
            if d:
                self._cfg_import_saves([d], target_version=ver)

        ctk.CTkButton(manual_frame, text="选择存档文件夹导入", height=32,
                      font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                      corner_radius=10, fg_color="transparent",
                      border_width=1, border_color=BORDER,
                      text_color=TEXT_SEC, hover_color=ACCENT_DIM,
                      command=browse_import).grid(row=0, column=0, sticky="ew")

        self._nav_row(pg, lambda: self._cfg_goto(1), go,
                      next_text="下一步  →", next_enabled=True)

    def _cfg_p3(self):
        """第 3 步：解析存档所属版本，智能匹配 versions 目录，写入对应 saves。"""
        # 收集目标版本列表
        target_versions = []
        if self.versions_path and os.path.isdir(self.versions_path):
            try:
                target_versions = sorted(
                    d for d in os.listdir(self.versions_path)
                    if self._is_version_dir(os.path.join(self.versions_path, d))
                    and d not in NON_VERSION_DIRS
                )
            except (PermissionError, OSError):
                target_versions = []

        # ── 核心：解析每个存档所属版本，智能匹配 versions 目录 ──
        def _score_match(parsed_ver, parsed_api, cand):
            """计算 parsed 与目标版本名 cand 的匹配分。分数越高越匹配。"""
            cv, ca = self._parse_version_string(cand)
            score = 0
            if parsed_ver and cv:
                # 版本号：前缀越完整分越高
                if cv == parsed_ver:
                    score += 100
                elif cv.startswith(parsed_ver + ".") or parsed_ver.startswith(cv + "."):
                    score += 60
                elif parsed_ver.split(".")[0] == cv.split(".")[0]:
                    score += 30
            if parsed_api and ca:
                score += 50 if ca == parsed_api else -20   # API 一致加分，冲突减分
            elif parsed_api and not ca:
                score += 5   # 纯版本号目录（无 API 标识）也算可接受
            return score

        # 为每个存档计算推荐目标版本
        save_recommend = {}          # name -> 推荐版本名
        save_api_info = {}           # name -> (version, api)
        for name, ver_dir_name, src in self.cfg_selected_items:
            pver, papi = self._parse_version_string(ver_dir_name)
            save_api_info[name] = (pver, papi)
            best, best_score = None, -999
            for cand in target_versions:
                sc = _score_match(pver, papi, cand)
                if sc > best_score:
                    best_score, best = sc, cand
            # 只在有合理匹配时推荐（纯版本号至少 30，含 API 至少 50）
            threshold = 50 if papi else 30
            save_recommend[name] = best if (best and best_score >= threshold) else None

        # 默认推荐版本：取第一个有推荐的存档的推荐值
        default_rec = None
        for name, _, _ in self.cfg_selected_items:
            if save_recommend.get(name):
                default_rec = save_recommend[name]
                break

        pg = self._new_page(key="cfg_p3")
        self._title(pg, "选择目标版本并配置",
                    "存档版本已自动识别，可下拉修改；确认后写入 versions/版本/saves")

        content = self._make_content(pg)

        # row=0 信息卡：已选存档 + 识别结果
        card = Card(content)
        card.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text="待配置存档", anchor="w",
                     font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                     text_color=TEXT_SEC).grid(row=0, column=0, sticky="w", padx=16, pady=10)

        lines = []
        for name, ver_dir_name, src in self.cfg_selected_items:
            pver, papi = save_api_info.get(name, (None, None))
            tag = f"{pver or '?'} / {papi or '原版'}"
            rec = save_recommend.get(name)
            suffix = f"→ 推荐 {rec}" if rec else "→ 未匹配"
            lines.append(f"• {name}  ({tag})  {suffix}")
        ctk.CTkLabel(card, text="\n".join(lines), anchor="w", justify="left",
                     font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
                     text_color=TEXT).grid(row=0, column=1, sticky="w", padx=(0, 16), pady=10)

        # row=1 版本选择区
        sel_frame = ctk.CTkFrame(content, fg_color="transparent")
        sel_frame.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        sel_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(sel_frame, text="目标版本",
                     font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                     text_color=TEXT_SEC).grid(row=0, column=0, padx=(0, 10))

        ver_var = ctk.StringVar(value="")
        if target_versions:
            if default_rec and default_rec in target_versions:
                ver_var.set(default_rec)
            else:
                ver_var.set(target_versions[0])
            values = target_versions
            menu_state = "normal"
        else:
            ver_var.set("—")
            values = ["—"]
            menu_state = "disabled"

        ver_menu = ctk.CTkOptionMenu(sel_frame, values=values,
                                     variable=ver_var,
                                     font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                                     dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                                     corner_radius=10, width=220,
                                     state=menu_state)
        ver_menu.grid(row=0, column=1, sticky="w")

        # 匹配说明
        hint_lbl = ctk.CTkLabel(sel_frame,
                                text="匹配规则：版本号优先，其次 API（fabric/forge/quilt…），loader 版本号忽略",
                                font=ctk.CTkFont(family=FONT_FAMILY, size=10),
                                text_color=TEXT_DIM)
        hint_lbl.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # 进度区
        progress_frame = ctk.CTkFrame(content, fg_color="transparent")
        pbar = ctk.CTkProgressBar(progress_frame)
        pbar.grid(row=0, column=0, sticky="ew", pady=(8, 4))
        plbl = ctk.CTkLabel(progress_frame, text="",
                            font=ctk.CTkFont(family=FONT_FAMILY, size=12))
        plbl.grid(row=1, column=0, sticky="w")

        def do_config():
            target_ver = ver_var.get()
            if target_ver == "—" or not target_ver:
                messagebox.showwarning("提示", "请先选择目标版本")
                return

            target_saves = os.path.join(self.versions_path, target_ver, "saves")
            if not os.path.isdir(target_saves):
                if not messagebox.askyesno("确认",
                                           f"版本 {target_ver} 下没有 saves 目录，是否自动创建？"):
                    return
                os.makedirs(target_saves, exist_ok=True)

            overwrite = [n for n, _, _ in self.cfg_selected_items
                         if os.path.exists(os.path.join(target_saves, n))]
            if overwrite:
                if not messagebox.askyesno(
                    "确认覆盖",
                    f"以下 {len(overwrite)} 个存档在目标目录已存在，将自动重命名保留（追加 _时间 后缀）：\n"
                    + "\n".join(overwrite)):
                    return

            config_btn.configure(state="disabled", text="配置中...")
            progress_frame.grid(row=2, column=0, sticky="ew")
            pbar.start()
            plbl.configure(text="正在写入存档，请稍候...", text_color=TEXT_SEC)

            def worker():
                ok_list, renamed = [], []
                try:
                    for name, version, src in self.cfg_selected_items:
                        dst = os.path.join(target_saves, name)
                        if os.path.exists(dst):
                            dst = os.path.join(target_saves, f"{name}_{_now_ts()}")
                            renamed.append(name)
                        shutil.copytree(src, dst)
                        ok_list.append(name)
                    self.after(0, lambda: done(ok_list, renamed, target_ver, target_saves))
                except Exception as e:
                    self.after(0, lambda: done(None, None, target_ver, str(e)))

            threading.Thread(target=worker, daemon=True).start()

        def done(ok_list, renamed, target_ver, dst):
            pbar.stop()
            progress_frame.grid_remove()
            config_btn.configure(state="normal", text="确认配置")
            if ok_list is None:
                messagebox.showerror("配置失败", dst)
                return

            msg = f"✓ 已写入 {len(ok_list)} 个存档到：\n{os.path.join(self.versions_path, target_ver, 'saves')}"
            if renamed:
                msg += (f"\n\n⚠ 其中 {len(renamed)} 个因目标已存在而自动重命名：\n"
                        + "\n".join(renamed))
            messagebox.showinfo("配置完成", msg)

        nxt = self._nav_row(pg, lambda: self._cfg_goto(2), do_config,
                            next_text="确认配置", next_enabled=True)
        config_btn = nxt

        if not target_versions:
            plbl.configure(text="未在配置中找到有效版本目录，请先到「存档备份」或「模组备份」识别路径",
                          text_color=RED)
            plbl.grid(row=3, column=0, sticky="w", pady=(8, 0))


def main():
    app = MCToolboxApp()
    _center(app, 640, 560)
    app.mainloop()


if __name__ == "__main__":
    main()
