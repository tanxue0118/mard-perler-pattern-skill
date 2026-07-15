---
name: mard-perler-pattern
description: Use when converting photos, illustrations, pixel art, or transparent PNGs into Chinese-language MARD 291-color perler-bead previews, color-coded construction charts, board recommendations, bead counts, or printable pattern PDFs.
---

# MARD 拼豆施工图

使用经过审计的 `assets/mard-291-colors.json` 色库，把图片转换为可直接手工制作的 MARD 迷你拼豆施工图。所有面向用户的预览、最终 PNG、PDF、命令行提示、警告和报错必须使用简体中文；命令、参数、JSON 字段和文件名保持英文兼容形式。

## 必须遵循的流程

1. 处理真实图片前，如用户尚未说明，确认：
   - 用途或大致成品尺寸；
   - 根据画面细节和比例建议的实际图案宽×高颗数；
   - 保留背景、抠主体或保留透明区域；
   - 裁剪铺满或完整留边，禁止拉伸变形；
   - 使用完整 291 色或库存文件。
2. 运行 `preview`，展示原图采样、干净色块版、轻度抖动版及两版指标。
3. 报告非透明图案边界、按每颗间距 `2.6 mm` 计算的预计尺寸和建议底板。
4. 用户明确选择 `clean` 或 `dither` 后才能运行 `finalize`。
5. 最终只交付一张 PNG 施工图和一份 PDF。
6. 超过 40,000 颗或预计 PDF 超过 50 页时，必须先警告并等待明确同意，再使用 `--yes-large`。

## 底板与实际图案尺寸

`52×52`、`78×78`、`104×104` 是常见方形拼豆板容量，不是强制图案尺寸，图案不需要铺满底板。

- 根据非透明实际图案宽高，选择能容纳图案的最小常见底板。
- 任一边超过 104 颗时，说明需要自定义或多块底板。
- 外围透明留白不计入实际图案尺寸；内部透明孔洞保留为空格。

## 尺寸与用途建议

本 Skill 按每颗间距 `2.6 mm` 计算宽高：

| 实际图案 | 约方形尺寸 | 建议用途 |
|---|---:|---|
| `10×10` | `2.6×2.6 cm` | 小配饰 |
| `15×15` | `3.9×3.9 cm` | 手机挂饰或冰箱贴 |
| `20×20` | `5.2×5.2 cm` | 冰箱贴或钥匙扣 |
| `25×25` | `6.5×6.5 cm` | 较大冰箱贴、钥匙扣或小挂件 |
| 超过 25 格 | 按实际宽高计算 | 精细或较大型图案 |

这些是建议而非硬限制。人脸、文字、轮廓和细节通常需要更多格数。非方形主体应保持原图比例，分别建议宽度和高度。

## 命令

预览：

```powershell
python scripts/pattern_cli.py preview `
  --input "photo.png" `
  --width 20 `
  --height 25 `
  --fit pad `
  --background transparent `
  --palette all `
  --output-dir "work/job-name"
```

库存文件可以使用逗号、分号或空白分隔，并接受 `A1`、`A01`、`zg8` 等别名：

```powershell
python scripts/pattern_cli.py preview `
  --input "photo.png" `
  --width 15 `
  --height 15 `
  --inventory "inventory.txt" `
  --output-dir "work/job-name"
```

用户选择版本后：

```powershell
python scripts/pattern_cli.py finalize `
  --job "work/job-name" `
  --variant clean `
  --output-dir "outputs/job-name"
```

最终输出目录必须是新目录或空目录。

## 图像和颜色处理保证

- 应用 EXIF 方向，并尽力把嵌入 ICC 配置转换为 sRGB。
- 使用 Alpha 感知面积采样；低于阈值的格子保持透明且不计豆数。
- 使用 Oklab 欧氏距离匹配；距离相同时按规范色库顺序决定，确保结果可重复。
- 同时生成直接最近色的 `clean` 版和 50% 蛇形 Floyd–Steinberg 的 `dither` 版。
- 每个非透明输出格只能使用规范 MARD 色号；库存别名统一规范化。
- 相同输入和参数重复运行必须得到相同结果。

## 中文字体要求

图片和 PDF 必须使用支持简体中文的系统字体，禁止回退到不支持中文的位图默认字体。字体顺序为：

1. 环境变量 `MARD_CJK_FONT`；
2. Windows 微软雅黑、黑体、宋体；
3. macOS 苹方、冬青黑体；
4. Linux Noto Sans CJK、思源黑体、文泉驿。

找不到字体时停止生成，并用中文提示安装字体或设置 `MARD_CJK_FONT`。不得把 Windows 自带字体复制到 Skill、ZIP 或 GitHub 仓库。

## 最终输出

详细排版见 `references/output-spec.md`。

- `<variant>-pattern.png`：完整彩色施工图，含色号、四边坐标、图案尺寸、预计成品尺寸、建议底板、总豆数、使用色数、用途建议和准确数量图例。
- `<variant>-pattern.pdf`：单一 PDF，第一页为完整图纸；密集图案在同一 PDF 中附加 8 毫米可读施工分图。

8 毫米只表示打印阅读格大小，不代表拼豆实体尺寸。实体尺寸始终按每颗间距 `2.6 mm` 计算。

## 色库注意事项

色库有 291 个唯一色号和 290 个唯一 HEX。`Q04` 与规范 `R11` 都是 `#FFEBFA`，这是已记录关系。完整色库精确匹配该 HEX 时按规范顺序选择 `Q04`；库存仅保留 `R11` 时仍可生成 `R11`。`R11` 的旧值 `#FFEBFB` 保存在 `legacy_hex`。修改色库前必须阅读 `references/provenance.md`。

## 验证

修改 Skill 后运行：

```powershell
python -m unittest discover -s tests -v
python scripts/validate_palette.py --root .
python <skill-creator>/scripts/quick_validate.py .
```

PDF 改动还必须用 `pdfinfo` 检查页面与元数据、用 `pdftoppm` 重渲染全部页面，并目视确认中文无方框、乱码、重叠或裁切。
