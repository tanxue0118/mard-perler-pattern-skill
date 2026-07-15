# MARD 拼豆施工图 Skill

一个面向 Codex 的用户级 Skill：把照片、插画、像素画或透明 PNG 转换为使用 **MARD 291 色**的拼豆预览，并生成可以直接照着制作的中文施工图。

最终交付固定为：

- 一张带色号、坐标、尺寸、底板建议和用量图例的中文 PNG；
- 一份可打印的中文 PDF；
- 不在最终任务目录中额外生成 CSV、JSON 或其他辅助文件。

## 主要功能

- 使用经过审计并固定哈希的 MARD 291 色规范色库；
- 使用 Oklab 色差匹配最接近的 MARD 色号；
- 提供“干净色块版”和“轻度抖动版”两种预览；
- 支持保留背景、透明背景、裁剪铺满和完整留边；
- 支持库存受限色库，并接受 `A1`、`A01`、`zg8` 等色号写法；
- 自动处理 EXIF 图片方向以及常见 ICC 色彩配置；
- 透明格不计入豆数，透明边缘采用 Alpha 感知采样；
- 按每颗间距 2.6 毫米计算预计成品尺寸；
- 根据实际非透明图案推荐 52×52、78×78 或 104×104 底板；
- 大图自动生成带全局坐标、分页位置和相邻页提示的施工分图；
- PNG、PDF、命令行提示、警告和报错均使用简体中文。

## 仓库结构

```text
mard-perler-pattern/
├── SKILL.md                     # Codex Skill 主说明
├── README.md                    # GitHub 中文说明
├── agents/openai.yaml           # Skill 显示与调用配置
├── assets/                      # MARD 291 色 JSON/CSV
├── references/                  # 来源、审计和输出规范
├── scripts/                     # 图片处理、色彩匹配、渲染和 CLI
└── tests/                       # 自动测试
```

## 安装到 Codex

### 方法一：手动复制（推荐）

1. 下载或解压本仓库。
2. 确认文件夹名称为 `mard-perler-pattern`。
3. 把整个文件夹复制到：

```text
%USERPROFILE%\.codex\skills\mard-perler-pattern
```

在 Windows PowerShell 中可以使用：

```powershell
$source = "D:\拼豆\mard-perler-pattern"
$target = "$env:USERPROFILE\.codex\skills\mard-perler-pattern"
Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
```

安装后的关键文件应位于：

```text
%USERPROFILE%\.codex\skills\mard-perler-pattern\SKILL.md
```

复制完成后，如果当前 Codex 任务尚未识别该 Skill，可以新建一个任务或重新打开 Codex。

### 方法二：从 GitHub 克隆

把下面的仓库地址替换为你实际创建的 GitHub 地址：

```powershell
git clone "https://github.com/你的用户名/mard-perler-pattern.git" `
  "$env:USERPROFILE\.codex\skills\mard-perler-pattern"
```

### 方法三：ZIP 安装

1. 下载 GitHub 仓库 ZIP；
2. 解压后确认不存在重复目录层级；
3. 最终路径必须是：

```text
%USERPROFILE%\.codex\skills\mard-perler-pattern\SKILL.md
```

以下路径是错误示例：

```text
%USERPROFILE%\.codex\skills\mard-perler-pattern\mard-perler-pattern\SKILL.md
```

## 运行依赖

建议使用 Python 3.10 或更高版本，并安装：

```powershell
python -m pip install Pillow numpy reportlab pypdf
```

其中 `pypdf` 主要用于测试和 PDF 文本验证。进行 PDF 视觉验收时，建议另外安装 Poppler，以使用 `pdfinfo` 和 `pdftoppm`。

## 在 Codex 中使用

安装后，可以直接向 Codex 提出类似请求：

```text
使用 mard-perler-pattern，把这张图片制作成干净色块版拼豆施工图，只保留主体。
```

处理真实图片时，Skill 会根据缺失信息确认或建议：

1. 实际图案宽×高颗数；
2. 保留背景、抠主体或透明区域；
3. 裁剪铺满或完整留边；
4. 使用完整 291 色或库存限制；
5. 选择干净色块版或轻度抖动版。

未经用户选择，不会直接跳过双预览完成最终导出。

## 命令行使用

### 生成双预览

在 Skill 根目录运行：

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

常用参数：

- `--fit crop`：按比例裁剪并铺满；
- `--fit pad`：完整保留图片并补透明留边；
- `--background keep`：保留背景；
- `--background transparent`：保留输入图片的透明区域；
- `--inventory inventory.txt`：只使用库存文件列出的色号。

库存文件示例：

```text
A1,A02,B03,C10,ZG8
```

### 最终导出干净色块版

```powershell
python scripts/pattern_cli.py finalize `
  --job "work/job-name" `
  --variant clean `
  --output-dir "outputs/job-name"
```

### 最终导出轻度抖动版

```powershell
python scripts/pattern_cli.py finalize `
  --job "work/job-name" `
  --variant dither `
  --output-dir "outputs/job-name"
```

最终目录必须为空，并且只会生成：

```text
clean-pattern.png
clean-pattern.pdf
```

或：

```text
dither-pattern.png
dither-pattern.pdf
```

## 图案尺寸、成品尺寸和底板

本 Skill 使用 2.6 毫米豆距：

| 实际图案 | 预计方形尺寸 | 建议用途 |
|---|---:|---|
| 10×10 | 2.6×2.6 厘米 | 小配饰 |
| 15×15 | 3.9×3.9 厘米 | 手机挂饰或冰箱贴 |
| 20×20 | 5.2×5.2 厘米 | 冰箱贴或钥匙扣 |
| 25×25 | 6.5×6.5 厘米 | 较大冰箱贴、钥匙扣或小挂件 |
| 超过 25 格 | 按实际宽高计算 | 精细或较大型图案 |

`52×52`、`78×78`、`104×104` 是常见底板容量，不是强制图案尺寸。程序会根据非透明图案的实际宽高推荐能容纳图案的最小底板。

外围透明留白不计入实际图案尺寸，图案内部的透明孔洞会继续保留为空格。

## 最终施工图内容

PNG 会显示：

- MARD 规范色号；
- 全局行列坐标；
- 每 5 格和每 10 格的分隔线；
- 图案宽高；
- 预计成品尺寸；
- 建议底板；
- 总豆数和使用色数；
- 用途建议；
- 每种颜色的准确用量，例如 `A01（18颗）`。

PDF 首页包含完整图纸。大图会继续生成 8 毫米可读施工分图，每张分图包含全局坐标、分页位置、相邻页面方向和中文页码。

超过 40,000 颗豆或预计超过 50 页 PDF 时，程序会先给出警告，只有明确添加 `--yes-large` 才会继续生成。

## MARD 291 色库

规范色库位于：

```text
assets/mard-291-colors.json
assets/mard-291-colors.csv
```

规范化色库 SHA-256：

```text
6dd3ee913a4c8e9e20819730be2f1185d7ebeb8f455fb51392572bd96bc2a15e
```

说明：

- 规范色号总数为 291；
- `R11` 的规范值为 `#FFEBFA`；
- 旧值 `#FFEBFB` 保存在 `legacy_hex`；
- `Q04` 与 `R11` 同为 `#FFEBFA`，这是已记录的色号关系，不是数据错误；
- 数据来源和审计方法见 `references/provenance.md`。

这里的准确性指 291 个规范色号在结构、HEX、RGB、来源和算法引用上机器可验证一致，不代表不同屏幕、拍摄光线或塑料生产批次下的实体颜色肉眼绝对一致。

## 验证 Skill

在仓库根目录执行：

```powershell
python -m unittest discover -s tests -v
python scripts/validate_palette.py --root .
```

如果本机存在 Codex 的 `skill-creator` 校验脚本，还可以运行：

```powershell
python -X utf8 "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" .
```

当前版本验收结果：

- 29 项自动测试通过；
- 291 色完整性验证通过；
- 单页和多页 PDF 中文重渲染检查通过；
- 最终目录只包含一张 PNG 和一份 PDF。
