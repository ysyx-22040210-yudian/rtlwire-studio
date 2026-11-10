# FSDB 隔离与掉电自动检查

**0.4.0 更新：** 新的 GUI 检查按每层 RPT 和用户关键词分为钳 1、钳 0、不钳位。三类分组、位选、对账、配置和最新演示见 [rpt_groups_040.md](rpt_groups_040.md)。下文的全 0 示例描述 0.3.0 原有规则及 `legacy_zero` 兼容模式；通用控制边沿、时间戳、5 ns 窗口、FSDB 覆盖范围和 SDK 部署规则仍适用。

本分支在现有 RTLWire Tk GUI 中新增独立工作区。连接检查继续只读 elab；波形检查只读 FSDB。两个工作区可切换并保留各自的输入和结果。工具没有 SSH 设置、服务器连接或远程登录流程。

## 用户输入

GUI 提供一个 FSDB 文件输入和两个层次配置行，每行分别填写层次、iso_en、power_down。完整配置示例：

```json
{
  "kind": "power_wave",
  "fsdb_path": "/data/run/power.fsdb",
  "domains": [
    {"scope": "tb.chip.u_a", "iso_en": "iso_en", "power_down": "power_down"},
    {"scope": "tb.chip.u_wrap.u_b", "iso_en": "tb.pmu.iso_b", "power_down": "tb.pmu.pd_b"}
  ],
  "padding_ns": 5,
  "edge_policy": "settled"
}
```

不包含点号的控制名按本层短名解释；包含点号的名字按完整路径精确匹配。`u_child.iso_en` 若要表示子层信号，应填完整的 `tb.chip.u_a.u_child.iso_en`。输出口由 FSDB 层次树自动枚举，无需用户逐个填写。

GUI 使用两个层次；CLI 支持配置 1–64 个不重复层次。层次之间可以嵌套：每个层次仅检查它自身的直接 output 端口，两组输出清单独立；同一物理信号若出现在两个层次的接口上，分别以相应的完整端口名报告。

## 已确认的判定语义

用户已选择“同一仿真时刻内所有更新完成后的最终值”。先将同一信号、同一整数时间戳的 FSDB 更新合并为最后一个值，再检测控制边沿和输出变化。FSDB 保留的中间更新另外列为 delta 提示，不导致检查失败；FSDB 没有保存的中间更新无法恢复。

定义四个时间：A = iso_en 0→1，B = power_down 1→0，C = power_down 0→1，D = iso_en 1→0。

```text
                  A            B                   C             D
iso_en       _____|‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾|_____
power_down   ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾|___________________|‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾
output       idle |     0      |      全 X          |      0      | ...
                  <  稳定钳位  >                   < 恢复后隔离 >
显示窗口       A−5 ns                                         D+5 ns
```

| 检查 | 判定 |
|---|---|
| idle 值 | A 之前最后一个有数据的时刻的最终值，严格排除 A 时刻的新值。 |
| 钳位值 | A 时刻所有更新完成后的最终值。 |
| idle / 钳位一致 | 对当前层次的每个 output、每个周期进行完整位向量比较；不进行不同输出口之间的互相比较。 |
| 钳位为 0 | 半开区间 `[A, B)` 的所有最终值都是全 0。 |
| 钳位稳定 | `[A, B)` 内没有偏离该输出钳位值的变化；跨不同时间戳的短脉冲即使恢复，也会失败。 |
| 掉电全 X | `[B, C)` 内每一位都是 X。部分 X、0/1 或 Z 均不等于全 X。 |
| 恢复后隔离 | `[C, D)` 内输出恢复为全 0；此时 iso_en 仍为 1。 |

掉电阶段优先适用全 X 规则；不能同时要求掉电阶段保持 0。B 时刻的最终 X 不算钳位区间的翻转，C 时刻的最终 0 不算掉电区间异常。解除隔离 D 之后可恢复正常活动，本规则不限制 D 之后的输出值。因为用户同时要求“钳位为 0”和“idle 等于钳位”，通过检查的 idle 必须也是全 0。

完整周期要求 A < B < C < D。控制边沿错序、未先隔离就掉电、重复掉电等报告失败；边沿缺失、窗口从隔离状态中途开始、控制含 X/Z、信号没有值或不支持的数据类型报告未知。发现确定的违例时保留失败，同时保留缺失证据。没有找到完整周期不等于通过。

时间运算使用 FSDB 的整数 tick，时间精度通过十进制换算为 ns；避免浮点误差改变边沿归属。默认前后各 5 ns，精度无法整除时向外取整。文件起止不足时裁剪到实际范围，并在界面与报告中标注。未结束周期展示到文件末尾并标为不完整。

## 数据覆盖与限制

- 数据来自 `ffrReadScopeVarTree2` 的层次、变量和端口方向，以及 `ffrVCTrvsHdl` 的四态值变化。SDK 适配器不解析 RTL，不运行模拟器，也不把 FSDB 转成 VCD。
- 自动枚举范围是所选 scope 中 `FSDB_VD_OUTPUT` 的直接端口。支持已经验证的 Verilog/SystemVerilog 标量与四态逻辑总线。子模块 output、内部 net 和 inout 不混入本层清单。
- 没有方向元数据时报告 `NO_OUTPUT_PORT_METADATA`。真实的 X、没有波形的信号和不支持的数据分别处理；后两者不作为真实 X 通过检查。
- FSDB 若根本没有 dump 某个端口，单凭该文件不能发现它。报告中的通过含义是“FSDB 已记录并识别出的输出口在已覆盖周期内通过”。若要证明与设计所有 output 的覆盖一致，需要另行用既有 elab 端口清单对账；本版没有将该对账伪装成已完成。
- dump-off 区间导致覆盖未知。间断前的旧值不会被当成间断后的真实保持值；必须等到信号重新记录后才恢复有效值。已观察到的确定违例仍保留。
- VHDL FSDB、实数/复杂值类型、接口 modport 方向推断、未记录的 delta 和全芯片规模性能不在已验证范围。遇到不支持值类型明确标记未知，不猜测为 0 或 X。
- 默认限制：2,000,000 条原始更新、10,000 个选中信号（含控制）、单信号 65,536 位、单层次 1,000 周期、128 MiB 原始值字节。可在 JSON `limits` 中调整。超限会明确报错，并且不会发布半份通过结果。

## 图形界面

正常结果、失败结果和未知结果使用不同颜色。左侧周期列表可切换层次和周期；主图默认显示选中输出口与两根控制信号，勾选“全部输出”可查看该周期全部输出；“展开波形”让波形占据结果表的空间。“完整周期”恢复 A−5 ns 至 D+5 ns 的窗口，滚轮缩放、左键拖动平移，鼠标指针显示时间与信号值。

逐口表列出 idle、钳位值、相等/零值检查、稳定性、掉电 X 和恢复 0。点击失败行显示完整路径、首次错误时刻、实际值及期望值。“问题与证据”给出控制时序问题、未知原因和 delta 提示。

导出 SVG 始终包含当前周期的两个控制与全部输出，以及完整默认窗口，不受 GUI 当前缩放或单口查看影响。结果目录可重新打开；结果表和波形共享同一份判定数据。修改输入后会标记“结果待更新”，避免将旧结果误认为新查询结果。

## 本机部署与命令行

```bash
export VERDI_HOME=/path/to/your/verdi
cd /path/to/rtlwire-0.3.0
./rtlwire-studio --config examples/power_wave.json

# 编辑示例中的实际路径；结果目录必须为空。
python3 -m rtlwire.wave_cli --query my_power_query.json --out work/power_001

# 仅打开已提取结果，不重新调用 SDK。
./rtlwire-studio --result work/power_001
```

需要 Python 3.6+、Tk 8.5+（仅 GUI）、g++/gcc、strace、本机兼容的 FSDB Reader SDK。适配器在本机使用安装的头文件和动态库编译；发布包不含厂商 SDK、共享库或许可证。默认库目录为 `$VERDI_HOME/share/FsdbReader/linux64`；CLI 可用 `--reader-lib` 指定同一安装中匹配 ABI 的目录。单阶段默认超时 600 秒，可用 `--timeout` 设置。

返回码 0 表示完成提取与报告生成，检查结论必须读取 `wave_report.json.summary.status`；FAIL/UNKNOWN 也可以是一次成功完成的分析。配置、SDK、读取、超限等运行错误返回 2，取消返回 130。GUI 会将检查结论显示在周期与逐口结果中，并独立处理运行失败。

## 输出文件

| 文件 | 内容 |
|---|---|
| `query.json` | 已归一化的完整路径及检查配置。 |
| `wave_report.json` | 层次、输出清单、周期、判定值、逐规则结果、错误时刻、未知和 delta 提示。 |
| `wave_data.json` | 提取后的所选信号最终值序列、元数据、已记录 delta；供 Tk 重开结果。 |
| `domain_N_cycle_M.svg` | 每个层次每个周期的全部输出波形，前后默认各 5 ns。 |
| `checks.csv` | 每个输出口×周期的五项检查和首次错误时间。 |
| `native.jsonl` | SDK 直接提取记录；没有 complete 记录时拒绝分析。 |
| `audit.json` / `access.log` | 输入 SHA-256 前后对比、RTL 文件访问保护和文件/进程审计。 |
| `manifest.json` | 工具版本、Reader SDK 路径、适配器源码摘要和检查汇总。 |
| `reader.log` / `reader_build.log` | 本机 SDK 读取及适配器编译日志。 |

波形分支通过只读 Reader API 读取 FSDB，运行前后比较输入摘要，使用已有的 RTL 文件打开保护和 strace 进程/文件记录。它不需要 root 或 mount namespace。这里只编译本工具的 C/C++ 适配器，不编译 RTL。

## 可重复测试

`tests/make_wave_fixtures.py` 与 `tests/fsdb_fixture_writer.cpp` 是独立测试数据生成器，使用已安装的 Writer SDK 生成真正的 FSDB；产品运行不调用 Writer。测试波形由工具自身的规格文件生成，未借用开源设计或重新编译 RTL。

```bash
python3 tests/make_wave_fixtures.py --out validation/wave_030/fixtures
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 tests/validate_wave_backend.py
# Linux 图形桌面或独立 Xvfb 会话；测试截图需要 Pillow 和 xwd。
PYTHONPATH=. python3 tests/validate_wave_gui.py
```

正常文件包含两个层次、每层三个 output、两个周期，以及一个同时间戳变化后恢复的更新。故障文件包含 idle 不一致、非零钳位、钳位期间翻转、部分 X、Z、恢复时非零和不完整周期。另有无端口方向元数据的文件，验证未知结论。实际验证记录见 [wave_validation_030.md](wave_validation_030.md)。
