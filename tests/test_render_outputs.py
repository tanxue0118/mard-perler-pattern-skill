import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from image_pipeline import PatternResult
from palette import Palette
from render_outputs import (
    CHART_CELL_PX,
    CHART_COORD_BAND_PX,
    CHART_MARGIN_PX,
    estimate_total_pdf_pages,
    material_rows,
    render_all_outputs,
    render_pattern_chart_png,
)


def make_result(codes, variant="clean"):
    values = np.asarray(codes, dtype=object)
    return PatternResult(
        width=values.shape[1],
        height=values.shape[0],
        codes=values,
        source_rgb=np.zeros((values.shape[0], values.shape[1], 3), dtype=np.uint8),
        mean_distance=0.0,
        variant=variant,
        fit="pad",
        background="transparent",
        inventory_codes=(),
    )


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.palette = Palette.load(ROOT / "assets" / "mard-291-colors.json")

    def test_reference_style_chart_crops_outer_transparency_and_keeps_hole(self):
        result = make_result([
            [None, None, None, None, None, None],
            [None, "A01", "A01", "B01", "B01", None],
            [None, "A01", None, "B01", "B01", None],
            [None, "A01", "A01", "B01", "B01", None],
            [None, None, None, None, None, None],
        ])
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "chart.png"
            render_pattern_chart_png(result, self.palette, path, title='合成测试')
            self.assertTrue(path.exists())
            with Image.open(path) as image:
                expected_width = CHART_MARGIN_PX * 2 + CHART_COORD_BAND_PX * 2 + 4 * CHART_CELL_PX
                self.assertEqual(expected_width, image.width)
                grid_left = CHART_MARGIN_PX + CHART_COORD_BAND_PX
                grid_top = CHART_MARGIN_PX + CHART_COORD_BAND_PX
                first_center = (grid_left + 4, grid_top + 4)
                hole_center = (grid_left + CHART_CELL_PX + CHART_CELL_PX // 2, grid_top + CHART_CELL_PX + CHART_CELL_PX // 2)
                self.assertEqual(self.palette.by_code["A01"].rgb, image.convert("RGB").getpixel(first_center))
                self.assertEqual((255, 255, 255), image.convert("RGB").getpixel(hole_center))
            rows = material_rows(result, self.palette)
            self.assertEqual(result.total_beads, sum(row["exact_count"] for row in rows))
            self.assertEqual(["A01", "B01"], [row["code"] for row in rows])

    def test_render_all_outputs_creates_only_png_and_one_pdf(self):
        result = make_result([["A01", "B01"], ["B01", "A01"]])
        with tempfile.TemporaryDirectory() as td:
            paths = render_all_outputs(result, self.palette, Path(td), title='小图测试')
            self.assertEqual({"pattern_png", "pattern_pdf"}, set(paths))
            self.assertEqual({"clean-pattern.png", "clean-pattern.pdf"}, {p.name for p in Path(td).iterdir()})
            reader = PdfReader(str(paths["pattern_pdf"]))
            self.assertEqual(1, len(reader.pages))
            box = reader.pages[0].mediabox
            self.assertIn(round(float(box.width), 2), {595.28, 841.89})
            self.assertIn(round(float(box.height), 2), {595.28, 841.89})
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn('拼豆施工图', text)
            self.assertIn('总豆数', text)
            self.assertIn('建议底板', text)
            self.assertIn('完整图纸 / 第1页', text)
            self.assertIn('MARD拼豆施工图', reader.metadata.title)
            self.assertIn('每颗间距2.6毫米', reader.metadata.subject)

    def test_large_pattern_adds_readable_8mm_tile_pages(self):
        result = make_result([["A01"] * 52 for _ in range(52)])
        with tempfile.TemporaryDirectory() as td:
            paths = render_all_outputs(result, self.palette, Path(td), title='大图测试')
            reader = PdfReader(str(paths["pattern_pdf"]))
            self.assertEqual(estimate_total_pdf_pages(result), len(reader.pages))
            self.assertGreater(len(reader.pages), 1)
            tile_text = "\n".join(page.extract_text() or "" for page in reader.pages[1:])
            self.assertIn("A01", tile_text)
            for expected in ('分图', '列', '行', '相邻页面', '8毫米可读施工分图', 'PDF第'):
                self.assertIn(expected, tile_text)
            all_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            for old_label in ("Complete pattern", "Tile", "Adjacent", "Pattern size"):
                self.assertNotIn(old_label, all_text)


if __name__ == "__main__":
    unittest.main()


