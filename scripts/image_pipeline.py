from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageCms, ImageDraw, ImageOps

from font_support import load_pil_cjk_font
from palette import Palette, rgb_to_oklab

TRANSPARENT_ALPHA_THRESHOLD = 128
DITHER_STRENGTH = 0.5


@dataclass
class PatternResult:
    width: int
    height: int
    codes: np.ndarray
    source_rgb: np.ndarray
    mean_distance: float
    variant: str
    fit: str
    background: str
    inventory_codes: tuple[str, ...]

    @property
    def total_beads(self) -> int:
        return int(sum(code is not None for code in self.codes.flat))

    @property
    def used_color_count(self) -> int:
        return len({code for code in self.codes.flat if code is not None})

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "codes": self.codes.tolist(),
            "source_rgb": self.source_rgb.astype(int).tolist(),
            "mean_distance": self.mean_distance,
            "variant": self.variant,
            "fit": self.fit,
            "background": self.background,
            "inventory_codes": list(self.inventory_codes),
            "total_beads": self.total_beads,
            "used_color_count": self.used_color_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PatternResult":
        return cls(
            width=int(data["width"]), height=int(data["height"]),
            codes=np.asarray(data["codes"], dtype=object),
            source_rgb=np.asarray(data["source_rgb"], dtype=np.uint8),
            mean_distance=float(data["mean_distance"]), variant=data["variant"],
            fit=data.get("fit", "crop"), background=data.get("background", "keep"),
            inventory_codes=tuple(data.get("inventory_codes", [])),
        )


def _apply_color_management(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    icc = image.info.get("icc_profile")
    if icc:
        try:
            alpha = image.getchannel("A") if "A" in image.getbands() else None
            rgb = image.convert("RGB")
            source = ImageCms.ImageCmsProfile(__import__("io").BytesIO(icc))
            target = ImageCms.createProfile("sRGB")
            converted = ImageCms.profileToProfile(rgb, source, target, outputMode="RGB")
            if alpha is not None:
                converted.putalpha(alpha)
            image = converted
        except Exception:
            image = image.convert("RGBA")
    return image.convert("RGBA")


def _crop_box(source_size: tuple[int, int], target_size: tuple[int, int]) -> tuple[int, int, int, int]:
    sw, sh = source_size
    tw, th = target_size
    source_ratio = sw / sh
    target_ratio = tw / th
    if source_ratio > target_ratio:
        new_w = int(round(sh * target_ratio))
        left = (sw - new_w) // 2
        return left, 0, left + new_w, sh
    new_h = int(round(sw / target_ratio))
    top = (sh - new_h) // 2
    return 0, top, sw, top + new_h


def _premultiplied_resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    arr = np.asarray(image.convert("RGBA"), dtype=np.float32)
    alpha = arr[..., 3:4] / 255.0
    premul = arr[..., :3] * alpha
    resized_channels = []
    for channel in range(3):
        plane = Image.fromarray(premul[..., channel], mode="F").resize(size, Image.Resampling.BOX)
        resized_channels.append(np.asarray(plane, dtype=np.float32))
    alpha_plane = Image.fromarray(alpha[..., 0], mode="F").resize(size, Image.Resampling.BOX)
    resized_alpha = np.asarray(alpha_plane, dtype=np.float32)
    rgb = np.stack(resized_channels, axis=-1)
    safe_alpha = np.maximum(resized_alpha[..., None], 1e-8)
    rgb = np.where(resized_alpha[..., None] > 0, rgb / safe_alpha, 0)
    out = np.concatenate((np.clip(rgb, 0, 255), np.clip(resized_alpha[..., None] * 255.0, 0, 255)), axis=-1)
    return Image.fromarray(np.rint(out).astype(np.uint8), mode="RGBA")


def prepare_grid_image(input_path: str | Path, width: int, height: int, fit: str = "crop", background: str = "keep") -> Image.Image:
    if width <= 0 or height <= 0:
        raise ValueError("网格宽度和高度必须为正整数")
    if fit not in {"crop", "pad"}:
        raise ValueError("fit 必须是 crop 或 pad")
    if background not in {"keep", "transparent"}:
        raise ValueError("background 必须是 keep 或 transparent")
    with Image.open(input_path) as source:
        image = _apply_color_management(source)
    if fit == "crop":
        image = image.crop(_crop_box(image.size, (width, height)))
        grid = _premultiplied_resize(image, (width, height))
    else:
        scale = min(width / image.width, height / image.height)
        inner = (max(1, int(round(image.width * scale))), max(1, int(round(image.height * scale))))
        resized = _premultiplied_resize(image, inner)
        grid = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        grid.alpha_composite(resized, ((width - inner[0]) // 2, (height - inner[1]) // 2))
    if background == "keep":
        white = Image.new("RGBA", grid.size, (255, 255, 255, 255))
        white.alpha_composite(grid)
        grid = white
    return grid


def _resolve_palette(palette: Palette, inventory: Iterable[str] | None) -> Palette:
    if inventory is None:
        return palette
    inventory = [code.strip() for code in inventory if code and code.strip()]
    if not inventory:
        raise ValueError("库存色号为空")
    return palette.subset(inventory)


def _map_clean(rgb: np.ndarray, opaque: np.ndarray, palette: Palette) -> tuple[np.ndarray, np.ndarray]:
    codes = np.empty(opaque.shape, dtype=object)
    codes[:] = None
    distances = np.zeros(opaque.shape, dtype=np.float64)
    for y, x in zip(*np.where(opaque)):
        color, distance = palette.nearest_with_distance(rgb[y, x])
        codes[y, x] = color.code
        distances[y, x] = distance
    return codes, distances


def _map_dither(rgb: np.ndarray, opaque: np.ndarray, palette: Palette, strength: float) -> tuple[np.ndarray, np.ndarray]:
    labs = rgb_to_oklab(rgb)
    errors = np.zeros_like(labs, dtype=np.float64)
    codes = np.empty(opaque.shape, dtype=object)
    codes[:] = None
    distances = np.zeros(opaque.shape, dtype=np.float64)
    height, width = opaque.shape
    for y in range(height):
        reverse = bool(y % 2)
        xs = range(width - 1, -1, -1) if reverse else range(width)
        for x in xs:
            if not opaque[y, x]:
                continue
            target = labs[y, x] + errors[y, x]
            palette_distances = np.linalg.norm(palette._lab - target, axis=1)
            idx = int(np.argmin(palette_distances))
            color = palette.colors[idx]
            codes[y, x] = color.code
            distances[y, x] = float(np.linalg.norm(palette._lab[idx] - labs[y, x]) * 100.0)
            error = (target - palette._lab[idx]) * strength
            direction = -1 if reverse else 1
            neighbors = [
                (x + direction, y, 7 / 16),
                (x - direction, y + 1, 3 / 16),
                (x, y + 1, 5 / 16),
                (x + direction, y + 1, 1 / 16),
            ]
            for nx, ny, weight in neighbors:
                if 0 <= nx < width and 0 <= ny < height and opaque[ny, nx]:
                    errors[ny, nx] += error * weight
    return codes, distances


def map_image(
    input_path: str | Path,
    width: int,
    height: int,
    palette: Palette,
    fit: str = "crop",
    background: str = "keep",
    inventory: Iterable[str] | None = None,
    dither: bool = False,
    dither_strength: float = DITHER_STRENGTH,
) -> PatternResult:
    active = _resolve_palette(palette, inventory)
    grid = prepare_grid_image(input_path, width, height, fit=fit, background=background)
    rgba = np.asarray(grid, dtype=np.uint8)
    rgb = rgba[..., :3]
    opaque = rgba[..., 3] >= TRANSPARENT_ALPHA_THRESHOLD
    if dither:
        codes, distances = _map_dither(rgb, opaque, active, dither_strength)
        variant = "dither"
    else:
        codes, distances = _map_clean(rgb, opaque, active)
        variant = "clean"
    mean_distance = float(distances[opaque].mean()) if np.any(opaque) else 0.0
    inventory_codes = tuple(color.code for color in active.colors) if inventory is not None else ()
    return PatternResult(width, height, codes, rgb.copy(), mean_distance, variant, fit, background, inventory_codes)


def pattern_image(result: PatternResult, palette: Palette, scale: int = 12) -> Image.Image:
    rgba = np.zeros((result.height, result.width, 4), dtype=np.uint8)
    for y in range(result.height):
        for x in range(result.width):
            code = result.codes[y, x]
            if code is not None:
                rgba[y, x, :3] = palette.by_code[code].rgb
                rgba[y, x, 3] = 255
    return Image.fromarray(rgba, "RGBA").resize((result.width * scale, result.height * scale), Image.Resampling.NEAREST)


def _font(size: int, bold: bool = False):
    return load_pil_cjk_font(size, bold=bold)


def render_preview_contact_sheet(input_path: str | Path, clean: PatternResult, dither: PatternResult, palette: Palette, output_dir: str | Path) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    original = prepare_grid_image(input_path, clean.width, clean.height, fit=clean.fit, background=clean.background)
    original_path = output_dir / "source-fitted.png"
    clean_path = output_dir / "preview-clean.png"
    dither_path = output_dir / "preview-dither.png"
    original.resize((clean.width * 12, clean.height * 12), Image.Resampling.NEAREST).save(original_path)
    clean_img = pattern_image(clean, palette)
    dither_img = pattern_image(dither, palette)
    clean_img.save(clean_path)
    dither_img.save(dither_path)
    image_w = clean_img.width
    tile_w = max(image_w, 420)
    top = 90
    gap = 20
    sheet = Image.new("RGB", (tile_w * 3 + gap * 4, clean_img.height + top + 30), "#F4F1EA")
    draw = ImageDraw.Draw(sheet)
    title_font = _font(24, bold=True)
    body_font = _font(16)
    labels = [
        ("原图采样", "尺寸 {}×{}".format(clean.width, clean.height)),
        ("干净色块", f"{clean.total_beads}颗 / {clean.used_color_count}色 / 平均误差 {clean.mean_distance:.2f}"),
        ("轻度抖动", f"{dither.total_beads}颗 / {dither.used_color_count}色 / 平均误差 {dither.mean_distance:.2f}"),
    ]
    images = [original.resize(clean_img.size, Image.Resampling.NEAREST).convert("RGB"), clean_img.convert("RGB"), dither_img.convert("RGB")]
    for i, (label, metric) in enumerate(labels):
        tile_x = gap + i * (tile_w + gap)
        image_x = tile_x + (tile_w - image_w) // 2
        draw.text((tile_x, 14), label, fill="#222222", font=title_font)
        draw.text((tile_x, 50), metric, fill="#555555", font=body_font)
        sheet.paste(images[i], (image_x, top))
    contact_path = output_dir / "preview-contact-sheet.png"
    sheet.save(contact_path)
    return {"source": original_path, "clean": clean_path, "dither": dither_path, "contact_sheet": contact_path}


