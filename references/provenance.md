# MARD 291 色库来源

## 固定上游版本

规范色库由 `source-data/` 中的本地快照可重复构建：

| 来源 | 提交 | 仓库路径 | 快照 SHA-256 |
|---|---|---|---|
| Zippland/perler-beads | `2efee730f73dd4eb472ebde443a022d11f98bc21` | `src/app/colorSystemMapping.json` | `eb24997c62073e68f5c821a86f2f4ec75cc19825bec90b812f4dca4a61c75047` |
| maxcleme/beadcolors | `29229889daab404fb30531d4bb785fd73f7f58e3` | `raw/mard.csv` | `623d229ace064a7ace700489ed98fa35e512300a574d9df2d94c7d01d5114dfa` |

两个快照都包含完整 MARD 色集，其中 290 个色号的记录一致。`R11` 在 perler-beads 中为 `#FFEBFB`，在 beadcolors 中为 `#FFEBFA`。

## 规范决定与已审计例外

- 规范 `R11`：`#FFEBFA`
- 旧版 `R11`：`#FFEBFB`
- 规范 `Q04`：`#FFEBFA`

因此色库包含 291 个唯一色号和 290 个唯一 HEX。`Q04`/`R11` 的重复关系记录在 `known_hex_collisions` 中，不是生成错误。完整色库对 `#FFEBFA` 做精确匹配时按规范顺序选择 `Q04`；库存限制为 `R11` 时仍可选择 `R11`。

## 系列数量

```text
A=26, B=32, C=29, D=26, E=24, F=25, G=21, H=23,
M=15, P=23, Q=5, R=28, T=1, Y=5, ZG=8
```

所有系列编号连续，规范色号使用 `A01` 等补零形式，`A1` 等紧凑形式作为别名。

## 完整性

规范化颜色数组 SHA-256：

```text
6dd3ee913a4c8e9e20819730be2f1185d7ebeb8f455fb51392572bd96bc2a15e
```

`validate_palette.py` 会检查上游快照哈希、色号连续性、JSON/CSV 一致性、RGB/HEX 一致性、唯一声明的 HEX 重复、`R11` 修正元数据和规范化哈希。只有在有意从固定快照重新构建资源时才使用 `--build`。

这里的“准确”是指 291 条规范记录、来源快照、RGB/HEX、修正元数据和算法引用达到机器可验证的一致，不代表不同显示器、光线、相机或塑料生产批次下的肉眼颜色绝对一致。
