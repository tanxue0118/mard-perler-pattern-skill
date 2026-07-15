from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from image_pipeline import PatternResult

BEAD_PITCH_MM = 2.6
COMMON_BOARD_SIZES = (52, 78, 104)


@dataclass(frozen=True)
class PatternGeometry:
    left: int
    top: int
    right: int
    bottom: int
    width: int
    height: int
    width_mm: float
    height_mm: float
    recommended_board: tuple[int, int] | None

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)

    @property
    def width_cm(self) -> float:
        return self.width_mm / 10.0

    @property
    def height_cm(self) -> float:
        return self.height_mm / 10.0


def analyze_pattern(result: PatternResult) -> PatternGeometry:
    occupied = [(x, y) for y in range(result.height) for x in range(result.width) if result.codes[y, x] is not None]
    if not occupied:
        raise ValueError("图案中没有非透明拼豆")
    xs = [point[0] for point in occupied]
    ys = [point[1] for point in occupied]
    left, top = min(xs), min(ys)
    right, bottom = max(xs) + 1, max(ys) + 1
    width, height = right - left, bottom - top
    maximum_side = max(width, height)
    board_side = next((size for size in COMMON_BOARD_SIZES if size >= maximum_side), None)
    board = (board_side, board_side) if board_side is not None else None
    return PatternGeometry(
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        width=width,
        height=height,
        width_mm=width * BEAD_PITCH_MM,
        height_mm=height * BEAD_PITCH_MM,
        recommended_board=board,
    )


def crop_codes(result: PatternResult, geometry: PatternGeometry | None = None) -> np.ndarray:
    geometry = geometry or analyze_pattern(result)
    return np.asarray(result.codes[geometry.top:geometry.bottom, geometry.left:geometry.right], dtype=object).copy()


def usage_recommendation(width: int, height: int) -> str:
    maximum_side = max(width, height)
    if maximum_side <= 10:
        return "小配饰"
    if maximum_side <= 15:
        return "手机挂饰或冰箱贴"
    if maximum_side <= 20:
        return "冰箱贴或钥匙扣"
    if maximum_side <= 25:
        return "较大冰箱贴、钥匙扣或小挂件"
    return "精细或较大型图案"
