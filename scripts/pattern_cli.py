from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from image_pipeline import PatternResult, map_image, render_preview_contact_sheet
from palette import Palette
from pattern_geometry import BEAD_PITCH_MM, analyze_pattern
from render_outputs import estimate_total_pdf_pages, render_all_outputs

SKILL_ROOT = Path(__file__).resolve().parents[1]
PALETTE_PATH = SKILL_ROOT / "assets" / "mard-291-colors.json"
LARGE_BEAD_THRESHOLD = 40_000
LARGE_PAGE_THRESHOLD = 50


def _read_inventory(path: str | Path, palette: Palette) -> list[str]:
    path = Path(path)
    if not path.exists():
        raise ValueError(f"库存文件不存在：{path}")
    raw = path.read_text(encoding="utf-8-sig")
    tokens = [token for token in re.split(r"[\s,;]+", raw) if token]
    if not tokens:
        raise ValueError("库存文件为空")
    normalized = []
    seen = set()
    errors = []
    for token in tokens:
        try:
            code = palette.normalize_code(token)
        except ValueError:
            errors.append(token)
            continue
        if code not in seen:
            normalized.append(code)
            seen.add(code)
    if errors:
        raise ValueError("库存文件包含无效的 MARD 色号：" + "、".join(errors))
    if not normalized:
        raise ValueError("库存文件中没有可用颜色")
    return normalized


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _geometry_metrics(result: PatternResult) -> dict | None:
    try:
        geometry = analyze_pattern(result)
    except ValueError:
        return None
    return {
        "occupied_bounds": [geometry.left, geometry.top, geometry.right, geometry.bottom],
        "occupied_width": geometry.width,
        "occupied_height": geometry.height,
        "bead_pitch_mm": BEAD_PITCH_MM,
        "physical_width_mm": geometry.width_mm,
        "physical_height_mm": geometry.height_mm,
        "recommended_board": list(geometry.recommended_board) if geometry.recommended_board is not None else None,
    }


def preview(args: argparse.Namespace) -> int:
    input_path = Path(args.input).resolve()
    if not input_path.exists():
        raise ValueError(f"输入图片不存在：{input_path}")
    if args.palette != "all":
        raise ValueError("目前只支持 --palette all；如需限制颜色，请使用 --inventory")
    palette = Palette.load(PALETTE_PATH)
    inventory = _read_inventory(args.inventory, palette) if args.inventory else None
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    clean = map_image(
        input_path, args.width, args.height, palette,
        fit=args.fit, background=args.background, inventory=inventory, dither=False,
    )
    dither = map_image(
        input_path, args.width, args.height, palette,
        fit=args.fit, background=args.background, inventory=inventory, dither=True,
        dither_strength=args.dither_strength,
    )
    preview_paths = render_preview_contact_sheet(input_path, clean, dither, palette, output_dir)
    original_copy = output_dir / ("input-original" + input_path.suffix.lower())
    if input_path != original_copy:
        shutil.copy2(input_path, original_copy)

    clean_path = output_dir / "clean-pattern.json"
    dither_path = output_dir / "dither-pattern.json"
    _write_json(clean_path, clean.to_dict())
    _write_json(dither_path, dither.to_dict())
    job = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_original": str(original_copy),
        "input_name": input_path.stem,
        "palette_path": str(PALETTE_PATH.resolve()),
        "palette_id": palette.metadata.get("palette_id", "mard-291"),
        "palette_sha256": palette.metadata.get("integrity", {}).get("normalized_colors_sha256", ""),
        "settings": {
            "width": args.width,
            "height": args.height,
            "fit": args.fit,
            "background": args.background,
            "inventory_codes": inventory or [],
            "dither_strength": args.dither_strength,
        },
        "variants": {"clean": str(clean_path), "dither": str(dither_path)},
        "preview_files": {key: str(value) for key, value in preview_paths.items()},
        "metrics": {
            "clean": {"total_beads": clean.total_beads, "used_color_count": clean.used_color_count, "mean_oklab_distance": clean.mean_distance, "geometry": _geometry_metrics(clean)},
            "dither": {"total_beads": dither.total_beads, "used_color_count": dither.used_color_count, "mean_oklab_distance": dither.mean_distance, "geometry": _geometry_metrics(dither)},
        },
    }
    _write_json(output_dir / "job.json", job)
    print(f"预览对比图已生成：{preview_paths['contact_sheet']}")
    print(f"干净色块版：{clean.total_beads}颗，{clean.used_color_count}色，平均 Oklab 误差 {clean.mean_distance:.2f}")
    print(f"轻度抖动版：{dither.total_beads}颗，{dither.used_color_count}色，平均 Oklab 误差 {dither.mean_distance:.2f}")
    geometry = _geometry_metrics(clean)
    if geometry is None:
        print("实际图案：无（所有格子均为透明）")
    else:
        board = geometry["recommended_board"]
        board_text = f"{board[0]}×{board[1]}" if board is not None else "自定义/多块底板"
        print(
            f"实际图案：{geometry['occupied_width']}×{geometry['occupied_height']}颗；"
            f"预计成品尺寸：{geometry['physical_width_mm'] / 10:.2f}×{geometry['physical_height_mm'] / 10:.2f}厘米；"
            f"建议底板：{board_text}"
        )
    print("请选择版本，然后运行 finalize，并使用 --variant clean 或 --variant dither。")
    return 0


def _confirm_large(result: PatternResult, estimated_pages: int, yes_large: bool) -> None:
    triggers = []
    if result.total_beads > LARGE_BEAD_THRESHOLD:
        triggers.append(f"总豆数 {result.total_beads:,}颗超过 {LARGE_BEAD_THRESHOLD:,}颗")
    if estimated_pages > LARGE_PAGE_THRESHOLD:
        triggers.append(f"预计 PDF 页数 {estimated_pages}页超过 {LARGE_PAGE_THRESHOLD}页")
    if not triggers:
        return
    message = "大图警告：" + "；".join(triggers) + "。"
    if yes_large:
        print(message + " 已通过 --yes-large 明确确认，继续生成。", file=sys.stderr)
        return
    if sys.stdin.isatty():
        answer = input(message + " 是否继续？请输入 YES：").strip()
        if answer == "YES":
            return
    raise ValueError(message + " 获得明确批准后，请添加 --yes-large 重新运行。")


def finalize(args: argparse.Namespace) -> int:
    job_dir = Path(args.job).resolve()
    job_path = job_dir / "job.json"
    if not job_path.exists():
        raise ValueError(f"缺少 job.json：{job_path}")
    job = json.loads(job_path.read_text(encoding="utf-8"))
    if args.variant not in {"clean", "dither"}:
        raise ValueError("variant 必须是 clean 或 dither")
    variant_path = Path(job["variants"][args.variant])
    if not variant_path.is_absolute():
        variant_path = job_dir / variant_path
    if not variant_path.exists():
        raise ValueError(f"缺少已保存的图案版本：{variant_path}")
    result = PatternResult.from_dict(json.loads(variant_path.read_text(encoding="utf-8")))
    palette = Palette.load(PALETTE_PATH)
    expected_hash = job.get("palette_sha256")
    actual_hash = palette.metadata.get("integrity", {}).get("normalized_colors_sha256")
    if expected_hash and expected_hash != actual_hash:
        raise ValueError("预览后色库完整性发生变化，请重新生成预览")

    geometry = analyze_pattern(result)
    estimated_pages = estimate_total_pdf_pages(result)
    _confirm_large(result, estimated_pages, args.yes_large)
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"输出目录必须为空，以确保最终只交付一张 PNG 和一份 PDF：{output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    image_name = job.get("input_name") or Path(job.get("input_original", "图片")).stem
    title = args.title or f"MARD拼豆施工图 - {image_name}"
    paths = render_all_outputs(result, palette, output_dir, title=title, reserve_percent=args.reserve_percent)
    board = (
        f"{geometry.recommended_board[0]}×{geometry.recommended_board[1]}"
        if geometry.recommended_board is not None
        else "自定义/多块底板"
    )
    print(f"最终文件已生成：{output_dir}")
    print(f"图案尺寸：{geometry.width}×{geometry.height}颗")
    print(f"预计成品尺寸：{geometry.width_cm:.2f}×{geometry.height_cm:.2f}厘米（每颗间距{BEAD_PITCH_MM:g}毫米）")
    print(f"建议底板：{board}")
    print(f"总豆数：{result.total_beads}颗；使用色数：{result.used_color_count}色；PDF页数：{estimated_pages}页")
    print(f"PNG文件：{paths['pattern_png']}")
    print(f"PDF文件：{paths['pattern_pdf']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将图片转换为 MARD 291 色拼豆施工图")
    sub = parser.add_subparsers(dest="command", required=True)

    preview_parser = sub.add_parser("preview", help="生成干净色块版和轻度抖动版预览")
    preview_parser.add_argument("--input", required=True, help="输入图片路径")
    preview_parser.add_argument("--width", required=True, type=int, help="目标宽度（颗）")
    preview_parser.add_argument("--height", required=True, type=int, help="目标高度（颗）")
    preview_parser.add_argument("--fit", choices=["crop", "pad"], default="crop", help="裁剪铺满或完整留边")
    preview_parser.add_argument("--background", choices=["keep", "transparent"], default="keep", help="保留背景或使用透明背景")
    preview_parser.add_argument("--palette", default="all", help="色库模式，当前使用 all")
    preview_parser.add_argument("--inventory", help="库存色号文件")
    preview_parser.add_argument("--dither-strength", type=float, default=0.5, help="抖动强度，范围 0 到 1")
    preview_parser.add_argument("--output-dir", required=True, help="预览任务目录")
    preview_parser.set_defaults(func=preview)

    finalize_parser = sub.add_parser("finalize", help="导出所选预览版本的最终图纸")
    finalize_parser.add_argument("--job", required=True, help="预览任务目录")
    finalize_parser.add_argument("--variant", required=True, choices=["clean", "dither"], help="选择干净色块版或轻度抖动版")
    finalize_parser.add_argument("--reserve-percent", type=float, default=10, help="备料百分比")
    finalize_parser.add_argument("--title", help="自定义图纸标题")
    finalize_parser.add_argument("--yes-large", action="store_true", help="明确确认生成超过豆数或页数阈值的大图")
    finalize_parser.add_argument("--output-dir", required=True, help="最终输出目录")
    finalize_parser.set_defaults(func=finalize)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if getattr(args, "dither_strength", 0.5) < 0 or getattr(args, "dither_strength", 0.5) > 1:
            raise ValueError("dither-strength 必须在 0 到 1 之间")
        if getattr(args, "reserve_percent", 0) < 0:
            raise ValueError("reserve-percent 不能为负数")
        return args.func(args)
    except (ValueError, RuntimeError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
