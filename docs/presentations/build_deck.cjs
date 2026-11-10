/* RTLWire Studio presentation. Editable PowerPoint shapes; genuine Linux UI captures.
 * Build: npm install pptxgenjs && node docs/presentations/build_deck.cjs
 */
const fs=require('fs');
const path=require('path');
const PptxGenJS=require('pptxgenjs');
const pptx=new PptxGenJS();
pptx.layout='LAYOUT_WIDE';
pptx.author='RTLWire Studio';pptx.subject='RTL connectivity and power waveform verification';
pptx.title='RTLWire Studio｜功能与实现原理';pptx.company='RTLWire Studio';pptx.lang='zh-CN';
pptx.theme={headFontFace:'Microsoft YaHei',bodyFontFace:'Microsoft YaHei',lang:'zh-CN'};
const W=13.333333,H=7.5;
const C={bg:'FAF9F5',ink:'292823',muted:'79766B',accent:'B56346',light:'F5E9E1',line:'E2DED2',white:'FFFFFF',nav:'EEECE3',teal:'38796C',sage:'EAF1E9',amber:'A27935',sand:'F7EFDF',red:'B24F4C',rose:'F8E8E3',dark:'292B26'};
const FONT='Microsoft YaHei',MONO='Consolas';
const imgs=path.resolve(__dirname,'../images');
const slides=[],audit=[];
function txt(s,t,x,y,w,h,size=16,color=C.ink,more={}){
  audit.push({slide:slides.length,type:'text',text:String(t),x,y,w,h});
  s.addText(t,{x,y,w,h,fontFace:FONT,fontSize:size,color,margin:0,breakLine:false,
    valign:'mid',paraSpaceAfterPt:0,...more});
}
function box(s,x,y,w,h,fill=C.white,stroke=C.line,r=.15,extra={}){
  s.addShape('roundRect',{x,y,w,h,rectRadius:r,fill:{color:fill},line:{color:stroke,width:.8},radius:r,...extra});
}
function pill(s,t,x,y,w,color=C.accent,fill=C.light){box(s,x,y,w,.32,fill,fill,.12);txt(s,t,x+.07,y+.025,w-.14,.26,10.5,color,{bold:true,align:'center'});}
function line(s,x1,y1,x2,y2,color=C.teal,width=1.7,arrow=false,dash=false){
  s.addShape('line',{x:Math.min(x1,x2),y:Math.min(y1,y2),w:Math.abs(x2-x1),h:Math.abs(y2-y1),flipH:x2<x1,flipV:y2<y1,
    line:{color,width,beginArrowType:'none',endArrowType:arrow?'triangle':'none',...(dash?{dashType:'dash'}:{})}});
}
function route(s,points,color=C.teal,arrow=true,dash=false,width=1.7){points.slice(1).forEach((p,i)=>line(s,...points[i],...p,color,width,arrow&&i===points.length-2,dash));}
function pin(s,x,y,label,side='right',color=C.teal){s.addShape('ellipse',{x:x-.055,y:y-.055,w:.11,h:.11,fill:{color:C.white},line:{color,width:1.3}});if(label)txt(s,label,side==='right'?x+.12:x-1.35,y-.13,1.23,.26,12,color,{fontFace:MONO,align:side==='right'?'left':'right'});}
function base(kicker,title,subtitle='',dark=false){
  const s=pptx.addSlide();slides.push(s);s.background={color:dark?C.dark:C.bg};
  const fg=dark?'FAF9F5':C.ink;
  txt(s,kicker.toUpperCase(),.55,.37,11.9,.22,10.5,dark?'D5A68B':C.accent,{charSpacing:2,bold:true});
  txt(s,title,.55,.81,12.15,.63,31,fg,{bold:true});
  if(subtitle)txt(s,subtitle,.58,1.49,12.1,.33,12.5,dark?'C6C3B8':C.muted);
  txt(s,'RTLWire Studio  /  0.5.0',.55,7.03,8,.2,9.5,dark?'BBB7AC':C.muted);
  txt(s,String(slides.length).padStart(2,'0'),12.0,7.01,.75,.24,10.5,dark?'D5A68B':C.accent,{align:'right'});
  return s;
}
function note(s,text,sources){s.addNotes(text+'\n\n实现依据：'+sources.join('；')+'。\n示意图用于解释机制；实际 GUI 截图来自 Linux Tk 运行窗口。');}
function body(s,text,x,y,w,h,size=16,color=C.ink){txt(s,text,x,y,w,h,size,color,{valign:'top',breakLine:false});}
function row(s,n,title,desc,x,y,w=3.5,color=C.accent){pill(s,n,x,y,.44,color,color===C.teal?C.sage:C.light);txt(s,title,x+.59,y-.025,w-.59,.38,18,C.ink,{bold:true});body(s,desc,x+.59,y+.48,w-.59,1.1,14.5,C.muted);}
function photo(s,name,x,y,w,h){
  const sizes={design:[1600,960],architecture:[1600,960],trace:[1600,960],waveform:[1600,960],rpt:[880,630]};
  const [iw,ih]=sizes[name];let fw=w,fh=w*ih/iw;if(fh>h){fh=h;fw=h*iw/ih;}
  box(s,x-.05,y-.05,w+.1,h+.1,C.white,C.line,.14,{shadow:{type:'outer',color:'40352B',opacity:.1,blur:4,offset:1.4,angle:90}});
  s.addImage({path:path.join(imgs,name+'.png'),x:x+(w-fw)/2,y:y+(h-fh)/2,w:fw,h:fh,altText:'RTLWire Studio actual Linux Tk '+name+' screenshot'});
}
function panel(s,title,desc,x,y,w,h,fill=C.white){box(s,x,y,w,h,fill);txt(s,title,x+.22,y+.19,w-.44,.4,20,C.ink,{bold:true});body(s,desc,x+.22,y+.78,w-.44,h-.98,15,C.muted);}
function table(s,headers,rows,x,y,widths,rh=.55,font=14){
 const total=widths.reduce((a,b)=>a+b,0);
 box(s,x,y,total,rh,C.nav,C.nav,.1);
 let xx=x;headers.forEach((t,j)=>{txt(s,t,xx+.14,y+.07,widths[j]-.28,rh-.14,font-1,C.muted,{bold:true});xx+=widths[j];});
 rows.forEach((row,i)=>{let yy=y+rh*(i+1);s.addShape('rect',{x,y:yy,w:total,h:rh,fill:{color:i%2?C.bg:C.white},line:{color:C.line,width:.35}});let xx=x;row.forEach((v,j)=>{let text=typeof v==='string'?v:v.t,color=typeof v==='string'?C.ink:v.c;txt(s,text,xx+.14,yy+.06,widths[j]-.28,rh-.12,font,color,{bold:j===0});xx+=widths[j];});});
}
function code(s,text,x,y,w,h,size=14){box(s,x,y,w,h,'F1EFE7','F1EFE7',.15);body(s,text,x+.22,y+.2,w-.44,h-.4,size,C.ink);}
function module(s,name,def,x,y,w=2.1,h=1.35,fill=C.white){box(s,x,y,w,h,fill,'C8D4C8',.13);txt(s,name,x+.16,y+.13,w-.32,.27,15.5,C.ink,{bold:true});txt(s,'module  '+def,x+.16,y+.46,w-.32,.19,10.5,C.muted,{fontFace:MONO});}

// 01 — cover
{
const s=base('RTL CONNECTIVITY  /  POWER WAVEFORM','RTLWire Studio','功能、使用流程与实现原理',true);
txt(s,'让连接可见，\n让判定可复查。',.62,2.2,5.1,1.65,34,'FAF9F5',{bold:true,breakLine:false});
body(s,'ELAB 接线检查\nFSDB 隔离与掉电检查\nLinux 原生 Tk 桌面',.66,4.26,4.7,1.35,18,'CDC8BB');
pill(s,'VERSION 0.5.0',.66,6.13,1.72,'E8B69B','474138');
photo(s,'architecture',6.02,2.18,6.65,4.03);
note(s,'这份演示文稿说明已经实现的 0.5.0 功能和边界。设计信息来自编译后的 elab；波形信息来自已有 FSDB。界面截图使用整理后的示例记录展示，不表示又执行了一次生产设计提取。',['README.md','rtlwire/__init__.py']);
}
// 02 — scope
{
const s=base('01 / PRODUCT','三种工作方式，一套证据链','从“是否接到端口”，到“经过哪些实例”，再到“掉电行为是否符合规则”。');
const cards=[['01','连接检查 · reach','父层信号是否连到目标 module\n实例的输入口或输出口？','ELAB → 端口命中与位覆盖'],['02','连接顺序 · trace','信号从起点向下游，跨越哪些\n层次接口和 module 实例？','ELAB → 分支路径与停止原因'],['03','掉电波形检查','隔离、掉电与恢复期间，输出\n是否符合该层 RPT 分组规则？','FSDB + RPT → 逐口判定']];
cards.forEach((a,i)=>{let x=.58+i*4.13;box(s,x,2.2,3.92,3.68);pill(s,a[0],x+.23,2.46,.55);txt(s,a[1],x+.23,3.02,3.46,.46,21,C.ink,{bold:true});body(s,a[2],x+.23,3.78,3.46,1.02,17,C.muted);pill(s,a[3],x+.23,5.26,3.46,C.teal,C.sage);});
txt(s,'共同输出：JSON / CSV / SVG  +  输入快照、错误位置与检查证据',.73,6.27,11.85,.4,17,C.ink);
note(s,'reach 和 trace 使用相同的原始图，但遍历方向和结果组织不同。波形分支使用独立数据通路和规则引擎，不要求读取 RTL 源码。',['rtlwire/core.py','rtlwire/wave_core.py','rtlwire/report.py']);
}
// 03 — design workspace
{
const s=base('02 / DESIGN WORKSPACE','输入层次、module 与信号，直接运行','输入区默认展开；打开历史结果后仍然可以继续编辑检查配置。');
photo(s,'design',.6,2.03,8.18,4.74);
row(s,'1','已有 elab 路径','指定编译库和遍历边界；\n不提供 RTL filelist。',9.13,2.13,3.52);
row(s,'2','三类检查对象','检查层次、module 定义名、\n待检查或起始信号。',9.13,3.65,3.52);
row(s,'3','结果与证据联动','选中端口或连线查看详情；\n可切换路径、日志和 SVG。',9.13,5.17,3.52);
note(s,'目标 module 填定义名，不是实例名。检查层次填完整实例路径；源信号和关注信号支持多行。点击专注画布可扩大显示，Esc 返回并保留输入。',['rtlwire/gui.py:Studio._build','rtlwire/gui.py:Studio.collect_config']);
}
// 04 — reach diagram
{
const s=base('03 / SCENARIO A','两根父层信号，分别检查同一实例的输入与输出','目标 module 可以位于任意深度；两根信号分别生成检查结论。');
box(s,.68,2.08,11.98,3.9,C.nav,'C7BCA9',.2);txt(s,'top.u_domain  ·  用户检查层次',.96,2.3,10.9,.34,18,C.ink,{bold:true});
box(s,3.24,2.98,6.82,2.54,C.bg,C.line,.17);txt(s,'u_wrap  ·  中间层次',3.5,3.17,5.8,.3,15,C.muted);
module(s,'u_pipe','target_module',5.39,3.79,2.48,1.25);
pin(s,.68,4.18,'','right',C.accent);pin(s,12.66,4.7,'','left',C.accent);
txt(s,'data_in',.9,3.81,1.4,.28,13,C.accent,{fontFace:MONO});txt(s,'data_out',10.97,4.32,1.43,.28,13,C.accent,{fontFace:MONO,align:'right'});
pin(s,5.39,4.76,'d','right');pin(s,7.87,4.76,'q','left');
route(s,[[.735,4.18],[3.0,4.18],[3.0,4.76],[5.335,4.76]]);
route(s,[[7.925,4.76],[10.7,4.76],[10.7,4.7],[12.605,4.7]]);
pill(s,'输入端口命中',1.35,5.16,1.56,C.teal,C.sage);pill(s,'输出端口命中',10.55,5.16,1.56,C.teal,C.sage);
txt(s,'两个独立问题：data_in → d；q → data_out。是否存在 d → q 的内部依赖，需要另有 NPI 证据。',.8,6.3,11.85,.42,16.5,C.ink);
note(s,'此页为概念示意。reach 对图进行双向可达性搜索，因此既能找到下游输入，也能反查子模块输出。结果展示时，上游见证会恢复真实信号方向，不把输入输出命中混为模块内部导通。',['rtlwire/core.py:analyze','rtlwire/core.py:reach_paths','tests/test_core.py:test_two_parent_signals_reach_same_child_input_and_output']);
}
// 05 — trace diagram
{
const s=base('04 / SCENARIO B','跨接口、跨层次，找出连接顺序','关注信号用于保留关键节点，不是限制遍历的白名单。以下为机制示意。');
box(s,.64,2.1,12.05,3.77,C.nav,C.line,.2);txt(s,'top',.86,2.28,11.4,.3,18,C.ink,{bold:true});
box(s,1.05,2.97,4.25,2.35,C.bg,C.line,.15);txt(s,'u_source_domain',1.25,3.14,3.7,.3,14,C.muted,{fontFace:MONO});
box(s,6.0,2.75,6.23,2.88,C.bg,C.line,.15);txt(s,'u_target_domain',6.23,2.96,5.7,.3,14,C.muted,{fontFace:MONO});
module(s,'u_m1','stage',2.34,3.77,2.25,1.1);pin(s,2.34,4.56,'in','right');pin(s,4.59,4.56,'out','left');
module(s,'u_m2','target',7.13,3.77,2.25,1.1);pin(s,7.13,4.56,'in','right');pin(s,9.38,4.56,'out','left');
pin(s,1.05,4.56,'','right',C.accent);txt(s,'src',1.2,4.12,.72,.28,12,C.accent,{fontFace:MONO});route(s,[[1.105,4.56],[2.285,4.56]]);
pin(s,5.3,4.56,'','right');pin(s,6.0,4.56,'','right');
route(s,[[4.645,4.56],[5.245,4.56]]);route(s,[[5.355,4.56],[5.945,4.56]]);route(s,[[6.055,4.56],[7.075,4.56]]);
pin(s,12.23,4.56,'','right');route(s,[[9.435,4.56],[12.175,4.56]]);pill(s,'next_if',10.0,4.93,1.1,C.teal,C.sage);
route(s,[[3.03,4.56],[3.87,4.56]],C.teal,true,true);route(s,[[7.82,4.56],[8.65,4.56]],C.teal,true,true);
pill(s,'bridge_if',4.89,3.91,1.3,C.accent,C.light);
txt(s,'src → u_m1.in ⇢ u_m1.out → bridge_if → u_m2.in ⇢ u_m2.out → next_if',.74,6.15,11.85,.4,17,C.ink,{fontFace:MONO,align:'center'});
txt(s,'实线：实际连接；虚线：已经提取到的组合依赖。遇到时序单元或不支持的映射会明确停止。',.85,6.66,11.7,.24,13,C.muted,{align:'center'});
note(s,'概念示意图中的模块内部虚线代表有证据的依赖，不保证所有模块都能穿透。程序沿 NPI load 关系向下游遍历，保留分叉、关注接口和停止原因。遇到寄存器不凭空连通 D 和 Q。',['npi/extract.tcl:explore','rtlwire/core.py:enumerate_paths']);
}
// 06 — ownership
{
const s=base('05 / HIERARCHY OWNERSHIP','检查归属与真实包含关系，分别保存','父范围扣除另行选择的子树；图上仍保留真实的父子层次。');
box(s,.65,2.16,7.05,4.24,C.nav,'C99A80',.2);txt(s,'top   [已选]',.91,2.4,6.5,.32,18,C.ink,{bold:true});
box(s,1.05,3.05,6.23,2.94,C.bg,C.line,.17);txt(s,'top.u_tile   [中间层次]',1.27,3.25,5.8,.28,15,C.muted);
box(s,1.48,3.94,2.7,1.52,C.light,'C99A80',.14);txt(s,'u_c0   [已选]',1.7,4.12,2.25,.3,17,C.ink,{bold:true});pill(s,'归属：top.u_tile.u_c0',1.69,4.73,2.25);
module(s,'u_c1','target',4.55,3.94,2.23,1.52);pill(s,'归属：top',4.75,4.94,1.84,C.teal,C.sage);
row(s,'1','最近的已选祖先','u_c0 及其后代归属于 u_c0；\nu_c1 归属于 top。',8.23,2.3,4.25);
row(s,'2','父范围扣除子范围','top 的统计不重复计入 u_c0\n整棵已选子树。',8.23,3.84,4.25);
row(s,'3','显示不重新挂接','u_c0 与 u_c1 仍放在\n真实父层次 u_tile 内。',8.23,5.32,4.25);
note(s,'核心算法沿 parent 链向上寻找最近的 selected scope，同时保留 actual_scope 和 owner_scope。对多个嵌套选择递归应用同一规则，与输入顺序无关。图布局读取真实 parent，不能把 owner_scope 当作显示父节点。',['rtlwire/core.py:assign_owners','rtlwire/architecture.py:build_architecture','tests/test_core.py:OwnershipTests']);
}
// 07 — data architecture
{
const s=base('06 / DATA FLOW','从编译库到检查结论：可追溯的数据通路','提取、分析、展示各有独立职责；原始连接证据随结果保留。');
const a=[['已编译 ELAB','用户已有编译产物'],['Tcl NPI 提取','实例 / 端口 / Driver / Load'],['标准化原始图','节点、边、位范围与证据'],['检查与路径分析','归属 / 可达性 / 分支'],['GUI 与导出','架构图 / JSON / CSV / SVG']];
a.forEach((v,i)=>{let x=.65+i*2.45;box(s,x,2.63,2.22,1.68,i===0?C.light:C.white);pill(s,String(i+1),x+.15,2.82,.38);txt(s,v[0],x+.15,3.27,1.92,.32,16,C.ink,{bold:true});txt(s,v[1],x+.15,3.77,1.92,.26,10.5,C.muted);if(i<4)line(s,x+2.24,3.45,x+2.43,3.45,C.teal,1.7,true);});
panel(s,'事实层','原始记录保留对象 ID、完整路径、真实层次、方向、位范围和原始边索引。',.65,4.85,5.88,1.7,C.nav);
panel(s,'展示层','合并端口绑定、压缩中间 net 的显示；点击图形仍能回到原始连接证据。',6.82,4.85,5.88,1.7,C.sage);
note(s,'Tcl 输出带类型标记和十六进制编码字段的 TSV；Python parse_records 读取实例、节点、边、信号、查询、停止和错误记录。图形投影不改变原始提取事实。',['npi/extract.tcl:emit','rtlwire/core.py:parse_records','rtlwire/core.py:display_graph']);
}
// 08 — NPI
{
const s=base('07 / NPI EXTRACTION','NPI 通过对象句柄读取连接事实','加载已有库、建立对象清单，再按方向遍历连接关系。');
const steps=[['加载','debImport -elab','仅加载已有的编译数据库'],['枚举','npi_nl_iterate / npi_nl_scan','实例、端口、net 与定义名'],['定位','npi_nl_sig_handle_by_name','将用户信号解析为对象 / 位范围'],['追踪','npiNlLoad / npiNlDriver','读取负载与驱动，保留边证据']];
steps.forEach((v,i)=>{let y=2.06+i*1.1;pill(s,String(i+1),.71,y+.09,.44);txt(s,v[0],1.35,y+.03,1.12,.36,20,C.ink,{bold:true});txt(s,v[1],2.78,y,6.8,.38,18,C.teal,{fontFace:MONO});txt(s,v[2],2.8,y+.49,8.9,.32,15,C.muted);});
pill(s,'位宽、方向与真实层次均来自 NPI；无法证明的映射明确停止。',.84,6.57,11.63,C.accent,C.light);
note(s,'代码实际使用 npi_L1::npi_nl_sig_handle_by_name 和 npi_nl_handle_by_range 定位信号和位；遍历时按需要使用 npi_nl_iterate_with_range。Primitive 穿越仅对白名单开放，输出边类型区分 ASSIGN 与 LOGIC_DEP。',['npi/extract.tcl:selected_nodes','npi/extract.tcl:explore']);
}
// 09 — algorithms
{
const s=base('08 / GRAPH ALGORITHMS','reach 做可达性检查，trace 列举下游分支','同一张原始有向图，在两种模式下采用不同的查询方式。');
panel(s,'reach：按源位执行 BFS','1  建立双向邻接索引用于连通性搜索\n\n2  匹配目标实例的端口与源位覆盖\n\n3  每个命中端口保留一条见证路径',.65,2.12,5.85,3.45);
panel(s,'trace：有向图路径枚举','1  仅沿下游邻接表展开路径\n\n2  保留分支、关注点及停止原因\n\n3  发现循环或达到资源限制时终止分支',6.83,2.12,5.85,3.45);
pill(s,'CONNECTED',.89,5.99,1.7,C.teal,C.sage);pill(s,'PARTIAL_BITS',2.79,5.99,1.92,C.amber,C.sand);pill(s,'NOT_CONNECTED',4.92,5.99,2.26,C.muted,C.nav);pill(s,'UNKNOWN',7.39,5.99,1.55,C.amber,C.sand);
txt(s,'“未连通”只在提取完整、边界与策略明确时成立。',9.19,5.92,3.22,.65,14.5,C.ink);
note(s,'reach 搜索对每个源位执行，目标按 base_name 和方向聚合；状态取决于所选源位是否全部命中。trace 使用栈展开路径，路径中已有节点用于检测循环。限制包括最大节点、边、深度和路径数。关注信号不会限制遍历。',['rtlwire/core.py:search','rtlwire/core.py:analyze','rtlwire/core.py:enumerate_paths']);
}
// 10 — read-only
{
const s=base('09 / ELAB-ONLY GUARANTEE','只读编译库：入口、运行时与审计共同约束','这些措施约束本工具的加载流程，不等同于任意程序的通用安全沙箱。');
const items=[['01','入口限制','只接受已有 elab；不接收 RTL filelist、宏、include 或参数覆盖。'],['02','只读挂载','在独立 mount namespace 内，把输入库与解析到的依赖目录只读挂载。'],['03','源码访问保护','LD_PRELOAD 保护库拒绝常见 RTL 源文件后缀的打开请求。'],['04','访问与完整性审计','strace 记录文件 / 进程访问；前后 SHA256 比较确认输入未改动。']];
items.forEach((v,i)=>{const x=.67+(i%2)*6.3,y=2.14+Math.floor(i/2)*2.18;box(s,x,y,5.98,1.91,i===3?C.sage:C.white);pill(s,v[0],x+.22,y+.22,.45);txt(s,v[1],x+.87,y+.18,4.8,.4,20,C.ink,{bold:true});body(s,v[2],x+.23,y+.88,5.5,.8,16,C.muted);});
note(s,'如果库依赖随附 TDC/library 编译产物，输入必须完整；缺少数据时失败而不是读取源码。工具会编译自己的 C 文件保护库与 C++ FSDB 适配器，这不属于 RTL 编译。NPI 只读挂载路径当前需要 mount namespace 权限。',['rtlwire/cli.py:package_manifest','rtlwire/cli.py:audit_access','npi/readonly_run.sh','npi/source_guard.c']);
}
// 11 — canvas implementation
{
const s=base('10 / ARCHITECTURE RENDERING','架构图不是平铺节点图，而是真实层次的投影','布局与绘制共用图形元素，界面选中可关联到连接见证。');
photo(s,'trace',.62,2.12,7.35,4.41);
const list=[['包含树','从真实 parent 构建嵌套容器'],['同级布局','按可见连接分组和排序'],['端口与布线','端口放在边界，正交路径避开其他模块'],['共享图元','Tk 与 SVG 共用矩形、文字、端口和连线']];
list.forEach((a,i)=>{let y=2.25+i*1.06;txt(s,a[0],8.37,y,4.22,.3,18,C.ink,{bold:true});body(s,a[1],8.37,y+.42,4.22,.5,14.5,C.muted);});
note(s,'architecture.py 负责包含树、同级列布局、端口位置和正交寻路；显示连线转角进行局部圆滑化，但原始连接与见证不变。primitives 同时供 Tk Canvas 和 SVG 导出使用。',['rtlwire/architecture.py:layout','rtlwire/architecture.py:orthogonal_route','rtlwire/architecture.py:primitives','rtlwire/gui.py:ArchitectureCanvas']);
}
// 12 — wave UI
{
const s=base('11 / POWER WORKSPACE','两个层次，独立配置控制信号与 RPT','枚举输出口、检查分组规则，并在同一界面查看周期波形与首次异常。');
photo(s,'waveform',.59,2.02,8.25,4.75);
row(s,'1','每层独立输入','层次、iso_en、power_down、\nRPT 文件和三类关键词。',9.13,2.13,3.52);
row(s,'2','自动读取输出口','只使用 FSDB 已记录且具有\n方向信息的本层 output。',9.13,3.67,3.52);
row(s,'3','定位具体问题','选择输出口，在完整周期中\n查看首个异常及实际 / 期望值。',9.13,5.21,3.52);
note(s,'截图使用独立故障测试 FSDB，因此显示 8 个 PASS 和 6 个 FAIL。这表明检查器识别到了注入故障，不代表程序测试失败。两层可以使用不同的 RPT 文件和不同的组名关键词。',['rtlwire/wave_gui.py:WavePanel','examples/power_groups_faults.json']);
}
// 13 — waveform timing
{
const s=base('12 / TIMING MODEL','四个边沿定义完整周期，前后各留 5 ns','示例：A=20 ns，B=35 ns，C=70 ns，D=90 ns；显示窗口为 15–95 ns。');
const x0=2.2,x1=12.48,y0=2.5,xx=t=>x0+(t-15)/80*(x1-x0);
[['钳位区间',20,35,C.sage],['掉电区间 · 全 X',35,70,C.sand],['恢复后仍隔离',70,90,C.light]].forEach(a=>{box(s,xx(a[1]),2.27,xx(a[2])-xx(a[1])-.03,3.38,a[3],a[3],.1);txt(s,a[0],xx(a[1])+.05,2.47,xx(a[2])-xx(a[1])-.14,.35,13,C.ink,{align:'center'});});
txt(s,'iso_en',.7,3.16,1.28,.35,18,C.accent,{fontFace:MONO});txt(s,'power_down',.7,4.22,1.43,.35,17,C.accent,{fontFace:MONO});
route(s,[[xx(15),3.78],[xx(20),3.78],[xx(20),3.2],[xx(90),3.2],[xx(90),3.78],[xx(95),3.78]],C.accent,false,false,2.2);
route(s,[[xx(15),4.3],[xx(35),4.3],[xx(35),4.88],[xx(70),4.88],[xx(70),4.3],[xx(95),4.3]],C.accent,false,false,2.2);
[['A',20,'iso↑'],['B',35,'pd↓'],['C',70,'pd↑'],['D',90,'iso↓']].forEach(a=>{line(s,xx(a[1]),2.96,xx(a[1]),5.9,'C1B7A7',1,false,true);txt(s,a[0]+' · '+a[1],xx(a[1])-.32,5.81,.64,.3,12,C.accent,{bold:true,align:'center'});});
txt(s,'5 ns 裕量',1.9,6.22,1.4,.28,12,C.muted);txt(s,'5 ns 裕量',11.68,6.22,1.1,.28,12,C.muted);
pill(s,'Idle = A 之前最后一个已知采样；Clamp = A 时刻所有已记录更新后的最终值。',2.97,6.34,8.5,C.ink,C.nav);
note(s,'时间坐标使用 FSDB 原生整数 tick，单位换算用 Decimal。周期要求严格 A<B<C<D；若文件不够长，5 ns 裕量裁剪到文件真实范围。缺少完整周期标记 UNKNOWN；同一时刻发生多个不同边沿不能当作严格有序完整周期。',['rtlwire/wave_core.py:find_cycles','rtlwire/wave_core.py:check_output','rtlwire/wave_core.py:analyze']);
}
// 14 — RPT
{
const s=base('13 / RPT CONFIGURATION','组名由用户定义，关键词负责分类','组名包含关键词，区分大小写；每组只能匹配一种类型。左侧为 RPT 节选。');
code(s,'ALPHA_KEEP1  { one_out, one_bus }\n\nALPHA_KEEP0  { zero_out, zero_bus }\n\nALPHA_BYPASS { free_out, free_bus }',.66,2.2,6.05,2.54,18);
table(s,['用户输入关键词','识别类型'],[['KEEP1','钳 1'],['KEEP0','钳 0'],['BYPASS','不钳位']],.66,5.02,[3.28,2.77],.42,13.5);
photo(s,'rpt',7.08,2.18,5.57,3.99);
txt(s,'各层可使用不同文件与关键词。支持中文 / 英文逗号、空格、换行、注释及位 / 片选。',7.19,6.36,5.3,.42,12.5,C.muted);
note(s,'关键词是字面子串，不是正则表达式。解析器不执行 RPT 中的命令；空组允许，但嵌套组不允许。未匹配组或命中多个关键词属于配置错误，预览/运行时直接报错。端口存在性与方向仍来自 FSDB。',['rtlwire/wave_groups.py:parse_rpt','rtlwire/wave_gui.py:GroupDialog']);
}
// 15 — bit masks
{
const s=base('14 / BIT-LEVEL GROUPING','一根总线可以按位混合分组','检查规则落实到 FSDB 声明的位号，而不是仅按信号名字归类。');
code(s,'KEEP1  { mixed_bus[3] }\nKEEP0  { mixed_bus[2] }\nBYPASS { mixed_bus[1:0] }',.68,2.26,5.1,2.01,20);
txt(s,'期望掩码',.8,4.72,2.8,.35,20,C.ink,{bold:true});txt(s,'10--',.82,5.23,4.62,.86,46,C.accent,{fontFace:MONO,bold:true});
const bits=[['3','1','钳 1',C.light],['2','0','钳 0',C.sage],['1','—','不钳位',C.nav],['0','—','不钳位',C.nav]];
bits.forEach((a,i)=>{let x=6.37+i*1.53;box(s,x,2.35,1.32,2.16,a[3],a[3],.13);txt(s,'bit '+a[0],x+.12,2.6,1.08,.3,14,C.muted,{align:'center'});txt(s,a[1],x+.12,3.1,1.08,.7,36,C.ink,{fontFace:MONO,align:'center'});txt(s,a[2],x+.12,3.99,1.08,.3,14,C.ink,{align:'center'});});
panel(s,'只比较需要钳位的位','钳位相关规则：只比较 bit 3 和 bit 2。\n掉电全 X 规则：检查 bit 3…0 全部位。',6.38,4.89,5.9,1.62,C.white);
note(s,'波形四态字符串按声明 left/right 映射为位号，支持升序与降序声明。重复归组、位越界、未覆盖输出位使用 UNKNOWN 问题记录，未明确分组位的掩码为 ?。- 表示已明确不钳位，含义与 ? 不同。',['rtlwire/wave_groups.py:resolve_groups','rtlwire/wave_groups.py:bit_numbers','rtlwire/wave_core.py:check_output','tests/test_wave_groups.py']);
}
// 16 — rule matrix
{
const s=base('15 / RULE MATRIX','五项规则覆盖隔离、掉电与恢复','“不钳位”跳过钳位相关规则，掉电期间仍必须全 X。');
const rows=[['A 前 idle = A 最终值','检查','检查',{t:'SKIP',c:C.muted}],['[A,B) 符合期望值',{t:'全 1',c:C.accent},{t:'全 0',c:C.teal},{t:'SKIP',c:C.muted}],['[A,B) 保持稳定','检查','检查',{t:'SKIP',c:C.muted}],['[B,C) 掉电值',{t:'全 X',c:C.amber},{t:'全 X',c:C.amber},{t:'全 X',c:C.amber}],['[C,D) 恢复后的隔离值','全 1','全 0',{t:'SKIP',c:C.muted}]];
table(s,['检查项','钳 1','钳 0','不钳位'],rows,.72,2.13,[5.44,2.08,2.08,2.28],.62,17);
box(s,.78,6.2,11.79,.49,C.light,C.light,.12);txt(s,'由于还检查 idle 与钳位值相等：钳 1 组通过时，相关位的 idle 也须为 1；钳 0 同理。',.98,6.29,11.37,.3,13.5,C.ink);
note(s,'内部规则名为 idle_equal、clamp_expected、clamp_stable、off_x、recovery_expected。所有区间使用左闭右开，因此 B 时刻的掉电变化不计入钳位稳定性，C 时刻回到恢复后的隔离检查。SKIP 不等于 PASS。',['rtlwire/wave_core.py:RULES','rtlwire/wave_core.py:check_output','docs/rpt_groups_040.md']);
}
// 17 — settled semantics
{
const s=base('16 / EDGE SEMANTICS','同一时间戳取最终值，数据不足明确报未知','这是已确认的判定口径；短暂的已记录 delta 更新作为提示。');
txt(s,'同一时刻 20 ns 的已记录更新',.78,2.2,5.5,.38,20,C.ink,{bold:true});
[['0',C.nav],['X',C.sand],['1',C.sage]].forEach((a,i)=>{box(s,.84+i*1.8,3.02,1.38,1.26,a[1],a[1],.16);txt(s,a[0],.98+i*1.8,3.24,1.1,.65,35,C.ink,{fontFace:MONO,align:'center'});if(i<2)line(s,2.28+i*1.8,3.63,2.57+i*1.8,3.63,C.teal,1.6,true);});
pill(s,'最终用于判定：1',1.95,4.63,2.65,C.teal,C.sage);body(s,'delta 作为提示保留。FSDB 未保存的\n瞬态变化，不能由工具事后重建。',.91,5.37,5.38,.9,16,C.muted);
const statuses=[['PASS','规则已经验证通过',C.teal,C.sage],['FAIL','有明确违例和首个失败位置',C.red,C.rose],['UNKNOWN','边沿、方向、波形或分组覆盖不足',C.amber,C.sand],['SKIP','该规则对不钳位的信号位不适用',C.muted,C.nav]];
statuses.forEach((a,i)=>{let y=2.22+i*1.01;pill(s,a[0],7.01,y,1.45,a[2],a[3]);txt(s,a[1],8.72,y-.015,3.81,.55,15.5,C.ink);});
note(s,'load_native 对同一时间戳保留最后一次已记录值，另外记录 deltas；Series 提供时点和区间查询。UNKNOWN 包括缺少完整周期、方向或值、控制信号 X/Z、dump-off 空洞、未分组/重复归组等。状态聚合保留确定 FAIL，不用 UNKNOWN 掩盖已经证实的失败。',['rtlwire/wave_core.py:load_native','rtlwire/wave_core.py:Series','rtlwire/wave_core.py:status_of']);
}
// 18 — FSDB engine
{
const s=base('17 / FSDB READER','C++ Reader 提取事件，Python 执行检查','使用本机安装的 Reader SDK，输出结构化记录，不把 FSDB 转成推测的设计端口表。');
const data=[['读取树与元数据','ffrReadScopeVarTree2','scope / module / direction / 位号'],['选择记录对象','控制信号 + 直接 output','严格匹配层次与 output 方向'],['遍历四态事件','ffrCreateVCTraverseHandle','64 位时间戳与 0 / 1 / X / Z'],['标准化和判定','JSONL → Series → 周期状态机','时间单位换算、掩码规则、首个异常']];
data.forEach((v,i)=>{let y=2.1+i*1.12;box(s,.73,y,11.88,.91,i%2?C.white:C.nav);pill(s,String(i+1),.95,y+.27,.43);txt(s,v[0],1.61,y+.17,3.15,.36,18,C.ink,{bold:true});txt(s,v[1],4.97,y+.12,7.21,.32,16,C.teal,{fontFace:MONO});txt(s,v[2],4.99,y+.52,7.2,.25,12.5,C.muted);});
note(s,'Reader 保留 scope/variable tree 的方向元数据，只加载所选控制信号和对应 scope 的 output。原生 tick 由 tag H/L 合为 uint64，Python 用整数和 Decimal 做单位换算；有事件数、信号数、位宽和数据量上限。没有 dump 的端口不能单靠 FSDB 枚举出来。',['wave/fsdb_reader.cpp:tree','wave/fsdb_reader.cpp:main','rtlwire/wave_cli.py','rtlwire/wave_core.py']);
}
// 19 — architecture runtime
{
const s=base('18 / SOFTWARE ARCHITECTURE','界面、任务进程和分析内核分层','耗时的 EDA / FSDB 读取在后台运行，GUI 通过事件队列接收进度与结果。');
box(s,.69,2.13,3.44,3.84,C.light,C.light,.17);txt(s,'Tk / ttk 视图',.94,2.41,2.94,.43,23,C.ink,{bold:true});body(s,'gui.py / theme.py\nwave_gui.py\n\n输入、表格、选择联动\n缩放、平移、SVG 导出',.96,3.15,2.93,2.28,17,C.ink);
box(s,4.76,2.13,3.56,3.84,C.white);txt(s,'任务与 CLI',5.03,2.41,3.04,.43,23,C.ink,{bold:true});body(s,'jobs.py\ncli.py / wave_cli.py\n\n独立运行目录\n进度事件、取消、审计',5.04,3.15,3.02,2.28,17,C.ink);
box(s,8.96,2.13,3.66,3.84,C.sage,C.sage,.17);txt(s,'提取与规则内核',9.2,2.41,3.18,.43,23,C.ink,{bold:true});body(s,'NPI / FSDB Reader\ncore.py / wave_core.py\n\n原始事实、图算法\n分组、时序与状态聚合',9.22,3.15,3.16,2.28,17,C.ink);
line(s,4.17,3.98,4.69,3.98,C.accent,2,true);line(s,8.36,3.98,8.89,3.98,C.teal,2,true);
txt(s,'共享绘图层：architecture.py / wave_plot.py    →    Tk Canvas + SVG',.89,6.39,11.59,.34,17,C.muted,{align:'center'});
note(s,'AnalysisJob 的后台线程启动本地 CLI 子进程，按 JSON phase/log/done 事件更新 GUI。取消通过 cancel 文件和任务状态协调，保留已产生的日志与审计。WaveAnalysisJob 复用同一机制，只更换 CLI 模块。',['rtlwire/jobs.py','rtlwire/gui.py:poll','rtlwire/wave_gui.py:poll']);
}
// 20 — evidence
{
const s=base('19 / VERIFICATION','用正常、故障和缺失数据，验证检查器行为','数字来自 0.5.0 开发验收记录；它们代表已验证案例，不等于全芯片覆盖率。');
[['62','单元测试'],['9','实际 FSDB GUI 流程'],['6','界面与布局检查']].forEach((a,i)=>{let x=.75+i*4.04;box(s,x,2.16,3.72,1.83,i===1?C.sage:C.white);txt(s,a[0],x+.24,2.37,1.30,.95,52,i===1?C.teal:C.accent,{fontFace:'Georgia'});txt(s,a[1],x+1.64,2.68,1.83,.67,16,C.ink,{bold:true});});
table(s,['独立测试波形','通过','失败','未知'],[['三类分组 + 混合总线','14','0','0'],['注入 6 类输出违例','8',{t:'6',c:C.red},'0'],['重复 / 未分组输出','12','0',{t:'2',c:C.amber}]],.75,4.42,[7.4,1.5,1.5,1.4],.51,15);
txt(s,'额外验证：普通账号读取只读 FSDB / RPT、打包后启动、旧报告兼容、SVG 导出。',.85,6.63,11.8,.23,12.5,C.muted);
note(s,'单元测试构成为 core 10、architecture 7、wave 22、wave_groups 23，共 62。三类分组样例为两个层次各 7 个输出。故障包括钳位值、稳定性、idle、恢复、不钳位掉电值和混合位掉电值等问题。界面验收包括 1600×960 三条波形可见、缩放、1280×800 布局和配置对话框。',['tests/test_core.py','tests/test_architecture.py','tests/test_wave.py','tests/test_wave_groups.py','docs/verification_summary.json']);
}
// 21 — deployment boundaries
{
const s=base('20 / DEPLOYMENT & LIMITS','Linux 本机部署，支持范围清楚可见','已验证环境：CentOS 7 · Python 3.6.8 · Tk 8.5 · Verdi O-2018.09-SP2。');
panel(s,'运行条件','GUI：Python 标准库 + Tk + 中文字体\n\nELAB：本机 Verdi / NPI 与许可证\n\nFSDB：本机 Reader SDK、编译器与 strace',.68,2.17,5.84,3.82,C.white);
panel(s,'当前支持边界','时序单元明确停止，不凭空跨越 D → Q\n\n复杂或不确定的组合映射报告停止 / 未知\n\nFSDB 只覆盖已 dump 且具方向的直接 output',6.82,2.17,5.84,3.82,C.nav);
txt(s,'NPI 只读挂载需要相应权限；FSDB 分支可由普通账号运行。不同 SDK 版本需确认兼容性。',.84,6.35,11.84,.48,15,C.muted);
note(s,'当前组合穿越白名单为 Assign、Buf、Neg、And、Or、Xor、Nand。接口 modport、VHDL、复杂波形类型和完整芯片性能不在本版已验证范围。GUI 保留系统窗口装饰；应用内容使用原生 Tk 圆角组件。',['README.md','rtlwire/cli.py','wave/fsdb_reader.cpp','docs/power_wave.md']);
}
// 22 — workflow
{
const s=base('21 / USING THE TOOL','配置 → 检查 → 定位 → 保存','每一次运行产生独立目录，便于复查配置、结论与证据。');
const a=[['配置','ELAB 或 FSDB\n层次 / 信号 / RPT'],['检查','后台执行\n查看进度与日志'],['定位','架构对象或波形\n首个异常及完整路径'],['保存','JSON / CSV / SVG\n配置与结果目录']];
a.forEach((v,i)=>{const x=.89+i*2.98;box(s,x,2.42,2.59,2.28,i%2?C.white:C.nav);pill(s,String(i+1),x+.20,2.66,.44);txt(s,v[0],x+.20,3.2,2.19,.43,24,C.ink,{bold:true});body(s,v[1],x+.20,3.84,2.19,.67,14.5,C.muted);if(i<3)line(s,x+2.63,3.6,x+2.93,3.6,C.teal,1.8,true);});
code(s,'sh rtlwire-studio --result validation/reach_dual_io\nsh rtlwire-studio --result validation/wave_groups_faults',.89,5.4,11.53,1.02,17);
note(s,'保存结果可以离线查看，不需要再次打开 EDA 工具。代码仓库提供独立 FSDB 示例和整理过的历史架构记录，elab 查询模板需要替换成本机已有编译库路径。运行中的检查可取消，输入与结果存放在独立目录。',['README.md','rtlwire/jobs.py','rtlwire/gui.py','rtlwire/wave_gui.py']);
}
// 23 — implementation index
{
const s=base('APPENDIX / CODE MAP','从功能定位到实现文件','用于代码评审、维护和后续扩展。图形与核心规则均可独立阅读。');
table(s,['功能','主要实现','关键职责'],[
 ['ELAB 提取','npi/extract.tcl','枚举实例 / 端口，追踪 Driver / Load'],
 ['接线分析','rtlwire/core.py','最近祖先归属、BFS、路径枚举'],
 ['架构绘图','rtlwire/architecture.py','真实包含、布局、正交布线与 SVG'],
 ['FSDB 读取','wave/fsdb_reader.cpp','方向与位号、原生 tick、四态事件'],
 ['RPT 与规则','wave_groups.py / wave_core.py','按位归组、周期状态机和区间检查'],
 ['界面与任务','gui.py / wave_gui.py / jobs.py','用户输入、异步进度、选择联动'],
 ['只读与审计','cli.py / wave_cli.py / source_guard.c','输入保护、日志、SHA256 与资源限制']
 ],.71,2.12,[2.43,4.43,5.02],.56,14.5);
note(s,'这页是导航索引，不是完整调用图。使用演讲者备注中的源文件和函数名可以进一步核对每项结论。代码与示例以随附 GitHub 仓库为准；原始供应商 NPI 手册、SDK 与许可证不属于仓库内容。',['rtlwire/','npi/','wave/']);
}
// 24 — closing and delivery
{
const s=base('DELIVERY / RTLWIRE STUDIO','连接有路径，判定有依据。','以编译库与波形记录为事实来源，把检查过程做成可复查的工程工具。',true);
txt(s,'两类接线检查\n三类输出分组\n一个本地桌面工作区',.75,2.42,6.7,2.18,32,'FAF9F5',{bold:true});
box(s,8.2,2.44,4.42,2.91,'3A3D35','4B4D43',.18);
txt(s,'交付内容',8.49,2.73,3.8,.37,21,'E8B69B',{bold:true});body(s,'源码与可运行示例\nPPT / PDF 与实际界面截图\n配置说明与核心测试',8.5,3.45,3.82,1.28,18,'E7E3D7');
txt(s,'github.com/ysyx-22040210-yudian/rtlwire-studio',.79,6.09,11.73,.5,20,'D5A68B',{fontFace:MONO,hyperlink:{url:'https://github.com/ysyx-22040210-yudian/rtlwire-studio'}});
note(s,'交付版本为 0.5.0。公开仓库链接经发布后核验；PPT 和 PDF 放在 docs/presentations，真实 Linux 窗口截图放在 docs/images。',['README.md','docs/presentations/']);
}

for(const a of audit){if(a.x<0||a.y<0||a.x+a.w>W+.01||a.y+a.h>H+.01)throw new Error('Out of slide: '+JSON.stringify(a));}
fs.writeFileSync(path.join(__dirname,'slide_content.json'),JSON.stringify({version:'0.5.0',slideCount:slides.length,text:audit},null,2));
pptx.writeFile({fileName:path.join(__dirname,'RTLWire_Studio_Functions_and_Architecture_v0.5.0.pptx')});
console.log('Created '+slides.length+' slides');
