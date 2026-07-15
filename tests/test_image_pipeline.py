import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from palette import Palette
from image_pipeline import PatternResult, map_image, prepare_grid_image


class ImagePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.palette = Palette.load(ROOT / "assets" / "mard-291-colors.json")

    def _save(self, pixels, mode="RGBA", **save_kwargs):
        td = tempfile.TemporaryDirectory()
        path = Path(td.name) / "input.png"
        Image.fromarray(np.asarray(pixels, dtype=np.uint8), mode).save(path, **save_kwargs)
        return td, path

    def test_exact_2x2_colors(self):
        codes = ["A01", "B01", "C01", "T01"]
        pixels = np.array([[self.palette.by_code[c].rgb + (255,) for c in codes[:2]], [self.palette.by_code[c].rgb + (255,) for c in codes[2:]]], dtype=np.uint8)
        td, path = self._save(pixels)
        try:
            result = map_image(path, 2, 2, self.palette, fit="crop", background="keep", dither=False)
            self.assertEqual([["A01", "B01"], ["C01", "T01"]], result.codes.tolist())
            self.assertEqual(4, result.total_beads)
        finally:
            td.cleanup()

    def test_transparent_and_half_alpha_threshold(self):
        px = np.zeros((1, 3, 4), dtype=np.uint8)
        px[0, 0] = self.palette.by_code["A01"].rgb + (255,)
        px[0, 1] = (255, 0, 0, 127)
        px[0, 2] = (255, 0, 0, 128)
        td, path = self._save(px)
        try:
            result = map_image(path, 3, 1, self.palette, fit="crop", background="transparent", dither=False)
            self.assertEqual("A01", result.codes[0, 0])
            self.assertIsNone(result.codes[0, 1])
            self.assertIsNotNone(result.codes[0, 2])
            self.assertEqual(2, result.total_beads)
        finally:
            td.cleanup()

    def test_rgb_without_alpha_and_multiple_grid_shapes(self):
        rgb = np.full((7, 31, 3), self.palette.by_code["B01"].rgb, dtype=np.uint8)
        td, path = self._save(rgb, mode="RGB")
        try:
            for width, height in ((29, 29), (1, 47), (17, 11)):
                result = map_image(path, width, height, self.palette, fit="crop", background="keep")
                self.assertEqual((height, width), result.codes.shape)
                self.assertEqual(width * height, result.total_beads)
        finally:
            td.cleanup()

    def test_inventory_limits_output_and_accepts_aliases(self):
        px = np.full((2, 2, 4), (250, 244, 200, 255), dtype=np.uint8)
        td, path = self._save(px)
        try:
            result = map_image(path, 2, 2, self.palette, inventory=["a1", "T1"], dither=False)
            self.assertTrue(set(c for c in result.codes.flat if c) <= {"A01", "T01"})
            with self.assertRaisesRegex(ValueError, "库存色号为空"):
                map_image(path, 2, 2, self.palette, inventory=[])
            with self.assertRaisesRegex(ValueError, "未知的 MARD 色号"):
                map_image(path, 2, 2, self.palette, inventory=["BAD"])
        finally:
            td.cleanup()

    def test_dither_is_deterministic_and_palette_bounded(self):
        gradient = np.zeros((8, 16, 4), dtype=np.uint8)
        for x in range(16):
            gradient[:, x, :3] = (x * 17, x * 17, x * 17)
            gradient[:, x, 3] = 255
        td, path = self._save(gradient)
        try:
            a = map_image(path, 16, 8, self.palette, dither=True)
            b = map_image(path, 16, 8, self.palette, dither=True)
            self.assertEqual(a.codes.tolist(), b.codes.tolist())
            self.assertTrue(set(a.codes.flat) <= set(self.palette.by_code))
            restored = PatternResult.from_dict(a.to_dict())
            self.assertEqual(a.codes.tolist(), restored.codes.tolist())
            self.assertEqual(a.total_beads, restored.total_beads)
        finally:
            td.cleanup()

    def test_pad_does_not_distort_and_creates_transparency(self):
        px = np.full((10, 20, 4), self.palette.by_code["A01"].rgb + (255,), dtype=np.uint8)
        td, path = self._save(px)
        try:
            result = map_image(path, 20, 20, self.palette, fit="pad", background="transparent", dither=False)
            transparent = sum(c is None for c in result.codes.flat)
            self.assertGreater(transparent, 0)
            self.assertLess(transparent, 400)
        finally:
            td.cleanup()

    def test_valid_and_damaged_icc_profiles_are_handled(self):
        px = np.full((5, 7, 3), self.palette.by_code["C01"].rgb, dtype=np.uint8)
        srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        for profile in (srgb, b"damaged-profile"):
            td, path = self._save(px, mode="RGB", icc_profile=profile)
            try:
                result = map_image(path, 7, 5, self.palette)
                self.assertEqual(35, result.total_beads)
            finally:
                td.cleanup()

    def test_exif_orientation_is_applied(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "oriented.jpg"
            image = Image.new("RGB", (12, 6), "red")
            exif = Image.Exif()
            exif[274] = 6
            image.save(path, quality=100, exif=exif)
            # Orientation 6 rotates the decoded image, changing the pre-crop aspect ratio.
            prepared = prepare_grid_image(path, 6, 12, fit="pad", background="keep")
            self.assertEqual((6, 12), prepared.size)
            arr = np.asarray(prepared)
            self.assertGreater((arr[..., 0] > arr[..., 1] * 2).mean(), 0.9)

    def test_invalid_dimensions_and_modes_fail(self):
        px = np.zeros((1, 1, 4), dtype=np.uint8)
        td, path = self._save(px)
        try:
            with self.assertRaises(ValueError):
                map_image(path, 0, 1, self.palette)
            with self.assertRaises(ValueError):
                map_image(path, 1, 1, self.palette, fit="stretch")
            with self.assertRaises(ValueError):
                map_image(path, 1, 1, self.palette, background="black")
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()

