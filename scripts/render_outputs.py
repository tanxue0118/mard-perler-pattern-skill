from __future__ import annotations

import math
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.colors import Color as PdfColor
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from font_support import load_pil_cjk_font, register_reportlab_cjk_fonts
from image_pipeline import PatternResult
from palette import Palette
from pattern_geometry import BEAD_PITCH_MM, PatternGeometry, analyze_pattern, crop_codes, usage_recommendation

CHART_CELL_PX = 38
CHART_COORD_BAND_PX = 42
CHART_MARGIN_PX = 18
CHART_INFO_HEIGHT_PX = 132
LEGEND_ITEM_WIDTH_PX = 172
LEGEND_ITEM_HEIGHT_PX = 42
LEGEND_GAP_PX = 8
READABLE_CELL_MM = 8.0
OVERVIEW_READABLE_CELL_MM = 5.5
PAGE_MARGIN_MM = 10.0


def _pil_font(size: int, bold: bool = False):
    return load_pil_cjk_font(size, bold=bold)


def _display_title(title: str | None) -> str:
    title = (title or "").strip()
    if not title:
        return "MARD拼豆施工图"
    if "MARD拼豆施工图" in title:
        return title
    return f"MARD拼豆施工图 - {title}"


def _luminance(rgb: tuple[int, int, int]) -> float:
    values = []
    for channel in rgb:
        value = channel / 255.0
        values.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * values[0] + 0.7152 * values[1] + 0.0722 * values[2]


def count_materials(result: PatternResult) -> Counter:
    return Counter(code for code in result.codes.flat if code is not None)


def material_rows(result: PatternResult, palette: Palette, reserve_percent: float = 0) -> list[dict]:
    if reserve_percent < 0:
        raise ValueError("备料百分比不能为负数")
    counts = count_materials(result)
    rows = []
    for color in palette.colors:
        exact = counts.get(color.code, 0)
        if exact:
            rows.append({"code": color.code, "hex": color.hex, "exact_count": exact})
    if sum(row["exact_count"] for row in rows) != result.total_beads:
        raise ValueError("用量统计总数与非透明拼豆总数不一致")
    return rows


def _center_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font, fill) -> None:
    bounds = draw.textbbox((0, 0), text, font=font)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    x0, y0, x1, y1 = box
    draw.text((x0 + (x1 - x0 - width) / 2, y0 + (y1 - y0 - height) / 2 - bounds[1]), text, font=font, fill=fill)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    if not text:
        return [""]
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        width = draw.textbbox((0, 0), candidate, font=font)[2]
        if current and width > max_width:
            lines.append(current.rstrip())
            current = char.lstrip()
        else:
            current = candidate
    if current:
        lines.append(current.rstrip())
    return lines or [text]


def _board_text(geometry: PatternGeometry) -> str:
    if geometry.recommended_board is None:
        return "自定义/多块底板"
    return f"{geometry.recommended_board[0]}×{geometry.recommended_board[1]}"


def _chart_info_lines(draw: ImageDraw.ImageDraw, geometry: PatternGeometry, result: PatternResult, title: str, max_width: int):
    title_font = _pil_font(18, bold=True)
    info_font = _pil_font(16)
    title_lines = _wrap_text(draw, _display_title(title), title_font, max_width)
    facts = [
        f"图案尺寸：{geometry.width}×{geometry.height}颗　预计成品尺寸：{geometry.width_cm:.2f}×{geometry.height_cm:.2f}厘米",
        f"建议底板：{_board_text(geometry)}　总豆数：{result.total_beads}颗　使用色数：{result.used_color_count}色",
        f"适合用途：{usage_recommendation(geometry.width, geometry.height)}　每颗间距：{BEAD_PITCH_MM:g}毫米",
    ]
    lines: list[tuple[str, object, str, int]] = []
    for line in title_lines:
        lines.append((line, title_font, "#202020", 28))
    for fact in facts:
        for line in _wrap_text(draw, fact, info_font, max_width):
            lines.append((line, info_font, "#404040", 25))
    return lines


def render_pattern_chart_png(
    result: PatternResult,
    palette: Palette,
    path: str | Path,
    title: str = "MARD拼豆施工图",
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    geometry = analyze_pattern(result)
    codes = crop_codes(result, geometry)
    rows = material_rows(result, palette)

    grid_width = geometry.width * CHART_CELL_PX
    grid_height = geometry.height * CHART_CELL_PX
    width = CHART_MARGIN_PX * 2 + CHART_COORD_BAND_PX * 2 + grid_width
    legend_columns = max(1, (width - CHART_MARGIN_PX * 2 + LEGEND_GAP_PX) // (LEGEND_ITEM_WIDTH_PX + LEGEND_GAP_PX))
    legend_rows = math.ceil(len(rows) / legend_columns)
    grid_left = CHART_MARGIN_PX + CHART_COORD_BAND_PX
    grid_top = CHART_MARGIN_PX + CHART_COORD_BAND_PX
    grid_bottom = grid_top + grid_height
    info_top = grid_bottom + CHART_COORD_BAND_PX + 8

    measure_image = Image.new("RGB", (max(1, width), 1), "white")
    measure_draw = ImageDraw.Draw(measure_image)
    info_lines = _chart_info_lines(measure_draw, geometry, result, title, width - CHART_MARGIN_PX * 2)
    info_height = max(CHART_INFO_HEIGHT_PX, 12 + sum(item[3] for item in info_lines))
    legend_top = info_top + info_height
    height = legend_top + legend_rows * (LEGEND_ITEM_HEIGHT_PX + LEGEND_GAP_PX) + CHART_MARGIN_PX

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    code_font = _pil_font(max(11, int(CHART_CELL_PX * 0.42)), bold=True)
    coord_font = _pil_font(max(12, int(CHART_COORD_BAND_PX * 0.45)), bold=True)
    legend_font = _pil_font(15, bold=True)

    for y in range(geometry.height):
        for x in range(geometry.width):
            x0 = grid_left + x * CHART_CELL_PX
            y0 = grid_top + y * CHART_CELL_PX
            code = codes[y, x]
            fill = (255, 255, 255) if code is None else palette.by_code[code].rgb
            draw.rectangle((x0, y0, x0 + CHART_CELL_PX, y0 + CHART_CELL_PX), fill=fill)
            if code is not None:
                text_color = "white" if _luminance(fill) < 0.38 else "black"
                _center_text(draw, (x0, y0, x0 + CHART_CELL_PX, y0 + CHART_CELL_PX), code, code_font, text_color)

    for x in range(geometry.width + 1):
        px = grid_left + x * CHART_CELL_PX
        line_width = 3 if x % 10 == 0 else (2 if x % 5 == 0 else 1)
        color = "#777777" if x % 10 == 0 else ("#A8A8A8" if x % 5 == 0 else "#D7D7D7")
        draw.line((px, grid_top, px, grid_bottom), fill=color, width=line_width)
    for y in range(geometry.height + 1):
        py = grid_top + y * CHART_CELL_PX
        line_width = 3 if y % 10 == 0 else (2 if y % 5 == 0 else 1)
        color = "#777777" if y % 10 == 0 else ("#A8A8A8" if y % 5 == 0 else "#D7D7D7")
        draw.line((grid_left, py, grid_left + grid_width, py), fill=color, width=line_width)

    for x in range(geometry.width):
        label = str(x + 1)
        x0 = grid_left + x * CHART_CELL_PX
        _center_text(draw, (x0, CHART_MARGIN_PX, x0 + CHART_CELL_PX, grid_top), label, coord_font, "#111111")
        _center_text(draw, (x0, grid_bottom, x0 + CHART_CELL_PX, grid_bottom + CHART_COORD_BAND_PX), label, coord_font, "#111111")
    for y in range(geometry.height):
        label = str(y + 1)
        y0 = grid_top + y * CHART_CELL_PX
        _center_text(draw, (CHART_MARGIN_PX, y0, grid_left, y0 + CHART_CELL_PX), label, coord_font, "#111111")
        _center_text(draw, (grid_left + grid_width, y0, width - CHART_MARGIN_PX, y0 + CHART_CELL_PX), label, coord_font, "#111111")

    cursor_y = info_top + 4
    for text, font, fill, line_height in info_lines:
        draw.text((CHART_MARGIN_PX, cursor_y), text, font=font, fill=fill)
        cursor_y += line_height

    for index, row in enumerate(rows):
        column = index % legend_columns
        row_index = index // legend_columns
        x0 = CHART_MARGIN_PX + column * (LEGEND_ITEM_WIDTH_PX + LEGEND_GAP_PX)
        y0 = legend_top + row_index * (LEGEND_ITEM_HEIGHT_PX + LEGEND_GAP_PX)
        rgb = palette.by_code[row["code"]].rgb
        draw.rounded_rectangle((x0, y0, x0 + LEGEND_ITEM_WIDTH_PX, y0 + LEGEND_ITEM_HEIGHT_PX), radius=4, fill=rgb, outline="#B0B0B0", width=1)
        text_color = "white" if _luminance(rgb) < 0.38 else "black"
        legend_text = f'{row["code"]}（{row["exact_count"]}颗）'
        _center_text(draw, (x0, y0, x0 + LEGEND_ITEM_WIDTH_PX, y0 + LEGEND_ITEM_HEIGHT_PX), legend_text, legend_font, text_color)

    image.save(path, optimize=True)
    return path


def _overview_page_size(geometry: PatternGeometry):
    return landscape(A4) if geometry.width > geometry.height * 1.15 else portrait(A4)


def _overview_cell_mm(geometry: PatternGeometry) -> float:
    page_width, page_height = _overview_page_size(geometry)
    available_width = page_width / mm - 2 * PAGE_MARGIN_MM
    available_height = page_height / mm - 2 * PAGE_MARGIN_MM - 15
    return min(available_width / geometry.width, available_height / geometry.height)


def _needs_readable_tiles(geometry: PatternGeometry) -> bool:
    return _overview_cell_mm(geometry) < OVERVIEW_READABLE_CELL_MM


def _tile_geometry(cell_mm: float = READABLE_CELL_MM) -> tuple[int, int, float, float, float]:
    page_width, page_height = A4
    margin_x = 10 * mm
    margin_y = 12 * mm
    coord_band = 7 * mm
    cell = cell_mm * mm
    cols = max(1, int((page_width - 2 * margin_x - coord_band) // cell))
    rows = max(1, int((page_height - 2 * margin_y - coord_band - 13 * mm) // cell))
    return cols, rows, margin_x, margin_y, coord_band


def estimate_total_pdf_pages(result: PatternResult) -> int:
    geometry = analyze_pattern(result)
    if not _needs_readable_tiles(geometry):
        return 1
    cols, rows, _, _, _ = _tile_geometry()
    return 1 + math.ceil(geometry.width / cols) * math.ceil(geometry.height / rows)


def _draw_overview_page(c: canvas.Canvas, chart_path: Path, geometry: PatternGeometry, result: PatternResult, title: str, regular_font: str) -> None:
    page_width, page_height = _overview_page_size(geometry)
    c.setPageSize((page_width, page_height))
    with Image.open(chart_path) as chart:
        image_width, image_height = chart.size
    max_width = page_width - 2 * PAGE_MARGIN_MM * mm
    max_height = page_height - 2 * PAGE_MARGIN_MM * mm - 5 * mm
    scale = min(max_width / image_width, max_height / image_height)
    draw_width = image_width * scale
    draw_height = image_height * scale
    c.drawImage(
        ImageReader(str(chart_path)),
        (page_width - draw_width) / 2,
        (page_height - draw_height) / 2 + 2 * mm,
        width=draw_width,
        height=draw_height,
        preserveAspectRatio=True,
        mask="auto",
    )
    summary = (
        f"拼豆施工图｜图案尺寸：{geometry.width}×{geometry.height}颗｜总豆数：{result.total_beads}颗｜"
        f"建议底板：{_board_text(geometry)}"
    )
    c.setFillColorRGB(0, 0, 0)
    c.setFont(regular_font, 6.5)
    c.drawString(7 * mm, 5 * mm, summary)
    c.drawRightString(page_width - 7 * mm, 5 * mm, "完整图纸 / 第1页")
    c.showPage()


def _draw_readable_tiles(c: canvas.Canvas, codes, palette: Palette, title: str, regular_font: str, bold_font: str) -> None:
    page_width, page_height = A4
    cols_per_page, rows_per_page, margin_x, margin_y, coord_band = _tile_geometry()
    cell = READABLE_CELL_MM * mm
    pattern_height, pattern_width = codes.shape
    tiles_x = math.ceil(pattern_width / cols_per_page)
    tiles_y = math.ceil(pattern_height / rows_per_page)
    total_tiles = tiles_x * tiles_y
    tile_index = 0

    for tile_y in range(tiles_y):
        for tile_x in range(tiles_x):
            tile_index += 1
            c.setPageSize(A4)
            x_start = tile_x * cols_per_page
            y_start = tile_y * rows_per_page
            x_end = min(pattern_width, x_start + cols_per_page)
            y_end = min(pattern_height, y_start + rows_per_page)
            tile_cols = x_end - x_start
            tile_rows = y_end - y_start
            origin_x = margin_x + coord_band
            origin_y = page_height - margin_y - 12 * mm

            c.setFillColorRGB(0, 0, 0)
            c.setFont(bold_font, 9)
            header = f"{_display_title(title)}｜分图{tile_x + 1},{tile_y + 1}｜列{x_start + 1}–{x_end}，行{y_start + 1}–{y_end}"
            c.drawString(margin_x, page_height - margin_y, header)
            neighbors = []
            if tile_y > 0:
                neighbors.append("上")
            if tile_y + 1 < tiles_y:
                neighbors.append("下")
            if tile_x > 0:
                neighbors.append("左")
            if tile_x + 1 < tiles_x:
                neighbors.append("右")
            c.setFont(regular_font, 7)
            adjacent_text = "相邻页面：" + "、".join(neighbors) if neighbors else "无相邻页面"
            c.drawString(margin_x, page_height - margin_y - 5 * mm, adjacent_text)

            for local_y, global_y in enumerate(range(y_start, y_end)):
                y = origin_y - (local_y + 1) * cell
                for local_x, global_x in enumerate(range(x_start, x_end)):
                    x = origin_x + local_x * cell
                    code = codes[global_y, global_x]
                    if code is None:
                        c.setFillColorRGB(1, 1, 1)
                    else:
                        rgb = palette.by_code[code].rgb
                        c.setFillColor(PdfColor(*(value / 255 for value in rgb)))
                    c.rect(x, y, cell, cell, stroke=0, fill=1)
                    if code is not None:
                        rgb = palette.by_code[code].rgb
                        c.setFillColorRGB(1, 1, 1) if _luminance(rgb) < 0.38 else c.setFillColorRGB(0, 0, 0)
                        font_size = 6.6
                        c.setFont(bold_font, font_size)
                        text_width = stringWidth(code, bold_font, font_size)
                        c.drawString(x + (cell - text_width) / 2, y + cell / 2 - font_size * 0.34, code)

            for local_x in range(tile_cols + 1):
                global_boundary = x_start + local_x
                c.setLineWidth(1.4 if global_boundary % 10 == 0 else (1.1 if global_boundary % 5 == 0 else 0.3))
                c.setStrokeColorRGB(0.35, 0.35, 0.35)
                x = origin_x + local_x * cell
                c.line(x, origin_y, x, origin_y - tile_rows * cell)
            for local_y in range(tile_rows + 1):
                global_boundary = y_start + local_y
                c.setLineWidth(1.4 if global_boundary % 10 == 0 else (1.1 if global_boundary % 5 == 0 else 0.3))
                c.setStrokeColorRGB(0.35, 0.35, 0.35)
                y = origin_y - local_y * cell
                c.line(origin_x, y, origin_x + tile_cols * cell, y)

            c.setFillColorRGB(0, 0, 0)
            c.setFont(regular_font, 5.5)
            for local_x, global_x in enumerate(range(x_start, x_end)):
                label = str(global_x + 1)
                text_width = stringWidth(label, regular_font, 5.5)
                c.drawString(origin_x + local_x * cell + (cell - text_width) / 2, origin_y + 1.7 * mm, label)
            for local_y, global_y in enumerate(range(y_start, y_end)):
                label = str(global_y + 1)
                text_width = stringWidth(label, regular_font, 5.5)
                c.drawString(origin_x - 1.5 * mm - text_width, origin_y - (local_y + 0.62) * cell, label)

            c.setFont(regular_font, 7)
            c.drawString(margin_x, 8 * mm, f"8毫米可读施工分图 {tile_index}/{total_tiles}；坐标从裁剪后的图案边界开始。")
            c.drawRightString(page_width - margin_x, 8 * mm, f"PDF第{tile_index + 1}页")
            c.showPage()


def render_pattern_pdf(
    result: PatternResult,
    palette: Palette,
    path: str | Path,
    chart_path: str | Path,
    title: str = "MARD拼豆施工图",
) -> Path:
    path = Path(path)
    chart_path = Path(chart_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    geometry = analyze_pattern(result)
    codes = crop_codes(result, geometry)
    regular_font, bold_font = register_reportlab_cjk_fonts()
    pdf = canvas.Canvas(str(path), pagesize=_overview_page_size(geometry), pageCompression=1)
    pdf.setTitle(f"{_display_title(title)} - MARD拼豆施工图")
    pdf.setAuthor("mard-perler-pattern")
    pdf.setSubject(f"MARD拼豆施工图；每颗间距{BEAD_PITCH_MM:g}毫米；图案尺寸{geometry.width}×{geometry.height}颗")
    _draw_overview_page(pdf, chart_path, geometry, result, title, regular_font)
    if _needs_readable_tiles(geometry):
        _draw_readable_tiles(pdf, codes, palette, title, regular_font, bold_font)
    pdf.save()
    return path


def render_all_outputs(
    result: PatternResult,
    palette: Palette,
    output_dir: str | Path,
    title: str = "MARD拼豆施工图",
    reserve_percent: float = 10,
) -> dict[str, Path]:
    if reserve_percent < 0:
        raise ValueError("备料百分比不能为负数")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = result.variant
    pattern_png = render_pattern_chart_png(result, palette, output_dir / f"{slug}-pattern.png", title)
    pattern_pdf = render_pattern_pdf(result, palette, output_dir / f"{slug}-pattern.pdf", pattern_png, title)
    return {"pattern_png": pattern_png, "pattern_pdf": pattern_pdf}
