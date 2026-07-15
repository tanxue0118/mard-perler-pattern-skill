from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from palette import compute_colors_sha256, hex_to_rgb

SERIES_ORDER = ["A", "B", "C", "D", "E", "F", "G", "H", "M", "P", "Q", "R", "T", "Y", "ZG"]
EXPECTED_COUNTS = {"A":26,"B":32,"C":29,"D":26,"E":24,"F":25,"G":21,"H":23,"M":15,"P":23,"Q":5,"R":28,"T":1,"Y":5,"ZG":8}
PERLER_COMMIT = "2efee730f73dd4eb472ebde443a022d11f98bc21"
BEADCOLORS_COMMIT = "29229889daab404fb30531d4bb785fd73f7f58e3"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact_code(code: str) -> str:
    match = re.fullmatch(r"([A-Z]+)(\d+)", code.upper())
    if not match:
        raise ValueError(f"无效色号： {code}")
    return f"{match.group(1)}{int(match.group(2))}"


def build_assets(perler_path: Path, beadcolors_path: Path, json_path: Path, csv_path: Path) -> dict:
    perler = json.loads(perler_path.read_text(encoding="utf-8-sig"))
    upstream = {}
    with beadcolors_path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            code, _, r, g, b, source = row[:6]
            upstream[compact_code(code)] = {"hex": f"#{int(r):02X}{int(g):02X}{int(b):02X}", "source": source}

    colors = []
    for repo_hex, mapping in perler.items():
        code = str(mapping["MARD"]).upper()
        match = re.fullmatch(r"([A-Z]+)(\d+)", code)
        if not match:
            raise ValueError(f"上游仓库中存在无效 MARD 色号： {code}")
        series, number = match.group(1), int(match.group(2))
        raw_code = f"{series}{number}"
        if raw_code not in upstream:
            raise ValueError(f"缺少上游颜色： {raw_code}")
        canonical_hex = upstream[raw_code]["hex"]
        rgb = hex_to_rgb(canonical_hex)
        legacy = [repo_hex.upper()] if repo_hex.upper() != canonical_hex else []
        aliases = [raw_code] if raw_code != code else []
        colors.append({
            "code": code, "aliases": aliases, "series": series, "index": number,
            "hex": canonical_hex, "rgb": {"r": rgb[0], "g": rgb[1], "b": rgb[2]},
            "legacy_hex": legacy, "source": upstream[raw_code]["source"],
            "note": "Canonicalized from beadcolors; perler-beads uses #FFEBFB." if code == "R11" else "",
        })
    rank = {name: i for i, name in enumerate(SERIES_ORDER)}
    colors.sort(key=lambda c: (rank[c["series"]], c["index"]))
    data = {
        "schema_version": "1.0",
        "palette_id": "mard-291",
        "color_count": len(colors),
        "sources": [
            {"name": "Zippland/perler-beads", "commit": PERLER_COMMIT, "path": "src/app/colorSystemMapping.json", "sha256": file_sha256(perler_path)},
            {"name": "maxcleme/beadcolors", "commit": BEADCOLORS_COMMIT, "path": "raw/mard.csv", "sha256": file_sha256(beadcolors_path)},
        ],
        "corrections": [{"code": "R11", "canonical_hex": "#FFEBFA", "legacy_hex": "#FFEBFB", "reason": "Pinned beadcolors source and confirmed canonical decision."}],
        "known_hex_collisions": [{"hex": "#FFEBFA", "codes": ["Q04", "R11"], "reason": "The pinned beadcolors source assigns the same RGB value to both codes."}],
        "integrity": {"normalized_colors_sha256": compute_colors_sha256(colors)},
        "colors": colors,
    }
    validate_data(data)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["code","aliases","series","index","hex","r","g","b","legacy_hex","source","note"])
        writer.writeheader()
        for color in colors:
            writer.writerow({
                "code": color["code"], "aliases": "|".join(color["aliases"]), "series": color["series"], "index": color["index"],
                "hex": color["hex"], "r": color["rgb"]["r"], "g": color["rgb"]["g"], "b": color["rgb"]["b"],
                "legacy_hex": "|".join(color["legacy_hex"]), "source": color["source"], "note": color["note"],
            })
    return data


def validate_data(data: dict) -> None:
    colors = data["colors"]
    if len(colors) != 291 or data.get("color_count") != 291:
        raise ValueError(f"色库应为 291 色，实际为 {len(colors)}")
    if Counter(c["series"] for c in colors) != Counter(EXPECTED_COUNTS):
        raise ValueError("系列数量与 MARD 291 规范不一致")
    if len({c["code"] for c in colors}) != 291:
        raise ValueError("存在重复色号")
    by_hex = {}
    for color in colors:
        by_hex.setdefault(color["hex"], []).append(color["code"])
    collisions = {hex_value: codes for hex_value, codes in by_hex.items() if len(codes) > 1}
    if collisions != {"#FFEBFA": ["Q04", "R11"]}:
        raise ValueError(f"存在未声明的 HEX 重复： {collisions}")
    for series, count in EXPECTED_COUNTS.items():
        found = sorted(c["index"] for c in colors if c["series"] == series)
        if found != list(range(1, count + 1)):
            raise ValueError(f"系列编号不连续：{series}: {found}")
    r11 = next(c for c in colors if c["code"] == "R11")
    if r11["hex"] != "#FFEBFA" or "#FFEBFB" not in r11["legacy_hex"]:
        raise ValueError("缺少 R11 规范修正记录")
    actual_hash = compute_colors_sha256(colors)
    expected_hash = data.get("integrity", {}).get("normalized_colors_sha256")
    if expected_hash != actual_hash:
        raise ValueError("完整性哈希不匹配")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or validate the MARD 291 palette assets.")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root
    json_path = root / "assets" / "mard-291-colors.json"
    csv_path = root / "assets" / "mard-291-colors.csv"
    if args.build:
        build_assets(root / "references" / "source-data" / "perler-beads-colorSystemMapping.json", root / "references" / "source-data" / "beadcolors-mard.csv", json_path, csv_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    validate_data(data)
    print(f"校验通过：{len(data['colors'])} 色；sha256={data['integrity']['normalized_colors_sha256']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())




