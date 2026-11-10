# RPT 分组检查 · RTLWire 0.4.0

每个检查层次独立提供一个 `.rpt` 文件，并由用户输入三项组名关键词：钳 1、钳 0、不钳位。三组名称没有固定拼写，不依赖它们在文件中的顺序。用户已明确：不钳位组仍要检查掉电期间全 X。

## 文件与关键词

例如某层次的文件为：

```text
BLOCK_HIGH_LEVEL {
    ready_n, response[7:0]
}
BLOCK_LOW_LEVEL { valid，error }
BLOCK_BYPASS { debug_out, trace_out }
```

对应输入：

| 类型 | 用户填写的关键词 |
|---|---|
| 钳 1 | `HIGH_LEVEL` |
| 钳 0 | `LOW_LEVEL` |
| 不钳位 | `BYPASS` |

匹配的是**组名中包含关键词**，区分大小写，关键词按普通文本处理，不是正则表达式。第二个层次可以使用另一个 RPT 和完全不同的关键词。一种关键词可以匹配多个分组，这些组的条目共同参与该类检查。每个组必须且只能匹配一种类型；未匹配或同时匹配多种类型会在导入预览或运行时明确报错。

支持英文逗号、中文逗号、空格及换行分隔，支持 `#`、`//` 行注释和 `/* ... */` 块注释；允许空组。使用 ASCII 或 UTF-8（可带 BOM），文件扩展名为 `.rpt`。分组不能嵌套；不执行文件中的任何命令。当前限制为 16 MiB、10000 个分组、250000 个信号条目。

## 信号名与分组核对

条目支持本层短名、完整输出口路径、位选和片选，例如 `dout`、`tb.chip.u_a.dout`、`dout[3]`、`dout[7:4]`。短名只匹配当前所选层次的直接输出口；完整路径必须对应同一层次的已记录输出口，不按叶子名跨层次猜测，也不把内部 net、input 或子模块端口当成本层 output。

整根总线归到钳 1 时，每一位都应为 1。例如 4 位信号的期望是 `1111` / `4'hF`，不是 `0001`。支持同一个总线的不同位分组：

```text
BLOCK_HIGH_LEVEL { mixed_bus[3] }
BLOCK_LOW_LEVEL  { mixed_bus[2] }
BLOCK_BYPASS     { mixed_bus[1:0] }
```

该总线显示为“混合”，期望掩码为 `10--`，其中 `-` 表示明确不钳位。idle 相等、期望值、稳定性和恢复钳位只比较第 3、2 位；掉电全 X 仍比较所有四位。按 FSDB 声明的位号映射，支持 `[3:0]` 和 `[0:3]` 声明方向。

| 核对问题 | 处理 |
|---|---|
| 同一个输出位重复出现，即使在同一类中重复 | `RPT_DUPLICATE_ASSIGNMENT`，对应位不使用后出现的规则覆盖，相关检查未知。 |
| FSDB 中有 output 位未被 RPT 覆盖 | `RPT_OUTPUT_UNASSIGNED`，不默认为钳 0。 |
| RPT 名称不能匹配本层已记录 output | `RPT_SIGNAL_NOT_OUTPUT`，层次整体结论未知；保留已能验证的端口结果。 |
| 位索引越界 | `RPT_BIT_OUT_OF_RANGE`，明确指出条目和端口。 |
| 某些位没有明确分组 | 期望掩码用 `?` 表示，输出标为“未完整分组”。 |

确定的波形违例仍保留 FAIL；配置或覆盖不足不会变成通过。RPT 是用户提供的检查规则，端口存在性和方向仍取自 FSDB，不通过 RPT 虚构设计信息。没有 dump 的端口若出现在 RPT 中，会成为未匹配条目；同时没有出现在 FSDB 和 RPT 中的端口，仍无法据此发现。

## 三类检查

设 A=iso_en↑，B=power_down↓，C=power_down↑，D=iso_en↓。沿用同一时间戳最终值判定和前后各 5 ns 的窗口。

| 检查 | 钳 1 | 钳 0 | 不钳位 |
|---|---|---|---|
| A 之前的 idle 与 A 时刻最终值一致 | 检查 | 检查 | 不适用 |
| `[A,B)` 期望值 | 全 1 | 全 0 | 不适用 |
| `[A,B)` 稳定性 | 检查 | 检查 | 不适用，允许变化 |
| `[B,C)` 掉电值 | 全 X | 全 X | **全 X** |
| `[C,D)` 供电恢复后的隔离值 | 全 1 | 全 0 | 不适用，允许变化 |

不适用项目在 GUI 显示“不适用”，JSON/CSV 使用 `SKIP`，不会被伪装成 PASS。由于仍要求 idle 与隔离后值相同，钳 1 组通过时 idle 也必须是全 1，钳 0 组通过时 idle 必须是全 0。混合总线只在需要钳位的位上进行这项比较。

## GUI 与配置

在主界面填写每层的 RPT 路径，点击“RPT 配置”打开关键词输入和预览窗口。预览列出实际组名、识别类型和信号条目数；应用后可以保存完整配置。不同层次的关键词互不影响。

结果表新增“分组”“期望钳位”列；原来的“恢复 0”改为“恢复钳位”。选择一个输出口后，波形阶段会显示钳 1、钳 0、不钳位或按位混合，错误详情给出实际值、期望值和时间。“问题与证据”记录 RPT 路径、关键词、分组统计、未覆盖和重复等问题。

```json
{
  "kind": "power_wave",
  "grouping_mode": "rpt",
  "fsdb_path": "/data/run/waves.fsdb",
  "domains": [
    {
      "scope": "tb.chip.u_a",
      "iso_en": "iso_en",
      "power_down": "power_down",
      "rpt_path": "/data/checks/domain_a.rpt",
      "group_keywords": {
        "clamp_one": "HIGH_LEVEL",
        "clamp_zero": "LOW_LEVEL",
        "no_clamp": "BYPASS"
      }
    },
    {
      "scope": "tb.chip.u_wrap.u_b",
      "iso_en": "iso_en",
      "power_down": "power_down",
      "rpt_path": "/data/checks/domain_b.rpt",
      "group_keywords": {
        "clamp_one": "FORCE_HIGH",
        "clamp_zero": "FORCE_LOW",
        "no_clamp": "TRANSPARENT"
      }
    }
  ],
  "edge_policy": "settled",
  "padding_ns": 5
}
```

命令行：

```bash
python3 -m rtlwire.wave_cli --query my_groups.json --out work/group_check
```

每次运行保存原始 RPT 快照 `rpt_inputs/domain_N.rpt`、解析结果 `rpt_groups.json` 和输入前后 SHA-256。重开结果依据保存的报告和波形，不要求原始 RPT 仍在原位置；再次运行时会重新读取当前 RPT。

原 0.3.0 已保存结果仍可打开，保持原判定并标注为旧版全 0 规则。CLI 支持 `grouping_mode: "legacy_zero"`，未包含任何 RPT 字段的旧 CLI 查询沿用全 0 兼容模式；GUI 发起新检查统一要求每层 RPT 和关键词。

## 随包演示与实际验收

```bash
./rtlwire-studio --config examples/power_groups_pass.json
./rtlwire-studio --config examples/power_groups_faults.json
./rtlwire-studio --result validation/wave_groups_faults
```

演示 RPT 位于 `examples/rpt/`，真实 FSDB 位于 `examples/fsdb/`。两层使用不同关键词，包含钳 1、钳 0、不钳位及混合位总线。数据由独立 Writer SDK 测试程序生成，产品不调用 Writer 或 RTL 编译器。

2026-11-11 在既有 CentOS 7 / Python 3.6.8 / Tk 8.5 / Verdi O-2018.09-SP2 VM 验证：

- 62 个单元测试通过，其中 23 个新增测试覆盖关键词解析、中文逗号、错误格式、三类规则、混合位、重复、遗漏、越界和旧报告兼容。
- 6 项后端验证通过：正常 14 条全 PASS；故障 8 PASS / 6 FAIL；RPT 对账异常 12 PASS / 2 UNKNOWN；歧义关键词与缺文件明确报错；旧版全 0 正常样例仍为 12 PASS。
- 9 项真实 Tk 验收通过：两层独立关键词输入、歧义拒绝、保存配置、真实 FSDB 检查、分组波形和导出、错误定位、分组缺陷、旧结果查看及架构工作区切换。

具体日志、截图、输入快照和机器可读结果在 0.4.0 验收包的 `validation/wave_040/` 中；安装包与普通账号的验证另见同目录 `package_acceptance.json`。

在新目录中复现当前验收：

```bash
python3 tests/make_wave_group_fixtures.py --out validation/wave_040/fixtures
python3 -m unittest discover -s tests -p 'test_*.py' -v
PYTHONPATH=. python3 tests/validate_wave_group_backend.py
# 在 Linux 图形桌面或独立 Xvfb 会话中运行；截图需要 xwd 和 Pillow。
PYTHONPATH=. python3 tests/validate_wave_group_gui.py
```

旧的 `validate_wave_gui.py` 保留为 0.3.0 输入界面的历史验收脚本；当前分组界面使用上述 `validate_wave_group_gui.py`。
