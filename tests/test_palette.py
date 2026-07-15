import csv
import json
import re
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from palette import Palette, compute_colors_sha256, hex_to_rgb, rgb_to_hex

EXPECTED_COUNTS = {"A":26,"B":32,"C":29,"D":26,"E":24,"F":25,"G":21,"H":23,"M":15,"P":23,"Q":5,"R":28,"T":1,"Y":5,"ZG":8}

class PaletteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.json_path = ROOT / "assets" / "mard-291-colors.json"
        cls.csv_path = ROOT / "assets" / "mard-291-colors.csv"
        cls.palette = Palette.load(cls.json_path)

    def test_palette_count_series_uniqueness_and_continuity(self):
        colors = self.palette.colors
        self.assertEqual(291, len(colors))
        self.assertEqual(291, len({c.code for c in colors}))
        self.assertEqual(290, len({c.hex for c in colors}))
        collisions = {c.code for c in colors if c.hex == "#FFEBFA"}
        self.assertEqual({"Q04", "R11"}, collisions)
        self.assertEqual(EXPECTED_COUNTS, Counter(c.series for c in colors))
        for series, count in EXPECTED_COUNTS.items():
            self.assertEqual(list(range(1, count + 1)), sorted(c.index for c in colors if c.series == series))

    def test_hex_rgb_round_trip_and_format(self):
        for color in self.palette.colors:
            self.assertRegex(color.hex, r"^#[0-9A-F]{6}$")
            self.assertEqual(color.rgb, hex_to_rgb(color.hex))
            self.assertEqual(color.hex, rgb_to_hex(color.rgb))

    def test_csv_mirrors_json(self):
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(291, len(rows))
        by_code = {r["code"]: r for r in rows}
        for color in self.palette.colors:
            row = by_code[color.code]
            self.assertEqual(color.hex, row["hex"])
            self.assertEqual(str(color.rgb[0]), row["r"])
            self.assertEqual(str(color.rgb[1]), row["g"])
            self.assertEqual(str(color.rgb[2]), row["b"])

    def test_r11_canonical_and_legacy(self):
        r11 = self.palette.by_code["R11"]
        self.assertEqual("#FFEBFA", r11.hex)
        self.assertIn("#FFEBFB", r11.legacy_hex)

    def test_alias_normalization(self):
        self.assertEqual("A01", self.palette.normalize_code("a1"))
        self.assertEqual("A01", self.palette.normalize_code("A01"))
        self.assertEqual("ZG8", self.palette.normalize_code("zg8"))
        with self.assertRaises(ValueError):
            self.palette.normalize_code("NOPE")

    def test_integrity_hash(self):
        raw = json.loads(self.json_path.read_text(encoding="utf-8"))
        self.assertEqual(raw["integrity"]["normalized_colors_sha256"], compute_colors_sha256(raw["colors"]))

    def test_all_unique_exact_colors_map_deterministically(self):
        first_by_rgb = {}
        for color in self.palette.colors:
            first_by_rgb.setdefault(color.rgb, color.code)
        for rgb, expected_code in first_by_rgb.items():
            self.assertEqual(expected_code, self.palette.nearest(rgb).code)
        self.assertEqual("R11", self.palette.subset(["R11"]).nearest((255, 235, 250)).code)

if __name__ == "__main__":
    unittest.main()




