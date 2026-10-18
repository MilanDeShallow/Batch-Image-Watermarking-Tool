# 开发与实现

## 从源码运行

### 环境要求

- Windows 10 / 11（已测试）
- Python 3.10 及以上

**3.10 是硬下限**，依据是依赖而非偏好：约束来自 `pillow==12.3.0` 的 `Requires-Python >=3.10`（其余依赖更低：reportlab ≥3.9、pyinstaller ≥3.8、customtkinter ≥3.7）。全部源码用 3.10 解释器做过 `compileall` 校验，且未使用 3.11+ 专有特性。CI 在 **3.10 与 3.14** 双版本上跑：3.10 验下限，3.14 是发布产物实际构建所用的版本。

### 安装依赖

```bash
cd watermark_tool
pip install -r requirements.txt
```

依赖一律**固定版本**而非区间：同一套参数在不同 Pillow 大版本下可能产出不同字节，出问题时要能精确复现。

```
pillow==12.3.0
customtkinter==6.0.0
tkinterdnd2==0.6.2

# PDF 功能（仅做图片水印时可不装）
reportlab==5.0.1
pypdf==6.16.2
pypdfium2==5.13.0

# 内存预算与进度显示：拿不到时程序会回落到保守值，不会崩
psutil>=5.9.0

# 仅打包时需要
pyinstaller==6.21.0
```

> `pyinstaller` 仅打包时需要；`reportlab` / `pypdf` / `pypdfium2` 仅为 PDF 功能所需；`psutil` 未装时并行度会按 2GB 兜底预算估算。

### 启动

```bash
python main.py
```

或双击仓库中的 `启动水印工具.bat`。

## 打包为可执行文件

```bash
build_exe.bat
```

脚本会自动完成依赖检查、清理旧构建、打包、验证输出。手动打包：

```bash
python -m PyInstaller build.spec --noconfirm
```

输出目录 `dist/WatermarkTool/`，主程序为 `dist/WatermarkTool/<APP_NAME>.exe`。将整个 `WatermarkTool` 文件夹分发即可 —— exe 与同目录的 `_internal` 是一体的，单独把 exe 拷出来无法运行。

`build.spec` 已处理 CustomTkinter、tkinterdnd2 的数据文件收集，以及 PDF 所需的 `pypdfium2` 原生 DLL（`collect_dynamic_libs`）与 `reportlab` / `pypdf` 隐式导入。预设**不**进安装目录：运行时统一读写 `%APPDATA%/WatermarkTool/presets`。

## 技术设计

### 健壮性

1. **EXIF 方向自动校正**：调用 `ImageOps.exif_transpose()` 实际旋转像素，并把 `Orientation` 清成 `1`，防止查看器二次旋转。
2. **色彩空间归一化**：`RGB` / `RGBA` / `L` 原样保留；`LA` 与带 `transparency` 的调色板 PNG 一律转 `RGBA` —— 它们的模式名里不带 `A`，却确实携带透明通道，以前统一 `convert("RGB")` 会把透明区域变成实心（半透明 Logo 导出来是一块黑底方块，且没有任何报错）。16/32 位灰度与浮点模式无法保留位深，转换时**写一条日志**说明位深被压缩。
3. **读取失败带文件名**：`Image.open` 与 `src.load()` 的异常统一包装成 `ValueError("无法读取图片 xxx：…")`。Pillow 原始抛出的 `Truncated File Read` 不带文件名，批量失败清单里只会留下一句无从下手的报错。
4. **超大图有安全上限**：`MAX_IMAGE_PIXELS = 300_000_000`（约 3 亿像素，解码后约 1.2GB RGBA），渲染引擎与内存预算共用这一个值。超限文件在批处理开始前被识别出来，**明确告知后跳过**。
5. **字体多级回退**：用户指定路径 → 微软雅黑 → 黑体 → Pillow 内置字体。
6. **空字符串容错**：文字为空或纯空白时直接返回原图。
7. **路径清洗**：自动清除 Windows 拖拽传入的 `{}` 包裹与引号。
8. **文件句柄释放**：所有图片读取路径使用 `with Image.open(...)` 并在加载后返回脱离文件的对象副本。若在打开与加载之间抛异常，句柄会被一直占用，导致源文件无法重命名 / 删除。
9. **输入值统一校验**：`src/validators.py` 对所有数值输入做解析与区间夹取，非法值回退默认值并在状态栏提示；同时兜底平铺步长，避免间距为 0 或负数时 `range()` 抛异常。
10. **界面不会被自己的弹窗卡死**：完成提示框不调用 `grab_set()`。根因是 CTkToplevel 为了刷新标题栏颜色会在构造时 `withdraw()` 自己再 `after(5)` `deiconify()`，模态抓取落在"当时不可见"的窗口上；主窗被最小化时子对话框被连带 withdrawn，而输入抓取仍攥在它手里。修法：完成对话框改「单例 + `lift()` + `bind("<Destroy>")`」，另加 `_release_stale_grab()` 安全网。
11. **原子写出**：先写同目录的临时文件 `.{名字}.part{扩展名}`，成功后 `os.replace()`；失败就删掉残留。临时名**必须保留扩展名**，否则 Pillow 会选错编码器。勾了「覆盖原图」时这一层同时是源文件的保命索。
12. **有界任务队列 + 任务内取消**：线程池只保持「并行度」个在飞任务。取消后立刻停止提交新任务，已启动的任务在可中断点（每个文件入口、PDF 每一页之间）退出。
13. **内存预算决定并行度**：按「最坏单张解码后的峰值内存」反推线程数（详见下节）。
14. **失败清单落盘**：有失败时在输出目录写 `失败清单_YYYYMMDD_HHMMSS.txt`，完成对话框提供「查看失败清单」按钮。打包后的 exe 没有控制台，没有这个文件用户无从回溯"哪几张错了、为什么"。

### PDF 水印实现原理

采用**覆盖层合并**方案，而非把页面渲染成图片再重新组卷 —— 后者会丢失文本可选中性与矢量清晰度。

```
Pillow 引擎在透明底图渲染水印 ──▶ 透明 PNG 覆盖层
        │
        ▼
reportlab 包成与页面同尺寸的覆盖 PDF
        │
        ▼
pypdf merge_page 逐页叠加到原 PDF（原内容保留）
```

- 覆盖层渲染倍率 `OVERLAY_SCALE = 2.0`（约 144 DPI），保证 200% 缩放下的清晰度；批处理开始时取一次快照，整批固定
- 预览（`pypdfium2` 渲染当前页 + Pillow 叠加）与导出使用相同的相对几何计算
- 覆盖层按「页面尺寸 + 旋转角 + 倍率 + 配置指纹」缓存，多页同规格只生成一次。缓存有上限（条数 + 总字节双约束，LRU 淘汰）
- `/Rotate` 页面按**显示方向**渲染覆盖层，再反向旋转同角度写入页面坐标系。旧实现按未旋转 mediabox 创建覆盖层，90° 下横向 ×0.707、纵向 ×1.415，水印被拉伸约 2 倍

**元数据与数字签名**

| 项 | 行为 |
|----|------|
| 保留的元数据 | `/Title`、`/Author`、`/Subject`、`/Keywords`、`/Creator` 原样带到输出 |
| `/Producer` | 改写为本工具（毕竟确实动过这个文件） |
| 数字签名 | 处理前用 `signed_pdf_files()` 检测（DocMDP / UR、`/FT = /Sig` 签名字段、`/AcroForm/SigFlags`）。检测到会**明确弹窗告知签名必然失效**，由用户决定是否继续 |

**已知限制**

| 限制 | 说明 / 计划 |
|------|-------------|
| 覆盖层是整页位图 | A4 单页覆盖层约 1190×1684 RGBA，输出体积随页数线性上升；缓存已加 LRU 上限。体积敏感时可用 `set_overlay_scale()` 调低倍率 |
| 加密 PDF | 仅支持空密码（自动解密）；有密码的 PDF 会明确报错 |
| 水印本身仍是位图 | 后续可升级为矢量文字覆盖层，代价是要解决字体嵌入与中文子集化 |

### 智能保存

- **JPEG**：`RGBA→RGB`（白底合成）+ 安全 EXIF
- **PNG**：保持 `RGBA`
- **TIFF / WebP**：支持 EXIF 透传
- 自动创建输出目录

### 内存与并发

并行度不看压缩文件大小，只看**解码后的像素**：10000×7000 的 JPEG 压缩后约 200 KB，解码后约 280 MB；1920×1080 的 PNG 压缩后约 5 MB，解码后约 8 MB。

`src/resource_budget.py` 的规则：

| 项 | 值 | 说明 |
|----|----|------|
| `BYTES_PER_PIXEL` | 4 | RGBA |
| `TASK_SLACK` | 5.0 | 图片单任务峰值系数，等效 20 B/px（实测 16.2） |
| `PDF_PAGE_SLACK` | 7.0 | PDF 单页峰值系数，等效 28 B/px（实测 21~23） |
| `MEMORY_BUDGET_RATIO` | 0.5 | 最多用掉可用内存的一半 |
| `MAX_WORKERS` | 8 | 并行度上限 |
| `MAX_IMAGE_PIXELS` | 3 亿 | 超过即拒绝处理 |
| `LARGE_IMAGE_PIXELS` | 5000 万 | 超过即触发开始前的内存预警 |
| `PDF_SIZE_PROBE_PAGES` | 24 | 预检最多读多少页的 MediaBox |
| `UNKNOWN_FILE_BYTES` | 64 MB | 探不到尺寸时的兜底 |

`plan_workers()` 按**最坏单张**而不是平均值算并行度 —— 平均值会被一堆小图拉低，然后让某张大图在峰值时把内存顶爆。

#### PDF 的像素基数

PDF 是矢量、没有"分辨率"。真正吃内存的是按页面显示尺寸渲染出来的覆盖层位图：

- 像素基数 = 页面点数（media box）× 覆盖层倍率
- 预检只扫前 24 页取最大值（成本几乎全在"打开 PDF"，实测 5 页 1.5 ms、400 页 33.3 ms）
- 同一套逻辑也用于 `oversized_files` / `large_images`，PDF 不再被静默跳过

实测峰值（`overlay_scale=2.0`，RSS 增量，缓存未命中）：A4 40.1 MB（21.0 B/px）、A3 83.0 MB、A2 169.6 MB、A1 345.8 MB、A0 702.7 MB。旧实现把 PDF 一律按 64 MB 估，A0 级页面低估约 11 倍。

图片侧 `TASK_SLACK`：6000×4000 峰值 369.8 MB（16.2 B/px）、8000×6000 峰值 736.7 MB（16.1 B/px），取 5.0（=20 B/px）比实测高约 25% 作余量。**不要按平均值调小** —— 本机不一定立刻出问题，但在别人的高分辨率图上会 OOM，且很难复现。

批处理开始前的预检（图片读文件头、PDF 读 media box、检查签名）跑在**后台线程**里，界面只显示"正在检查 N 个文件…"。

### 日志系统

- 路径 `%APPDATA%/WatermarkTool/app.log`，单文件超过 1MB 轮转，保留最近 5 个
- 线程安全，同时输出到控制台与文件
- `install_excepthook()` 同时挂钩 `sys.excepthook` 与 `threading.excepthook`
- `AppWindow.report_callback_exception` 覆盖 Tk 默认行为（打包后没有控制台，回调异常否则彻底消失）
- 批处理里的失败走 `log_exception()`，带文件名与堆栈

### 架构分层

```
GUI 层 (src/ui/*)  ──仅持有──▶  WatermarkConfig (src/config.py)
        │                              │
        └──── 调用 ────  watermark_engine.py ◀── 唯一图像处理入口
```

水印引擎不依赖任何 GUI 库，`WatermarkConfig` 作为单一数据契约，保证引擎可独立测试与命令行调用。

## 项目结构

```
watermark_tool/
├── main.py                    # 入口（先装日志与异常钩子，再建窗口）
├── requirements.txt           # 依赖（版本全部固定）
├── build.spec                 # PyInstaller 打包配置
├── build_exe.py               # 一键打包逻辑
├── 启动水印工具.bat            # 启动脚本
├── docs/                      # 参数 / API / 开发文档
├── assets/                    # 资源（图标、截图）
├── hooks/hook-tkinterdnd2.py  # PyInstaller hook
├── tests/                     # 单元测试 + 三个冒烟脚本
└── src/
    ├── __init__.py            # __version__ / APP_NAME 唯一来源
    ├── config.py              # WatermarkConfig + 默认值/常量唯一来源
    ├── watermark_engine.py    # 图片水印引擎（无 GUI 依赖）
    ├── pdf_engine.py          # PDF 引擎（覆盖层合并 / 逐页参数 / 合并输出）
    ├── video_engine.py        # 视频引擎（ffmpeg 叠加 / 抽帧 / 进度 / SSIM 自检）
    ├── overrides.py           # 三层参数作用域
    ├── batch_planner.py       # 批处理规划：任务清单 / 输出路径 / 执行
    ├── validators.py          # 输入值校验
    ├── resource_budget.py     # 内存估算 / 并行度决策
    ├── file_manager.py        # 文件收集 / 去重 / 原子写出
    ├── preset_manager.py      # 预设管理
    ├── logger.py              # 日志系统
    └── ui/                    # 主窗 / 文件列表 / 各参数面板 / 预览画布
```

## 运行测试

```bash
python -m pytest tests/ -q          # 单元与集成测试
python tests/smoke_gui.py           # 界面冒烟（退出码 0 表示全过）
python tests/smoke_preview.py       # 预览管线冒烟
python tests/smoke_exe.py           # 打包产物冒烟（需先打包）
```

三个冒烟脚本文件名不是 `test_*`，**不会被 pytest 自动收集** —— 它们需要真实窗口、`mainloop` 或打包产物，由 CI 显式串行执行。

CI 见 `.github/workflows/tests.yml`：在 **Python 3.10 与 3.14** 的矩阵上跑；打包与产物探测只在 3.14 上做（发布产物就是它构建的）。

打包 + 产物探测这一环不能省：源码层面全绿并不代表 exe 里就有这些改动（漏了 `hiddenimport`、忘了重新打包，本地测试都发现不了）。

### 怎么保证改预览没改坏导出

预览与导出走同一条代码路径，唯一的区别是 `scale` 参数。因此改预览时用**导出基线指纹**兜底：把若干种配置（平铺 / 单次定位 / 自定义坐标 / Logo / 两者叠加 / 触发字号下限）在固定底图上的输出取 SHA-256，改动前后必须逐字节一致。

`scale=1.0` 是导出唯一走的分支，这条约束保证「把预览改准」永远不会顺手把导出改歪。
