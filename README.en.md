<p align="center">
  <img src="assets/logo.png" width="160" alt="Easy Batch Watermark">
</p>

<h1 align="center">Easy Batch Watermark</h1>

<p align="center"><b>Batch watermark images, PDFs, and videos — 100% locally. Your files never leave your computer.</b></p>

<p align="center"><a href="README.md">简体中文</a> ｜ English</p>

<p align="center">
  <a href="#download"><img src="https://img.shields.io/badge/platform-Windows%2010%20%2F%2011-2F5D4A?style=flat-square" alt="Platform"></a>
  <a href="https://github.com/MilanDeShallow/EasyBatchWatermark/releases/latest"><img src="https://img.shields.io/github/v/release/MilanDeShallow/EasyBatchWatermark?style=flat-square&amp;label=version&amp;color=2F5D4A" alt="Version"></a>
  <a href="https://github.com/MilanDeShallow/EasyBatchWatermark/releases"><img src="https://img.shields.io/github/downloads/MilanDeShallow/EasyBatchWatermark/total?style=flat-square&amp;label=downloads&amp;color=2F5D4A" alt="Downloads"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/MilanDeShallow/EasyBatchWatermark?style=flat-square&amp;color=2F5D4A" alt="License"></a>
</p>

Tired of paying for watermark features, opening a video editor just to add a logo, or uploading sensitive files to cloud tools?
Easy Batch Watermark does batch watermarking for images, PDFs, and videos in one local app.

- **One tool, three formats**: batch watermark images, PDFs, and videos without switching apps
- **Actually built for batches**: import many files at once and apply consistent position, style, and opacity
- **100% local & private**: no uploads, no account required, safe for contracts and unreleased material
- **Open source and auditable**: verify what runs on your machine
- **If you can't upload your files, this is the batch watermark tool for you**

**Supported**: 16 image formats (JPG · PNG · WebP · HEIC · AVIF · TIFF · BMP · JP2 · ICO · SVG · GIF …), PDF, 12 video formats (MP4 · MOV · MKV · AVI · WebM · FLV · WMV · MPEG · TS · M2TS …) — full list below.

Built for photographers, e-commerce sellers, designers, legal/admin teams, and anyone who batches files and cares about privacy.

![Screenshot](assets/screenshot.png)

## What it does

- **Text watermarks**: font size scales with the short edge; color, opacity, rotation, 3×3 anchors or custom coordinates
- **Logo watermarks**: scale, opacity, rotation — can be stacked on top of text (text first, then logo)
- **Tiling & stagger**: fill the whole image, offset alternate rows; spacing is measured from the visible edge, so transparent padding leaves no gaps
- **Preview is the export**: drag the watermark where you want it — what you see is what gets written
- **Batches & presets**: import a whole batch, save the setup as a preset; override a single file or a single page
- **PDF page by page**: overlay compositing keeps the original text layer selectable and searchable; per-page parameters supported
- **Video**: same geometry engine as images; CRF 16 visually lossless, 10-bit and HDR preserved, audio stream copied
- **Output**: keep the original format, or convert to PNG / JPEG / WebP / TIFF / HEIC / AVIF / JP2 / PDF — including merging a whole batch into one multi-page PDF

## Download

| What | Notes |
|------|-------|
| [Latest release](https://github.com/MilanDeShallow/EasyBatchWatermark/releases/latest) | `WatermarkTool-vX.Y.Z.zip` — unzip and run. No Python or dependencies required |

> Keep the `WatermarkTool` folder intact — the exe and the `_internal` folder next to it belong together. Copying the exe out on its own will not work.
> The archive is about 130 MB because ffmpeg ships inside (that is what keeps video processing offline). There is no auto-update; download the new version manually.

## Quick start

1. Unzip the archive and run `万物可印.exe` (the app name in Chinese, literally "everything printable")
2. Drop your files into the window (images, GIFs, PDFs and videos can be mixed in one batch)
3. Adjust the watermark and hit **Start**

## Supported formats

| Type | Input | Output |
|------|-------|--------|
| Images (16) | `.jpg` `.jpeg` `.png` `.bmp` `.webp` `.tiff` `.tif` `.heic` `.heif` `.avif` `.avifs` `.jp2` `.j2k` `.ico` `.svg` `.gif` | Same format, or PNG / JPEG / WebP / TIFF / HEIC / AVIF / JP2 / PDF |
| PDF | `.pdf` | `.pdf` (overlay compositing; original content and text layer preserved) |
| Video (12) | `.mp4` `.m4v` `.mov` `.mkv` `.avi` `.webm` `.flv` `.wmv` `.mpg` `.mpeg` `.ts` `.m2ts` | `.mp4` (default) or the source container; H.264 or the source codec |

All three source types can live in the same batch. Notes: GIF is processed from its first frame (this is a still-image pipeline); SVG is rasterized before watermarking; ICO keeps its original container. ffmpeg is bundled — nothing to install for video.

## FAQ

<details>
<summary><b>Do my files get uploaded?</b></summary>
No. Everything runs on your machine. The app does not connect to the network and needs no account — apart from you opening the download page, there are no network requests.
</details>

<details>
<summary><b>Will it modify my originals?</b></summary>
No. Output goes to <code>watermarked_output/</code> next to each source file, and name collisions are auto-renamed. Only the explicit "overwrite original" option writes in place — it requires two confirmations and cannot be undone.
</details>

<details>
<summary><b>Can text still be selected in a watermarked PDF?</b></summary>
Yes. The watermark is composited as an overlay; the original page content and text layer stay intact and remain selectable, copyable and searchable.
</details>

<details>
<summary><b>Does video lose quality?</b></summary>
CRF 16 with preset slow (visually lossless). Measured SSIM on a 1080p re-encode is 0.999; 10-bit sources stay 10-bit, HDR color tags are preserved, and the audio track is copied as-is.
</details>

<details>
<summary><b>Where do I see why a file failed?</b></summary>
A <code>失败清单_YYYYMMDD_HHMMSS.txt</code> is written to the output folder, and the completion dialog has a "view failure report" button. Full stack traces live in <code>%APPDATA%\WatermarkTool\app.log</code>.
</details>

<details>
<summary><b>Can I call it from a script?</b></summary>
Yes. The engine has no GUI dependency and takes the same <code>WatermarkConfig</code> the UI uses — see <a href="docs/api.md">docs/api.md</a>.
</details>

## Docs

- [Configuration reference](docs/parameters.md) — every field, defaults, anchors, output rules, presets
- [Scripting & API](docs/api.md) — CLI, image / PDF engines, parameter scopes, batch planner
- [Build & internals](docs/development.md) — source setup, packaging, design notes, project layout, tests

> The detailed docs are currently written in Chinese. Code identifiers, field names and examples are language-neutral.

## License

[MIT](LICENSE).

Third-party components: Pillow, customtkinter, tkinterdnd2, reportlab, pypdf, pypdfium2, psutil (all permissive licenses).

Video watermarking uses **FFmpeg (GPL-3.0)**, shipped as a separate executable inside the Windows package (not statically linked, unmodified). Source: <https://ffmpeg.org/download.html>; the build used is from <https://www.gyan.dev/ffmpeg/builds/>.
