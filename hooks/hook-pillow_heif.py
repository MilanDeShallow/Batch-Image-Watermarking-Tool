"""Hook for pillow_heif —— 收集 libheif / libstdc++ 动态库

为什么不能只用 collect_dynamic_libs('pillow_heif')
==================================================
pillow-heif 的原生扩展 _pillow_heif.cp3xx-win_amd64.pyd 只有约 59KB，
它**自己不含解码器**：运行时通过 import 表加载两个 dll

    libheif-<构建哈希>.dll
    libstdc++-6-<构建哈希>.dll

这两个 dll 由 wheel 装在 site-packages 根目录（pillow_heif 包的**父目录**），
不在 pillow_heif 包目录内。而 collect_dynamic_libs('pillow_heif') 只扫
包目录，因此一个也扫不到；_pyinstaller_hooks_contrib 里也没有现成的
pillow_heif hook。后果是：打包后 import pillow_heif 成功、
一打开 .heic 才报"找不到 libheif"，属于最晚暴露的一类错误。

它们是唯一的搜索路径来源吗？
----------------------------
pillow_heif/__init__.py 顶部有一段 delvewheel 生成的补丁，import 时执行
    os.add_dll_directory(<pillow_heif 包的父目录>)
也就是说它把"包目录的上一层"加进 DLL 搜索路径。打包成 onedir 后
pillow_heif 落在 _internal/pillow_heif/，父目录就是 _internal，
所以 dll 必须放到**二进制目标目录 '.'**（即 _internal 根），
与开发环境 site-packages 根目录的布局保持一致 —— 放到子目录里就找不到。

dll 文件名带 wheel 构建哈希（如 libheif-18c57b0....dll），每次升级
pillow-heif 都可能变，所以这里按通配符匹配而不是写死文件名。
"""

import glob
import os

from PyInstaller.utils.hooks import collect_dynamic_libs, get_package_paths

# get_package_paths 返回 (包所在目录, 包目录本身)：
# 元素 0 是 site-packages，也就是这两个 dll 的实际落点。
site_packages = get_package_paths('pillow_heif')[0]

binaries = collect_dynamic_libs('pillow_heif')

for pattern in ('libheif*.dll', 'libstdc++*.dll'):
    for dll in glob.glob(os.path.join(site_packages, pattern)):
        # 目标目录固定为 '.'：见文件头说明，扩展模块按"父目录"找 dll
        binaries.append((dll, '.'))

# _pillow_heif 是原生扩展，PyInstaller 的静态分析看不到它被谁 import
# （pillow_heif 里是运行时按需加载的），必须显式声明。
hiddenimports = ['pillow_heif', '_pillow_heif']
