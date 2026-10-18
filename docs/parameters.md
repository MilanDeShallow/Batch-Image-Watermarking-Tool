# 配置参数详解

`WatermarkConfig`（`src/config.py`）是 GUI 与引擎之间的单一数据契约。界面上的所有参数，最终都落成这份配置；脚本调用也用它。

完整字段如下。

## 水印类型

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `watermark_type` | `text` | `text` / `image` / `both` |

实际生效的类型由**内容**推导，而不是由"当前打开的是哪个 Tab"决定：

| 条件 | 实际类型 |
|------|----------|
| 文字非空 **且** 有 Logo | `both` |
| 只有 Logo | `image` |
| 其余 | `text` |

两个面板的参数会**合并成一份完整配置**提交，切换 Tab 只影响你正在编辑哪一组参数，不会把另一组静默关掉。

## 文字水印

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `text` | `""` | 水印文字，支持 `\n` 多行 |
| `font_path` | `""` | 空 = 自动探测系统字体 |
| `font_ratio` | `0.04` | 字号相对图片短边百分比（1%–20%） |
| `color_rgba` | `(255,255,255,128)` | 文字颜色。**只有前三位 RGB 是输入**，第 4 位由 `opacity` 派生 |
| `opacity` | `None` | 不透明度 0–100，**唯一权威来源**。留 `None` 表示未指定，此时从 `color_rgba` 第 4 位推断（兼容旧写法） |
| `position` | `bottom-right` | 九宫格位置 |
| `position_mode` | `grid` | `grid` / `custom` |
| `custom_x` / `custom_y` | `50` / `50` | 自定义位置百分比（0–100） |
| `margin` | `20` | 边距 px |
| `angle` | `0.0` | 旋转角度（-180°–180°） |
| `tile` | `False` | 是否平铺 |
| `spacing_x` / `spacing_y` | `100` / `100` | 平铺间距，按**可见边缘**计算 |
| `stagger` | `False` | 平铺行间错位 |

## 图片 / Logo 水印

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `logo_path` | `""` | Logo 文件路径 |
| `scale_ratio` | `0.10` | Logo 相对底图宽度比例（1%–50%），以可见内容为准，自动裁掉透明留白 |
| `logo_opacity` | `50` | Logo 不透明度 0–100 |
| `logo_tile` | `False` | Logo 平铺 |
| `logo_spacing_x` / `logo_spacing_y` | `100` / `100` | 平铺间距，按可见边缘计算 |
| `logo_stagger` | `False` | Logo 平铺行间错位 |
| `logo_angle` | `0.0` | Logo 旋转 |
| `logo_position` | `bottom-right` | 九宫格位置 |
| `logo_position_mode` | `grid` | `grid` / `custom` |
| `logo_custom_x` / `logo_custom_y` | `50` / `50` | 自定义位置百分比 |
| `logo_margin` | `20` | 边距 |

## 输出

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `output_dir` | `""` | 空 = 按源文件所在目录分别输出（见下） |
| `output_format` | `auto` | `auto` / `png` / `jpeg` / `webp` / `tiff` / `heic` / `avif` / `jp2` / `pdf` |
| `jpeg_quality` | `90` | JPEG 质量 60–100 |
| `filename_template` | `{original}_watermarked` | 文件名模板，支持 `{original}` / `{date}` / `{time}` / `{seq}` |
| `on_conflict` | `rename` | 同名输出：`rename`（自动重命名）/ `overwrite` / `skip` |
| `overwrite_original` | `False` | 就地写回源文件（不可逆，界面需两次确认） |

### 输出目录怎么定

输出位置完全由 `src/file_manager.resolve_output_target()` 决定，界面提示与执行同源，不会出现"提示说 A、实际写 B"：

| 情况 | 输出位置 |
|------|----------|
| 指定了输出目录 | 全部写到该目录 |
| 留空 + 单个来源目录 | 该目录下的 `watermarked_output/` |
| 留空 + 多个来源目录 | **各来源目录下各自建 `watermarked_output/`** |
| 留空 + 多个来源目录 + 合并为单个 PDF | 桌面「水印输出」（单文件必须有唯一落点，界面会提示） |

### 文件名模板

- `{original}`：原文件名（不含扩展名）
- `{date}`：`20261013`
- `{time}`：`174500`
- `{seq}`：批内序号

模板清空或全是空格时自动回落为 `{original}_watermarked`，不会把整批文件写成同一个名字。

## 九宫格位置取值

格式为 `{vertical}-{horizontal}`，或直接使用 `center`。

- vertical：`top` / `middle` / `bottom`
- horizontal：`left` / `center` / `right`

示例：`top-left`、`middle-center`、`bottom-right`。

旧版本曾用 `center-left` / `center-right` 表示「左中 / 右中」。这两个写法**仍被接受**，加载旧预设时会自动归一化为 `middle-left` / `middle-right`。原因：引擎的垂直分量只认 `top / middle / bottom`，`center` 落到垂直分量上会命中字典默认值，让水印悄悄跑到正中，而且界面按钮高亮正常、不报任何错。

## 预设系统

预设存储为 JSON 文件，位于 **`%APPDATA%/WatermarkTool/presets/`**，每个预设一个文件。

为什么放在用户目录：PyInstaller 打包后 `__file__` 落在 `_internal/` 下，程序若装到 `Program Files`，那里是只读的 —— 用户一保存就报"保存预设失败"。界面布局与日志也都走 `APPDATA`，这里是同一套口径。

首次访问时会把旧版本留在项目 `presets/` 目录下的预设**复制**过来（是复制不是移动，旧目录保持原样，用户可以随时退回旧版本；同名文件不覆盖，以用户目录里的那份为准）。

- **保存**：当前所有参数序列化为 `{预设名}.json`
- **加载**：反序列化时自动过滤未知字段、恢复 tuple 类型、按 `version` 字段做版本迁移
- **路径失效容错**：若预设绑定的 Logo 文件已不存在，自动清空 `logo_path` 并给出警告，不阻断流程
- **文件名安全化**：预设名中的非法字符自动替换为下划线

脚本里可直接使用 `PresetManager`：

```python
from src.preset_manager import PresetManager
from src.config import WatermarkConfig

PresetManager.save_preset("品牌水印", cfg)          # 保存
cfg, warnings = PresetManager.load_preset("品牌水印")  # 加载
names = PresetManager.list_presets()                # 列出全部
PresetManager.delete_preset("品牌水印")              # 删除
```

## 输入值校验

所有数值输入（坐标百分比、间距、透明度、缩放、旋转角度）在进入引擎前统一校验：越界值自动夹取到合法区间、非法值回退默认值，并在状态栏提示修正结果，不会静默产生错误水印。
