import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from font_support import load_pil_cjk_font, resolve_cjk_font


class FontSupportTests(unittest.TestCase):
    def test_environment_font_path_wins(self):
        windows_font = Path(os.environ.get("WINDIR", r"C:\\Windows")) / "Fonts" / "msyh.ttc"
        if not windows_font.exists():
            self.skipTest('当前测试机没有微软雅黑字体')
        with patch.dict(os.environ, {"MARD_CJK_FONT": str(windows_font)}):
            self.assertEqual(windows_font.resolve(), resolve_cjk_font())

    def test_invalid_environment_font_reports_actionable_chinese_error(self):
        missing = Path(tempfile.gettempdir()) / "missing-mard-cjk-font.ttf"
        with patch.dict(os.environ, {"MARD_CJK_FONT": str(missing)}):
            with self.assertRaisesRegex(RuntimeError, "MARD_CJK_FONT.*" + '不存在'):
                resolve_cjk_font()

    def test_system_font_resolves_and_pillow_uses_truetype(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MARD_CJK_FONT", None)
            font_path = resolve_cjk_font()
            self.assertTrue(font_path.exists())
            font = load_pil_cjk_font(18)
            self.assertIsInstance(font, ImageFont.FreeTypeFont)


if __name__ == "__main__":
    unittest.main()
