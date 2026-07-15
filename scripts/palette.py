from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

HEX_RE = re.compile(r"^#[0-9A-F]{6}$")
CODE_RE = re.compile(r"^([A-Z]+)(\d+)$")


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.upper()
    if not HEX_RE.fullmatch(value):
        raise ValueError(f"无效的 HEX 颜色： {value}")
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def rgb_to_hex(rgb: Sequence[int]) -> str:
    if len(rgb) != 3 or any(int(v) < 0 or int(v) > 255 for v in rgb):
        raise ValueError(f"无效的 RGB 颜色： {rgb}")
    return "#{:02X}{:02X}{:02X}".format(*(int(v) for v in rgb))


def _srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    value = np.asarray(rgb, dtype=np.float64) / 255.0
    return np.where(value <= 0.04045, value / 12.92, ((value + 0.055) / 1.055) ** 2.4)


def rgb_to_oklab(rgb: Sequence[int] | np.ndarray) -> np.ndarray:
    linear = _srgb_to_linear(np.asarray(rgb, dtype=np.float64))
    r, g, b = np.moveaxis(linear, -1, 0)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = np.cbrt(l), np.cbrt(m), np.cbrt(s)
    return np.stack((
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    ), axis=-1)


def compute_colors_sha256(colors: list[dict]) -> str:
    normalized = []
    for color in colors:
        normalized.append({
            "code": color["code"],
            "aliases": list(color.get("aliases", [])),
            "series": color["series"],
            "index": int(color["index"]),
            "hex": color["hex"].upper(),
            "rgb": {"r": int(color["rgb"]["r"]), "g": int(color["rgb"]["g"]), "b": int(color["rgb"]["b"])},
            "legacy_hex": list(color.get("legacy_hex", [])),
            "source": color.get("source", ""),
        })
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class Color:
    code: str
    aliases: tuple[str, ...]
    series: str
    index: int
    hex: str
    rgb: tuple[int, int, int]
    legacy_hex: tuple[str, ...]
    source: str
    note: str = ""


class Palette:
    def __init__(self, colors: Iterable[Color], metadata: dict | None = None):
        self.colors = tuple(colors)
        if not self.colors:
            raise ValueError("色库不能为空")
        self.metadata = metadata or {}
        self.by_code = {color.code: color for color in self.colors}
        self._aliases: dict[str, str] = {}
        for color in self.colors:
            for alias in (color.code, *color.aliases):
                self._aliases[alias.upper()] = color.code
        self._rgb = np.asarray([color.rgb for color in self.colors], dtype=np.float64)
        self._lab = rgb_to_oklab(self._rgb)

    @classmethod
    def load(cls, path: str | Path) -> "Palette":
        path = Path(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        colors = []
        for item in raw["colors"]:
            rgb = item["rgb"]
            colors.append(Color(
                code=item["code"], aliases=tuple(item.get("aliases", [])), series=item["series"],
                index=int(item["index"]), hex=item["hex"].upper(),
                rgb=(int(rgb["r"]), int(rgb["g"]), int(rgb["b"])),
                legacy_hex=tuple(item.get("legacy_hex", [])), source=item.get("source", ""), note=item.get("note", "")
            ))
        palette = cls(colors, raw)
        expected = raw.get("integrity", {}).get("normalized_colors_sha256")
        if expected and expected != compute_colors_sha256(raw["colors"]):
            raise ValueError("色库完整性哈希不匹配")
        return palette

    def normalize_code(self, value: str) -> str:
        key = value.strip().upper()
        if key in self._aliases:
            return self._aliases[key]
        match = CODE_RE.fullmatch(key)
        if match:
            compact = f"{match.group(1)}{int(match.group(2))}"
            if compact in self._aliases:
                return self._aliases[compact]
        raise ValueError(f"未知的 MARD 色号： {value}")

    def subset(self, codes: Iterable[str]) -> "Palette":
        normalized = []
        seen = set()
        for code in codes:
            canonical = self.normalize_code(code)
            if canonical not in seen:
                normalized.append(self.by_code[canonical])
                seen.add(canonical)
        if not normalized:
            raise ValueError("库存中没有有效颜色")
        return Palette(normalized, self.metadata)

    def nearest(self, rgb: Sequence[int] | np.ndarray) -> Color:
        target = rgb_to_oklab(np.asarray(rgb, dtype=np.float64))
        distances = np.linalg.norm(self._lab - target, axis=1)
        return self.colors[int(np.argmin(distances))]

    def nearest_with_distance(self, rgb: Sequence[int] | np.ndarray) -> tuple[Color, float]:
        target = rgb_to_oklab(np.asarray(rgb, dtype=np.float64))
        distances = np.linalg.norm(self._lab - target, axis=1) * 100.0
        idx = int(np.argmin(distances))
        return self.colors[idx], float(distances[idx])

