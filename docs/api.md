# 脚本与 API

水印引擎与 GUI 完全解耦。`WatermarkConfig` 是唯一的数据契约，下面所有入口都接受同一份配置。

## 命令行用法

```bash
python -m src.watermark_engine <输入图片> <输出图片>
```

默认会叠加「内部资料 / Confidential」平铺文字水印，便于快速验证引擎可用性。如需自定义参数，在脚本中构造 `WatermarkConfig` 并调用 `apply_watermark()`。

## 核心引擎 API

```python
from src.config import WatermarkConfig
from src.watermark_engine import safe_open_image, apply_watermark, save_with_format

cfg = WatermarkConfig(
    watermark_type="both",       # "text" | "image" | "both"
    text="© 品牌方",
    color_rgba=(255, 255, 255, 128),
    opacity=50,
    font_ratio=0.04,
    angle=30,
    tile=True,
    spacing_x=150,
    spacing_y=150,
    stagger=True,
    logo_path="logo.png",
    scale_ratio=0.10,
    logo_opacity=80,
)

img = safe_open_image("input.jpg")
result = apply_watermark(img, cfg)
save_with_format(result, "output.jpg", jpeg_quality=90)
```

`apply_watermark(img, cfg, scale=1.0)` 的 `scale` 参数用于预览：`scale=1.0` 是导出（行为与历史版本逐字节一致），预览传小于 1 的值，**绝对像素量会按比例同步换算**（字号与 Logo 的下限也一起缩放）。

## PDF 引擎 API

PDF 使用独立入口 `apply_pdf_watermark()`，参数复用同一个 `WatermarkConfig`：

```python
from src.config import WatermarkConfig
from src.pdf_engine import apply_pdf_watermark, render_pdf_page, get_pdf_page_count

cfg = WatermarkConfig(
    watermark_type="text",
    text="内部资料",
    angle=30,
    tile=True,
    spacing_x=200,
    spacing_y=200,
)

pages = apply_pdf_watermark("input.pdf", cfg, "output.pdf")   # 返回处理页数
print(f"已处理 {pages} 页")

first_page = render_pdf_page("input.pdf", page_num=0, scale=2.0)   # 返回 PIL.Image
print(get_pdf_page_count("input.pdf"))
```

覆盖层渲染倍率（默认 2.0 ≈ 144 DPI）。调低换体积，调高换清晰度：

```python
from src.pdf_engine import set_overlay_scale, get_overlay_scale
set_overlay_scale(1.5)
```

> 批处理会在开始时取一次倍率快照并贯穿该批 —— 处理途中调它只影响下一批。否则同一份 PDF 的前后几页会按不同参考尺寸渲染，同一文件里出现两种水印大小。

数字签名检测（加水印必然让签名失效，处理前应当告知用户）：

```python
from src.pdf_engine import has_digital_signature, signed_pdf_files
signed_pdf_files(["a.pdf", "b.pdf"])   # 从列表里挑出带签名的
has_digital_signature("a.pdf")         # bool
```

`apply_pdf_watermark()` 对加密 PDF 会抛 `ValueError`；若 PDF 可用空密码解锁，则自动解密后处理。

### 逐页不同参数

传 `page_configs={页码: WatermarkConfig}` 只对指定页使用另一套参数（页码 0 起，未列出的页仍用 `cfg`）：

```python
base = WatermarkConfig(text="内部资料", opacity=40)
page_cfgs = {1: WatermarkConfig(text="样片", color_rgba=(255, 0, 0, 255), opacity=100)}

apply_pdf_watermark("input.pdf", base, "output.pdf", page_configs=page_cfgs)
```

### 图片 → PDF 与多合一

```python
from src.pdf_engine import build_merged_pdf, image_file_to_pdf_bytes

data = image_file_to_pdf_bytes("photo.jpg", cfg, jpeg_quality=90)   # 单张图片 → 单页 PDF 字节

pages = build_merged_pdf(
    [
        {"path": "photo.jpg", "config": cfg},
        {"path": "report.pdf", "config": cfg, "page_configs": {0: cfg}},
    ],
    "merged.pdf",
    jpeg_quality=90,
)
```

`build_merged_pdf()` 支持 `progress(index, total, filename)` 与 `should_cancel()` 回调；取消时抛 `MergeCancelled`，且**不会写出任何文件**。

## 参数作用域 API

`src/overrides.py` 提供三层参数存储（无 GUI 依赖，GUI 与脚本共用同一套语义）：

```python
from src.overrides import ScopeStore

store = ScopeStore()
store.update_base({"text": "内部资料", "opacity": 50})   # 全局默认
store.update_file("B.jpg", {"text": "样片"})             # B 的专属参数
store.update_page("C.pdf", 2, {"opacity": 100})          # C 第 3 页的专属参数

store.config_for("C.pdf", 2).text      # '内部资料' —— 页层没设 text，逐层继承
store.config_for("C.pdf", 2).opacity   # 100        —— 被页层覆盖
store.marker_text("C.pdf")             # '专属 第3页'
```

面板提交的是**完整参数**而不是小补丁，这种场景用 `set_file` / `set_page`：它们会自动与父层做差，只把真正不同的字段记下来。

```python
store.set_base({"text": "内部资料", "opacity": 50, "margin": 20})
store.set_file("B.jpg", {"text": "样片", "opacity": 50, "margin": 20})

store.to_dict()["files"]["B.jpg"]   # {'text': '样片'} —— 只存了差异

store.update_base({"opacity": 30})
store.config_for("B.jpg").opacity   # 30 —— 没动过的字段跟着变，没被旧快照冻住
```

每层只保存**改动过的字段**，未改动的字段继续向上继承；输出类字段（输出目录、格式、质量、文件名模板）不进入作用域。`update_file` / `update_page` 保留为「按字段合并」语义，适合脚本里手写小补丁。

## 批处理 API

`src/batch_planner.py` 把「文件列表 + 作用域参数 + 输出设置」翻译成可执行的任务清单，不含任何 GUI 代码：

```python
from src.batch_planner import plan_batch, plan_output_paths, execute_task

plan = plan_batch(files, store, out_format="PDF", merge_pdf=True)
plan.out_format        # 'pdf'
plan.merge             # True
plan.tasks[1].config   # 该文件真正生效的 WatermarkConfig
plan.tasks[2].page_configs   # {页码: WatermarkConfig}，只含被单独设置过的页

output_paths, merged_path = plan_output_paths(
    plan, output_dir,
    filename_template="{original}_wm",
    on_conflict="rename",          # "rename" | "overwrite" | "skip"
    overwrite_original=False,
)

for task, out_path in zip(plan.tasks, output_paths):
    if out_path is None:
        continue                   # 冲突策略判定为「跳过」
    execute_task(task, out_path, jpeg_quality=90,
                 should_cancel=lambda: cancelled,   # 文件入口 + PDF 每页之间都会查
                 overlay_scale=snapshot)            # 本批固定倍率

from src.pdf_engine import build_merged_pdf
build_merged_pdf(plan.merge_items(), merged_path, jpeg_quality=90,
                 overlay_scale=snapshot)
```

几点约定：

- `execute_task()` / `build_merged_pdf()` 的 `should_cancel` 返回真时，分别抛 `TaskCancelled` / `MergeCancelled`。取消**不算失败** —— 原子写出保证不留下半成品
- 所有输出路径都走原子写出（临时文件 → `os.replace()`），异常或中断时旧文件原封不动
- `plan_output_paths()` 内部维护「本批已占用名字」集合，所以即使选「覆盖同名文件」，同一批里的两个文件也不会互相盖掉
- `file_manager.generate_output_path()` 在冲突策略为「跳过」时返回 `None`（不是空字符串），调用方必须先判空
- `overlay_scale` 是覆盖层渲染倍率快照：批处理入口取一次并贯穿整批
- `plan_batch` 的两条内置规则：PDF 源文件无论输出格式选什么都强制输出 PDF；`merge` 只在输出格式为 PDF 且显式勾选时才为真
