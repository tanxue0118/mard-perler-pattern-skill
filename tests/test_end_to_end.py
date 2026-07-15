import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
CLI = ROOT / "scripts" / "pattern_cli.py"
sys.path.insert(0, str(ROOT / "scripts"))
from pattern_cli import _confirm_large


class EndToEndTests(unittest.TestCase):
    def _source(self, path: Path) -> None:
        canvas = Image.new("RGBA", (64, 48), (255, 255, 255, 0))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((4, 4, 30, 42), fill="#F77C31")
        draw.ellipse((24, 8, 58, 42), fill="#8BDBFA")
        canvas.save(path)

    def test_preview_then_finalize_delivers_only_png_and_pdf(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            image = td / "source.png"
            self._source(image)
            job = td / "job"
            out = td / "out"
            preview = subprocess.run(
                [PYTHON, str(CLI), "preview", "--input", str(image), "--width", "16", "--height", "12", "--fit", "pad", "--background", "transparent", "--output-dir", str(job)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, preview.returncode, preview.stderr)
            for name in ("preview-contact-sheet.png", "preview-clean.png", "preview-dither.png", "source-fitted.png", "clean-pattern.json", "dither-pattern.json", "job.json"):
                self.assertTrue((job / name).exists(), name)
            job_data = json.loads((job / "job.json").read_text(encoding="utf-8"))
            geometry = job_data["metrics"]["clean"]["geometry"]
            self.assertGreater(geometry["occupied_width"], 0)
            self.assertEqual(2.6, geometry["bead_pitch_mm"])
            self.assertEqual([52, 52], geometry["recommended_board"])
            self.assertIn('实际图案：', preview.stdout)
            for old_label in ('Preview created:', 'Clean:', 'Dither:', 'Occupied pattern:'):
                self.assertNotIn(old_label, preview.stdout)
            finalize = subprocess.run(
                [PYTHON, str(CLI), "finalize", "--job", str(job), "--variant", "clean", "--output-dir", str(out)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, finalize.returncode, finalize.stderr)
            self.assertEqual({"clean-pattern.png", "clean-pattern.pdf"}, {path.name for path in out.iterdir()})
            self.assertIn('图案尺寸：', finalize.stdout)
            self.assertIn('预计成品尺寸：', finalize.stdout)
            self.assertIn('建议底板：', finalize.stdout)
            self.assertIn('每颗间距2.6毫米', finalize.stdout)
            for old_label in ('Final package created:', 'Pattern size:', 'Physical size:', 'Recommended board:', 'Beads:'):
                self.assertNotIn(old_label, finalize.stdout)

    def test_invalid_inventory_reports_specific_codes(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            image = td / "source.png"
            inventory = td / "inventory.txt"
            self._source(image)
            inventory.write_text("A1, NOT-A-CODE", encoding="utf-8")
            run = subprocess.run([PYTHON, str(CLI), "preview", "--input", str(image), "--width", "8", "--height", "6", "--inventory", str(inventory), "--output-dir", str(td / "job")], capture_output=True, text=True)
            self.assertEqual(2, run.returncode)
            self.assertIn("NOT-A-CODE", run.stderr)

    def test_large_output_requires_explicit_approval(self):
        result = SimpleNamespace(total_beads=40_001)
        with self.assertRaisesRegex(ValueError, "--yes-large"):
            _confirm_large(result, 2, False)
        with self.assertRaisesRegex(ValueError, "--yes-large"):
            _confirm_large(SimpleNamespace(total_beads=1), 51, False)
        _confirm_large(result, 51, True)


if __name__ == "__main__":
    unittest.main()

