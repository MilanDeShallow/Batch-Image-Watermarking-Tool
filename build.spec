# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — 批量图片水印工具（图片 + PDF）"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# CI（英文 Windows）的 stdout 默认是 cp1252 —— 中文输出会 UnicodeEncodeError。
# 与 build_exe.py / 冒烟脚本同一处理：显式切成 UTF-8。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

block_cipher = None

# 版本号唯一来源：src/__init__.py。
# 产物目录名（WatermarkTool）与 exe 名（中文名）保持不变 ——
# 桌面快捷方式、打开水印工具.bat 与分发脚本都指着它们，改名会连带失效。
sys.path.insert(0, os.path.dirname(os.path.abspath(SPEC)))
from src import APP_NAME                          # noqa: E402
from src import __version__ as APP_VERSION        # noqa: E402

print(f"[build] {APP_NAME} v{APP_VERSION} — 批量图片水印工具")

# 收集 CustomTkinter 数据文件
ctk_datas = collect_data_files('customtkinter')

# 收集 tkinterdnd2 数据文件（含 tkdnd Tcl 库）
dnd_datas = collect_data_files('tkinterdnd2')

# 收集 pypdfium2 的 PDFium 动态库（DLL）
pdfium_binaries = collect_dynamic_libs('pypdfium2')

# 合并所有数据文件，并带上应用图标：
# 图标既要嵌进 exe（EXE 的 icon=，决定资源管理器/任务栏显示的图标），
# 也要留在 _internal 里（运行时 iconbitmap 会去读它 —— 只嵌不进包的话，
# 开发运行有图标、打包后反而没有）
all_datas = ctk_datas + dnd_datas + [('assets/app.ico', 'assets')]

# ---- 视频支持的 ffmpeg 不在这里打包 ----
# 试过用 datas 传 vendor/ffmpeg：PyInstaller 会顺着 ffmpeg.exe 的导入表
# 把同一批 dll 再收一遍到 _internal 根目录 —— 234MB 变成 468MB，
# 分发包从 110MB 涨到 212MB。而把重复项从 a.binaries 删掉更糟：
# PyInstaller 在 Analysis 阶段已经把 datas 里的 dll 挪进 binaries，
# 删 binaries 等于两处都没了，包直接退回 27MB 且没有视频功能。
# 结论：让 PyInstaller 完全不碰 ffmpeg，改由 build_exe.py 在打包完成后
# 手动复制到 dist/WatermarkTool/_internal/ffmpeg/。

# 不再打包 presets/ 目录：预设现在存到 %APPDATA%/WatermarkTool/presets，
# 安装目录是只读的。把空目录打进包里只会让用户以为预设存在那里。

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=pdfium_binaries,
    datas=all_datas,
    hiddenimports=[
        'customtkinter',
        'tkinterdnd2',
        'tkinterdnd2.TkinterDnD',
        'PIL',
        'PIL._tkinter_finder',
        # PDF 支持三件套
        'reportlab',
        'reportlab.pdfgen.canvas',
        'reportlab.lib.utils',
        'pypdf',
        'pypdfium2',
        # HEIC/HEIF 支持：模块在这里显式列出，libheif / libstdc++ 两个 dll
        # 由 hooks/hook-pillow_heif.py 负责收集（dll 不在包目录里，
        # collect_dynamic_libs('pillow_heif') 扫不到，原因见该 hook 的注释）
        'pillow_heif',
        '_pillow_heif',
        # SVG 光栅化：单个 pyd（Rust 静态链接），PyInstaller 能直接分析到
        'resvg_py',
    ],
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'unittest', 'test'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    # 这两个 dll 是 pillow-heif 的解码器本体（由 hooks/hook-pillow_heif.py 收集）。
    # 不排除的后果：换了装了 UPX 的机器打包时，2~3MB 的 mingw 大 dll 会被压 ——
    # 压缩失败刷一堆警告，压缩成功也更容易被杀软当成可疑载荷误报，
    # 而且 UPX 处理 C++ 导入表出过问题。为这点体积冒运行期风险不值得。
    upx_exclude=['libheif*.dll', 'libstdc++*.dll'],
    name='WatermarkTool',
)
