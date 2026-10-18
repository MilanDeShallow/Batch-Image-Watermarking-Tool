"""
图片格式支持测试 —— 输入解码 / 输出编码 / 格式归一化

覆盖范围（与 README「支持的格式」一节对应）：
- 7 种图片格式的读写往返：JPEG / PNG / WebP / TIFF / BMP / GIF / HEIC
- 动图（多帧 GIF）按首帧处理，且不抛异常
- 输出格式白名单只有一份（config.EXPORT_FORMATS），batch_planner 引用它
- 缺少 HEIC 解码器时输出 .heic 抛 ValueError（而不是崩在 Pillow 里）

这些断言都在守"看起来支持、实际存错格式"这类静默失败：
用户选了 WebP 却拿到 PNG，界面上不会有任何提示，只有打开文件才知道。
"""

import os
import subprocess
import sys

import pytest
from PIL import Image, ImageChops

from src.batch_planner import FORMAT_ALIASES, VALID_FORMATS, normalize_format
from src.config import (
    EXPORT_FORMATS,
    SUPPORTED_EXTENSIONS,
    SVG_RASTER_LONG_EDGE,
    WatermarkConfig,
)
from src.file_manager import generate_output_path, is_image_file
from src.watermark_engine import (
    HEIF_AVAILABLE,
    apply_watermark,
    safe_open_image,
    save_with_format,
)

# 仓库根目录（子进程测试要用它做 cwd，才能 import src.*）
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# HEIC 依赖 pillow-heif + 两个 dll；缺环境时跳过而不是让整批红掉
requires_heif = pytest.mark.skipif(
    not HEIF_AVAILABLE, reason="pillow-heif 不可用，跳过 HEIC 相关用例"
)

SIZE = (64, 48)


def _rgba_image(size: tuple = SIZE) -> Image.Image:
    """造一张带半透明像素的测试图（半透明最容易暴露 alpha 被丢掉）"""
    img = Image.new("RGBA", size, (30, 120, 200, 128))
    # 左上角补一块不透明红，便于肉眼/像素级区分
    for x in range(size[0] // 4):
        for y in range(size[1] // 4):
            img.putpixel((x, y), (255, 0, 0, 255))
    return img


def _make_gif(path: str, frames: int = 3) -> None:
    """
    造一张多帧 GIF（P 模式 + 透明索引 0）。

    为什么用固定调色板而不是 Image.ADAPTIVE：自适应调色板会把画面主色排到
    索引 0，而我们又把索引 0 声明为透明色 —— 整帧就变成全透明，
    测试看似通过、实际什么都没验证。这里把索引 0 固定成"抠图色"，
    索引 1..N 是帧内容，于是"透明区 + 实体内容"两种像素都真实存在。

    为什么必须带 transparency：GIF 的透明是"调色板索引 + transparency 标记"，
    不是 alpha 通道。safe_open_image 里 P+transparency → RGBA 的分支
    正是历史上把透明区存成黑块的地方，这里必须覆盖到。
    """
    # 索引 0 = 透明色（品红），索引 1..4 = 各帧的实体色
    content_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
    palette = [255, 0, 255] + [c for rgb in content_colors for c in rgb]
    palette += [0, 0, 0] * (256 - len(palette) // 3)

    palette_frames = []
    for index in range(frames):
        frame = Image.new("P", SIZE, 0)
        frame.putpalette(palette)
        # 中间画一块实体色（索引 index+1），四周保持透明
        for x in range(SIZE[0] // 4, SIZE[0] * 3 // 4):
            for y in range(SIZE[1] // 4, SIZE[1] * 3 // 4):
                frame.putpixel((x, y), index + 1)
        palette_frames.append(frame)

    palette_frames[0].save(
        path,
        save_all=True,
        append_images=palette_frames[1:],
        transparency=0,
        duration=100,
        loop=0,
    )


# 每种格式：(扩展名, 造源文件的函数)
def _write_source(path: str, ext: str) -> None:
    """按扩展名写出一个可被 Pillow 读回的源文件"""
    if ext in (".jpg", ".jpeg"):
        _rgba_image().convert("RGB").save(path, quality=90)
    elif ext == ".gif":
        _make_gif(path)
    elif ext in (".heic", ".heif"):
        _rgba_image().save(path, quality=90)
    elif ext == ".bmp":
        # BMP 的 24 位存法不支持 alpha，用 RGB 造源文件避免与测试目标混淆
        _rgba_image().convert("RGB").save(path)
    else:
        # png / webp / tiff 都能直接存 RGBA
        _rgba_image().save(path)


ROUNDTRIP_EXTS = [".jpg", ".png", ".webp", ".tiff", ".bmp", ".gif"]
HEIF_EXTS = [".heic", ".heif"]


class TestRoundTrip:
    """每种输入格式读回 → 写回 → 再读，尺寸必须一致"""

    @pytest.mark.parametrize("ext", ROUNDTRIP_EXTS)
    def test_roundtrip(self, tmp_path, ext):
        src = str(tmp_path / f"src{ext}")
        _write_source(src, ext)

        img = safe_open_image(src)
        assert img.size == SIZE

        out = str(tmp_path / f"out{ext}")
        save_with_format(img, out, jpeg_quality=90)

        assert os.path.isfile(out), f"{ext} 未写出文件"
        with Image.open(out) as check:
            assert check.size == SIZE

    @requires_heif
    @pytest.mark.parametrize("ext", HEIF_EXTS)
    def test_heif_roundtrip(self, tmp_path, ext):
        """HEIC/HEIF：读写都走 pillow-heif，且必须保住 RGBA"""
        src = str(tmp_path / f"src{ext}")
        _write_source(src, ext)

        img = safe_open_image(src)
        assert img.size == SIZE

        out = str(tmp_path / f"out{ext}")
        save_with_format(img, out, jpeg_quality=90)
        assert os.path.isfile(out)

        with Image.open(out) as check:
            assert check.size == SIZE


class TestGifAnimation:
    """动图只取首帧 —— 静态管线 + 动画 = 叠影，宁可明确降级"""

    def test_first_frame_of_animated_gif(self, tmp_path):
        src = str(tmp_path / "anim.gif")
        _make_gif(src, frames=3)

        img = safe_open_image(src)

        assert img.size == SIZE
        # P + transparency 必须变 RGBA：否则透明区导出后是黑块
        assert img.mode == "RGBA"
        # 读回来的是"一张图"，不带帧概念
        assert getattr(img, "n_frames", 1) == 1
        # 四角是透明区（alpha=0），中间是实体内容（alpha=255）。
        # 只断言 mode 的话，"整张全透明"和"整张全不透明"都能通过。
        assert img.getpixel((0, 0))[3] == 0
        center = img.getpixel((SIZE[0] // 2, SIZE[1] // 2))
        assert center[3] == 255
        # 首帧是红色（索引 1），不能被后续帧染色
        assert center[0] > center[1] and center[0] > center[2]

    def test_animated_gif_does_not_raise(self, tmp_path):
        """多帧文件不许让整批失败：历史上的原始异常会污染失败清单"""
        src = str(tmp_path / "anim2.gif")
        _make_gif(src, frames=4)
        img = safe_open_image(src)
        assert img is not None

    def test_gif_output_is_single_frame(self, tmp_path):
        """导出 .gif 只能是单帧静态图，绝不能残留动画"""
        img = _rgba_image()
        out = str(tmp_path / "static.gif")
        save_with_format(img, out)

        with Image.open(out) as check:
            assert check.size == SIZE
            assert getattr(check, "n_frames", 1) == 1

    def test_gif_output_keeps_transparency(self, tmp_path):
        """
        GIF 输出必须保留透明区（这里是 QA 抓到的回归）。

        曾经在 .gif 分支里先 `convert("P", palette=ADAPTIVE)` 再存：
        GIF 的透明标记只有 Pillow 在 save() 内部做 RGBA→P 时才会写进文件头，
        自己先转 P 就把那一步绕过去了 —— 透明背景导出成实色，且不报错。
        光断言 size / n_frames 是看不见的，必须读回像素。
        """
        img = Image.new("RGBA", SIZE, (0, 0, 0, 0))       # 全透明背景
        for x in range(10, 30):
            for y in range(10, 30):
                img.putpixel((x, y), (255, 0, 0, 255))    # 实心红块

        out = str(tmp_path / "alpha.gif")
        save_with_format(img, out)

        with Image.open(out) as check:
            assert "transparency" in check.info, "GIF 文件头缺 transparency 标记"
            rgba = check.convert("RGBA")
            # 角落是透明区，不能被量化成不透明像素
            assert rgba.getpixel((0, 0))[3] == 0, rgba.getpixel((0, 0))
            # 内容区必须仍然不透明（别为了保透明把整张弄透明）
            center = rgba.getpixel((20, 20))
            assert center[3] == 255
            assert center[0] > center[1] and center[0] > center[2]

    def test_gif_roundtrip_from_animated_source_keeps_transparency(self, tmp_path):
        """端到端回归：动图源 → 引擎 → 静态 .gif，透明区仍透明"""
        src = str(tmp_path / "anim_src.gif")
        _make_gif(src, frames=3)
        base = safe_open_image(src)

        out = str(tmp_path / "anim_out.gif")
        save_with_format(base, out)

        with Image.open(out) as check:
            assert getattr(check, "n_frames", 1) == 1
            assert "transparency" in check.info
            rgba = check.convert("RGBA")
            assert rgba.getpixel((0, 0))[3] == 0
            assert rgba.getpixel((SIZE[0] // 2, SIZE[1] // 2))[3] == 255

    def test_gif_output_of_opaque_image_has_no_transparency(self, tmp_path):
        """全不透明的源不该凭空多出透明索引（会误导看图工具）"""
        img = Image.new("RGB", SIZE, (10, 120, 200))
        out = str(tmp_path / "opaque.gif")
        save_with_format(img, out)

        with Image.open(out) as check:
            assert "transparency" not in check.info
            assert check.convert("RGB").getpixel((0, 0)) == (10, 120, 200)


class TestSaveParameters:
    """编码参数确实传下去了 —— 参数写了却不生效是本项目踩过的坑"""

    def test_tiff_uses_lzw(self, tmp_path):
        """TIFF 用 LZW 无损压缩（Compression 标签 259 = 5）"""
        img = _rgba_image()
        out = str(tmp_path / "c.tiff")
        save_with_format(img, out)

        with Image.open(out) as check:
            assert check.tag_v2.get(259) == 5

    def test_webp_honours_quality(self, tmp_path):
        """
        WebP 质量参数要生效：低质量文件明显更小。

        用一张有渐变的图，纯色图在任何质量下都很小，测不出来。
        """
        gradient = Image.new("RGB", (200, 200))
        for x in range(200):
            for y in range(200):
                gradient.putpixel((x, y), (x, y, (x * y) % 256))

        low = str(tmp_path / "low.webp")
        high = str(tmp_path / "high.webp")
        save_with_format(gradient, low, jpeg_quality=10)
        save_with_format(gradient, high, jpeg_quality=95)

        assert os.path.getsize(low) < os.path.getsize(high)

    def test_bmp_output_readable(self, tmp_path):
        """BMP 无 alpha 通道：RGBA 输入必须被接受（不能抛 'cannot write mode'）"""
        img = _rgba_image()
        out = str(tmp_path / "x.bmp")
        save_with_format(img, out)
        with Image.open(out) as check:
            assert check.size == SIZE


class TestWatermarkPixels:
    """
    水印必须真的写进像素里。

    之前的往返用例只断言尺寸 —— "能读能存、但水印根本没画上去"
    （比如把源图误当成结果去 save、或 sprite 合成被跳过）也能全绿。
    这里用"深色底 + 平铺白字"制造大面积高对比差异，再按像素比对。
    """

    # 用 ASCII 文案：底图字体四级回退链全部失败时会落到 Pillow 内置位图字体，
    # 它画不出中文 —— 那时如果文案是中文，这条用例会在"缺字体的机器上"假失败。
    WM_SIZE = (160, 120)

    def _watermark_cfg(self) -> WatermarkConfig:
        return WatermarkConfig(
            text="TEST",
            watermark_type="text",
            font_ratio=0.25,
            opacity=100,
            color_rgba=(255, 255, 255),
            tile=True,
            spacing_x=40,
            spacing_y=30,
        )

    def _changed_pixels(self, produced: str) -> tuple[int, int]:
        """返回 (明显变化的像素数, 总像素数)"""
        base = Image.new("RGB", self.WM_SIZE, (20, 20, 20))
        with Image.open(produced) as check:
            back = check.convert("RGB")
        diff = ImageChops.difference(back, base).convert("L")
        # 32 的阈值用来跳过有损编码（JPEG/WebP/HEIC）在纯色底上的细微抖动
        lut = diff.point([255 if v > 32 else 0 for v in range(256)])
        changed = lut.histogram()[-1]
        return changed, self.WM_SIZE[0] * self.WM_SIZE[1]

    @pytest.mark.parametrize("ext", ROUNDTRIP_EXTS)
    def test_watermark_changes_pixels(self, tmp_path, ext):
        base = Image.new("RGB", self.WM_SIZE, (20, 20, 20))
        result = apply_watermark(base, self._watermark_cfg())
        out = str(tmp_path / f"wm{ext}")
        save_with_format(result, out, jpeg_quality=95)

        changed, total = self._changed_pixels(out)
        assert changed > total * 0.01, f"{ext}: 只有 {changed}/{total} 个像素变化，水印可能没写进去"

        # 白字必然抬高最亮值（底图只有 20）：这条能抓住"差异来自编码噪声"的假阳性
        with Image.open(out) as check:
            assert check.convert("L").getextrema()[1] > 200, f"{ext}: 画面里没有出现白字"

    @requires_heif
    def test_watermark_changes_pixels_heic(self, tmp_path):
        base = Image.new("RGB", self.WM_SIZE, (20, 20, 20))
        result = apply_watermark(base, self._watermark_cfg())
        out = str(tmp_path / "wm.heic")
        save_with_format(result, out, jpeg_quality=95)

        changed, total = self._changed_pixels(out)
        assert changed > total * 0.01, f"heic: 只有 {changed}/{total} 个像素变化"
        with Image.open(out) as check:
            assert check.convert("L").getextrema()[1] > 200


class TestFormatNormalization:
    """格式标识只有一套口径：config.EXPORT_FORMATS"""

    def test_export_formats_is_single_source(self):
        assert tuple(EXPORT_FORMATS) == VALID_FORMATS
        assert isinstance(VALID_FORMATS, tuple)

    @pytest.mark.parametrize("written,expected", [
        ("WebP", "webp"),
        ("webp", "webp"),
        ("TIFF", "tiff"),
        ("tiff", "tiff"),
        ("HEIC", "heic"),
        ("heic", "heic"),
        # HEIF 与 HEIC 是同一个容器，统一落到 heic
        ("HEIF", "heic"),
        ("heif", "heic"),
    ])
    def test_normalize_new_formats(self, written, expected):
        assert normalize_format(written) == expected

    # 注意：AVIF / JP2 / SVG 都已是合法格式，不能再拿来当"未知值"。
    # BMP 是输入格式但不可导出，用来验证"认得出扩展名但选不了导出格式"
    @pytest.mark.parametrize("bogus", ["", "随便什么", "BMP", None])
    def test_unknown_falls_back_to_auto(self, bogus):
        assert normalize_format(bogus) == "auto"

    def test_aliases_cover_export_formats(self):
        """白名单里每个格式都得能从别名表里被映射出来，否则等于选不到"""
        mapped = set(FORMAT_ALIASES.values())
        for fmt in EXPORT_FORMATS:
            assert fmt in mapped, f"{fmt} 没有任何别名能映射过去"


class TestHeifRegistration:
    """
    解码器注册必须早于任何一次 Image.open。

    踩过的坑：注册写在引擎模块里，而 UI 对引擎全是延迟导入 ——
    启动后「先选 HEIC Logo、后加载图片」时引擎还没被导入，
    Logo 面板里选 .heic 直接报"无法打开图片"。所以注册挪到了 config，
    这里用**独立子进程**验证"只 import src.config"就已就绪。
    """

    @requires_heif
    def test_opener_registered_by_config_only(self):
        code = (
            "import src.config\n"
            "from PIL import Image\n"
            "exts = Image.registered_extensions()\n"
            "assert '.heic' in exts, sorted(exts)\n"
            "assert '.heif' in exts, sorted(exts)\n"
            "print('ok')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, result.stderr or result.stdout

    def test_flag_has_single_source(self):
        """引擎里的 HEIF_AVAILABLE 必须是 config 那个的同一份，不能各算一遍"""
        from src import config as config_module
        from src import watermark_engine as engine_module

        assert engine_module.HEIF_AVAILABLE is config_module.HEIF_AVAILABLE


class TestHeifUnavailable:
    """缺解码器时给明确错误，而不是让 Pillow 抛 "unknown file extension"""

    def test_heic_save_raises_when_unavailable(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.watermark_engine.HEIF_AVAILABLE", False)
        img = _rgba_image()
        with pytest.raises(ValueError, match="HEIC"):
            save_with_format(img, str(tmp_path / "x.heic"))

    def test_heif_ext_also_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.watermark_engine.HEIF_AVAILABLE", False)
        img = _rgba_image()
        with pytest.raises(ValueError, match="HEIC"):
            save_with_format(img, str(tmp_path / "x.heif"))


class TestExtensionWhitelist:
    """输入扩展名白名单：拖放/扫描都靠 is_image_file 判断"""

    @pytest.mark.parametrize("name", [
        "a.heic", "a.HEIC", "a.heif", "a.gif", "a.webp", "a.tiff", "a.tif",
    ])
    def test_new_formats_accepted(self, name):
        assert is_image_file(name) is True

    def test_video_rejected_by_image_whitelist(self):
        """视频必须走 ffmpeg 分支，混进 is_image_file 会让 Pillow 去开 mp4"""
        assert is_image_file("a.mp4") is False
        assert is_image_file("a.mov") is False

    def test_whitelist_matches_config(self):
        assert ".heic" in SUPPORTED_EXTENSIONS
        assert ".heif" in SUPPORTED_EXTENSIONS
        assert ".gif" in SUPPORTED_EXTENSIONS


class TestOutputPathExtension:
    """导出路径的扩展名必须跟着格式走（file_manager 那条分支）"""

    @pytest.mark.parametrize("fmt,expected", [
        ("webp", ".webp"),
        ("tiff", ".tiff"),
        ("heic", ".heic"),
        ("png", ".png"),
        ("jpeg", ".jpg"),
    ])
    def test_output_ext_follows_format(self, tmp_path, fmt, expected):
        path = generate_output_path(
            str(tmp_path / "photo.jpg"),
            str(tmp_path / "out"),
            output_format=fmt,
        )
        assert path is not None
        assert path.endswith(expected)

# ============================================================
# v1.7.4：AVIF / JPEG 2000 / ICO / SVG
# ============================================================

SVG_SMALL = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
    '<rect width="64" height="64" rx="12" fill="#264653"/>'
    '<circle cx="32" cy="32" r="18" fill="#e9c46a"/></svg>'
)


def _write_svg(path, content: str = SVG_SMALL) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


class TestSvgRasterization:
    """SVG 不是位图：必须先光栅化，且不能按 64x64 的原始逻辑尺寸草草了事"""

    def test_small_svg_is_scaled_up_to_target(self, tmp_path):
        path = str(tmp_path / "icon.svg")
        _write_svg(path)
        img = safe_open_image(path)

        assert img.mode == "RGBA"
        # 64x64 直接光栅化的话，水印字号按短边 5% 算只有 3 像素高，
        # 糊成一团；这里必须被放大到目标长边
        assert max(img.size) == SVG_RASTER_LONG_EDGE
        assert img.size == (SVG_RASTER_LONG_EDGE, SVG_RASTER_LONG_EDGE)

    def test_large_svg_is_not_downscaled(self, tmp_path):
        path = str(tmp_path / "big.svg")
        _write_svg(
            path,
            '<svg xmlns="http://www.w3.org/2000/svg" width="2400" height="1200">'
            '<rect width="2400" height="1200" fill="#333"/></svg>',
        )
        img = safe_open_image(path)
        # 比目标还大的矢量图本身分辨率够用，缩小只会白丢细节
        assert img.size == (2400, 1200)

    def test_svg_keeps_transparency(self, tmp_path):
        path = str(tmp_path / "alpha.svg")
        _write_svg(
            path,
            '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
            '<circle cx="100" cy="100" r="60" fill="#2a9d8f"/></svg>',
        )
        img = safe_open_image(path).convert("RGBA")
        assert img.getpixel((2, 2))[3] == 0

    def test_watermark_lands_on_svg(self, tmp_path):
        path = str(tmp_path / "icon.svg")
        _write_svg(path)
        img = safe_open_image(path)
        cfg = WatermarkConfig(text="万物可印", opacity=100,
                              position="bottom-right", font_ratio=0.05)
        out = apply_watermark(img, cfg, 1.0)

        w, h = out.size
        region = out.convert("RGB").crop((int(w * 0.55), int(h * 0.88), w, h))
        bright = sum(1 for px in region.get_flattened_data() if sum(px) > 600)
        assert bright > 50, "SVG 光栅化后水印没画上去"

    def test_broken_svg_raises_with_filename(self, tmp_path):
        path = str(tmp_path / "bad.svg")
        _write_svg(path, "<svg><this is not valid")
        with pytest.raises(ValueError) as exc:
            safe_open_image(path)
        assert "bad.svg" in str(exc.value)

    def test_svg_auto_output_becomes_png(self, tmp_path):
        # 矢量图加水印后存不回矢量路径，auto 必须落到 PNG 而不是原扩展名
        out = generate_output_path(
            str(tmp_path / "logo.svg"),
            str(tmp_path / "out"),
            output_format="auto",
        )
        assert out is not None
        assert out.endswith(".png")


class TestNewRasterFormats:
    """AVIF / JPEG 2000 / ICO：Pillow 12 原生支持，加白名单即可用"""

    @pytest.mark.parametrize("ext", ["avif", "jp2", "ico"])
    def test_roundtrip_keeps_size(self, tmp_path, ext):
        src = str(tmp_path / f"src.{ext}")
        base = Image.new("RGB", (320, 240), (40, 90, 140))
        base.save(src, **({"quality": 80} if ext == "avif" else {}))

        img = safe_open_image(src)
        cfg = WatermarkConfig(text="万物可印", opacity=90,
                              position="bottom-right", font_ratio=0.06)
        marked = apply_watermark(img, cfg, 1.0)

        dst = str(tmp_path / f"out.{ext}")
        save_with_format(marked, dst)
        back = Image.open(dst)
        assert back.size == img.size

    def test_avif_keeps_alpha(self, tmp_path):
        src = str(tmp_path / "a.avif")
        rgba = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
        rgba.putpixel((60, 60), (255, 0, 0, 200))
        rgba.save(src, quality=80)
        img = safe_open_image(src)
        assert "A" in img.mode

    def test_ico_writes_single_size(self, tmp_path):
        # Pillow 默认会把一张图摊成 7 个尺寸，对加水印的大图毫无意义
        out = str(tmp_path / "out.ico")
        save_with_format(Image.new("RGB", (256, 256), (10, 20, 30)), out)
        assert sorted(Image.open(out).ico.sizes()) == [(256, 256)]

    def test_jp2_quality_mapping_follows_slider(self, tmp_path):
        # JP2 的指标是压缩比（越小越清晰）：滑块调低必须得到更小的文件
        highs, lows = [], []
        img = Image.effect_noise((320, 240), 60).convert("RGB")
        for q, bucket in ((95, highs), (20, lows)):
            out = str(tmp_path / f"q{q}.jp2")
            save_with_format(img, out, jpeg_quality=q)
            bucket.append(os.path.getsize(out))
        assert highs[0] > lows[0], "JP2 的 rates 映射没有随质量滑块变化"

    def test_avif_quality_mapping_follows_slider(self, tmp_path):
        img = Image.effect_noise((320, 240), 60).convert("RGB")
        sizes = {}
        for q in (95, 30):
            out = str(tmp_path / f"q{q}.avif")
            save_with_format(img, out, jpeg_quality=q)
            sizes[q] = os.path.getsize(out)
        assert sizes[95] > sizes[30]


class TestNewFormatPlumbing:
    def test_extensions_whitelisted(self):
        for ext in (".avif", ".avifs", ".jp2", ".j2k", ".ico", ".svg"):
            assert ext in SUPPORTED_EXTENSIONS, f"{ext} 没进白名单"
            assert is_image_file("x" + ext)

    @pytest.mark.parametrize("name,expected", [
        ("AVIF", "avif"), ("avif", "avif"), ("Avif", "avif"),
        ("JP2", "jp2"), ("jp2", "jp2"), ("JPEG2000", "jp2"),
    ])
    def test_aliases(self, name, expected):
        assert normalize_format(name) == expected

    def test_export_formats_include_new_ones(self):
        assert "avif" in EXPORT_FORMATS
        assert "jp2" in EXPORT_FORMATS
        # 矢量与图标容器不进导出下拉：SVG 存不回去，ICO 由 auto 单独处理
        assert "svg" not in EXPORT_FORMATS
        assert "ico" not in EXPORT_FORMATS

    def test_aliases_all_in_whitelist(self):
        assert set(FORMAT_ALIASES.values()) <= set(VALID_FORMATS)

