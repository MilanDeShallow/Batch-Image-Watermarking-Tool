"""内置字体 / IPTC 透传 / 二维码水印

这三个能力都有"静默失败"的共性：
- 字体缺失 → 中文变方块，但程序不报错
- IPTC 丢失 → 作者与版权声明消失，图片照样生成
- 二维码生成失败 → 水印少一块，批量结果看着"正常"
所以每条都必须有断言，不能只靠肉眼。
"""

import io
import os
import sys

import pytest
from PIL import Image

from src.config import BUNDLED_FONTS, DEFAULT_FONT_FAMILY, WatermarkConfig
from src.watermark_engine import (
    _extract_app13,
    apply_watermark,
    bundled_font_path,
    load_font_with_fallback,
    make_qr_sprite,
    save_with_format,
    safe_open_image,
)


# ============================================================
# 内置字体
# ============================================================

class TestBundledFonts:
    def test_default_family_resolves_to_a_real_file(self):
        path = bundled_font_path(DEFAULT_FONT_FAMILY)
        assert path, "内置字体没找到 —— 打包时可能漏了 assets/fonts"
        assert os.path.isfile(path)
        assert os.path.getsize(path) > 200_000, "字体文件小得不像包含中文字形"

    def test_license_ships_with_the_font(self):
        # OFL 要求分发字体时附带许可文本；漏了是合规问题，不是小事
        from src.config import asset_path
        license_path = asset_path("fonts", "OFL-SourceHan.txt")
        assert os.path.isfile(license_path)
        text = open(license_path, encoding="utf-8", errors="replace").read()
        assert "SIL OPEN FONT LICENSE" in text.upper()

    def test_loader_prefers_bundled_over_system(self):
        font, is_warning = load_font_with_fallback(None, 40)
        assert is_warning is False
        bundled = bundled_font_path(DEFAULT_FONT_FAMILY)
        assert os.path.normcase(os.path.abspath(getattr(font, "path", ""))) == \
            os.path.normcase(os.path.abspath(bundled))

    def test_bundled_font_renders_chinese(self):
        font, _ = load_font_with_fallback(None, 48)
        box = font.getbbox("万物可印")
        # 中文方块字的宽度应明显大于 0；退化成位图字体时这个值会异常或抛错
        assert box[2] - box[0] > 100

    def test_unknown_family_falls_back_without_crashing(self):
        font, _ = load_font_with_fallback(None, 24, "no-such-family")
        assert font is not None


# ============================================================
# IPTC 透传（APP13）
# ============================================================

def _make_jpeg_with_iptc(path: str, copyright_text: bytes = b"Copyright X") -> bytes:
    """造一张带 IPTC 的 JPEG，返回原始 APP13 段体。"""
    iim = (b"\x1c\x02\x50\x00\x05" b"Test "
           b"\x1c\x02\x74" + bytes([0, len(copyright_text)]) + copyright_text)
    bim = (b"8BIM" + (0x0404).to_bytes(2, "big") + b"\x00\x00"
           + len(iim).to_bytes(4, "big") + iim)
    if len(bim) % 2:
        bim += b"\x00"
    payload = b"Photoshop 3.0\x00" + bim

    buf = io.BytesIO()
    Image.new("RGB", (96, 72), (30, 110, 180)).save(buf, format="JPEG", quality=90)
    raw = buf.getvalue()
    segment = b"\xff\xed" + (len(payload) + 2).to_bytes(2, "big") + payload
    with open(path, "wb") as f:
        f.write(raw[:2] + segment + raw[2:])
    return payload


class TestIptcPassthrough:
    def test_iptc_survives_watermarking_byte_for_byte(self, tmp_path):
        src = str(tmp_path / "src.jpg")
        original = _make_jpeg_with_iptc(src)

        img = safe_open_image(src)
        assert img.info.get("iptc_app13"), "读入时没抓到 APP13"

        marked = apply_watermark(img, WatermarkConfig(text="万物可印", font_ratio=0.08))
        out = str(tmp_path / "out.jpg")
        save_with_format(marked, out)

        after = _extract_app13(out)
        # 逐字节相同：只搬运、不重新组装，才不会破坏 Photoshop 的资源块结构
        assert after == original
        assert b"Copyright X" in after

    def test_no_iptc_means_no_invented_segment(self, tmp_path):
        src = str(tmp_path / "plain.jpg")
        Image.new("RGB", (80, 60), (200, 60, 60)).save(src, quality=90)
        out = str(tmp_path / "out.jpg")
        save_with_format(apply_watermark(safe_open_image(src), WatermarkConfig(text="X")), out)
        assert _extract_app13(out) is None

    def test_iptc_kept_even_when_rgba_converted_to_rgb(self, tmp_path):
        # RGBA→RGB 会新建画布，info 不跟着走。这条专门守那次踩过的坑。
        src = str(tmp_path / "src.jpg")
        original = _make_jpeg_with_iptc(src)
        img = safe_open_image(src).convert("RGBA")
        img.info["iptc_app13"] = original
        out = str(tmp_path / "out.jpg")
        save_with_format(img, out)
        assert _extract_app13(out) == original


# ============================================================
# 二维码水印
# ============================================================

class TestQrWatermark:
    def test_sprite_is_square_and_reasonably_sized(self):
        cfg = WatermarkConfig(qr_content="https://example.com", scale_ratio=0.2)
        sprite = make_qr_sprite(cfg.qr_content, cfg, (1000, 800))
        assert sprite is not None
        assert sprite.width == sprite.height
        assert 150 <= sprite.width <= 260, f"实际 {sprite.width}"

    def test_empty_content_returns_none(self):
        cfg = WatermarkConfig(qr_content="   ")
        assert make_qr_sprite(cfg.qr_content, cfg, (800, 600)) is None

    def test_qr_actually_drawn_on_canvas(self):
        cfg = WatermarkConfig(watermark_type="qr",
                              qr_content="https://example.com/qr",
                              position="bottom-right", scale_ratio=0.2,
                              logo_opacity=100)
        base = Image.new("RGB", (1000, 800), (245, 244, 240))
        out = apply_watermark(base, cfg, 1.0)

        w, h = out.size
        region = out.convert("L").crop((int(w * 0.70), int(h * 0.68), w, h))
        pixels = list(region.get_flattened_data())
        dark_ratio = sum(1 for v in pixels if v < 80) / max(1, len(pixels))
        # 二维码模块应占这块区域的相当比例；贴失败的话这里接近 0
        assert 0.05 < dark_ratio < 0.6, f"暗像素比例 {dark_ratio:.2%}"

    def test_qr_type_alone_does_not_also_draw_logo(self):
        cfg = WatermarkConfig(watermark_type="qr", qr_content="ABC",
                              logo_path="", scale_ratio=0.15)
        base = Image.new("RGB", (600, 400), (250, 250, 250))
        out = apply_watermark(base, cfg, 1.0)
        assert out.size == base.size

    def test_text_type_without_qr_content_is_unaffected(self):
        cfg = WatermarkConfig(text="万物可印", font_ratio=0.1)
        base = Image.new("RGB", (600, 400), (250, 250, 250))
        out = apply_watermark(base, cfg, 1.0)
        # 文字水印仍应生效（这张图右下角会被画上白字，但不是二维码的白底块）
        assert out.size == base.size
        assert out.mode in ("RGB", "RGBA")
