import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from image_pipeline import PatternResult
from pattern_geometry import BEAD_PITCH_MM, analyze_pattern, crop_codes, usage_recommendation


def make_result(codes):
    values = np.asarray(codes, dtype=object)
    return PatternResult(
        width=values.shape[1],
        height=values.shape[0],
        codes=values,
        source_rgb=np.zeros((values.shape[0], values.shape[1], 3), dtype=np.uint8),
        mean_distance=0.0,
        variant="clean",
        fit="pad",
        background="transparent",
        inventory_codes=(),
    )


class PatternGeometryTests(unittest.TestCase):
    def test_bounds_physical_size_board_and_crop(self):
        result = make_result([
            [None, None, None, None, None, None],
            [None, None, "A01", "A01", None, None],
            [None, None, "A01", None, "B01", None],
            [None, None, "A01", "A01", "B01", None],
            [None, None, None, None, None, None],
        ])
        geometry = analyze_pattern(result)
        self.assertEqual(2.6, BEAD_PITCH_MM)
        self.assertEqual((2, 1, 5, 4), geometry.bounds)
        self.assertEqual((3, 3), (geometry.width, geometry.height))
        self.assertAlmostEqual(7.8, geometry.width_mm)
        self.assertAlmostEqual(7.8, geometry.height_mm)
        self.assertEqual((52, 52), geometry.recommended_board)
        cropped = crop_codes(result, geometry)
        self.assertEqual((3, 3), cropped.shape)
        self.assertIsNone(cropped[1, 1])
        self.assertEqual("B01", cropped[2, 2])

    def test_board_selection_uses_smallest_common_capacity(self):
        result_52 = make_result([["A01"] * 52])
        result_78 = make_result([["A01"] * 53])
        result_104 = make_result([["A01"] * 79])
        result_custom = make_result([["A01"] * 105])
        self.assertEqual((52, 52), analyze_pattern(result_52).recommended_board)
        self.assertEqual((78, 78), analyze_pattern(result_78).recommended_board)
        self.assertEqual((104, 104), analyze_pattern(result_104).recommended_board)
        self.assertIsNone(analyze_pattern(result_custom).recommended_board)

    def test_empty_pattern_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '没有非透明拼豆'):
            analyze_pattern(make_result([[None, None], [None, None]]))

    def test_usage_recommendations(self):
        self.assertEqual('小配饰', usage_recommendation(10, 8))
        self.assertEqual('手机挂饰或冰箱贴', usage_recommendation(15, 12))
        self.assertEqual('冰箱贴或钥匙扣', usage_recommendation(20, 18))
        self.assertEqual('较大冰箱贴、钥匙扣或小挂件', usage_recommendation(25, 22))
        self.assertEqual('精细或较大型图案', usage_recommendation(26, 26))


if __name__ == "__main__":
    unittest.main()
