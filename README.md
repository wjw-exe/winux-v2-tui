# winux-v2-tui
# Winux TUI v2.0

[中文](#中文) | [English](#english)

---

## 中文

### 这是什么

Winux TUI 是一个跑在 Windows 终端里的文件管理器。它把传统的"方向键浏览 + 命令输入"两种操作方式整合在一起，目标是让你少切窗口、少敲 cd、少打开资源管理器，在终端里就能把日常的文件操作做完。

整个程序只有一个 Python 文件，没有安装向导，没有配置文件，下载下来就能跑。

### 适合谁用

如果你符合下面任意一条，可能会觉得它顺手：

- 经常和命令行打交道，但受够了反复 cd / ls / 记路径
- 喜欢 Norton Commander、Midnight Commander 那种双栏操作感，但想要更轻量、单窗口的方案
- 需要在终端里快速看文本文件、改几行代码、比对新旧版本
- 想在一个界面里同时管理本地文件和查网页资料

### 功能概览

**文件管理**
- 方向键浏览目录，Enter 进入，Backspace 返回上级
- 复制、移动、删除、批量重命名（支持正则表达式）
- 新建文件 / 目录，F4 一键调出菜单
- 文件哈希校验（MD5、SHA256）和逐行 diff 对比

**查看与统计**
- 内置文本编辑器，Nano 风格，支持中文输入、查找、跳行
- 目录大小统计、按文件类型分类汇总
- 文件详情查看（大小、权限、修改时间、哈希）

**压缩与解压**
- 创建和解析 ZIP、TAR、GZ 格式，一行命令搞定

**网页浏览**
- 内置纯 Python 的命令行浏览器，不依赖外部工具
- 支持直接输入网址查看网页正文，也支持关键词搜索（DuckDuckGo）
- 在浏览模式下按 W 或随手敲一个 URL 就能打开

**软件包管理**
- 对 winget、choco、scoop 做了统一封装，用 `apt install` 这样的命令就能装软件

**书签与剪贴板**
- 常用目录可以加书签，一键跳转
- 文件可以复制 / 剪切 / 粘贴，跨目录移动不用记路径

### 安装

**环境要求**
- Windows 10 或 11
- Python 3.8 及以上

**安装依赖**

打开终端，执行：

```bash
pip install windows-curses requests beautifulsoup4 html2text
```

各依赖的作用：

| 依赖 | 用途 | 是否必须 |
|---|---|---|
| windows-curses | 提供终端界面（curses 的 Windows 移植） | 必须 |
| requests | 网页抓取，web 命令需要 | 仅使用网页功能时需要 |
| beautifulsoup4 | 解析 HTML，提取正文 | 仅使用网页功能时需要 |
| html2text | 把网页转成更易读的格式 | 可选，装上效果更好 |

如果暂时用不到网页浏览功能，只装 `windows-curses` 也能跑。

**启动**

```bash
python winux_tui.py
```

建议在 **Windows Terminal** 里运行，图标和光标显示最完整。用传统 CMD 也能跑，只是图标会变成纯文本（DIR、FIL 这种），功能不受影响。

### 怎么用

启动后默认进入浏览模式，界面大致是这样：

```
Winux 文件管理器 v2.0  ↑↓:移动 Enter:打开 F2:命令 H:帮助 W:上网 D:盘符 Q:退出
C:\Users\YourName\Documents
  DIR  Projects
  FIL  notes.md
  PY   script.py
  IMG  photo.png
----------------------------------------------------------------------
 Dirs:3 Files:5 | 排序:名称 | 详情:开 | 预览:关 | H:帮助 W:上网
```

上半部分是文件列表，下半部分是状态栏，显示当前目录信息、排序方式、以及一些快捷键提示。

**两种模式**

- **浏览模式**：启动即进入，方向键移动光标，快捷键操作。这是主要的使用方式。
- **命令模式**：按 F2 进入，界面底部会出现一个命令输入框。输入命令后回车执行，Esc 退出。

浏览模式下想做任何事都有对应的快捷键；碰到复杂操作（比如按正则批量改名、查磁盘占用）再切到命令模式。

### 浏览模式快捷键

**移动光标**
- 上 / 下 或 J / K：上下移动
- Enter：打开文件或进入目录
- 左方向键 或 Backspace：返回上级目录
- D：切换到盘符选择视图

**调整显示**
- V：在详情视图和简洁视图之间切换
- P：开关右侧预览面板
- S：循环切换排序方式（名称、大小、时间、扩展名）
- I：反转当前排序方向
- 小数点（.）：显示或隐藏以点开头的隐藏文件
- F：设置文件名过滤器，支持通配符，比如 `*.py`

**文件操作**
- F3：批量重命名，输入正则表达式和替换规则
- F4：新建文件或目录，会弹出小菜单
- Delete：删除当前选中的文件或目录
- M：剪贴板菜单，可以复制、剪切、粘贴
- B：书签菜单，添加、跳转、删除书签

**其他**
- W：打开网页浏览器，会弹出输入框让你填网址
- H：打开帮助界面，列出所有快捷键和命令
- F5 或 R：刷新当前目录
- Q：退出程序

**一个顺手的小特性**：在浏览模式下直接敲 `https://...` 或者 `www.xxx.com`，程序会自动识别成网址并打开浏览器，不用先按 W。

### 命令模式参考

按 F2 进入，底部出现 `>` 提示符，输入命令后回车执行。方向键上下可以翻看历史命令，Tab 可以补全命令名和文件路径。按 Esc 退回浏览模式。

**文件管理**

```
ls [-l] [-a]            列出目录内容，可加 -l 看详情、-a 看隐藏文件
cd <路径>                切换目录
pwd                      显示当前所在路径
mkdir <名称> [-p]        创建目录，-p 表示递归创建多级
touch <文件>             创建空文件，若已存在则更新修改时间
cp <源> <目标> [-r]      复制文件或目录
mv <源> <目标>           移动或重命名
rm <路径> [-r] [-f]      删除，-r 删目录，-f 不确认直接删
rename <旧名> <新名>     重命名
```

**查看文件**

```
cat <文件>                查看文件全部内容
head <文件> [-n N]        查看前 N 行，默认 10 行
tail <文件> [-n N]        查看后 N 行
diff <文件1> <文件2>      比较两个文件的差异
info <文件>               显示文件详细信息，含 MD5 和 SHA256
```

**搜索与统计**

```
find <模式> [-t f|d]      按通配符搜索文件，可限定 f=文件、d=目录
du [-d 深度]              统计目录磁盘占用
stats                     按扩展名统计当前目录下的文件数量和总大小
```

**压缩与解压**

```
zip <输出.zip> <源...>        把文件或目录打包成 ZIP
unzip <压缩包> [-d 目标目录]   解压 ZIP
tar -c <输出.tar.gz> <源...>  打包并 gzip 压缩
tar -x <压缩包> [-d 目标目录] 解压 tar.gz
```

**网页浏览**

```
web <网址>                  打开网页，显示纯文本正文
web search <关键词>         用 DuckDuckGo 搜索
web search <关键词> -n 20    搜索并限制返回 20 条结果
open <网址>                 调用系统默认浏览器打开
```

**软件包管理**

```
apt install <包名>          安装软件包
apt remove <包名>           卸载软件包
apt search <关键词>         搜索可用的包
apt list                    列出已安装的包
apt update                  更新软件源
apt upgrade                 升级所有包
```

程序会自动检测系统里装了 winget、choco 还是 scoop，按优先级选用，不用手动指定。

**书签**

```
bookmark add <名称> [路径]   添加书签，路径省略则用书签当前目录
bookmark go <名称>          跳转到该书签对应的目录
bookmark del <名称>         删除书签
bookmark list               列出所有书签
```

**其他**

```
bulk-rename <正则> <替换>   按正则批量重命名
chmod <权限> <文件>         修改文件权限（类 Unix 风格）
edit <文件>                 用内置编辑器打开文件
history                     查看本次会话的命令历史
clear                       清屏
help                        打开帮助
quit                        退出程序
```

### 内置网页浏览器

这个功能最初只是想省去"切到浏览器查文档再切回来"的麻烦，后来慢慢加成了现在这样。

**三种打开方式**

1. 浏览模式下按 W，弹出输入框，填网址回车。
2. 浏览模式下直接敲 `https://...` 或 `www.python.org` 这种格式，程序会自动识别并打开。
3. 命令模式下执行 `web <网址>` 或 `web search <关键词>`。

**它怎么工作**

1. 用 requests 下载网页，自动识别编码（中文乱码基本不会出现）。
2. 优先用 html2text 把 HTML 转成带格式的纯文本，标题层级和链接都保留。
3. 如果没装 html2text，就退而求其次用 BeautifulSoup 提取正文。
4. 最终内容通过分页弹窗展示，左右键翻页。

搜索走的是 DuckDuckGo 的 HTML 版接口，不需要申请 API Key，直接就能用。

### 内置文本编辑器

按 Enter 打开文本文件，或者在命令模式里执行 `edit <文件>`，就会进入编辑器。操作逻辑模仿 Nano：

- 方向键移动光标，Enter 换行，Tab 插入 4 个空格
- Ctrl+S 保存，Ctrl+X 退出
- Ctrl+W 查找文本，Ctrl+G 跳转到指定行
- Esc 退出，如果有未保存的修改会先问你要不要保存

支持中文输入和 UTF-8 编码，大文件会分页显示。

### 不同终端下的表现

| 终端 | 图标显示 | 光标 | 推荐度 |
|---|---|---|---|
| Windows Terminal | 完整图标 | 正常 | 推荐 |
| PowerShell 7+ | 大部分正常 | 正常 | 可用 |
| 传统 CMD | 自动降级为文本 | 反色高亮模拟 | 能用 |

传统 CMD 看不到图形图标，会用 DIR、FIL、PY 这种缩写代替，功能完全一样。编辑器光标在 CMD 下可能不显示，程序会用反色高亮当前字符来帮你定位，习惯一下就好。

### 常见问题

**启动时报错 `ModuleNotFoundError: No module named 'curses'`**
Windows 上需要单独装 `windows-curses`，执行 `pip install windows-curses` 即可。

**web 命令报错**
先确认 `requests` 装了没有：`pip install requests`。想要更好的排版效果，再装 `beautifulsoup4` 和 `html2text`。

**中文文件名显示乱码**
程序启动时会自动把控制台切到 UTF-8 代码页（65001）。如果还有问题，换 Windows Terminal 基本都能解决。

**编辑器里看不到光标**
传统 CMD 对 curses 光标支持不好，程序会用反色方块标出当前位置。想看到原生光标，换 Windows Terminal。

**想做个启动快捷方式**
建一个 `winux.bat`，内容如下，双击就能跑：

```batch
@echo off
cd /d "D:\path\to\winux"
python winux_tui.py
```

### 许可证

MIT License

---

## English

### What is this

Winux TUI is a file manager that runs inside a Windows terminal. It combines two classic interaction styles — arrow-key browsing and a command-line mode — so you can do most day-to-day file operations without constantly typing `cd`, `ls`, or switching to Explorer.

The whole program is a single Python file. No installer, no config files — download and run.

### Who it's for

You might like this if any of the following sound familiar:

- You live in the terminal but are tired of typing `cd` and `ls` over and over
- You like the feel of Norton Commander or Midnight Commander but want something lighter and single-window
- You often need to glance at text files, tweak a few lines of code, or compare versions
- You want to manage local files and look up web references in one place

### Feature overview

**File management**
- Arrow-key navigation, Enter to open, Backspace to go up
- Copy, move, delete, bulk rename (with regex support)
- Create files / directories from a quick menu (F4)
- File hashing (MD5, SHA256) and line-by-line diff

**Viewing and statistics**
- Built-in Nano-style text editor with Chinese input, find, and goto-line
- Directory size statistics and file-type breakdowns
- File info (size, permissions, modification time, hashes)

**Archive handling**
- Create and extract ZIP, TAR, GZ with one-liners

**Web browsing**
- A pure-Python command-line browser, no external tools required
- Type a URL to read the page as text, or run a keyword search (via DuckDuckGo)
- Press W in browse mode, or just start typing a URL

**Package management**
- A unified wrapper around winget, choco, and scoop — `apt install something` just works

**Bookmarks and clipboard**
- Bookmark frequent directories and jump to them instantly
- Copy / cut / paste files across directories without memorizing paths

### Installation

**Requirements**
- Windows 10 or 11
- Python 3.8 or newer

**Install dependencies**

```bash
pip install windows-curses requests beautifulsoup4 html2text
```

What each package does:

| Package | Purpose | Required? |
|---|---|---|
| windows-curses | Terminal UI (Windows port of curses) | Yes |
| requests | Fetching web pages for the `web` command | Only for web features |
| beautifulsoup4 | Parsing HTML to extract text | Only for web features |
| html2text | Converts HTML to cleaner text | Optional, improves output |

If you don't need the web features, installing just `windows-curses` is enough to get the file manager running.

**Launch**

```bash
python winux_tui.py
```

Running inside **Windows Terminal** is recommended — icons and cursor render correctly. Legacy CMD works too; icons will appear as plain text (DIR, FIL, etc.) but all functionality remains.

### How to use it

You start in **browse mode**. The screen looks roughly like this:

```
Winux File Manager v2.0  Up/Dn:Move Enter:Open F2:Cmd H:Help W:Web D:Drive Q:Quit
C:\Users\YourName\Documents
  DIR  Projects
  FIL  notes.md
  PY   script.py
  IMG  photo.png
----------------------------------------------------------------------
 Dirs:3 Files:5 | Sort:Name | Detail:On | Preview:Off | H:Help W:Web
```

Top half is the file list, bottom bar shows the current directory info, sort mode, and a few shortcut hints.

**Two modes**

- **Browse mode** (default): arrow keys to move, single keys for actions. This is where you'll spend most of your time.
- **Command mode** (press F2): a command line appears at the bottom. Type a command, hit Enter, and Esc to leave.

Most things have a shortcut in browse mode. Reach for command mode when you need something more involved, like a regex bulk rename or a disk-usage report.

### Browse mode shortcuts

**Moving around**
- Up / Down or J / K: move cursor
- Enter: open file or enter directory
- Left or Backspace: go up one level
- D: switch to drive selection view

**Changing the view**
- V: toggle between detail and simple view
- P: toggle the preview panel on the right
- S: cycle sort order (name, size, time, extension)
- I: reverse the current sort direction
- . (period): show or hide dotfiles
- F: set a filename filter, supports wildcards like `*.py`

**File operations**
- F3: bulk rename — enter a regex pattern and a replacement
- F4: create a new file or directory (small menu pops up)
- Delete: delete the selected file or directory
- M: clipboard menu — copy, cut, paste
- B: bookmarks menu — add, jump to, or remove bookmarks

**Other**
- W: open the web browser (prompts for a URL)
- H: show the help screen with all shortcuts and commands
- F5 or R: refresh the current directory
- Q: quit

**A nice little touch**: in browse mode, if you just start typing `https://...` or `www.something.com`, the program recognizes it as a URL and opens the browser for you — no need to press W first.

### Command mode reference

Press F2, type at the `>` prompt, Enter to run. Up / Down arrows walk through command history, Tab completes command names and file paths. Esc returns to browse mode.

**File management**

```
ls [-l] [-a]            List directory; -l for details, -a for hidden files
cd <path>               Change directory
pwd                     Print current path
mkdir <name> [-p]       Create directory; -p for nested paths
touch <file>            Create empty file, or update mtime if it exists
cp <src> <dst> [-r]     Copy file or directory
mv <src> <dst>          Move or rename
rm <path> [-r] [-f]     Delete; -r for directories, -f to skip confirmation
rename <old> <new>      Rename a file
```

**Viewing files**

```
cat <file>              View entire file
head <file> [-n N]      View first N lines (default 10)
tail <file> [-n N]      View last N lines
diff <file1> <file2>    Compare two files line by line
info <file>             Show size, permissions, modification time, hashes
```

**Search and statistics**

```
find <pattern> [-t f|d]  Search by wildcard; restrict to f=files, d=dirs
du [-d depth]            Disk usage report for the current directory
stats                     Count files by extension and sum their sizes
```

**Archives**

```
zip <out.zip> <src...>        Pack files or directories into a ZIP
unzip <archive> [-d dest]    Extract a ZIP
tar -c <out.tar.gz> <src...> Create a gzip-compressed tarball
tar -x <archive> [-d dest]   Extract a tarball
```

**Web browsing**

```
web <url>                    Open a URL and display the page as text
web search <query>           Search the web via DuckDuckGo
web search <query> -n 20     Search, limit to 20 results
open <url>                   Open in the system's default browser
```

**Package management**

```
apt install <package>    Install a package
apt remove <package>     Uninstall a package
apt search <keyword>     Search for packages
apt list                 List installed packages
apt update               Refresh package sources
apt upgrade              Upgrade all packages
```

The program auto-detects whether you have winget, choco, or scoop installed and picks one by priority — no manual setup needed.

**Bookmarks**

```
bookmark add <name> [path]   Add a bookmark; defaults to current directory
bookmark go <name>           Jump to that bookmark
bookmark del <name>          Remove a bookmark
bookmark list                List all bookmarks
```

**Other**

```
bulk-rename <regex> <repl>   Rename files by regex match and replace
chmod <mode> <file>          Change file permissions (Unix-style)
edit <file>                  Open a file in the built-in editor
history                      Show command history from this session
clear                        Clear the screen
help                         Open the help screen
quit                         Quit the program
```

### The built-in web browser

This started as a small convenience — a way to look up docs without leaving the terminal — and grew from there.

**Three ways to open it**

1. Press W in browse mode, type a URL in the popup, hit Enter.
2. Just start typing `https://...` or `www.python.org` in browse mode; the program detects it and opens the browser.
3. In command mode, run `web <url>` or `web search <keywords>`.

**How it works**

1. `requests` downloads the page and auto-detects encoding (so Chinese text usually renders fine).
2. If `html2text` is installed, the HTML is converted to formatted plain text, keeping headings and links.
3. Without `html2text`, it falls back to `BeautifulSoup` for plain-text extraction.
4. The result is shown in a paginated popup; use Left / Right to flip pages.

Search goes through DuckDuckGo's HTML interface — no API key required.

### The built-in text editor

Press Enter on a text file, or run `edit <file>` in command mode, to enter the editor. It behaves like Nano:

- Arrow keys move the cursor; Enter inserts a newline; Tab inserts 4 spaces
- Ctrl+S saves, Ctrl+X exits
- Ctrl+W finds text, Ctrl+G jumps to a line number
- Esc exits; if you have unsaved changes it will ask whether to save

Chinese input and UTF-8 are supported, and large files are paginated.

### Behavior across terminals

| Terminal | Icons | Cursor | Recommended |
|---|---|---|---|
| Windows Terminal | Full icons | Normal | Yes |
| PowerShell 7+ | Mostly OK | Normal | Fine |
| Legacy CMD | Falls back to text | Reverse-highlight | Usable |

In legacy CMD, graphical icons are replaced by short labels like DIR, FIL, PY — functionality is unchanged. The editor cursor may be invisible in CMD; the program highlights the current character in reverse video so you can still see where you are.

### Troubleshooting

**`ModuleNotFoundError: No module named 'curses'` on startup**
On Windows you need to install `windows-curses` separately: `pip install windows-curses`.

**The `web` command errors out**
Make sure `requests` is installed: `pip install requests`. For better formatting, also install `beautifulsoup4` and `html2text`.

**Chinese filenames look garbled**
The program sets the console to UTF-8 codepage (65001) on startup. If problems persist, running inside Windows Terminal usually fixes it.

**Can't see the cursor in the editor**
Legacy CMD doesn't handle curses cursors well. The program uses reverse-video highlighting on the current character instead. For a native cursor, switch to Windows Terminal.

**How do I make a startup shortcut**
Create a `winux.bat` file with the following, then double-click it:

```batch
@echo off
cd /d "D:\path\to\winux"
python winux_tui.py
```

### License

MIT License
