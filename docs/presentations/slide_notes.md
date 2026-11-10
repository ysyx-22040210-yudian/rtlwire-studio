# RTLWire Studio 功能与实现原理

24 页演示文稿的文字与演讲者备注。图形对象可在 PowerPoint 中编辑；真实 GUI 截图为嵌入图片。

## 01 — RTLWire Studio

功能、使用流程与实现原理

让连接可见，
让判定可复查。

ELAB 接线检查
FSDB 隔离与掉电检查
Linux 原生 Tk 桌面

VERSION 0.5.0

讲解与依据：

这份演示文稿说明已经实现的 0.5.0 功能和边界。设计信息来自编译后的 elab；波形信息来自已有 FSDB。界面截图使用整理后的示例记录展示，不表示又执行了一次生产设计提取。

实现依据：README.md；rtlwire/__init__.py。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 02 — 三种工作方式，一套证据链

从“是否接到端口”，到“经过哪些实例”，再到“掉电行为是否符合规则”。

01

连接检查 · reach

父层信号是否连到目标 module
实例的输入口或输出口？

ELAB → 端口命中与位覆盖

连接顺序 · trace

信号从起点向下游，跨越哪些
层次接口和 module 实例？

ELAB → 分支路径与停止原因

03

掉电波形检查

隔离、掉电与恢复期间，输出
是否符合该层 RPT 分组规则？

FSDB + RPT → 逐口判定

共同输出：JSON / CSV / SVG  +  输入快照、错误位置与检查证据

讲解与依据：

reach 和 trace 使用相同的原始图，但遍历方向和结果组织不同。波形分支使用独立数据通路和规则引擎，不要求读取 RTL 源码。

实现依据：rtlwire/core.py；rtlwire/wave_core.py；rtlwire/report.py。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 03 — 输入层次、module 与信号，直接运行

输入区默认展开；打开历史结果后仍然可以继续编辑检查配置。

1

已有 elab 路径

指定编译库和遍历边界；
不提供 RTL filelist。

2

三类检查对象

检查层次、module 定义名、
待检查或起始信号。

3

结果与证据联动

选中端口或连线查看详情；
可切换路径、日志和 SVG。

讲解与依据：

目标 module 填定义名，不是实例名。检查层次填完整实例路径；源信号和关注信号支持多行。点击专注画布可扩大显示，Esc 返回并保留输入。

实现依据：rtlwire/gui.py:Studio._build；rtlwire/gui.py:Studio.collect_config。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 04 — 两根父层信号，分别检查同一实例的输入与输出

目标 module 可以位于任意深度；两根信号分别生成检查结论。

top.u_domain  ·  用户检查层次

u_wrap  ·  中间层次

u_pipe

module  target_module

data_in

data_out

d

q

输入端口命中

输出端口命中

两个独立问题：data_in → d；q → data_out。是否存在 d → q 的内部依赖，需要另有 NPI 证据。

讲解与依据：

此页为概念示意。reach 对图进行双向可达性搜索，因此既能找到下游输入，也能反查子模块输出。结果展示时，上游见证会恢复真实信号方向，不把输入输出命中混为模块内部导通。

实现依据：rtlwire/core.py:analyze；rtlwire/core.py:reach_paths；tests/test_core.py:test_two_parent_signals_reach_same_child_input_and_output。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 05 — 跨接口、跨层次，找出连接顺序

关注信号用于保留关键节点，不是限制遍历的白名单。以下为机制示意。

top

u_source_domain

u_target_domain

u_m1

module  stage

in

out

u_m2

module  target

in

out

src

next_if

bridge_if

src → u_m1.in ⇢ u_m1.out → bridge_if → u_m2.in ⇢ u_m2.out → next_if

实线：实际连接；虚线：已经提取到的组合依赖。遇到时序单元或不支持的映射会明确停止。

讲解与依据：

概念示意图中的模块内部虚线代表有证据的依赖，不保证所有模块都能穿透。程序沿 NPI load 关系向下游遍历，保留分叉、关注接口和停止原因。遇到寄存器不凭空连通 D 和 Q。

实现依据：npi/extract.tcl:explore；rtlwire/core.py:enumerate_paths。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 06 — 检查归属与真实包含关系，分别保存

父范围扣除另行选择的子树；图上仍保留真实的父子层次。

top   [已选]

top.u_tile   [中间层次]

u_c0   [已选]

归属：top.u_tile.u_c0

u_c1

module  target

归属：top

1

最近的已选祖先

u_c0 及其后代归属于 u_c0；
u_c1 归属于 top。

2

父范围扣除子范围

top 的统计不重复计入 u_c0
整棵已选子树。

3

显示不重新挂接

u_c0 与 u_c1 仍放在
真实父层次 u_tile 内。

讲解与依据：

核心算法沿 parent 链向上寻找最近的 selected scope，同时保留 actual_scope 和 owner_scope。对多个嵌套选择递归应用同一规则，与输入顺序无关。图布局读取真实 parent，不能把 owner_scope 当作显示父节点。

实现依据：rtlwire/core.py:assign_owners；rtlwire/architecture.py:build_architecture；tests/test_core.py:OwnershipTests。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 07 — 从编译库到检查结论：可追溯的数据通路

提取、分析、展示各有独立职责；原始连接证据随结果保留。

1

已编译 ELAB

用户已有编译产物

2

Tcl NPI 提取

实例 / 端口 / Driver / Load

3

标准化原始图

节点、边、位范围与证据

4

检查与路径分析

归属 / 可达性 / 分支

5

GUI 与导出

架构图 / JSON / CSV / SVG

事实层

原始记录保留对象 ID、完整路径、真实层次、方向、位范围和原始边索引。

展示层

合并端口绑定、压缩中间 net 的显示；点击图形仍能回到原始连接证据。

讲解与依据：

Tcl 输出带类型标记和十六进制编码字段的 TSV；Python parse_records 读取实例、节点、边、信号、查询、停止和错误记录。图形投影不改变原始提取事实。

实现依据：npi/extract.tcl:emit；rtlwire/core.py:parse_records；rtlwire/core.py:display_graph。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 08 — NPI 通过对象句柄读取连接事实

加载已有库、建立对象清单，再按方向遍历连接关系。

1

加载

debImport -elab

仅加载已有的编译数据库

2

枚举

npi_nl_iterate / npi_nl_scan

实例、端口、net 与定义名

3

定位

npi_nl_sig_handle_by_name

将用户信号解析为对象 / 位范围

4

追踪

npiNlLoad / npiNlDriver

读取负载与驱动，保留边证据

位宽、方向与真实层次均来自 NPI；无法证明的映射明确停止。

讲解与依据：

代码实际使用 npi_L1::npi_nl_sig_handle_by_name 和 npi_nl_handle_by_range 定位信号和位；遍历时按需要使用 npi_nl_iterate_with_range。Primitive 穿越仅对白名单开放，输出边类型区分 ASSIGN 与 LOGIC_DEP。

实现依据：npi/extract.tcl:selected_nodes；npi/extract.tcl:explore。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 09 — reach 做可达性检查，trace 列举下游分支

同一张原始有向图，在两种模式下采用不同的查询方式。

reach：按源位执行 BFS

1  建立双向邻接索引用于连通性搜索

2  匹配目标实例的端口与源位覆盖

3  每个命中端口保留一条见证路径

trace：有向图路径枚举

1  仅沿下游邻接表展开路径

2  保留分支、关注点及停止原因

3  发现循环或达到资源限制时终止分支

CONNECTED

PARTIAL_BITS

NOT_CONNECTED

UNKNOWN

“未连通”只在提取完整、边界与策略明确时成立。

讲解与依据：

reach 搜索对每个源位执行，目标按 base_name 和方向聚合；状态取决于所选源位是否全部命中。trace 使用栈展开路径，路径中已有节点用于检测循环。限制包括最大节点、边、深度和路径数。关注信号不会限制遍历。

实现依据：rtlwire/core.py:search；rtlwire/core.py:analyze；rtlwire/core.py:enumerate_paths。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 10 — 只读编译库：入口、运行时与审计共同约束

这些措施约束本工具的加载流程，不等同于任意程序的通用安全沙箱。

01

入口限制

只接受已有 elab；不接收 RTL filelist、宏、include 或参数覆盖。

02

只读挂载

在独立 mount namespace 内，把输入库与解析到的依赖目录只读挂载。

03

源码访问保护

LD_PRELOAD 保护库拒绝常见 RTL 源文件后缀的打开请求。

04

访问与完整性审计

strace 记录文件 / 进程访问；前后 SHA256 比较确认输入未改动。

讲解与依据：

如果库依赖随附 TDC/library 编译产物，输入必须完整；缺少数据时失败而不是读取源码。工具会编译自己的 C 文件保护库与 C++ FSDB 适配器，这不属于 RTL 编译。NPI 只读挂载路径当前需要 mount namespace 权限。

实现依据：rtlwire/cli.py:package_manifest；rtlwire/cli.py:audit_access；npi/readonly_run.sh；npi/source_guard.c。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 11 — 架构图不是平铺节点图，而是真实层次的投影

布局与绘制共用图形元素，界面选中可关联到连接见证。

包含树

从真实 parent 构建嵌套容器

同级布局

按可见连接分组和排序

端口与布线

端口放在边界，正交路径避开其他模块

共享图元

Tk 与 SVG 共用矩形、文字、端口和连线

讲解与依据：

architecture.py 负责包含树、同级列布局、端口位置和正交寻路；显示连线转角进行局部圆滑化，但原始连接与见证不变。primitives 同时供 Tk Canvas 和 SVG 导出使用。

实现依据：rtlwire/architecture.py:layout；rtlwire/architecture.py:orthogonal_route；rtlwire/architecture.py:primitives；rtlwire/gui.py:ArchitectureCanvas。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 12 — 两个层次，独立配置控制信号与 RPT

枚举输出口、检查分组规则，并在同一界面查看周期波形与首次异常。

1

每层独立输入

层次、iso_en、power_down、
RPT 文件和三类关键词。

2

自动读取输出口

只使用 FSDB 已记录且具有
方向信息的本层 output。

3

定位具体问题

选择输出口，在完整周期中
查看首个异常及实际 / 期望值。

讲解与依据：

截图使用独立故障测试 FSDB，因此显示 8 个 PASS 和 6 个 FAIL。这表明检查器识别到了注入故障，不代表程序测试失败。两层可以使用不同的 RPT 文件和不同的组名关键词。

实现依据：rtlwire/wave_gui.py:WavePanel；examples/power_groups_faults.json。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 13 — 四个边沿定义完整周期，前后各留 5 ns

示例：A=20 ns，B=35 ns，C=70 ns，D=90 ns；显示窗口为 15–95 ns。

钳位区间

掉电区间 · 全 X

恢复后仍隔离

iso_en

power_down

A · 20

B · 35

C · 70

D · 90

5 ns 裕量

5 ns 裕量

Idle = A 之前最后一个已知采样；Clamp = A 时刻所有已记录更新后的最终值。

讲解与依据：

时间坐标使用 FSDB 原生整数 tick，单位换算用 Decimal。周期要求严格 A<B<C<D；若文件不够长，5 ns 裕量裁剪到文件真实范围。缺少完整周期标记 UNKNOWN；同一时刻发生多个不同边沿不能当作严格有序完整周期。

实现依据：rtlwire/wave_core.py:find_cycles；rtlwire/wave_core.py:check_output；rtlwire/wave_core.py:analyze。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 14 — 组名由用户定义，关键词负责分类

组名包含关键词，区分大小写；每组只能匹配一种类型。左侧为 RPT 节选。

ALPHA_KEEP1  { one_out, one_bus }

ALPHA_KEEP0  { zero_out, zero_bus }

ALPHA_BYPASS { free_out, free_bus }

用户输入关键词

识别类型

KEEP1

钳 1

KEEP0

钳 0

BYPASS

不钳位

各层可使用不同文件与关键词。支持中文 / 英文逗号、空格、换行、注释及位 / 片选。

讲解与依据：

关键词是字面子串，不是正则表达式。解析器不执行 RPT 中的命令；空组允许，但嵌套组不允许。未匹配组或命中多个关键词属于配置错误，预览/运行时直接报错。端口存在性与方向仍来自 FSDB。

实现依据：rtlwire/wave_groups.py:parse_rpt；rtlwire/wave_gui.py:GroupDialog。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 15 — 一根总线可以按位混合分组

检查规则落实到 FSDB 声明的位号，而不是仅按信号名字归类。

KEEP1  { mixed_bus[3] }
KEEP0  { mixed_bus[2] }
BYPASS { mixed_bus[1:0] }

期望掩码

10--

bit 3

1

钳 1

bit 2

0

钳 0

bit 1

—

不钳位

bit 0

—

不钳位

只比较需要钳位的位

钳位相关规则：只比较 bit 3 和 bit 2。
掉电全 X 规则：检查 bit 3…0 全部位。

讲解与依据：

波形四态字符串按声明 left/right 映射为位号，支持升序与降序声明。重复归组、位越界、未覆盖输出位使用 UNKNOWN 问题记录，未明确分组位的掩码为 ?。- 表示已明确不钳位，含义与 ? 不同。

实现依据：rtlwire/wave_groups.py:resolve_groups；rtlwire/wave_groups.py:bit_numbers；rtlwire/wave_core.py:check_output；tests/test_wave_groups.py。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 16 — 五项规则覆盖隔离、掉电与恢复

“不钳位”跳过钳位相关规则，掉电期间仍必须全 X。

检查项

钳 1

钳 0

不钳位

A 前 idle = A 最终值

检查

检查

SKIP

[A,B) 符合期望值

全 1

全 0

SKIP

[A,B) 保持稳定

检查

检查

SKIP

[B,C) 掉电值

全 X

全 X

全 X

[C,D) 恢复后的隔离值

全 1

全 0

SKIP

由于还检查 idle 与钳位值相等：钳 1 组通过时，相关位的 idle 也须为 1；钳 0 同理。

讲解与依据：

内部规则名为 idle_equal、clamp_expected、clamp_stable、off_x、recovery_expected。所有区间使用左闭右开，因此 B 时刻的掉电变化不计入钳位稳定性，C 时刻回到恢复后的隔离检查。SKIP 不等于 PASS。

实现依据：rtlwire/wave_core.py:RULES；rtlwire/wave_core.py:check_output；docs/rpt_groups_040.md。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 17 — 同一时间戳取最终值，数据不足明确报未知

这是已确认的判定口径；短暂的已记录 delta 更新作为提示。

同一时刻 20 ns 的已记录更新

0

X

1

最终用于判定：1

delta 作为提示保留。FSDB 未保存的
瞬态变化，不能由工具事后重建。

PASS

规则已经验证通过

FAIL

有明确违例和首个失败位置

UNKNOWN

边沿、方向、波形或分组覆盖不足

SKIP

该规则对不钳位的信号位不适用

讲解与依据：

load_native 对同一时间戳保留最后一次已记录值，另外记录 deltas；Series 提供时点和区间查询。UNKNOWN 包括缺少完整周期、方向或值、控制信号 X/Z、dump-off 空洞、未分组/重复归组等。状态聚合保留确定 FAIL，不用 UNKNOWN 掩盖已经证实的失败。

实现依据：rtlwire/wave_core.py:load_native；rtlwire/wave_core.py:Series；rtlwire/wave_core.py:status_of。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 18 — C++ Reader 提取事件，Python 执行检查

使用本机安装的 Reader SDK，输出结构化记录，不把 FSDB 转成推测的设计端口表。

1

读取树与元数据

ffrReadScopeVarTree2

scope / module / direction / 位号

2

选择记录对象

控制信号 + 直接 output

严格匹配层次与 output 方向

3

遍历四态事件

ffrCreateVCTraverseHandle

64 位时间戳与 0 / 1 / X / Z

4

标准化和判定

JSONL → Series → 周期状态机

时间单位换算、掩码规则、首个异常

讲解与依据：

Reader 保留 scope/variable tree 的方向元数据，只加载所选控制信号和对应 scope 的 output。原生 tick 由 tag H/L 合为 uint64，Python 用整数和 Decimal 做单位换算；有事件数、信号数、位宽和数据量上限。没有 dump 的端口不能单靠 FSDB 枚举出来。

实现依据：wave/fsdb_reader.cpp:tree；wave/fsdb_reader.cpp:main；rtlwire/wave_cli.py；rtlwire/wave_core.py。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 19 — 界面、任务进程和分析内核分层

耗时的 EDA / FSDB 读取在后台运行，GUI 通过事件队列接收进度与结果。

Tk / ttk 视图

gui.py / theme.py
wave_gui.py

输入、表格、选择联动
缩放、平移、SVG 导出

任务与 CLI

jobs.py
cli.py / wave_cli.py

独立运行目录
进度事件、取消、审计

提取与规则内核

NPI / FSDB Reader
core.py / wave_core.py

原始事实、图算法
分组、时序与状态聚合

共享绘图层：architecture.py / wave_plot.py    →    Tk Canvas + SVG

讲解与依据：

AnalysisJob 的后台线程启动本地 CLI 子进程，按 JSON phase/log/done 事件更新 GUI。取消通过 cancel 文件和任务状态协调，保留已产生的日志与审计。WaveAnalysisJob 复用同一机制，只更换 CLI 模块。

实现依据：rtlwire/jobs.py；rtlwire/gui.py:poll；rtlwire/wave_gui.py:poll。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 20 — 用正常、故障和缺失数据，验证检查器行为

数字来自 0.5.0 开发验收记录；它们代表已验证案例，不等于全芯片覆盖率。

62

单元测试

9

实际 FSDB GUI 流程

6

界面与布局检查

独立测试波形

通过

失败

未知

三类分组 + 混合总线

14

0

0

注入 6 类输出违例

8

6

0

重复 / 未分组输出

12

0

2

额外验证：普通账号读取只读 FSDB / RPT、打包后启动、旧报告兼容、SVG 导出。

讲解与依据：

单元测试构成为 core 10、architecture 7、wave 22、wave_groups 23，共 62。三类分组样例为两个层次各 7 个输出。故障包括钳位值、稳定性、idle、恢复、不钳位掉电值和混合位掉电值等问题。界面验收包括 1600×960 三条波形可见、缩放、1280×800 布局和配置对话框。

实现依据：tests/test_core.py；tests/test_architecture.py；tests/test_wave.py；tests/test_wave_groups.py；docs/verification_summary.json。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 21 — Linux 本机部署，支持范围清楚可见

已验证环境：CentOS 7 · Python 3.6.8 · Tk 8.5 · Verdi O-2018.09-SP2。

运行条件

GUI：Python 标准库 + Tk + 中文字体

ELAB：本机 Verdi / NPI 与许可证

FSDB：本机 Reader SDK、编译器与 strace

当前支持边界

时序单元明确停止，不凭空跨越 D → Q

复杂或不确定的组合映射报告停止 / 未知

FSDB 只覆盖已 dump 且具方向的直接 output

NPI 只读挂载需要相应权限；FSDB 分支可由普通账号运行。不同 SDK 版本需确认兼容性。

讲解与依据：

当前组合穿越白名单为 Assign、Buf、Neg、And、Or、Xor、Nand。接口 modport、VHDL、复杂波形类型和完整芯片性能不在本版已验证范围。GUI 保留系统窗口装饰；应用内容使用原生 Tk 圆角组件。

实现依据：README.md；rtlwire/cli.py；wave/fsdb_reader.cpp；docs/power_wave.md。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 22 — 配置 → 检查 → 定位 → 保存

每一次运行产生独立目录，便于复查配置、结论与证据。

1

配置

ELAB 或 FSDB
层次 / 信号 / RPT

2

检查

后台执行
查看进度与日志

3

定位

架构对象或波形
首个异常及完整路径

4

保存

JSON / CSV / SVG
配置与结果目录

sh rtlwire-studio --result validation/reach_dual_io
sh rtlwire-studio --result validation/wave_groups_faults

讲解与依据：

保存结果可以离线查看，不需要再次打开 EDA 工具。代码仓库提供独立 FSDB 示例和整理过的历史架构记录，elab 查询模板需要替换成本机已有编译库路径。运行中的检查可取消，输入与结果存放在独立目录。

实现依据：README.md；rtlwire/jobs.py；rtlwire/gui.py；rtlwire/wave_gui.py。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 23 — 从功能定位到实现文件

用于代码评审、维护和后续扩展。图形与核心规则均可独立阅读。

功能

主要实现

关键职责

ELAB 提取

npi/extract.tcl

枚举实例 / 端口，追踪 Driver / Load

接线分析

rtlwire/core.py

最近祖先归属、BFS、路径枚举

架构绘图

rtlwire/architecture.py

真实包含、布局、正交布线与 SVG

FSDB 读取

wave/fsdb_reader.cpp

方向与位号、原生 tick、四态事件

RPT 与规则

wave_groups.py / wave_core.py

按位归组、周期状态机和区间检查

界面与任务

gui.py / wave_gui.py / jobs.py

用户输入、异步进度、选择联动

只读与审计

cli.py / wave_cli.py / source_guard.c

输入保护、日志、SHA256 与资源限制

讲解与依据：

这页是导航索引，不是完整调用图。使用演讲者备注中的源文件和函数名可以进一步核对每项结论。代码与示例以随附 GitHub 仓库为准；原始供应商 NPI 手册、SDK 与许可证不属于仓库内容。

实现依据：rtlwire/；npi/；wave/。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。

## 24 — 连接有路径，判定有依据。

以编译库与波形记录为事实来源，把检查过程做成可复查的工程工具。

两类接线检查
三类输出分组
一个本地桌面工作区

交付内容

源码与可运行示例
PPT / PDF 与实际界面截图
配置说明与核心测试

github.com/ysyx-22040210-yudian/rtlwire-studio

讲解与依据：

交付版本为 0.5.0。公开仓库链接经发布后核验；PPT 和 PDF 放在 docs/presentations，真实 Linux 窗口截图放在 docs/images。

实现依据：README.md；docs/presentations/。
示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。
