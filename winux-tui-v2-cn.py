#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Winux TUI v2.0 - 终极跨平台文件管理器
══════════════════════════════════════════
融合两大经典：
  ✦ cfe.py 的 curses 全屏 TUI 界面（中文不挤压）
  ✦ winux.py 的丰富命令行功能（30+ 命令）

操作模式：
  [浏览模式] 方向键导航，Enter 进入，F2 切命令模式
  [命令模式] 底部输入命令，回车执行，Esc 返回

依赖: pip install windows-curses pyreadline3 requests beautifulsoup4 html2text
运行: python winux_tui.py
"""

import os
import sys
import stat
import time
import re
import json
import shutil
import hashlib
import zipfile
import tarfile
import fnmatch
import platform
import subprocess
import ctypes
# msvcrt 仅 Windows 可用，条件导入避免 Linux/macOS 崩溃
try:
    import msvcrt
except ImportError:
    msvcrt = None
from datetime import datetime
from collections import defaultdict

# ============================================================
#  终端能力检测（修复：CMD 不支持 emoji 和 curses 光标）
# ============================================================

def is_modern_terminal():
    """
    检测当前终端是否支持 emoji 显示。
    - Windows Terminal 设置 WT_SESSION 环境变量 → 支持
    - 非 Windows 系统（Linux/macOS 终端） → 一般支持
    - 传统 Windows CMD / PowerShell 5 → 不支持
    """
    if os.environ.get("WT_SESSION"):
        return True
    if sys.platform != "win32":
        return True
    return False

# 全局终端能力标志，程序启动时确定
MODERN_TERM = is_modern_terminal()

def init_windows_console():
    """设置 Windows 控制台为 UTF-8 + 等宽字体"""
    if sys.platform != 'win32':
        return
    try:
        os.system('chcp 65001 >nul')
    except:
        pass
    try:
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except:
        pass
    # 仅在传统 CMD 下设置 Consolas 字体（现代终端自己管理字体）
    if not os.environ.get("WT_SESSION"):
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Console",
                0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "FaceName", 0, winreg.REG_SZ, "Consolas")
            winreg.SetValueEx(key, "FontFamily", 0, winreg.REG_DWORD, 54)
            winreg.SetValueEx(key, "FontSize", 0, winreg.REG_DWORD, 0x00100000)
            winreg.CloseKey(key)
        except:
            pass
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
        sys.stdin.reconfigure(encoding='utf-8')
    except:
        try:
            sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
            sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)
        except:
            pass
    # 启用 ANSI
    os.system("")


# ============================================================
#  中文宽字符处理（来自 cfe.py）
# ============================================================

def is_chinese_char(ch):
    code = ord(ch)
    if 0x4E00 <= code <= 0x9FFF: return True
    if 0x3400 <= code <= 0x4DBF: return True
    if 0xFF00 <= code <= 0xFFEF: return True
    if 0x3000 <= code <= 0x303F: return True
    return False

def is_wide_char(ch):
    if is_chinese_char(ch): return True
    code = ord(ch)
    if 0xAC00 <= code <= 0xD7AF: return True  # 韩文
    if 0x3040 <= code <= 0x30FF: return True  # 日文假名
    return False

def add_spaces(name):
    """在中文字符后面加空格，防止挤压"""
    result = []
    for ch in name:
        result.append(ch)
        if is_wide_char(ch):
            result.append(' ')
    return ''.join(result)

def visible_len(s):
    """计算字符串可见宽度"""
    width = 0
    for ch in s:
        width += 2 if is_wide_char(ch) else 1
    return width

def pad_to_width(s, target_width):
    """填充/截断到目标宽度"""
    processed = add_spaces(s)
    if visible_len(processed) <= target_width:
        return processed + ' ' * (target_width - visible_len(processed))
    result = []
    w = 0
    for ch in processed:
        cw = 2 if is_wide_char(ch) else 1
        if w + cw > target_width:
            break
        result.append(ch)
        w += cw
    while w < target_width:
        result.append(' ')
        w += 1
    return ''.join(result)

def truncate_middle(s, max_width):
    """中间截断过长字符串"""
    processed = add_spaces(s)
    if visible_len(processed) <= max_width:
        return pad_to_width(s, max_width)
    half = max_width // 2 - 1
    left_part = []
    w = 0
    for ch in processed:
        cw = 2 if is_wide_char(ch) else 1
        if w + cw > half:
            break
        left_part.append(ch)
        w += cw
    right_part = []
    w = 0
    for ch in reversed(processed):
        cw = 2 if is_wide_char(ch) else 1
        if w + cw > half - 1:
            break
        right_part.insert(0, ch)
        w += cw
    return ''.join(left_part) + '~' + ''.join(right_part)


# ============================================================
#  颜色 & 图标（根据终端能力自动选择）
# ============================================================

class C:
    """curses 颜色对编号"""
    DIR = 1
    FILE = 2
    SELECTED = 3
    STATUS = 4
    ERROR = 5
    SUCCESS = 6
    WARNING = 7
    TITLE = 8
    TREE = 9
    CMD = 10
    HIGHLIGHT = 11
    GRAY = 12
    BLUE = 13
    RED = 14

# ANSI 颜色（用于编辑器弹窗等场景）
class A:
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    MAGENTA= "\033[95m"
    CYAN   = "\033[96m"
    GRAY   = "\033[90m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"
    INVERSE = "\033[7m"

# ---- 现代终端用 emoji 图标 ----
EXT_ICON_EMOJI = {
    "py": "🐍", "pyw": "🐍",
    "js": "📜", "ts": "📜", "json": "📋",
    "html": "🌐", "css": "🎨",
    "md": "📝", "txt": "📄", "rst": "📄",
    "png": "🖼️", "jpg": "🖼️", "jpeg": "🖼️", "gif": "🖼️",
    "svg": "🖼️", "webp": "🖼️", "bmp": "🖼️",
    "mp3": "🎵", "wav": "🎵", "flac": "🎵",
    "mp4": "🎬", "avi": "🎬", "mkv": "🎬", "mov": "🎬",
    "zip": "📦", "tar": "📦", "gz": "📦", "rar": "📦", "7z": "📦",
    "pdf": "📕", "doc": "📘", "docx": "📘", "xls": "📗", "xlsx": "📗",
    "exe": "⚙️", "bat": "⚙️", "cmd": "⚙️",
}

# ---- 传统 CMD 降级用 ASCII/文本图标（修复：CMD 不显示 emoji）----
EXT_ICON_ASCII = {
    "py": "PY", "pyw": "PY",
    "js": "JS", "ts": "TS", "json": "JSN",
    "html": "HTM", "css": "CSS",
    "md": "MD", "txt": "TXT", "rst": "RST",
    "png": "IMG", "jpg": "IMG", "jpeg": "IMG", "gif": "IMG",
    "svg": "IMG", "webp": "IMG", "bmp": "IMG",
    "mp3": "SND", "wav": "SND", "flac": "SND",
    "mp4": "VID", "avi": "VID", "mkv": "VID", "mov": "VID",
    "zip": "ZIP", "tar": "TAR", "gz": "GZP", "rar": "RAR", "7z": "7ZP",
    "pdf": "PDF", "doc": "DOC", "docx": "DOC", "xls": "XLS", "xlsx": "XLS",
    "exe": "EXE", "bat": "BAT", "cmd": "CMD",
}

# 根据终端能力选择图标集
EXT_ICON = EXT_ICON_EMOJI if MODERN_TERM else EXT_ICON_ASCII

# 通用图标（也根据终端能力选择）
if MODERN_TERM:
    ICON_FOLDER   = "📁"
    ICON_FILE     = "📄"
    ICON_DRIVE    = "💿"
    ICON_SELECTED = "  "
    ICON_CLIP_COPY  = "[C]"
    ICON_CLIP_CUT   = "[失败]"
    ICON_TITLE    = "Winux"
    ICON_PREVIEW  = "预览"
    ICON_SEARCH   = "搜索"
    ICON_BOOKMARK = "[B]"
    ICON_CHECK    = "[成功]"
    ICON_CROSS    = "[失败]"
    ICON_ARROW    = ">"
    ICON_PROMPT   = ">"
    ICON_TREE     = "+"
    ICON_WEB      = "🌐"
else:
    ICON_FOLDER   = "DIR"
    ICON_FILE     = "FIL"
    ICON_DRIVE    = "DRV"
    ICON_SELECTED = " *"
    ICON_CLIP_COPY  = "[C]"
    ICON_CLIP_CUT   = "[失败]"
    ICON_TITLE    = "Winux"
    ICON_PREVIEW  = "预览"
    ICON_SEARCH   = "搜索"
    ICON_BOOKMARK = "[B]"
    ICON_CHECK    = "[成功]"
    ICON_CROSS    = "[失败]"
    ICON_ARROW    = ">"
    ICON_PROMPT   = ">"
    ICON_TREE     = "+"
    ICON_WEB      = "WEB"

# 文件扩展名 → 颜色对
EXT_COLOR = {
    # 代码
    "py": C.SUCCESS, "pyw": C.SUCCESS,
    "js": C.WARNING, "ts": C.WARNING, "json": C.WARNING,
    "html": C.CMD, "css": C.CMD, "xml": C.CMD,
    "c": C.WARNING, "cpp": C.WARNING, "h": C.WARNING,
    "java": C.WARNING, "go": C.SUCCESS, "rs": C.WARNING,
    "php": C.CMD, "rb": C.RED, "sh": C.SUCCESS,
    # 文档
    "md": C.TITLE, "txt": C.TITLE, "rst": C.TITLE,
    "pdf": C.RED, "doc": C.BLUE, "docx": C.BLUE,
    "xls": C.SUCCESS, "xlsx": C.SUCCESS, "pptx": C.RED,
    # 图片
    "png": C.HIGHLIGHT, "jpg": C.HIGHLIGHT, "jpeg": C.HIGHLIGHT,
    "gif": C.HIGHLIGHT, "bmp": C.HIGHLIGHT, "svg": C.HIGHLIGHT,
    "webp": C.HIGHLIGHT, "ico": C.HIGHLIGHT,
    # 音频/视频
    "mp3": C.RED, "wav": C.RED, "flac": C.RED, "aac": C.RED,
    "mp4": C.RED, "avi": C.RED, "mkv": C.RED, "mov": C.RED,
    # 压缩
    "zip": C.WARNING, "tar": C.WARNING, "gz": C.WARNING,
    "rar": C.WARNING, "7z": C.WARNING, "bz2": C.WARNING,
    # 可执行
    "exe": C.RED, "msi": C.RED, "bat": C.RED, "cmd": C.RED, "ps1": C.RED,
    # 配置
    "ini": C.GRAY, "cfg": C.GRAY, "conf": C.GRAY, "yml": C.GRAY, "yaml": C.GRAY,
    "json": C.WARNING, "xml": C.CMD, "csv": C.TITLE,
}


# ============================================================
#  工具函数
# ============================================================

def get_icon(name, is_dir=False):
    if is_dir:
        return ICON_FOLDER
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return EXT_ICON.get(ext, ICON_FILE)

def get_color_pair(name, is_dir=False):
    if is_dir:
        return C.DIR
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return EXT_COLOR.get(ext, C.FILE)

def format_size(size):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f}{unit}" if unit != "B" else f"{int(size)}{unit}"
        size /= 1024
    return f"{size:.1f}PB"

def format_perm(mode):
    if platform.system() == "Windows":
        return "rw-"
    perm = ""
    for shift in [6, 3, 0]:
        t = (mode >> shift) & 0o7
        perm += "r" if t & 4 else "-"
        perm += "w" if t & 2 else "-"
        perm += "x" if t & 1 else "-"
    return perm

def format_time(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

def safe_input(prompt=""):
    try:
        return input(prompt)
    except (KeyboardInterrupt, EOFError):
        return None

def colorize_ansi(text, color):
    return f"{color}{text}{A.RESET}"

def is_url(text):
    """判断字符串是否是 URL"""
    text = text.strip()
    if text.startswith(('http://', 'https://', 'ftp://')):
        return True
    if re.match(r'^www\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?\.[a-zA-Z]{2,}', text):
        return True
    # 支持省略协议的常见 URL 格式: example.com, google.com/search
    if re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?\.[a-zA-Z]{2,}', text) and '.' in text:
        return True
    return False

def normalize_url(text):
    """补全 URL 协议前缀"""
    text = text.strip()
    if text.startswith(('http://', 'https://', 'ftp://')):
        return text
    if text.startswith('www.'):
        return 'https://' + text
    return 'https://' + text


# ============================================================
#  盘符获取
# ============================================================
def get_drives():
    drives = []
    if sys.platform == 'win32':
        try:
            mask = ctypes.windll.kernel32.GetLogicalDrives()
            for i in range(26):
                if mask & (1 << i):
                    letter = chr(ord('A') + i) + ':\\'
                    label = ''
                    free = 0
                    try:
                        usage = shutil.disk_usage(letter)
                        free = usage.free / (1024**3)
                        buf = ctypes.create_unicode_buffer(256)
                        if ctypes.windll.kernel32.GetVolumeInformationW(
                            ctypes.c_wchar_p(letter),
                            buf, 256, None, None, None, None, 0
                        ):
                            label = buf.value
                    except:
                        pass
                    drives.append((letter, label, free))
        except:
            for d in 'CDEFGH':
                p = d + ':\\'
                if os.path.exists(p):
                    drives.append((p, '', 0))
    else:
        drives.append(('/', 'root', 0))
        for mp in ['/mnt', '/media', '/home']:
            if os.path.exists(mp):
                try:
                    for entry in os.listdir(mp):
                        fp = os.path.join(mp, entry)
                        if os.path.ismount(fp) or os.path.isdir(fp):
                            drives.append((fp, entry, 0))
                except:
                    pass
    return drives


# ============================================================
#  安全绘制
# ============================================================
def safe_addstr(win, y, x, text, attr=0, max_width=None):
    if max_width is not None:
        text = pad_to_width(text, max_width)
    else:
        try:
            _, w = win.getmaxyx()
            text = pad_to_width(text, max(w - x - 1, 1))
        except:
            pass
    try:
        win.addstr(y, x, text, attr)
    except:
        try:
            win.addstr(y, x, text.encode('ascii', errors='replace').decode(), attr)
        except:
            pass


# ============================================================
#  内嵌 Nano 风格编辑器（修复：用反色高亮模拟光标）
# ============================================================
class NanoEditor:
    """迷你 nano 风格编辑器，支持 UTF-8 / 中文"""

    def __init__(self, filepath):
        self.filepath = filepath
        self.modified = False
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                self.lines = f.read().split("\n")
        except FileNotFoundError:
            self.lines = [""]
        if not self.lines:
            self.lines = [""]
        self.cur_row = 0
        self.cur_col = 0
        self.row_offset = 0

    def _clamp(self):
        self.cur_row = max(0, min(self.cur_row, len(self.lines) - 1))
        self.cur_col = max(0, min(self.cur_col, len(self.lines[self.cur_row])))

    def _save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(self.lines))
            self.modified = False
            return True
        except OSError:
            return False

    def run(self, stdscr):
        """在 curses 环境中运行编辑器"""
        # 修复：传统 CMD 下 curs_set 不可靠，尝试设置但主要靠反色模拟
        try:
            curses.curs_set(2)  # 高可见度块状光标
        except:
            pass

        maxy, maxx = stdscr.getmaxyx()
        edit_h = maxy - 2  # 留 2 行状态栏

        while True:
            self._clamp()
            # 滚动
            if self.cur_row < self.row_offset:
                self.row_offset = self.cur_row
            elif self.cur_row >= self.row_offset + edit_h:
                self.row_offset = self.cur_row - edit_h + 1

            stdscr.erase()

            # ---- 绘制文本区 ----
            for i in range(edit_h):
                abs_row = self.row_offset + i
                if abs_row >= len(self.lines):
                    safe_addstr(stdscr, i, 0, "~", curses.A_DIM, maxx)
                    continue

                line = self.lines[abs_row]
                lineno = f"{abs_row+1:>4} | "
                safe_addstr(stdscr, i, 0, lineno, curses.A_DIM, len(lineno))

                if abs_row == self.cur_row:
                    # 修复：用反色高亮当前字符来模拟光标
                    col = self.cur_col
                    if col < len(line):
                        before = line[:col]
                        char = line[col]
                        after = line[col+1:]
                        safe_addstr(stdscr, i, len(lineno), before, 0, maxx - len(lineno))
                        try:
                            stdscr.addstr(i, len(lineno) + visible_len(before),
                                          char, curses.A_REVERSE | curses.A_BOLD)
                        except:
                            try:
                                stdscr.addstr(i, len(lineno) + visible_len(before),
                                              " ", curses.A_REVERSE | curses.A_BOLD)
                            except:
                                pass
                        cursor_screen_x = len(lineno) + visible_len(before) + (2 if is_wide_char(char) else 1)
                        remaining = maxx - cursor_screen_x - 1
                        if remaining > 0 and after:
                            safe_addstr(stdscr, i, cursor_screen_x, after, 0, remaining)
                    else:
                        safe_addstr(stdscr, i, len(lineno), line, 0, maxx - len(lineno))
                        try:
                            stdscr.addstr(i, len(lineno) + visible_len(line),
                                          " ", curses.A_REVERSE | curses.A_BOLD)
                        except:
                            pass
                else:
                    safe_addstr(stdscr, i, len(lineno), line, 0, maxx - len(lineno))

            # ---- 状态栏 ----
            mod = " **[已修改]**" if self.modified else ""
            状态栏文本 = f" {os.path.basename(self.filepath)}{mod} | 行 {self.cur_row+1}/{len(self.lines)} 列 {self.cur_col+1} | Ctrl+S:保存 Ctrl+X:退出 Ctrl+W:查找 Ctrl+G:跳转 Tab:缩进 "
            safe_addstr(stdscr, maxy - 1, 0, 状态栏文本, curses.A_REVERSE, maxx)

            # 修复：确保光标位置在物理终端上更新
            try:
                if self.cur_row < len(self.lines):
                    line = self.lines[self.cur_row]
                    col_screen = visible_len(line[:self.cur_col])
                    stdscr.move(self.cur_row - self.row_offset,
                                min(len(f"{self.cur_row+1:>4} | ") + col_screen, maxx - 1))
            except:
                pass

            stdscr.refresh()

            # ---- 输入处理 ----
            ch = stdscr.getch()
            code = ch

            if code == 27:  # Esc
                if self.modified:
                    选择 = self._confirm(stdscr, "文件已修改！确定不保存退出？(Y/N)")
                    if 选择 == 'y':
                        break
                    elif 选择 == 'esc':
                        continue
                else:
                    break
            elif code == curses.KEY_UP:
                self.cur_row -= 1
            elif code == curses.KEY_DOWN:
                self.cur_row += 1
            elif code == curses.KEY_LEFT:
                self.cur_col -= 1
            elif code == curses.KEY_RIGHT:
                self.cur_col += 1
            elif code == curses.KEY_HOME:
                self.cur_col = 0
            elif code == curses.KEY_END:
                self.cur_col = len(self.lines[self.cur_row])
            elif code == curses.KEY_PPAGE:
                self.cur_row -= 10
            elif code == curses.KEY_NPAGE:
                self.cur_row += 10
            elif code == curses.KEY_DC:
                line = self.lines[self.cur_row]
                if self.cur_col < len(line):
                    self.lines[self.cur_row] = line[:self.cur_col] + line[self.cur_col+1:]
                    self.modified = True
            # Ctrl+S 保存
            elif ch == 19:
                if self._save():
                    self._show_msg(stdscr, "[成功] 已保存", C.SUCCESS)
                else:
                    self._show_msg(stdscr, "[XX] 保存失败", C.ERROR)
            # Ctrl+X 退出
            elif ch == 24:
                if self.modified:
                    选择 = self._confirm(stdscr, "退出前是否保存？(Y/N/Esc)")
                    if 选择 == 'y':
                        self._save()
                    elif 选择 == 'esc':
                        continue
                break
            # Ctrl+W 查找
            elif ch == 23:
                self._find(stdscr)
            # Ctrl+G 跳行
            elif ch == 7:
                num = self._input_prompt(stdscr, "跳转到行号: ")
                if num.isdigit():
                    self.cur_row = int(num) - 1
                    self.cur_col = 0
            # Enter
            elif code == 10 or code == 13:
                line = self.lines[self.cur_row]
                new_line = line[self.cur_col:]
                self.lines[self.cur_row] = line[:self.cur_col]
                self.lines.insert(self.cur_row + 1, new_line)
                self.cur_row += 1
                self.cur_col = 0
                self.modified = True
            # Backspace
            elif code == 8 or code == 127 or code == curses.KEY_BACKSPACE:
                if self.cur_col > 0:
                    line = self.lines[self.cur_row]
                    self.lines[self.cur_row] = line[:self.cur_col-1] + line[self.cur_col:]
                    self.cur_col -= 1
                    self.modified = True
                elif self.cur_row > 0:
                    prev = self.lines[self.cur_row - 1]
                    cur = self.lines[self.cur_row]
                    self.cur_col = len(prev)
                    self.lines[self.cur_row - 1] = prev + cur
                    del self.lines[self.cur_row]
                    self.cur_row -= 1
                    self.modified = True
            # Tab
            elif code == 9:
                line = self.lines[self.cur_row]
                self.lines[self.cur_row] = line[:self.cur_col] + "    " + line[self.cur_col:]
                self.cur_col += 4
                self.modified = True
            # 可打印字符
            elif code >= 32:
                try:
                    char = chr(code)
                    line = self.lines[self.cur_row]
                    self.lines[self.cur_row] = line[:self.cur_col] + char + line[self.cur_col:]
                    self.cur_col += 1
                    self.modified = True
                except:
                    pass
            # UTF-8 多字节首字节
            elif code >= 0xC0:
                buf = bytes([code])
                stdscr.timeout(50)
                while True:
                    ch2 = stdscr.getch()
                    if ch2 == -1:
                        break
                    if 0x80 <= ch2 <= 0xBF:
                        buf += bytes([ch2])
                    else:
                        break
                stdscr.timeout(-1)
                try:
                    char = buf.decode('utf-8', errors='ignore')
                    if char:
                        line = self.lines[self.cur_row]
                        self.lines[self.cur_row] = line[:self.cur_col] + char + line[self.cur_col:]
                        self.cur_col += 1
                        self.modified = True
                except:
                    pass

        try:
            curses.curs_set(0)
        except:
            pass

    def _show_msg(self, stdscr, msg, color_pair):
        maxy, maxx = stdscr.getmaxyx()
        safe_addstr(stdscr, maxy - 1, 0, f" {msg} (按任意键继续)", color_pair, maxx)
        stdscr.refresh()
        stdscr.getch()

    def _confirm(self, stdscr, prompt):
        maxy, maxx = stdscr.getmaxyx()
        safe_addstr(stdscr, maxy - 1, 0, f" {prompt} ", curses.A_REVERSE | curses.A_BLINK, maxx)
        stdscr.refresh()
        while True:
            ch = stdscr.getch()
            c = chr(ch).lower() if 32 <= ch < 127 else ''
            if c == 'y': return 'y'
            if c == 'n': return 'n'
            if ch == 27: return 'esc'

    # 修复：_input_prompt 现在接受所有可打印字符
    def _input_prompt(self, stdscr, prompt):
        maxy, maxx = stdscr.getmaxyx()
        input_str = ""
        while True:
            safe_addstr(stdscr, maxy - 1, 0, f" {prompt}{input_str}", curses.A_REVERSE, maxx)
            stdscr.refresh()
            ch = stdscr.getch()
            if ch == 10 or ch == 13:
                break
            elif ch == 8 or ch == 127:
                input_str = input_str[:-1]
            elif 32 <= ch < 127:
                input_str += chr(ch)
            elif ch >= 0xC0:
                buf = bytes([ch])
                stdscr.timeout(50)
                while True:
                    ch2 = stdscr.getch()
                    if ch2 == -1:
                        break
                    if 0x80 <= ch2 <= 0xBF:
                        buf += bytes([ch2])
                    else:
                        break
                stdscr.timeout(-1)
                try:
                    char = buf.decode('utf-8', errors='ignore')
                    if char:
                        input_str += char
                except:
                    pass
            elif ch == 27:
                return ""
        return input_str

    def _find(self, stdscr):
        query = self._input_prompt(stdscr, "查找: ")
        if not query:
            return
        q = query.lower()
        for i in range(self.cur_row + 1, len(self.lines)):
            if q in self.lines[i].lower():
                self.cur_row = i
                idx = self.lines[i].lower().find(q)
                self.cur_col = idx
                return
        for i in range(self.cur_row + 1):
            if q in self.lines[i].lower():
                self.cur_row = i
                idx = self.lines[i].lower().find(q)
                self.cur_col = idx
                return


# ============================================================
#  弹窗 / 对话框
# ============================================================

def popup(stdscr, lines, title="信息", width=None):
    """通用弹窗"""
    maxy, maxx = stdscr.getmaxyx()
    max_line_len = max((len(l) for l in lines), default=10)
    w = width or min(maxx - 4, max(max_line_len + 8, 30))
    h = min(len(lines) + 4, maxy - 2)
    y = (maxy - h) // 2
    x = (maxx - w) // 2
    win = curses.newwin(h, w, y, x)
    win.keypad(True)
    win.border()
    safe_addstr(win, 0, (w - len(title)) // 2, f" {title} ", curses.A_BOLD | C.TITLE)
    for i, l in enumerate(lines[:h-4]):
        safe_addstr(win, i + 2, 2, l, 0, w - 4)
    safe_addstr(win, h - 2, 2, "按任意键继续...", curses.A_DIM, w - 4)
    win.refresh()
    win.getch()
    del win
    stdscr.touchwin()


def input_popup(stdscr, prompt, default=""):
    """输入弹窗，返回字符串"""
    maxy, maxx = stdscr.getmaxyx()
    w = min(maxx - 4, max(len(prompt) + 20, 40))
    h = 5
    y = (maxy - h) // 2
    x = (maxx - w) // 2
    win = curses.newwin(h, w, y, x)
    win.keypad(True)
    win.border()
    safe_addstr(win, 1, 2, prompt, curses.A_BOLD, w - 4)
    input_str = default
    while True:
        safe_addstr(win, 3, 2, input_str + " " * (w - 4 - len(input_str)), 0, w - 2)
        try:
            win.move(3, 2 + len(input_str))
        except:
            pass
        win.refresh()
        ch = win.getch()
        if ch == 10 or ch == 13:
            break
        elif ch == 27:
            del win
            stdscr.touchwin()
            return None
        elif ch == 8 or ch == 127:
            input_str = input_str[:-1]
        elif 32 <= ch < 127:
            input_str += chr(ch)
        elif ch >= 0xC0:
            buf = bytes([ch])
            win.timeout(50)
            while True:
                ch2 = win.getch()
                if ch2 == -1:
                    break
                if 0x80 <= ch2 <= 0xBF:
                    buf += bytes([ch2])
                else:
                    break
            try:
                char = buf.decode('utf-8', errors='ignore')
                if char:
                    input_str += char
            except:
                pass
            win.timeout(-1)
    del win
    stdscr.touchwin()
    return input_str


def confirm_popup(stdscr, prompt):
    """确认弹窗，返回 True/False"""
    maxy, maxx = stdscr.getmaxyx()
    w = min(maxx - 4, len(prompt) + 16)
    h = 5
    y = (maxy - h) // 2
    x = (maxx - w) // 2
    win = curses.newwin(h, w, y, x)
    win.keypad(True)
    win.border()
    safe_addstr(win, 1, 2, prompt, curses.A_BOLD, w - 4)
    safe_addstr(win, 3, 2, "[Y] 是  [N] 否", curses.A_DIM, w - 4)
    win.refresh()
    while True:
        ch = win.getch()
        c = chr(ch).lower() if 32 <= ch < 127 else ''
        if c == 'y':
            del win
            stdscr.touchwin()
            return True
        if c == 'n' or ch == 27:
            del win
            stdscr.touchwin()
            return False


# ============================================================
#  URL 输入弹窗（TUI 浏览模式直接打开浏览器）
# ============================================================

def url_input_popup(stdscr, prompt="网址:", default=""):
    """
    URL 专用输入弹窗，支持更长的输入和 URL 自动补全提示。
    返回完整 URL 字符串，或 None（取消）。
    """
    maxy, maxx = stdscr.getmaxyx()
    w = min(maxx - 4, 70)
    h = 7
    y = (maxy - h) // 2
    x = (maxx - w) // 2
    win = curses.newwin(h, w, y, x)
    win.keypad(True)
    win.border()
    safe_addstr(win, 1, 2, prompt, curses.A_BOLD | C.CMD, w - 4)
    safe_addstr(win, 2, 2, "(缺少协议将自动补 https://)", curses.A_DIM, w - 4)
    input_str = default
    while True:
        # 显示输入内容（如果太长则截断显示末尾）
        display = input_str
        if len(display) > w - 6:
            display = "..." + display[-(w - 9):]
        safe_addstr(win, 4, 2, display + " " * (w - 4 - len(display)), 0, w - 2)
        try:
            win.move(4, 2 + len(display))
        except:
            pass
        win.refresh()
        ch = win.getch()
        if ch == 10 or ch == 13:
            break
        elif ch == 27:
            del win
            stdscr.touchwin()
            return None
        elif ch == 8 or ch == 127:
            input_str = input_str[:-1]
        elif 32 <= ch < 127:
            input_str += chr(ch)
        elif ch >= 0xC0:
            buf = bytes([ch])
            win.timeout(50)
            while True:
                ch2 = win.getch()
                if ch2 == -1:
                    break
                if 0x80 <= ch2 <= 0xBF:
                    buf += bytes([ch2])
                else:
                    break
            try:
                char = buf.decode('utf-8', errors='ignore')
                if char:
                    input_str += char
            except:
                pass
            win.timeout(-1)
    del win
    stdscr.touchwin()
    return input_str.strip()


# ============================================================
#  网页获取工具（纯 Python，用于 web 命令）
# ============================================================

def _fetch_web_page(url, timeout=15):
    """
    用 requests + BeautifulSoup + html2text 获取网页纯文本内容。
    优先 html2text（保留标题层级、链接），降级到 BeautifulSoup 纯文本。
    返回 (title, lines_list) 或 (None, error_message)
    """
    # 确保 URL 有协议前缀
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # 检查依赖
    try:
        import requests
    except ImportError:
        return None, "需要安装 requests: pip install requests"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }

    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        return None, f"请求超时 ({timeout}秒): {url}"
    except requests.exceptions.ConnectionError:
        return None, f"连接失败: {url}"
    except requests.exceptions.HTTPError as e:
        return None, f"HTTP 错误: {e}"
    except Exception as e:
        return None, f"请求失败: {e}"

    # 自动检测编码
    if resp.encoding is None or resp.encoding == 'ISO-8859-1':
        resp.encoding = resp.apparent_encoding or 'utf-8'

    html = resp.text

    # 提取标题
    title = ""
    try:
        from bs4 import BeautifulSoup
        soup_tmp = BeautifulSoup(html, 'html.parser')
        title_tag = soup_tmp.find('title')
        if title_tag and title_tag.string:
            title = title_tag.string.strip()[:80]
    except ImportError:
        pass

    # 尝试用 html2text 转换
    try:
        import html2text
        converter = html2text.HTML2Text()
        converter.body_width = 78
        converter.ignore_links = False
        converter.ignore_images = True
        converter.ignore_emphasis = False
        converter.skip_internal_links = True
        converter.protect_links = True
        text = converter.handle(html)
        lines = text.splitlines()
    except ImportError:
        # Fallback: BeautifulSoup 纯文本
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript']):
                tag.decompose()
            text = soup.get_text(separator='\n', strip=True)
            lines = text.splitlines()
        except ImportError:
            # 最终降级：去除所有 HTML 标签
            import re as re_mod
            text = re_mod.sub(r'<[^>]+>', '\n', html)
            text = re_mod.sub(r'\n{3,}', '\n\n', text)
            lines = text.splitlines()

    # 清理空行（保留段落结构但去掉多余空行）
    cleaned = []
    prev_empty = False
    for line in lines:
        stripped = line.strip()
        if stripped:
            cleaned.append(stripped)
            prev_empty = False
        elif not prev_empty:
            cleaned.append('')
            prev_empty = True

    # 截断过长内容
    max_lines = 5000
    if len(cleaned) > max_lines:
        cleaned = cleaned[:max_lines]
        cleaned.append('... (内容过长，已截断)')

    return title, cleaned


# ============================================================
#  主文件管理器类
# ============================================================

class WinuxTUI:
    """Winux TUI - 终极文件管理器"""

    MODE_BROWSE = 0
    MODE_DRIVE = 1
    MODE_COMMAND = 2
    MODE_URL_INPUT = 3  # URL 输入模式

    SORT_NAME = 0
    SORT_SIZE = 1
    SORT_TIME = 2
    SORT_EXT = 3

    def __init__(self, stdscr, start_dir=None):
        self.stdscr = stdscr
        self.cwd = os.path.abspath(start_dir or os.getcwd())
        self.items = []
        self.idx = 0
        self.scroll = 0
        self.show_hidden = False
        self.detail = True
        self.preview = False
        self.preview_text = ""
        self.msg = ""
        self.msg_color = C.STATUS
        self.running = True
        self.mode = self.MODE_BROWSE
        self.drives = []
        self.command_buf = ""
        self.command_history = []
        self.history_idx = -1
        self.sort_mode = self.SORT_NAME
        self.sort_reverse = False
        self.filter_pattern = ""
        self.bookmarks = self._load_bookmarks()
        self.apt_backend = self._detect_apt_backend()
        self.clipboard = None
        self._init_colors()
        self.load_dir()

    def _init_colors(self):
        try:
            if not curses.has_colors():
                return
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(C.DIR, curses.COLOR_BLUE, -1)
            curses.init_pair(C.FILE, curses.COLOR_WHITE, -1)
            curses.init_pair(C.SELECTED, curses.COLOR_BLACK, curses.COLOR_CYAN)
            curses.init_pair(C.STATUS, curses.COLOR_BLACK, curses.COLOR_WHITE)
            curses.init_pair(C.ERROR, curses.COLOR_RED, -1)
            curses.init_pair(C.SUCCESS, curses.COLOR_GREEN, -1)
            curses.init_pair(C.WARNING, curses.COLOR_YELLOW, -1)
            curses.init_pair(C.TITLE, curses.COLOR_CYAN, -1)
            curses.init_pair(C.CMD, curses.COLOR_MAGENTA, -1)
            curses.init_pair(C.HIGHLIGHT, curses.COLOR_GREEN, -1)
            curses.init_pair(C.GRAY, curses.COLOR_WHITE, -1)
            curses.init_pair(C.BLUE, curses.COLOR_BLUE, -1)
            curses.init_pair(C.RED, curses.COLOR_RED, -1)
        except:
            pass

    def _load_bookmarks(self):
        path = os.path.expanduser("~/.winux_bookmarks.json")
        try:
            with open(path) as f:
                return json.load(f)
        except:
            return {}

    def _save_bookmarks(self):
        path = os.path.expanduser("~/.winux_bookmarks.json")
        try:
            with open(path, "w") as f:
                json.dump(self.bookmarks, f, indent=2)
        except:
            pass

    def _detect_apt_backend(self):
        if platform.system() != "Windows":
            return None
        for cmd in ["winget", "choco", "scoop"]:
            try:
                subprocess.run([cmd, "--version"], capture_output=True, timeout=3)
                return cmd
            except:
                continue
        return None

    # ==================== 目录加载 ====================
    def load_dir(self):
        try:
            names = os.listdir(self.cwd)
        except PermissionError:
            self.set_msg("[失败] 权限不足，无法访问", C.ERROR)
            self.items = []
            return
        lst = []
        for n in names:
            if not self.show_hidden and n.startswith('.'):
                continue
            if self.filter_pattern:
                if not fnmatch.fnmatch(n.lower(), self.filter_pattern.lower()):
                    continue
            fp = os.path.join(self.cwd, n)
            try:
                st = os.stat(fp)
                lst.append({
                    'name': n, 'path': fp,
                    'is_dir': stat.S_ISDIR(st.st_mode),
                    'size': st.st_size, 'mtime': st.st_mtime,
                    'mode': st.st_mode,
                })
            except:
                lst.append({'name': n, 'path': fp, 'is_dir': False,
                            'size': 0, 'mtime': 0, 'mode': 0})

        if self.sort_mode == self.SORT_NAME:
            lst.sort(key=lambda x: (not x['is_dir'], x['name'].lower()), reverse=self.sort_reverse)
        elif self.sort_mode == self.SORT_SIZE:
            lst.sort(key=lambda x: (not x['is_dir'], x['size']), reverse=not self.sort_reverse)
        elif self.sort_mode == self.SORT_TIME:
            lst.sort(key=lambda x: (not x['is_dir'], x['mtime']), reverse=not self.sort_reverse)
        elif self.sort_mode == self.SORT_EXT:
            lst.sort(key=lambda x: (not x['is_dir'], os.path.splitext(x['name'])[1].lower()),
                     reverse=self.sort_reverse)

        self.items = lst
        self.idx = 0
        self.scroll = 0
        dc = sum(1 for it in self.items if it['is_dir'])
        fc = len(self.items) - dc
        排序名称 = {0: "名称", 1: "大小", 2: "时间", 3: "扩展名"}
        self.set_msg(f"共 {len(self.items)} 项 (目录:{dc} 文件:{fc}) | 排序: {排序名称[self.sort_mode]}", C.STATUS)

    def set_msg(self, msg, color=C.STATUS):
        self.msg = msg
        self.msg_color = color

    # ==================== 盘符视图 ====================
    def enter_drive_view(self):
        self.mode = self.MODE_DRIVE
        self.drives = get_drives()
        self.idx = 0
        self.scroll = 0
        cur = (self.cwd[:2] + ':\\').upper()
        for i, (d, _, _) in enumerate(self.drives):
            if d.upper() == cur:
                self.idx = i
                break
        self.set_msg("盘符选择模式 - Enter 进入 | Esc 返回", C.WARNING)

    def open_drive(self):
        if not self.drives or self.idx >= len(self.drives):
            return
        letter, _, _ = self.drives[self.idx]
        try:
            os.chdir(letter)
            self.cwd = os.getcwd()
            self.mode = self.MODE_BROWSE
            self.load_dir()
            self.set_msg(f"[成功] 已进入 {letter}", C.SUCCESS)
        except:
            self.set_msg(f"[失败] 无法访问 {letter}", C.ERROR)

    # ==================== 导航 ====================
    def go_up(self):
        if self.mode == self.MODE_DRIVE:
            self.mode = self.MODE_BROWSE
            self.set_msg("已取消", C.STATUS)
            return
        c = self.cwd.upper().rstrip('\\/')
        if len(c) <= 2 and c.endswith(':'):
            self.enter_drive_view()
            return
        parent = os.path.dirname(self.cwd)
        if parent and parent != self.cwd:
            self.cwd = parent
            self.load_dir()
            self.set_msg(f"上级目录: {parent}", C.STATUS)

    def open_item(self):
        if not self.items:
            return
        it = self.items[self.idx]
        if it['is_dir']:
            self.cwd = it['path']
            self.load_dir()
            self.set_msg(f"[成功] 打开: {it['name']}", C.SUCCESS)
        else:
            self._open_file(it)

    def _open_file(self, it):
        ext = os.path.splitext(it['name'])[1].lower()
        text_exts = {'.txt','.py','.md','.json','.xml','.html','.css','.js',
                     '.log','.ini','.cfg','.yml','.yaml','.csv','.conf',
                     '.sh','.bat','.ps1','.c','.cpp','.h','.java','.go',
                     '.rs','.ts','.php','.rb','.sql','.tex'}
        if ext in text_exts:
            editor = NanoEditor(it['path'])
            editor.run(self.stdscr)
            self.set_msg(f"编辑器已关闭: {it['name']}", C.STATUS)
            self.load_dir()
        else:
            try:
                if sys.platform == 'win32':
                    os.startfile(it['path'])
                else:
                    subprocess.run(['xdg-open', it['path']], check=True)
                self.set_msg(f"[成功] 已打开: {it['name']}", C.SUCCESS)
            except:
                self.set_msg(f"[失败] 无法打开: {it['name']}", C.ERROR)

    def _load_preview(self):
        if not self.items:
            self.preview_text = ""
            return
        it = self.items[self.idx]
        if it['is_dir']:
            try:
                children = os.listdir(it['path'])[:50]
                self.preview_text = "\n".join(children)
            except:
                self.preview_text = "(无法读取)"
        else:
            ext = os.path.splitext(it['name'])[1].lower()
            text_exts = {'.txt','.py','.md','.json','.xml','.html','.css','.js',
                         '.log','.ini','.cfg','.yml','.yaml','.csv','.conf'}
            if ext in text_exts:
                try:
                    with open(it['path'], 'r', encoding='utf-8') as f:
                        self.preview_text = f.read(3000)
                except:
                    try:
                        with open(it['path'], 'r', encoding='gbk') as f:
                            self.preview_text = f.read(3000)
                    except:
                        self.preview_text = "(无法读取)"
            else:
                self.preview_text = f"类型: {ext or '未知'}\n大小: {format_size(it['size'])}\n修改时间: {format_time(it['mtime'])}"

    # ==================== 绘制 ====================
    def draw(self):
        self.stdscr.erase()
        maxy, maxx = self.stdscr.getmaxyx()

        content_h = maxy - 4
        preview_w = maxx // 3 if self.preview else 0
        list_w = maxx - preview_w - 1 if self.preview else maxx

        # ---- 标题栏 ----
        if MODERN_TERM:
            title = f"{ICON_WEB} Winux 文件管理器 v2.0"
        else:
            title = "Winux 文件管理器 v2.0"
        快捷键提示 = "↑↓:移动 Enter:打开 F2:命令 H:帮助 W:上网 D:盘符 Q:退出"
        title_bar = pad_to_width(title + "  " + 快捷键提示, maxx)
        safe_addstr(self.stdscr, 0, 0, title_bar, curses.A_REVERSE | curses.A_BOLD, maxx)

        # ---- 路径栏 ----
        if self.mode == self.MODE_DRIVE:
            path_str = "[盘符选择模式]"
        elif self.mode == self.MODE_URL_INPUT:
            path_str = f"[{ICON_WEB} 浏览器模式 - 按 W 输入网址或 Esc 取消]"
        else:
            path_str = self.cwd
        safe_addstr(self.stdscr, 1, 0, pad_to_width(path_str, maxx), curses.A_REVERSE, maxx)

        # ---- 内容区 ----
        if self.mode == self.MODE_DRIVE:
            self._draw_drives(content_h, list_w)
        elif self.mode == self.MODE_URL_INPUT:
            self._draw_url_hint(content_h, list_w)
        else:
            self._draw_files(content_h, list_w)

        if self.preview and self.mode not in (self.MODE_DRIVE, self.MODE_URL_INPUT):
            self._draw_preview(content_h, list_w, preview_w)

        # ---- 命令输入栏 ----
        if self.mode == self.MODE_COMMAND:
            cmd_prompt = "命令> "
            safe_addstr(self.stdscr, maxy - 3, 0,
                        pad_to_width(cmd_prompt + self.command_buf, maxx),
                        curses.A_REVERSE | C.CMD, maxx)
            try:
                self.stdscr.move(maxy - 3, len(cmd_prompt) + len(self.command_buf))
            except:
                pass

        # ---- 状态栏 ----
        if self.mode == self.MODE_DRIVE:
            dc = len(self.drives)
            foot = f" 盘符模式 - 共 {dc} 个盘符 - 回车:选择 Esc:返回 "
        elif self.mode == self.MODE_URL_INPUT:
            foot = f" {ICON_WEB} 浏览器模式 - W:输入网址 Esc:取消 "
            foot = pad_to_width(foot, maxx)
        elif self.mode == self.MODE_COMMAND:
            foot = f" 命令模式 - Tab:补全 Esc:退出 | 输入 'help' 查看帮助 "
        else:
            dc = sum(1 for it in self.items if it['is_dir'])
            fc = len(self.items) - dc
            排序名称 = {0: "名称", 1: "大小", 2: "时间", 3: "扩展名"}
            sort_indicator = "+" if not self.sort_reverse else "-"
            filter_s = f" | 过滤: {self.filter_pattern}" if self.filter_pattern else ""
            clip_s = f" | {self.clipboard[0]}:{os.path.basename(self.clipboard[1])}" if self.clipboard else ""
            foot = f" 目录:{dc} 文件:{fc} | 排序:{排序名称[self.sort_mode]}{sort_indicator} | 详情:{'开' if self.detail else '关'} | 预览:{'开' if self.preview else '关'}{filter_s}{clip_s} | H:帮助 W:上网 "
            foot = pad_to_width(foot, maxx)
        safe_addstr(self.stdscr, maxy - 2, 0, foot, curses.A_REVERSE, maxx)

        # ---- 消息行 ----
        safe_addstr(self.stdscr, maxy - 1, 0, pad_to_width(self.msg, maxx), self.msg_color, maxx)

        # ---- 滚动条 ----
        items = self.drives if self.mode == self.MODE_DRIVE else self.items
        if len(items) > content_h:
            barh = max(1, content_h * content_h // len(items))
            ratio = self.scroll / max(1, len(items) - content_h)
            pos = int(ratio * (content_h - barh))
            bar_x = list_w
            for i in range(content_h):
                yy = 2 + i
                if pos <= i < pos + barh:
                    try:
                        self.stdscr.addch(yy, bar_x, curses.ACS_BLOCK, C.SELECTED)
                    except:
                        try:
                            self.stdscr.addch(yy, bar_x, '#', C.SELECTED)
                        except:
                            pass
                else:
                    try:
                        self.stdscr.addch(yy, bar_x, ' ', curses.A_DIM)
                    except:
                        pass

        self.stdscr.refresh()

    def _draw_drives(self, ch, maxx):
        for i in range(ch):
            y = 2 + i
            real = self.scroll + i
            if real >= len(self.drives):
                safe_addstr(self.stdscr, y, 0, "", 0, maxx)
                continue
            letter, label, free = self.drives[real]
            sel = (real == self.idx)
            attr = curses.color_pair(C.SELECTED) if sel else 0
            display = letter.replace('\\', '')
            if label:
                display += f" [{label}]"
            if free > 0:
                display += f" ({free:.0f}GB 可用)"
            icon = ICON_DRIVE if sel else "  "
            safe_addstr(self.stdscr, y, 0, icon + " " + display, attr, maxx - 1)

    def _draw_url_hint(self, ch, maxx):
        """在 URL 输入模式下显示提示信息"""
        lines = [
            "",
            "  输入网址即可浏览网页：",
            "",
            "  示例：",
            "    https://www.python.org",
            "    https://docs.python.org/3/",
            "    www.github.com",
            "",
            "  或输入搜索关键词：",
            "    search: python curses tutorial",
            "",
            "  按 W 弹出网址输入框",
            "  按 Esc 返回浏览模式",
        ]
        for i, text in enumerate(lines):
            y = 2 + i
            if i >= ch:
                break
            if i == 1:
                safe_addstr(self.stdscr, y, 0, text, curses.A_BOLD | C.CMD, maxx)
            else:
                safe_addstr(self.stdscr, y, 0, text, curses.A_DIM, maxx)

    def _draw_files(self, ch, maxx):
        if self.detail:
            name_w = max(20, maxx - 45)
        else:
            name_w = maxx - 4

        vis = self.items[self.scroll:self.scroll + ch]
        for i, it in enumerate(vis):
            y = 2 + i
            real = self.scroll + i
            sel = (real == self.idx)

            icon = get_icon(it['name'], it['is_dir'])
            color_pair = get_color_pair(it['name'], it['is_dir'])

            if sel:
                attr = curses.color_pair(C.SELECTED)
            else:
                attr = curses.color_pair(color_pair)

            mark = ""
            if self.clipboard and self.clipboard[1] == it['path']:
                mark = ICON_CLIP_COPY if self.clipboard[0] == 'copy' else ICON_CLIP_CUT

            if self.detail:
                sz = format_size(it['size'])
                tm = format_time(it['mtime'])
                perm = format_perm(it['mode'])
                name_field = pad_to_width(it['name'], name_w)
                line = f" {icon}{mark} {perm} {name_field} {sz:>10} {tm}"
            else:
                line = f" {icon}{mark} {it['name']}"

            safe_addstr(self.stdscr, y, 0, line, attr, maxx - 1)

        for y in range(2 + len(vis), ch + 2):
            safe_addstr(self.stdscr, y, 0, "", 0, maxx)

    def _draw_preview(self, ch, list_w, preview_w):
        if not self.preview_text:
            self._load_preview()

        x_start = list_w + 1
        safe_addstr(self.stdscr, 2, x_start, pad_to_width("📄 " + ICON_PREVIEW, preview_w),
                    curses.A_BOLD | C.TITLE, preview_w)

        lines = self.preview_text.split("\n")
        for i in range(min(ch - 1, len(lines))):
            y = 3 + i
            line = lines[i]
            if len(line) > preview_w - 2:
                line = line[:preview_w - 5] + "..."
            safe_addstr(self.stdscr, y, x_start, pad_to_width(line, preview_w),
                        curses.A_DIM, preview_w)

        for y in range(2, ch + 2):
            try:
                self.stdscr.addch(y, list_w, curses.ACS_VLINE, curses.A_DIM)
            except:
                try:
                    self.stdscr.addch(y, list_w, '|', curses.A_DIM)
                except:
                    pass

    # ==================== 帮助 ====================
    def draw_help(self):
        lines = [
            "Winux 文件管理器 v2.0 - 帮助",
            "══════════════════════════════════════════",
            "",
            "【浏览模式快捷键】",
            "  ↑↓ 或 J/K        移动光标",
            "  Enter            打开文件/目录",
            "  ← / Backspace    返回上级目录",
            "  D                盘符选择",
            "  W                打开浏览器（输入网址）",
            "  H                显示此帮助",
            "  F2               进入命令模式",
            "  F5 / R           刷新目录",
            "  V                切换详细/简略视图",
            "  P                切换预览面板",
            "  S                循环排序（名称>大小>时间>扩展名）",
            "  I                反转排序方向",
            "  .                显示/隐藏隐藏文件",
            "  F                过滤模式",
            "  B                书签菜单",
            "  M                复制/剪切/粘贴菜单",
            "  Del              删除选中项",
            "  F3               批量重命名",
            "  F4               创建文件/目录",
            "  Q                退出程序",
            "",
            "  【提示】在浏览模式直接输入网址",
            "        即可快速打开网页浏览器！",
            "",
            "【命令模式（按 F2 进入）】",
            "  输入命令后回车执行，Esc 退出。",
            "  方向键↑↓ 查看历史命令。",
            "",
            "【常用命令】",
            "  ls [-l] [-a] [-s]          列出文件",
            "  cd <路径>                   切换目录",
            "  pwd                         当前路径",
            "  mkdir <名称> [-p]           创建目录",
            "  touch <文件>                创建文件",
            "  cp <源> <目标> [-r]         复制",
            "  mv <源> <目标>              移动/重命名",
            "  rm <路径> [-r] [-f]         删除",
            "  cat <文件>                  查看文件",
            "  head/tail <文件> [-n N]     查看头部/尾部",
            "  find <模式> [-t f|d]        搜索文件",
            "  info <文件>                 文件信息",
            "  du [-d 深度]                磁盘使用量",
            "  stats                       文件统计",
            "  zip/unzip/tar               压缩/解压",
            "  diff <文件1> <文件2>        文件对比",
            "  bulk-rename <正则> <替换>   批量重命名",
            "  open <文件|网址>            外部打开",
            "  edit <文件>                 编辑文件",
            "  web <网址>                  浏览网页（纯 Python）",
            "  web search <关键词>         搜索网页",
            "  apt install/remove/search   软件包管理",
            "  bookmark add/del/list/go    书签管理",
            "  history                     命令历史",
            "  clear                       清屏",
            "  help                       显示帮助",
            "  quit                       退出程序",
            "",
            "══════════════════════════════════════════",
            "按任意键继续...",
        ]
        popup(self.stdscr, lines, "Winux 帮助", 60)

    # ==================== URL 浏览器功能 ====================

    def open_web_browser(self, preset_url=""):
        """
        弹出 URL 输入框，获取网页内容并显示。
        可以直接传入 preset_url 跳过输入步骤。
        """
        if preset_url:
            url = preset_url.strip()
        else:
            url = url_input_popup(self.stdscr, f"{ICON_WEB} 请输入网址:")
            if not url:
                self.set_msg("已取消", C.STATUS)
                return

        # 判断是搜索还是直接 URL
        if url.lower().startswith("search:"):
            query = url[7:].strip()
            if query:
                self._web_search(query, 10)
            else:
                self.set_msg("搜索关键词为空", C.WARNING)
            return

        # 如果不是合法 URL 格式，当作搜索处理
        if not is_url(url):
            self.set_msg(f"{ICON_WEB} 正在搜索: {url} ...", C.CMD)
            self._web_search(url, 10)
            return

        # 补全协议
        url = normalize_url(url)

        # 抓取网页
        self.set_msg(f"{ICON_WEB} 正在加载: {url} ...", C.CMD)
        self.draw()  # 立即刷新显示加载提示

        title, result = _fetch_web_page(url)

        if title is None:
            self.set_msg(f"[失败] {result}", C.ERROR)
            return

        display_title = title if title else url
        page_title = f"{ICON_WEB} {display_title}"
        lines = [f"来源: {url}", "─" * 60] + result
        self._show_paged_lines(page_title, lines)
        self.set_msg(f"[成功] 已加载: {display_title}", C.SUCCESS)

    # ==================== 命令模式 ====================
    def enter_command_mode(self):
        self.mode = self.MODE_COMMAND
        self.command_buf = ""
        self.history_idx = len(self.command_history)
        self.set_msg("命令模式 - 输入命令后回车执行", C.CMD)

    def exit_command_mode(self):
        self.mode = self.MODE_BROWSE
        self.command_buf = ""
        self.set_msg("已退出命令模式", C.STATUS)

    def enter_url_mode(self):
        """进入 URL 输入模式（显示提示界面）"""
        self.mode = self.MODE_URL_INPUT
        self.set_msg(f"{ICON_WEB} 浏览器模式 - 按 W 输入网址", C.CMD)

    def exit_url_mode(self):
        """退出 URL 输入模式"""
        self.mode = self.MODE_BROWSE
        self.set_msg("已退出浏览器模式", C.STATUS)

    def execute_command(self, cmd_line):
        cmd_line = cmd_line.strip()
        if not cmd_line:
            return
        self.command_history.append(cmd_line)
        if len(self.command_history) > 100:
            self.command_history = self.command_history[-100:]

        parts = cmd_line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        handlers = {
            "ls": self.cmd_ls, "ll": self.cmd_ll,
            "cd": self.cmd_cd, "pwd": self.cmd_pwd,
            "back": self.cmd_back, "tree": self.cmd_tree,
            "mkdir": self.cmd_mkdir, "touch": self.cmd_touch,
            "rm": self.cmd_rm, "cp": self.cmd_cp, "mv": self.cmd_mv,
            "rename": self.cmd_rename,
            "cat": self.cmd_cat, "head": self.cmd_head, "tail": self.cmd_tail,
            "diff": self.cmd_diff,
            "find": self.cmd_find, "info": self.cmd_info,
            "du": self.cmd_du, "stats": self.cmd_stats,
            "zip": self.cmd_zip, "unzip": self.cmd_unzip, "tar": self.cmd_tar,
            "bulk-rename": self.cmd_bulk_rename, "chmod": self.cmd_chmod,
            "open": self.cmd_open, "edit": self.cmd_edit, "nano": self.cmd_edit,
            "web": self.cmd_web,
            "apt": self.cmd_apt,
            "bookmark": self.cmd_bookmark, "bm": self.cmd_bookmark,
            "history": self.cmd_show_history,
            "clear": self.cmd_clear, "cls": self.cmd_clear,
            "help": self.draw_help_cmd,
            "quit": self.cmd_quit, "exit": self.cmd_quit,
        }

        handler = handlers.get(cmd)
        if handler:
            try:
                handler(args)
            except Exception as e:
                self.set_msg(f"[失败] 错误: {e}", C.ERROR)
        else:
            self.set_msg(f"[失败] 未知命令: {cmd} (输入 'help' 查看帮助)", C.ERROR)

    # ==================== 命令实现 ====================

    def _resolve_path(self, path):
        if path.startswith("~"):
            path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = os.path.join(self.cwd, path)
        return os.path.normpath(path)

    def cmd_ls(self, args):
        显示隐藏 = "-a" in args
        详细格式 = "-l" in args
        按大小排序 = "-s" in args
        target = self.cwd
        for a in args:
            if not a.startswith("-"):
                target = self._resolve_path(a)
                break
        if not os.path.isdir(target):
            self.set_msg(f"[失败] 不是目录: {target}", C.ERROR)
            return
        items = os.listdir(target)
        if not 显示隐藏:
            items = [i for i in items if not i.startswith(".")]
        entries = []
        for n in sorted(items, key=str.lower):
            fp = os.path.join(target, n)
            try:
                st = os.stat(fp)
                entries.append((n, os.path.isdir(fp), st.st_size, st.st_mtime))
            except:
                entries.append((n, False, 0, 0))
        if 按大小排序:
            entries.sort(key=lambda e: e[2], reverse=True)
        else:
            entries.sort(key=lambda e: (not e[1], e[0].lower()))

        lines = []
        for n, is_dir, sz, mt in entries:
            icon = ICON_FOLDER if is_dir else get_icon(n)
            if 详细格式:
                lines.append(f"  {icon} {n:<30} {format_size(sz):>10}  {format_time(mt)}")
            else:
                lines.append(f"  {icon} {n}")
        self._show_paged_lines(f"目录: {target}", lines)

    def cmd_ll(self, args):
        self.cmd_ls(["-l"] + args)

    def cmd_cd(self, args):
        if not args:
            self.cwd = os.path.expanduser("~")
        else:
            target = args[0]
            if target == "..":
                self.cwd = os.path.dirname(self.cwd)
            elif target == "~":
                self.cwd = os.path.expanduser("~")
            elif target in self.bookmarks:
                self.cwd = self.bookmarks[target]
            else:
                self.cwd = self._resolve_path(target)
        if os.path.isdir(self.cwd):
            self.load_dir()
            self.set_msg(f"-> {self.cwd}", C.SUCCESS)
        else:
            self.set_msg(f"[失败] 路径不存在: {self.cwd}", C.ERROR)

    def cmd_pwd(self, args):
        self.set_msg(f"当前目录: {self.cwd}", C.STATUS)

    def cmd_back(self, args):
        self.go_up()

    def cmd_tree(self, args):
        max_depth = 3
        for i, a in enumerate(args):
            if a == "-L" and i + 1 < len(args):
                try:
                    max_depth = int(args[i + 1])
                except:
                    pass
        lines = []
        lines.append(f"{os.path.basename(self.cwd) or self.cwd}/")
        self._tree_collect(self.cwd, "", max_depth, 0, lines)
        self._show_paged_lines("目录树", lines)

    def _tree_collect(self, path, prefix, max_d, depth, lines):
        if depth >= max_d:
            return
        try:
            items = sorted(os.listdir(path),
                          key=lambda x: (not os.path.isdir(os.path.join(path, x)), x.lower()))
        except PermissionError:
            lines.append(prefix + "  [无权限访问]")
            return
        items = [i for i in items if not i.startswith(".")]
        for idx, name in enumerate(items):
            full = os.path.join(path, name)
            is_last = idx == len(items) - 1
            branch = "`-- " if is_last else "|-- "
            icon = ICON_FOLDER if os.path.isdir(full) else get_icon(name)
            lines.append(f"{prefix}{branch}{icon} {name}")
            if os.path.isdir(full) and not is_last:
                ext = "    " if is_last else "|   "
                self._tree_collect(full, prefix + ext, max_d, depth + 1, lines)

    def cmd_mkdir(self, args):
        if not args:
            name = input_popup(self.stdscr, "目录名称:")
            if not name: return
            args = [name]
        递归创建 = "-p" in args
        name = [a for a in args if not a.startswith("-")][0]
        path = self._resolve_path(name)
        try:
            if 递归创建:
                os.makedirs(path, exist_ok=True)
            else:
                os.mkdir(path)
            self.load_dir()
            self.set_msg(f"[成功] 已创建: {name}", C.SUCCESS)
        except OSError as e:
            self.set_msg(f"[失败] 创建失败: {e}", C.ERROR)

    def cmd_touch(self, args):
        if not args:
            name = input_popup(self.stdscr, "文件名称:")
            if not name: return
            args = [name]
        for n in args:
            path = self._resolve_path(n)
            try:
                if os.path.exists(path):
                    os.utime(path, None)
                    self.set_msg(f"[成功] 已更新时间戳: {n}", C.SUCCESS)
                else:
                    with open(path, "w") as f:
                        pass
                    self.load_dir()
                    self.set_msg(f"[成功] 已创建: {n}", C.SUCCESS)
            except OSError as e:
                self.set_msg(f"[失败] 失败: {n} - {e}", C.ERROR)

    def cmd_rm(self, args):
        if not args:
            self.set_msg("用法: rm <路径> [-r] [-f]", C.ERROR)
            return
        递归 = "-r" in args
        强制 = "-f" in args
        targets = [a for a in args if not a.startswith("-")]
        for t in targets:
            path = self._resolve_path(t)
            if not os.path.exists(path):
                if not 强制:
                    self.set_msg(f"文件不存在: {t}", C.WARNING)
                continue
            if os.path.isdir(path) and not 递归:
                self.set_msg(f"[失败] {t} 是目录，需要 -r 参数", C.ERROR)
                continue
            if not 强制:
                if not confirm_popup(self.stdscr, f"确定删除 {t}？"):
                    continue
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                self.set_msg(f"[成功] 已删除: {t}", C.SUCCESS)
            except OSError as e:
                self.set_msg(f"[失败] 删除失败: {t} - {e}", C.ERROR)
        self.load_dir()

    def cmd_cp(self, args):
        if len(args) < 2:
            self.set_msg("用法: cp <源> <目标> [-r]", C.ERROR)
            return
        递归 = "-r" in args
        src = self._resolve_path(args[0])
        dst = self._resolve_path(args[1])
        if not os.path.exists(src):
            self.set_msg(f"[失败] 源文件不存在: {args[0]}", C.ERROR)
            return
        try:
            if os.path.isdir(src):
                if not 递归:
                    self.set_msg("[失败] 复制目录需要 -r 参数", C.ERROR)
                    return
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            self.set_msg(f"[成功] 已复制: {args[0]} -> {args[1]}", C.SUCCESS)
            self.load_dir()
        except OSError as e:
            self.set_msg(f"[失败] 复制失败: {e}", C.ERROR)

    def cmd_mv(self, args):
        if len(args) < 2:
            self.set_msg("用法: mv <源> <目标>", C.ERROR)
            return
        src = self._resolve_path(args[0])
        dst = self._resolve_path(args[1])
        if not os.path.exists(src):
            self.set_msg(f"[失败] 源文件不存在: {args[0]}", C.ERROR)
            return
        try:
            shutil.move(src, dst)
            self.set_msg(f"[成功] 已移动: {args[0]} -> {args[1]}", C.SUCCESS)
            self.load_dir()
        except OSError as e:
            self.set_msg(f"[失败] 移动失败: {e}", C.ERROR)

    def cmd_rename(self, args):
        if len(args) < 2:
            self.set_msg("用法: rename <旧名> <新名>", C.ERROR)
            return
        old = self._resolve_path(args[0])
        new = self._resolve_path(args[1])
        if not os.path.exists(old):
            self.set_msg(f"[失败] 文件不存在: {args[0]}", C.ERROR)
            return
        try:
            os.rename(old, new)
            self.set_msg(f"[成功] {args[0]} -> {args[1]}", C.SUCCESS)
            self.load_dir()
        except OSError as e:
            self.set_msg(f"[失败] 重命名失败: {e}", C.ERROR)

    def cmd_cat(self, args):
        if not args:
            self.set_msg("用法: cat <文件>", C.ERROR)
            return
        path = self._resolve_path(args[0])
        if not os.path.isfile(path):
            self.set_msg(f"[失败] 不是文件: {args[0]}", C.ERROR)
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            lines = [f"{i+1:>5}  {l.rstrip()}" for i, l in enumerate(lines[:500])]
            if len(lines) > 500:
                lines.append("... (内容过长，已截断)")
            self._show_paged_lines(f"文件: {os.path.basename(path)}", lines)
        except OSError as e:
            self.set_msg(f"[失败] {e}", C.ERROR)

    # 修复：cmd_head 不再重复调用 f.readline()
    def cmd_head(self, args):
        if not args:
            self.set_msg("用法: head <文件> [-n N]", C.ERROR)
            return
        n = 10
        for i, a in enumerate(args):
            if a == "-n" and i + 1 < len(args):
                try: n = int(args[i+1])
                except: pass
        path = self._resolve_path(args[0])
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = []
                for _ in range(n):
                    line = f.readline()
                    if not line:
                        break
                    lines.append(line.rstrip())
            self._show_paged_lines(f"head -{n} {os.path.basename(path)}", lines)
        except OSError as e:
            self.set_msg(f"[失败] {e}", C.ERROR)

    def cmd_tail(self, args):
        if not args:
            self.set_msg("用法: tail <文件> [-n N]", C.ERROR)
            return
        n = 10
        for i, a in enumerate(args):
            if a == "-n" and i + 1 < len(args):
                try: n = int(args[i+1])
                except: pass
        path = self._resolve_path(args[0])
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            lines = [l.rstrip() for l in all_lines[-n:]]
            self._show_paged_lines(f"tail -{n} {os.path.basename(path)}", lines)
        except OSError as e:
            self.set_msg(f"[失败] {e}", C.ERROR)

    def cmd_diff(self, args):
        if len(args) < 2:
            self.set_msg("用法: diff <文件1> <文件2>", C.ERROR)
            return
        f1 = self._resolve_path(args[0])
        f2 = self._resolve_path(args[1])
        for f in [f1, f2]:
            if not os.path.isfile(f):
                self.set_msg(f"[失败] 不是文件: {f}", C.ERROR)
                return
        h1 = self._file_hash(f1)
        h2 = self._file_hash(f2)
        lines = []
        lines.append(f"  MD5:  {os.path.basename(f1):<20} {h1['md5']}")
        lines.append(f"  MD5:  {os.path.basename(f2):<20} {h2['md5']}")
        if h1['md5'] == h2['md5']:
            lines.append("[成功] 两个文件完全相同")
            self._show_paged_lines("文件对比", lines)
            return
        try:
            with open(f1) as a, open(f2) as b:
                la = a.readlines()
                lb = b.readlines()
        except OSError as e:
            self.set_msg(f"[失败] {e}", C.ERROR)
            return
        lines.append("--- 差异如下 ---")
        shown = 0
        for i in range(max(len(la), len(lb))):
            al = la[i].rstrip() if i < len(la) else "<EOF>"
            bl = lb[i].rstrip() if i < len(lb) else "<EOF>"
            if al != bl:
                lines.append(f"  L{i+1} - {al}")
                lines.append(f"  L{i+1} + {bl}")
                shown += 1
                if shown >= 50:
                    lines.append("... (差异过多，已截断)")
                    break
        self._show_paged_lines("文件对比", lines)

    def _file_hash(self, path):
        h1 = hashlib.md5()
        h2 = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h1.update(chunk)
                    h2.update(chunk)
        except:
            pass
        return {"md5": h1.hexdigest(), "sha256": h2.hexdigest()}

    def cmd_find(self, args):
        if not args:
            self.set_msg("用法: find <模式> [-t f|d] [-i] [路径]", C.ERROR)
            return
        pattern = args[0]
        target_type = "all"
        ignore_case = False
        search_path = self.cwd
        for i, a in enumerate(args[1:], 1):
            if a == "-t" and i < len(args) - 1:
                target_type = args[i + 1]
            elif a == "-i":
                ignore_case = True
            elif not a.startswith("-"):
                search_path = self._resolve_path(a)
        if ignore_case:
            pat_re = re.compile(fnmatch.translate(pattern), re.IGNORECASE)
        else:
            pat_re = re.compile(fnmatch.translate(pattern))

        results = []
        for root, dirs, files in os.walk(search_path):
            for d in dirs:
                if target_type in ("all", "d") and pat_re.match(d):
                    results.append(os.path.join(root, d))
            for f in files:
                if target_type in ("all", "f") and pat_re.match(f):
                    results.append(os.path.join(root, f))
        if not results:
            self.set_msg(f"未找到匹配: {pattern}", C.WARNING)
            return
        lines = [f"找到 {len(results)} 个匹配项:"]
        for r in results[:200]:
            rel = os.path.relpath(r, self.cwd)
            icon = ICON_FOLDER if os.path.isdir(r) else get_icon(os.path.basename(r))
            lines.append(f"  {icon} {rel}")
        if len(results) > 200:
            lines.append(f"  ... 还有 {len(results)-200} 项未显示")
        self._show_paged_lines(f"搜索: {pattern}", lines)

    def cmd_info(self, args):
        if not args:
            if not self.items:
                self.set_msg("没有选中项", C.WARNING)
                return
            path = self.items[self.idx]['path']
        else:
            path = self._resolve_path(args[0])
        if not os.path.exists(path):
            self.set_msg(f"[失败] 文件不存在: {path}", C.ERROR)
            return
        st = os.stat(path)
        is_dir = os.path.isdir(path)
        lines = [
            f"文件信息: {os.path.basename(path)}",
            "────────────────────────────────────────",
            f"  路径:    {path}",
            f"  类型:    {'目录' if is_dir else '文件'}",
            f"  大小:    {format_size(st.st_size)} ({st.st_size} 字节)",
            f"  权限:    {format_perm(st.st_mode)}",
            f"  创建:    {format_time(st.st_ctime)}",
            f"  修改:    {format_time(st.st_mtime)}",
            f"  访问:    {format_time(st.st_atime)}",
        ]
        if not is_dir:
            h = self._file_hash(path)
            lines.append(f"  MD5:     {h['md5']}")
            lines.append(f"  SHA256:  {h['sha256']}")
        self._show_paged_lines("文件信息", lines)

    def cmd_du(self, args):
        max_depth = 2
        for i, a in enumerate(args):
            if a == "-d" and i + 1 < len(args):
                try: max_depth = int(args[i+1])
                except: pass
        target = self.cwd
        for a in args:
            if not a.startswith("-"):
                target = self._resolve_path(a)
                break
        results = self._calc_usage(target, max_depth, 0)
        if not results:
            self.set_msg("目录为空", C.WARNING)
            return
        max_size = max(r["size"] for r in results) or 1
        lines = [f"磁盘使用量: {target}"]
        lines.append("-" * 40)
        for entry in sorted(results, key=lambda x: x["size"], reverse=True)[:30]:
            bar_len = int(entry["size"] / max_size * 20)
            bar = "#" * bar_len
            icon = ICON_FOLDER if entry["is_dir"] else get_icon(entry["name"])
            lines.append(f"  {bar} {format_size(entry['size']):>10}  {icon} {entry['name']}")
        self._show_paged_lines("磁盘使用量", lines)

    def _calc_usage(self, path, max_d, depth):
        results = []
        if depth >= max_d:
            return results
        try:
            items = os.listdir(path)
        except PermissionError:
            return results
        for item in items:
            full = os.path.join(path, item)
            try:
                if os.path.isdir(full):
                    size = self._dir_size(full)
                    results.append({"name": item, "size": size, "is_dir": True})
                    if depth + 1 < max_d:
                        results.extend(self._calc_usage(full, max_d, depth + 1))
                elif os.path.isfile(full):
                    results.append({"name": item, "size": os.path.getsize(full), "is_dir": False})
            except OSError:
                pass
        return results

    def _dir_size(self, path):
        total = 0
        try:
            for root, dirs, files in os.walk(path):
                for f in files:
                    try: total += os.path.getsize(os.path.join(root, f))
                    except: pass
        except OSError:
            pass
        return total

    def cmd_stats(self, args):
        target = self.cwd
        for a in args:
            if not a.startswith("-"):
                target = self._resolve_path(a)
                break
        if not os.path.isdir(target):
            self.set_msg("需要指定目录", C.ERROR)
            return
        counts = defaultdict(int)
        total_size = defaultdict(int)
        for root, dirs, files in os.walk(target):
            for f in files:
                ext = f.rsplit(".", 1)[-1].lower() if "." in f else "(无扩展名)"
                try:
                    sz = os.path.getsize(os.path.join(root, f))
                except:
                    sz = 0
                counts[ext] += 1
                total_size[ext] += sz
        if not counts:
            self.set_msg("目录为空", C.WARNING)
            return
        lines = [f"文件统计: {target}", "-" * 40]
        lines.append(f"  {'类型':<15} {'数量':>6}  {'总大小':>12}")
        lines.append("  " + "-" * 38)
        for ext, cnt in sorted(counts.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  {ext:<15} {cnt:>6}  {format_size(total_size[ext]):>12}")
        self._show_paged_lines("文件统计", lines)

    def cmd_zip(self, args):
        if len(args) < 2:
            self.set_msg("用法: zip <输出.zip> <源文件...>", C.ERROR)
            return
        archive = self._resolve_path(args[0])
        sources = [self._resolve_path(a) for a in args[1:]]
        try:
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
                for src in sources:
                    if not os.path.exists(src):
                        continue
                    if os.path.isfile(src):
                        zf.write(src, os.path.basename(src))
                    else:
                        for root, dirs, files in os.walk(src):
                            for f in files:
                                full = os.path.join(root, f)
                                arcname = os.path.relpath(full, os.path.dirname(src))
                                zf.write(full, arcname)
            sz = os.path.getsize(archive)
            self.set_msg(f"[成功] 已创建: {archive} ({format_size(sz)})", C.SUCCESS)
        except OSError as e:
            self.set_msg(f"[失败] 压缩失败: {e}", C.ERROR)

    def cmd_unzip(self, args):
        if not args:
            self.set_msg("用法: unzip <压缩包> [-d 目标目录]", C.ERROR)
            return
        archive = self._resolve_path(args[0])
        dest = self.cwd
        for i, a in enumerate(args[1:], 1):
            if a == "-d" and i < len(args):
                dest = self._resolve_path(args[i + 1])
        if not os.path.isfile(archive):
            self.set_msg(f"[失败] 文件不存在: {args[0]}", C.ERROR)
            return
        os.makedirs(dest, exist_ok=True)
        try:
            if archive.endswith(".zip"):
                with zipfile.ZipFile(archive) as zf:
                    zf.extractall(dest)
            elif archive.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2")):
                with tarfile.open(archive, "r:*") as tf:
                    tf.extractall(dest)
            else:
                self.set_msg("[失败] 不支持的格式", C.ERROR)
                return
            self.set_msg(f"[成功] 已解压到: {dest}", C.SUCCESS)
        except Exception as e:
            self.set_msg(f"[失败] 解压失败: {e}", C.ERROR)

    def cmd_tar(self, args):
        if len(args) < 2:
            self.set_msg("用法: tar -c <归档.tar.gz> <源...> | tar -x <归档> [-d 目标]", C.ERROR)
            return
        mode = args[0]
        archive = self._resolve_path(args[1])
        if mode in ("-c", "create"):
            sources = [self._resolve_path(a) for a in args[2:]]
            try:
                with tarfile.open(archive, "w:gz") as tf:
                    for src in sources:
                        if os.path.exists(src):
                            tf.add(src, arcname=os.path.basename(src))
                self.set_msg(f"[成功] 已创建: {archive}", C.SUCCESS)
            except OSError as e:
                self.set_msg(f"[失败] 创建失败: {e}", C.ERROR)
        elif mode in ("-x", "extract"):
            dest = self.cwd
            for i, a in enumerate(args[2:], 2):
                if a == "-d" and i + 1 < len(args):
                    dest = self._resolve_path(args[i + 1])
            os.makedirs(dest, exist_ok=True)
            try:
                with tarfile.open(archive, "r:*") as tf:
                    tf.extractall(dest)
                self.set_msg(f"[成功] 已解压到: {dest}", C.SUCCESS)
            except Exception as e:
                self.set_msg(f"[失败] 解压失败: {e}", C.ERROR)
        else:
            self.set_msg(f"[失败] 未知模式: {mode}", C.ERROR)

    def cmd_bulk_rename(self, args):
        if len(args) < 2:
            self.set_msg("用法: bulk-rename <正则> <替换> [路径]", C.ERROR)
            return
        try:
            pattern = re.compile(args[0])
        except re.error as e:
            self.set_msg(f"[失败] 正则错误: {e}", C.ERROR)
            return
        replacement = args[1]
        target_dir = self.cwd
        for a in args[2:]:
            if not a.startswith("-"):
                target_dir = self._resolve_path(a)
        try:
            items = os.listdir(target_dir)
        except OSError as e:
            self.set_msg(f"[失败] {e}", C.ERROR)
            return
        matched = []
        for name in sorted(items):
            if pattern.search(name):
                new_name = pattern.sub(replacement, name)
                if new_name != name:
                    matched.append((name, new_name))
        if not matched:
            self.set_msg("没有匹配项", C.WARNING)
            return
        lines = [f"将重命名 {len(matched)} 个文件:"]
        for old, new in matched:
            lines.append(f"  {old} -> {new}")
        self._show_paged_lines("批量重命名预览", lines)
        if confirm_popup(self.stdscr, f"确认重命名 {len(matched)} 个文件？"):
            for old, new in matched:
                try:
                    os.rename(os.path.join(target_dir, old), os.path.join(target_dir, new))
                except OSError:
                    pass
            self.set_msg(f"[成功] {len(matched)} 个文件已重命名", C.SUCCESS)
            self.load_dir()

    def cmd_chmod(self, args):
        if platform.system() == "Windows":
            self.set_msg("chmod 仅支持 Linux/macOS 系统", C.WARNING)
            return
        if len(args) < 2:
            self.set_msg("用法: chmod <权限> <文件>", C.ERROR)
            return
        try:
            mode = int(args[0], 8)
            path = self._resolve_path(args[1])
            os.chmod(path, mode)
            self.set_msg(f"[成功] 权限已设为 {args[0]}", C.SUCCESS)
        except (ValueError, OSError) as e:
            self.set_msg(f"[失败] {e}", C.ERROR)

    def cmd_open(self, args):
        if not args:
            self.set_msg("用法: open <文件|目录|网址>", C.ERROR)
            return
        target = args[0]
        # 如果是 URL，交给 web 浏览器处理
        if is_url(target):
            self.open_web_browser(target)
            return
        target_path = self._resolve_path(target)
        if not os.path.exists(target_path):
            self.set_msg(f"[失败] 文件不存在: {target}", C.ERROR)
            return
        try:
            if sys.platform == "win32":
                os.startfile(target_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", target_path], check=True)
            else:
                subprocess.run(["xdg-open", target_path], check=True)
            self.set_msg(f"[成功] 已打开: {args[0]}", C.SUCCESS)
        except Exception as e:
            self.set_msg(f"[失败] 打开失败: {e}", C.ERROR)

    def cmd_edit(self, args):
        if not args:
            if not self.items or self.items[self.idx]['is_dir']:
                self.set_msg("请选择一个文件进行编辑", C.WARNING)
                return
            path = self.items[self.idx]['path']
        else:
            path = self._resolve_path(args[0])
            if not os.path.exists(path):
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        pass
                except OSError as e:
                    self.set_msg(f"[失败] 无法创建: {e}", C.ERROR)
                    return
        try:
            with open(path, "rb") as f:
                chunk = f.read(512)
                if b"\x00" in chunk:
                    self.set_msg("不支持编辑二进制文件", C.WARNING)
                    return
        except OSError:
            pass
        editor = NanoEditor(path)
        editor.run(self.stdscr)
        self.set_msg(f"编辑器已关闭: {os.path.basename(path)}", C.STATUS)
        self.load_dir()

    # ==================== Web 浏览器命令（纯 Python 实现）====================

    def cmd_web(self, args):
        """
        web <网址>              - 浏览网页，显示纯文本内容
        web search <关键词>      - 搜索关键词（DuckDuckGo）
        web search <关键词> -n N - 限制结果数量（默认 10）
        """
        if not args:
            # 无参数时弹出 URL 输入框
            self.open_web_browser()
            return

        # ---- 搜索模式 ----
        if args[0].lower() == "search":
            if len(args) < 2:
                self.set_msg("用法: web search <关键词> [-n N]", C.ERROR)
                return
            query = args[1]
            max_results = 10
            for i, a in enumerate(args[1:], 1):
                if a == "-n" and i + 1 < len(args):
                    try: max_results = int(args[i + 1])
                    except: pass
            self._web_search(query, max_results)
            return

        # ---- 直接打开 URL ----
        url = args[0]
        self.open_web_browser(url)

    def _web_search(self, query, max_results=10):
        """使用 DuckDuckGo HTML 搜索"""
        # 检查依赖
        try:
            import requests
        except ImportError:
            self.set_msg("需要安装 requests: pip install requests", C.ERROR)
            return

        search_url = f"https://duckduckgo.com/html/?q={requests.utils.quote(query)}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }

        self.set_msg(f"{ICON_WEB} 正在搜索: {query} ...", C.CMD)

        try:
            resp = requests.get(search_url, headers=headers, timeout=15)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or 'utf-8'
        except Exception as e:
            self.set_msg(f"[失败] 搜索失败: {e}", C.ERROR)
            return

        # 解析搜索结果
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')

            results = []
            items = soup.select('.result, .web-result, .results_links')
            for item in items[:max_results]:
                link_el = item.select_one('a.result__a, a[href]')
                if not link_el:
                    continue
                title = link_el.get_text(strip=True)[:80]
                href = link_el.get('href', '')

                if href.startswith('//duckduckgo.com/l/?uddg='):
                    from urllib.parse import parse_qs, urlparse
                    parsed = urlparse(href)
                    qs = parse_qs(parsed.query)
                    real_url = qs.get('uddg', [href])[0]
                elif href.startswith('/'):
                    real_url = 'https://duckduckgo.com' + href
                else:
                    real_url = href

                snippet_el = item.select_one('.result__snippet, .snippet')
                snippet = snippet_el.get_text(strip=True)[:120] if snippet_el else ''

                if title and real_url:
                    results.append((title, real_url, snippet))

            if not results:
                links = soup.select('a[href]')
                seen = set()
                for a in links:
                    text = a.get_text(strip=True)
                    href = a.get('href', '')
                    if len(text) > 10 and 'duckduckgo.com' not in href and href.startswith('http'):
                        if href not in seen and len(results) < max_results:
                            seen.add(href)
                            results.append((text[:80], href, ''))

        except ImportError:
            import re as re_mod
            results = []
            matches = re_mod.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', resp.text)
            for href, text in matches[:max_results]:
                text = re_mod.sub(r'<[^>]+>', '', text).strip()[:80]
                if href.startswith('//duckduckgo.com/l/?uddg='):
                    from urllib.parse import parse_qs, urlparse
                    parsed = urlparse(href)
                    qs = parse_qs(parsed.query)
                    href = qs.get('uddg', [href])[0]
                results.append((text, href, ''))

        if not results:
            self.set_msg(f"[失败] 未找到结果: {query}", C.WARNING)
            return

        # 格式化输出
        lines = [f"搜索: {query}", f"找到 {len(results)} 条结果", "─" * 60]
        for i, (title, url, snippet) in enumerate(results, 1):
            lines.append(f"  [{i}] {title}")
            lines.append(f"      {url}")
            if snippet:
                lines.append(f"      {snippet}")
            lines.append("")

        self._show_paged_lines(f"{ICON_WEB} 搜索: {query}", lines)
        self.set_msg(f"[成功] 找到 {len(results)} 条结果: {query}", C.SUCCESS)

    def cmd_apt(self, args):
        if platform.system() != "Windows":
            self.set_msg("apt 命令仅支持 Windows 系统", C.WARNING)
            return
        if not args:
            self._apt_help()
            return
        if not self.apt_backend:
            self.set_msg("[失败] 未检测到 winget/choco/scoop", C.ERROR)
            return
        action = args[0].lower()
        packages = args[1:] if len(args) > 1 else []
        cmd = self._build_apt_command(action, packages)
        if cmd is None:
            self.set_msg(f"[失败] 未知操作: {action}", C.ERROR)
            return
        display = " ".join(cmd) if isinstance(cmd, list) else cmd
        self.set_msg(f"> {display}", C.CMD)
        try:
            if isinstance(cmd, list):
                result = subprocess.run(cmd, check=False)
            else:
                result = subprocess.run(cmd, shell=True, check=False)
            if result.returncode == 0:
                self.set_msg(f"[成功] 完成 (后端: {self.apt_backend})", C.SUCCESS)
            else:
                self.set_msg(f"返回码: {result.returncode}", C.WARNING)
        except FileNotFoundError:
            self.set_msg(f"[失败] {self.apt_backend} 不可用", C.ERROR)
            self.apt_backend = self._detect_apt_backend()

    def _build_apt_command(self, action, packages):
        b = self.apt_backend
        if b == "winget":
            if action in ("install","i"):
                return ["winget","install","--exact","--silent"] + packages if packages else ["winget","install","--help"]
            elif action in ("remove","uninstall","rm"):
                return ["winget","uninstall","--exact","--silent"] + packages if packages else ["winget","uninstall","--help"]
            elif action == "update": return ["winget","source","update"]
            elif action in ("upgrade","update-all"): return ["winget","upgrade","--all"]
            elif action in ("search","s"):
                return ["winget","search"] + packages if packages else ["winget","search"]
            elif action in ("list","ls"): return ["winget","list"]
            elif action in ("show","info"):
                return ["winget","show"] + packages if packages else ["winget","show","--help"]
        elif b == "choco":
            if action in ("install","i"):
                return ["choco","install","-y"] + packages if packages else ["choco","install","--help"]
            elif action in ("remove","uninstall","rm"):
                return ["choco","uninstall","-y"] + packages if packages else ["choco","uninstall","--help"]
            elif action in ("update","upgrade","update-all"): return ["choco","upgrade","all","-y"]
            elif action in ("search","s"):
                return ["choco","search"] + packages if packages else ["choco","search"]
            elif action in ("list","ls"): return ["choco","list","-y","--local-only"]
            elif action in ("show","info"):
                return ["choco","info"] + packages if packages else ["choco","info"]
            elif action == "clean": return ["choco","clean","-y"]
        elif b == "scoop":
            if action in ("install","i"):
                return ["scoop","install"] + packages if packages else ["scoop","install","--help"]
            elif action in ("remove","uninstall","rm"):
                return ["scoop","uninstall"] + packages if packages else ["scoop","uninstall","--help"]
            elif action in ("update","upgrade","update-all"): return ["scoop","update","*"]
            elif action in ("search","s"):
                return ["scoop","search"] + packages if packages else ["scoop","search"]
            elif action in ("list","ls"): return ["scoop","list"]
            elif action in ("show","info"):
                return ["scoop","info"] + packages if packages else ["scoop","info","--help"]
            elif action == "clean": return ["scoop","cache","rm","*"]
        return None

    def _apt_help(self):
        lines = [
            "软件包管理器前端",
            "══════════════════════════════════════════",
            f"后端: {self.apt_backend or '未检测到'}",
            "",
            "  install <包名>     安装软件包",
            "  remove  <包名>     卸载软件包",
            "  update             更新软件源",
            "  upgrade            升级所有软件包",
            "  search  <关键词>   搜索软件包",
            "  list               已安装列表",
            "  show    <包名>     软件包信息",
            "  clean              清理缓存",
            "",
            "后端优先级: winget > choco > scoop",
        ]
        self._show_paged_lines("软件包管理帮助", lines)

    def cmd_bookmark(self, args):
        if not args or args[0] == "list":
            if not self.bookmarks:
                self.set_msg("暂无书签", C.WARNING)
                return
            lines = ["书签列表:"]
            for name, path in self.bookmarks.items():
                lines.append(f"  [B] {name} -> {path}")
            self._show_paged_lines("书签", lines)
            return
        action = args[0]
        if action == "add":
            if len(args) >= 3:
                name = args[1]
                path = self._resolve_path(args[2])
            else:
                name = args[1] if len(args) > 1 else os.path.basename(self.cwd)
                path = self.cwd
            self.bookmarks[name] = os.path.abspath(path)
            self._save_bookmarks()
            self.set_msg(f"[成功] 书签 '{name}' -> {path}", C.SUCCESS)
        elif action in ("del","remove"):
            name = args[1] if len(args) > 1 else ""
            if name in self.bookmarks:
                del self.bookmarks[name]
                self._save_bookmarks()
                self.set_msg(f"[成功] 已删除: {name}", C.SUCCESS)
            else:
                self.set_msg(f"书签不存在: {name}", C.WARNING)
        elif action in ("go","open"):
            name = args[1] if len(args) > 1 else ""
            if name in self.bookmarks:
                self.cwd = self.bookmarks[name]
                self.load_dir()
                self.set_msg(f"-> {name}: {self.cwd}", C.SUCCESS)
            else:
                self.set_msg(f"书签不存在: {name}", C.WARNING)
        else:
            self.set_msg(f"[失败] 未知操作: {action}", C.ERROR)

    def cmd_show_history(self, args):
        if not self.command_history:
            self.set_msg("暂无历史记录", C.WARNING)
            return
        lines = []
        for i, cmd in enumerate(self.command_history[-20:], 1):
            lines.append(f"  {i:>3}  {cmd}")
        self._show_paged_lines("命令历史", lines)

    def cmd_clear(self, args):
        pass

    def cmd_quit(self, args):
        self.running = False

    def draw_help_cmd(self, args=None):
        self.draw_help()

    # ==================== 弹窗输出 ====================
    def _show_paged_lines(self, title, lines):
        maxy, maxx = self.stdscr.getmaxyx()
        page_h = maxy - 6
        pages = []
        for i in range(0, len(lines), page_h):
            pages.append(lines[i:i+page_h])
        if not pages:
            pages = [["(空)"]]

        current_page = 0
        while True:
            page_lines = pages[current_page]
            page_title = f"{title} ({current_page+1}/{len(pages)})"
            footer = "← →: 翻页 | 其他键: 关闭"
            display_lines = page_lines + [""] * max(0, page_h - len(page_lines))
            display_lines = display_lines[:page_h]
            if len(pages) > 1:
                display_lines[-1] = footer

            popup_h = min(len(display_lines) + 4, maxy - 2)
            max_line_len = max((len(l) for l in display_lines), default=10)
            popup_w = min(maxx - 4, max(max_line_len + 6, 30))
            y = (maxy - popup_h) // 2
            x = (maxx - popup_w) // 2
            win = curses.newwin(popup_h, popup_w, y, x)
            win.keypad(True)
            win.border()
            safe_addstr(win, 0, (popup_w - len(page_title)) // 2, f" {page_title} ", curses.A_BOLD | C.TITLE)
            for i, l in enumerate(display_lines[:popup_h-4]):
                safe_addstr(win, i + 2, 2, l, 0, popup_w - 4)
            win.refresh()
            ch = win.getch()
            del win
            self.stdscr.touchwin()
            if ch == curses.KEY_RIGHT and current_page < len(pages) - 1:
                current_page += 1
            elif ch == curses.KEY_LEFT and current_page > 0:
                current_page -= 1
            else:
                break

    # ==================== 书签菜单 ====================
    def show_bookmark_menu(self):
        actions = ["添加当前目录", "跳转到书签...", "删除书签...", "列出全部", "取消"]
        choice = self._menu_popup("书签管理", actions)
        if choice == 0:
            name = input_popup(self.stdscr, "书签名称:")
            if name:
                self.bookmarks[name] = self.cwd
                self._save_bookmarks()
                self.set_msg(f"[成功] 书签 '{name}' -> {self.cwd}", C.SUCCESS)
        elif choice == 1:
            if not self.bookmarks:
                self.set_msg("暂无书签", C.WARNING)
                return
            bm_names = list(self.bookmarks.keys())
            idx = self._menu_popup("跳转书签", bm_names)
            if idx >= 0:
                name = bm_names[idx]
                self.cwd = self.bookmarks[name]
                self.load_dir()
                self.set_msg(f"-> {name}: {self.cwd}", C.SUCCESS)
        elif choice == 2:
            if not self.bookmarks:
                self.set_msg("暂无书签", C.WARNING)
                return
            bm_names = list(self.bookmarks.keys())
            idx = self._menu_popup("删除书签", bm_names)
            if idx >= 0:
                name = bm_names[idx]
                del self.bookmarks[name]
                self._save_bookmarks()
                self.set_msg(f"[成功] 已删除: {name}", C.SUCCESS)
        elif choice == 3:
            lines = []
            for name, path in self.bookmarks.items():
                lines.append(f"  [B] {name} -> {path}")
            if not lines:
                lines = ["(暂无)"]
            self._show_paged_lines("书签列表", lines)

    # ==================== 剪贴板菜单 ====================
    def show_clipboard_menu(self):
        if not self.items:
            return
        it = self.items[self.idx]
        actions = [f"复制: {it['name']}", f"剪切: {it['name']}"]
        if self.clipboard:
            actions.append("粘贴到这里")
        actions.append("取消")
        choice = self._menu_popup("剪贴板", actions)
        if choice == 0:
            self.clipboard = ('copy', it['path'])
            self.set_msg(f"已复制: {it['name']}", C.SUCCESS)
        elif choice == 1:
            self.clipboard = ('cut', it['path'])
            self.set_msg(f"已剪切: {it['name']}", C.SUCCESS)
        elif choice == 2 and self.clipboard:
            op, src = self.clipboard
            dst = os.path.join(self.cwd, os.path.basename(src))
            try:
                if op == 'copy':
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, dst)
                else:
                    shutil.move(src, dst)
                    self.clipboard = None
                self.set_msg(f"[成功] 已粘贴: {os.path.basename(src)}", C.SUCCESS)
                self.load_dir()
            except OSError as e:
                self.set_msg(f"[失败] 粘贴失败: {e}", C.ERROR)

    # ==================== 通用菜单弹窗 ====================
    def _menu_popup(self, title, items):
        maxy, maxx = self.stdscr.getmaxyx()
        if not items:
            return -1
        w = min(maxx - 4, max((len(item) for item in items), default=10) + 8)
        h = min(len(items) + 4, maxy - 2)
        y = (maxy - h) // 2
        x = (maxx - w) // 2
        win = curses.newwin(h, w, y, x)
        win.keypad(True)
        win.border()
        safe_addstr(win, 0, (w - len(title)) // 2, f" {title} ", curses.A_BOLD | C.TITLE)
        sel = 0
        while True:
            for i, item in enumerate(items):
                attr = curses.color_pair(C.SELECTED) if i == sel else 0
                safe_addstr(win, i + 2, 2, pad_to_width(item, w - 4), attr, w - 4)
            win.refresh()
            ch = win.getch()
            if ch == curses.KEY_UP or ch == ord('k'):
                sel = max(0, sel - 1)
            elif ch == curses.KEY_DOWN or ch == ord('j'):
                sel = min(len(items) - 1, sel + 1)
            elif ch == 10 or ch == 13 or ch == ord('\n'):
                del win
                self.stdscr.touchwin()
                return sel
            elif ch == 27 or ch == ord('q'):
                del win
                self.stdscr.touchwin()
                return -1

    # ==================== 创建菜单 (F4) ====================
    def show_create_menu(self):
        actions = ["创建目录", "创建文件", "取消"]
        choice = self._menu_popup("新建", actions)
        if choice == 0:
            name = input_popup(self.stdscr, "目录名称:")
            if name:
                path = os.path.join(self.cwd, name)
                try:
                    os.mkdir(path)
                    self.load_dir()
                    self.set_msg(f"[成功] 已创建目录: {name}", C.SUCCESS)
                except OSError as e:
                    self.set_msg(f"[失败] 创建失败: {e}", C.ERROR)
        elif choice == 1:
            name = input_popup(self.stdscr, "文件名称:")
            if name:
                path = os.path.join(self.cwd, name)
                try:
                    with open(path, "w") as f:
                        pass
                    self.load_dir()
                    self.set_msg(f"[成功] 已创建文件: {name}", C.SUCCESS)
                except OSError as e:
                    self.set_msg(f"[失败] 创建失败: {e}", C.ERROR)

    # ==================== 排序切换 ====================
    def cycle_sort(self):
        self.sort_mode = (self.sort_mode + 1) % 4
        names = {0: "名称", 1: "大小", 2: "时间", 3: "扩展名"}
        self.sort_reverse = False
        self.load_dir()
        self.set_msg(f"排序方式: {names[self.sort_mode]}", C.STATUS)

    # ==================== 过滤 ====================
    def set_filter(self):
        pat = input_popup(self.stdscr, "过滤条件 (如 *.py):")
        if pat is not None:
            self.filter_pattern = pat
            self.load_dir()
            self.set_msg(f"过滤: {pat} ({len(self.items)} 项匹配)", C.STATUS)

    # ==================== 删除当前项 ====================
    def delete_current(self):
        if not self.items:
            return
        it = self.items[self.idx]
        if not confirm_popup(self.stdscr, f"确定删除 '{it['name']}'？"):
            return
        try:
            if it['is_dir']:
                shutil.rmtree(it['path'])
            else:
                os.remove(it['path'])
            self.set_msg(f"[成功] 已删除: {it['name']}", C.SUCCESS)
            self.load_dir()
        except OSError as e:
            self.set_msg(f"[失败] 删除失败: {e}", C.ERROR)

    # ==================== 批量重命名当前目录 ====================
    def bulk_rename_current(self):
        pat = input_popup(self.stdscr, "匹配正则 (如 img_\\d+):")
        if not pat:
            return
        repl = input_popup(self.stdscr, "替换为:")
        if repl is None:
            return
        self.execute_command(f"bulk-rename {pat} {repl}")

    # ==================== 主循环 ====================
    def run(self):
        while self.running:
            self.draw()
            key = self.stdscr.getch()
            maxy, maxx = self.stdscr.getmaxyx()
            content_h = maxy - 4

            # ============ 全局按键 ============
            if key in (ord('q'), ord('Q')) and self.mode not in (self.MODE_COMMAND, self.MODE_URL_INPUT):
                if confirm_popup(self.stdscr, "确定退出 Winux 文件管理器？"):
                    self.running = False
                    continue

            # ============ 命令模式 ============
            if self.mode == self.MODE_COMMAND:
                self._handle_command_input(key)
                continue

            # ============ URL 输入模式 ============
            if self.mode == self.MODE_URL_INPUT:
                self._handle_url_input(key)
                continue

            # ============ 盘符视图 ============
            if self.mode == self.MODE_DRIVE:
                self._handle_drive_input(key, content_h)
                continue

            # ============ 浏览模式按键 ============
            self._handle_browse_input(key, content_h)

    def _handle_command_input(self, key):
        if key == 27:  # Esc
            self.exit_command_mode()
        elif key == 10 or key == 13:  # Enter
            cmd = self.command_buf.strip()
            self.command_buf = ""
            self.exit_command_mode()
            self.execute_command(cmd)
        elif key == 8 or key == 127 or key == curses.KEY_BACKSPACE:
            self.command_buf = self.command_buf[:-1]
        elif key == curses.KEY_UP:
            if self.history_idx > 0:
                self.history_idx -= 1
                self.command_buf = self.command_history[self.history_idx]
        elif key == curses.KEY_DOWN:
            if self.history_idx < len(self.command_history) - 1:
                self.history_idx += 1
                self.command_buf = self.command_history[self.history_idx]
        elif key == 9:  # Tab
            self._tab_complete()
        elif 32 <= key < 127:
            self.command_buf += chr(key)
        elif key >= 0xC0:
            buf = bytes([key])
            self.stdscr.timeout(50)
            while True:
                ch2 = self.stdscr.getch()
                if ch2 == -1:
                    break
                if 0x80 <= ch2 <= 0xBF:
                    buf += bytes([ch2])
                else:
                    break
            self.stdscr.timeout(-1)
            try:
                char = buf.decode('utf-8', errors='ignore')
                if char:
                    self.command_buf += char
            except:
                pass

    def _tab_complete(self):
        parts = self.command_buf.split()
        if not parts or (len(parts) == 1 and not self.command_buf.endswith(" ")):
            prefix = parts[0] if parts else ""
            commands = ["ls","ll","cd","pwd","back","tree","mkdir","touch","rm","cp","mv",
                       "rename","cat","head","tail","diff","find","info","du","stats",
                       "zip","unzip","tar","bulk-rename","chmod","open","edit","nano",
                       "web","apt","bookmark","bm","history","clear","help","quit","exit"]
            matches = [c for c in commands if c.startswith(prefix)]
            if len(matches) == 1:
                self.command_buf = matches[0] + " "
            elif len(matches) > 1:
                self.set_msg(f"补全选项: {', '.join(matches)}", C.STATUS)
        else:
            prefix = parts[-1] if self.command_buf.endswith(" ") else os.path.basename(parts[-1])
            dir_part = os.path.dirname(parts[-1]) or self.cwd
            try:
                items = [i for i in os.listdir(dir_part) if i.startswith(prefix)]
                if len(items) == 1:
                    full = os.path.join(dir_part, items[0])
                    parts[-1] = full
                    self.command_buf = " ".join(parts) + " "
            except OSError:
                pass

    def _handle_url_input(self, key):
        """处理 URL 输入模式下的按键"""
        if key == 27:  # Esc - 取消，返回浏览模式
            self.exit_url_mode()
        elif key in (ord('w'), ord('W')):
            # 弹出 URL 输入框
            url = url_input_popup(self.stdscr, f"{ICON_WEB} 请输入网址:")
            if url:
                self.exit_url_mode()
                self.open_web_browser(url)
            else:
                self.set_msg("已取消", C.STATUS)
        elif key == 10 or key == 13:
            # Enter - 也弹出输入框
            url = url_input_popup(self.stdscr, f"{ICON_WEB} 请输入网址:")
            if url:
                self.exit_url_mode()
                self.open_web_browser(url)
            else:
                self.set_msg("已取消", C.STATUS)

    def _handle_drive_input(self, key, content_h):
        if key in (27, ord('e'), ord('E')):
            self.mode = self.MODE_BROWSE
            self.set_msg("已取消", C.STATUS)
        elif key in (curses.KEY_UP, ord('k')):
            if self.idx > 0:
                self.idx -= 1
                if self.idx < self.scroll:
                    self.scroll = self.idx
        elif key in (curses.KEY_DOWN, ord('j')):
            if self.idx < len(self.drives) - 1:
                self.idx += 1
                if self.idx >= self.scroll + content_h:
                    self.scroll = self.idx - content_h + 1
        elif key in (ord('\n'), ord('\r'), 10, 13):
            self.open_drive()
        elif key in (ord('q'), ord('Q')):
            self.mode = self.MODE_BROWSE

    def _handle_browse_input(self, key, content_h):
        """
        浏览模式按键处理。
        注意：H 键必须优先于 URL 快速输入检测，
        否则 H 会被误判为 URL 开头而弹出浏览器。
        """
        # ---- H 键：帮助（最高优先级）----
        if key in (ord('h'), ord('H')):
            self.draw_help()
            return

        # ---- W 键：快速打开浏览器 ----
        if key in (ord('w'), ord('W')):
            self.open_web_browser()
            return

        # ---- 直接输入 URL（以 http/https/www 开头）----
        # 通过 URL 缓冲机制实现：用户连续输入字符组成 URL
        # 这里只处理第一个字符的触发
        ch = chr(key) if 32 <= key < 127 else ''
        if ch and ch.isalpha():
            # 收集可能的 URL 输入
            url_buf = self._collect_url_input(key)
            if url_buf:
                # 判断是 URL 还是普通文件名
                if is_url(url_buf) or url_buf.startswith(('search:', 'http', 'www')):
                    self.open_web_browser(url_buf)
                else:
                    # 不是 URL，当作普通操作——但我们已经消费了按键
                    # 需要把第一个字符当作按键重新处理
                    self._handle_single_key(ord(url_buf[0]) if len(url_buf) == 1 else key, content_h, url_buf)
            return

        # ---- 原有浏览模式按键 ----
        self._handle_single_key(key, content_h)

    def _collect_url_input(self, first_key):
        """
        快速收集用户输入，用于检测是否是 URL 直接输入。
        如果用户输入的是合法 URL 或 search: 开头，返回完整字符串。
        否则返回 None，让调用者按普通按键处理。
        """
        # 先读取一个字符看看
        self.stdscr.timeout(300)  # 300ms 超时
        buf = chr(first_key)
        while True:
            ch = self.stdscr.getch()
            if ch == -1:  # 超时
                break
            if ch == 27:  # Esc
                self.stdscr.timeout(-1)
                return None
            if ch == 10 or ch == 13:  # Enter
                break
            if 32 <= ch < 127:
                buf += chr(ch)
            elif ch >= 0xC0:
                # UTF-8 多字节
                mb_buf = bytes([ch])
                while True:
                    ch2 = self.stdscr.getch()
                    if ch2 == -1:
                        break
                    if 0x80 <= ch2 <= 0xBF:
                        mb_buf += bytes([ch2])
                    else:
                        break
                try:
                    buf += mb_buf.decode('utf-8', errors='ignore')
                except:
                    pass

        self.stdscr.timeout(-1)

        # 判断收集到的内容是否是 URL
        buf = buf.strip()
        if not buf:
            return None

        # 检查是否是 URL 模式
        if (buf.startswith(('http://', 'https://', 'ftp://', 'www.', 'search:')) or
            is_url(buf)):
            return buf

        return None  # 不是 URL，不处理

    def _handle_single_key(self, key, content_h, fallback_url=None):
        """处理单个按键（非 URL 模式）"""
        if key == curses.KEY_F2 or key == 4102:
            self.enter_command_mode()
        elif key in (curses.KEY_F5, ord('r'), ord('R')):
            self.load_dir()
            self.set_msg("已刷新", C.SUCCESS)
        elif key == curses.KEY_F3 or key == 4103:
            self.bulk_rename_current()
        elif key == curses.KEY_F4 or key == 4104:
            self.show_create_menu()
        elif key in (ord('d'), ord('D')):
            self.enter_drive_view()
        elif key in (ord('v'), ord('V')):
            self.detail = not self.detail
            self.set_msg(f"详情视图: {'开' if self.detail else '关'}", C.STATUS)
        elif key in (ord('p'), ord('P')):
            self.preview = not self.preview
            if self.preview:
                self._load_preview()
            else:
                self.preview_text = ""
            self.set_msg(f"预览面板: {'开' if self.preview else '关'}", C.STATUS)
        elif key in (ord('s'), ord('S')):
            self.cycle_sort()
        elif key in (ord('i'), ord('I')):
            self.sort_reverse = not self.sort_reverse
            self.load_dir()
            self.set_msg(f"反转排序: {'开' if self.sort_reverse else '关'}", C.STATUS)
        elif key == ord('.'):
            self.show_hidden = not self.show_hidden
            self.load_dir()
            self.set_msg(f"隐藏文件: {'显示' if self.show_hidden else '隐藏'}", C.STATUS)
        elif key in (ord('f'), ord('F')):
            self.set_filter()
        elif key in (ord('b'), ord('B')):
            self.show_bookmark_menu()
        elif key in (ord('m'), ord('M')):
            self.show_clipboard_menu()
        elif key in (curses.KEY_DC, 4107):
            self.delete_current()
        elif key in (curses.KEY_UP, ord('k')):
            if self.idx > 0:
                self.idx -= 1
                if self.idx < self.scroll:
                    self.scroll = self.idx
                if self.preview:
                    self._load_preview()
        elif key in (curses.KEY_DOWN, ord('j')):
            if self.idx < len(self.items) - 1:
                self.idx += 1
                if self.idx >= self.scroll + content_h:
                    self.scroll = self.idx - content_h + 1
                if self.preview:
                    self._load_preview()
        elif key in (curses.KEY_LEFT, curses.KEY_BACKSPACE, 127, 8):
            self.go_up()
        elif key in (ord('\n'), ord('\r'), 10, 13):
            self.open_item()
        elif key == ord('1'):
            self.sort_mode = self.SORT_NAME; self.load_dir()
        elif key == ord('2'):
            self.sort_mode = self.SORT_SIZE; self.load_dir()
        elif key == ord('3'):
            self.sort_mode = self.SORT_TIME; self.load_dir()
        elif key == ord('4'):
            self.sort_mode = self.SORT_EXT; self.load_dir()


# ============================================================
#  入口
# ============================================================

def main(stdscr):
    curses.curs_set(0)
    stdscr.keypad(True)
    try:
        curses.start_color()
        curses.use_default_colors()
    except:
        pass
    app = WinuxTUI(stdscr)
    app.run()


if __name__ == '__main__':
    init_windows_console()
    try:
        import curses
    except ImportError:
        print("错误: 需要 curses 库")
        print("Windows: pip install windows-curses")
        print("Linux/macOS: 通常已内置")
        sys.exit(1)

    # 检查 web 命令依赖
    try:
        import requests
    except ImportError:
        print("提示: web 命令需要 requests 库")
        print("安装: pip install requests")
        print("（可选: pip install beautifulsoup4 html2text 获得更好效果）")
        print()

    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        input("按回车键退出...")
