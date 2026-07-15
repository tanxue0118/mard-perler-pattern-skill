from __future__ import annotations

import hashlib
import os
import platform
from pathlib import Path

from PIL import ImageFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_FONT_SUFFIXES = {".ttf", ".ttc", ".otf"}


def _windows_fonts() -> tuple[list[Path], list[Path]]:
    fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    regular = [fonts / "msyh.ttc", fonts / "simhei.ttf", fonts / "simsun.ttc"]
    bold = [fonts / "msyhbd.ttc", fonts / "simhei.ttf", fonts / "simsun.ttc"]
    return regular, bold


def _mac_fonts() -> tuple[list[Path], list[Path]]:
    regular = [
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
    ]
    return regular, regular.copy()


def _linux_fonts() -> tuple[list[Path], list[Path]]:
    regular = [
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
        Path("/usr/share/fonts/opentype/source-han-sans/SourceHanSansSC-Regular.otf"),
        Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    ]
    bold = [
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Bold.otf"),
        Path("/usr/share/fonts/opentype/source-han-sans/SourceHanSansSC-Bold.otf"),
    ] + regular
    return regular, bold


def _system_candidates(bold: bool) -> list[Path]:
    system = platform.system()
    if system == "Windows":
        regular, bold_candidates = _windows_fonts()
    elif system == "Darwin":
        regular, bold_candidates = _mac_fonts()
    else:
        regular, bold_candidates = _linux_fonts()
    return (bold_candidates + [path for path in regular if path not in bold_candidates]) if bold else regular


def _validate_font_path(path: Path, source: str) -> Path:
    path = path.expanduser()
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"{source} 指定的中文字体不存在：{path}")
    if path.suffix.lower() not in _FONT_SUFFIXES:
        raise RuntimeError(f"{source} 必须指向 TTF、TTC 或 OTF 字体：{path}")
    return path.resolve()


def resolve_cjk_font(bold: bool = False) -> Path:
    """Resolve a system CJK font without falling back to a bitmap font."""
    configured = os.environ.get("MARD_CJK_FONT", "").strip()
    if configured:
        return _validate_font_path(Path(configured), "MARD_CJK_FONT")
    for candidate in _system_candidates(bold):
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    raise RuntimeError(
        "未找到可用的简体中文字体。请安装微软雅黑、黑体、宋体、苹方、Noto Sans CJK、思源黑体或文泉驿，"
        "也可以设置环境变量 MARD_CJK_FONT 指向 TTF、TTC 或 OTF 字体文件。"
    )


def load_pil_cjk_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = resolve_cjk_font(bold=bold)
    try:
        return ImageFont.truetype(str(path), size=size, index=0)
    except OSError as exc:
        raise RuntimeError(f"无法使用中文字体生成图片：{path}；{exc}") from exc


def register_reportlab_cjk_fonts() -> tuple[str, str]:
    regular_path = resolve_cjk_font(False)
    try:
        bold_path = resolve_cjk_font(True)
    except RuntimeError:
        bold_path = regular_path
    digest = hashlib.sha1((str(regular_path) + "|" + str(bold_path)).encode("utf-8")).hexdigest()[:10]
    regular_name = f"MARD-CJK-{digest}"
    bold_name = f"MARD-CJK-Bold-{digest}"
    registered = set(pdfmetrics.getRegisteredFontNames())
    try:
        if regular_name not in registered:
            pdfmetrics.registerFont(TTFont(regular_name, str(regular_path), subfontIndex=0))
        if bold_name not in registered:
            pdfmetrics.registerFont(TTFont(bold_name, str(bold_path), subfontIndex=0))
    except Exception as exc:
        raise RuntimeError(
            f"无法注册中文 PDF 字体：{regular_path}。请改用 MARD_CJK_FONT 指定可用的 TTF、TTC 或 OTF 字体。"
        ) from exc
    return regular_name, bold_name

