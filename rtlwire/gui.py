"""RTLWire Studio: native Tk/ttk desktop application (Tk 8.5+, Python 3.6+)."""
import argparse
import copy
import json
import os
from pathlib import Path
import queue
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont

from . import __version__
from .architecture import build_architecture, primitives, svg_architecture, witness_highlights
from .jobs import AnalysisJob, ROOT, default_environment, load_result, validate_environment


from .theme import C, Action, Surface, rounded, install_styles


def input_names(value):
    """Multiline fields also accept the comma-separated format used by old queries."""
    return list(dict.fromkeys(x.strip() for x in value.replace(',', '\n').splitlines() if x.strip()))


def port_direction(value):
    return {'npiNlInput':'输入 IN', 'npiNlOutput':'输出 OUT', 'npiNlInout':'双向 INOUT'}.get(value, '—')


class ArchitectureCanvas(tk.Frame):
    def __init__(self, parent, font_family, on_select, on_zoom):
        tk.Frame.__init__(self, parent, bg=C['canvas'])
        self.family, self.on_select, self.on_zoom = font_family, on_select, on_zoom
        self.canvas = tk.Canvas(self, bg=C['canvas'], highlightthickness=0, bd=0)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        sx = ttk.Scrollbar(self, orient='horizontal', command=self.canvas.xview)
        sy = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        # Panning/zooming is the primary canvas navigation; omit native beveled scrollbars.
        self.canvas.configure(xscrollcommand=sx.set, yscrollcommand=sy.set)
        self.rowconfigure(0, weight=1); self.columnconfigure(0, weight=1)
        self.scene, self.scale, self.selected, self.highlight = None, 1.0, None, None
        self.auto_fit,self.fit_job,self.offset=True,None,(0,0)
        self.item_keys, self._pressed, self._fit_pending = {}, None, False
        self.canvas.bind('<ButtonPress-1>', self.press)
        self.canvas.bind('<B1-Motion>', self.drag)
        self.canvas.bind('<ButtonRelease-1>', self.release)
        self.canvas.bind('<MouseWheel>', self.wheel)
        self.canvas.bind('<Button-4>', lambda e: self.zoom(1.12, e.x, e.y))
        self.canvas.bind('<Button-5>', lambda e: self.zoom(1/1.12, e.x, e.y))
        self.canvas.bind('<Configure>', self.resized)
        self.canvas.bind('<Motion>', self.motion)
        self.tooltip = None
        self._hover_key = None
        self._tooltip_job = None
        self.empty()

    def empty(self):
        self.canvas.delete('all')
        w,h=max(400,self.canvas.winfo_width()),max(250,self.canvas.winfo_height())
        x,y=w/2,h/2
        rounded(self.canvas,x-100,y-97,x+100,y-17,18,fill='#eeece3',outline=C['border'])
        for dx in (-53,53):
            rounded(self.canvas,x+dx-27,y-75,x+dx+27,y-37,10,fill=C['surface'],outline='#c9d4cc')
        self.canvas.create_line(x-26,y-56,x+26,y-56,fill=C['accent'],width=2,arrow=tk.LAST)
        self.canvas.create_text(x,y+13,text='层次架构，从设计事实开始',font=(self.family,18,'bold'),fill=C['ink'])
        self.canvas.create_text(x,y+51,text='打开已有结果，或配置 elab 后运行检查。',font=(self.family,10),fill=C['muted'])
        self.canvas.create_text(x,y+78,text='包含框显示真实层次 · 点击对象查看连接证据',font=(self.family,9),fill=C['muted'])

    def set_scene(self, scene):
        self.scene, self.selected, self.highlight = scene, None, None
        self.auto_fit=True
        self.after(100,self.fit)

    def resized(self, event):
        if not self.scene:self.empty();return
        if self.auto_fit and self.scene:
            if self.fit_job:self.after_cancel(self.fit_job)
            self.fit_job=self.after(100,self.fit)

    def fit(self):
        self.fit_job=None;self.auto_fit=True
        if not self.scene:
            return
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w < 50 or h < 50:
            self._fit_pending = True
            return
        self.scale = max(.2, min(1.5, (w-24)/self.scene['width'], (h-24)/self.scene['height']))
        self.draw()
        self.canvas.xview_moveto(0); self.canvas.yview_moveto(0)

    def zoom(self, factor, x=None, y=None):
        if not self.scene:
            return
        x = self.canvas.winfo_width()/2 if x is None else x
        y = self.canvas.winfo_height()/2 if y is None else y
        old = self.scale
        world_x, world_y = (self.canvas.canvasx(x)-self.offset[0])/old, (self.canvas.canvasy(y)-self.offset[1])/old
        self.auto_fit=False
        self.scale = max(.18, min(2.8, old * factor))
        self.draw()
        self.canvas.xview_moveto(max(0, (world_x*self.scale+self.offset[0]-x)/self.scroll_size[0]))
        self.canvas.yview_moveto(max(0, (world_y*self.scale+self.offset[1]-y)/self.scroll_size[1]))

    def wheel(self, event):
        self.zoom(1.12 if event.delta > 0 else 1/1.12, event.x, event.y)
        return 'break'

    def focus_module(self, name):
        if not self.scene or name not in self.scene['boxes']:
            return False
        self.selected = 'module:' + name
        self.auto_fit=False
        box = self.scene['boxes'][name]
        self.scale = min(1.4, max(.35, (self.canvas.winfo_width()-100)/box['w'], .6))
        self.draw()
        self.canvas.xview_moveto(max(0, (box['x']*self.scale+self.offset[0]-35)/self.scroll_size[0]))
        self.canvas.yview_moveto(max(0, (box['y']*self.scale+self.offset[1]-40)/self.scroll_size[1]))
        self.on_select(self.selected)
        return True

    def draw(self):
        if not self.scene:
            return
        self.hide_tooltip()
        self.canvas.delete('all'); self.item_keys = {}
        s = self.scale
        for x in range(16,self.canvas.winfo_width(),24):
            for y in range(16,self.canvas.winfo_height(),24):
                self.canvas.create_oval(x,y,x+1,y+1,fill='#e5e1d6',outline='')
        ox=max(12,(self.canvas.winfo_width()-self.scene['width']*s)/2)
        oy=max(12,(self.canvas.winfo_height()-self.scene['height']*s)/2)
        self.offset=ox,oy
        for p in primitives(self.scene, self.selected, self.highlight):
            key = p.get('key')
            if p['kind'] in ('rect', 'oval'):
                coords = [p['x']*s+ox, p['y']*s+oy, (p['x']+p['w'])*s+ox, (p['y']+p['h'])*s+oy]
                opts = dict(fill=p['fill'], outline=p.get('stroke', ''), width=max(.7, p.get('width', 1)*s))
                item = rounded(self.canvas, *coords, radius=p.get('radius', 4)*s, **opts) if p['kind']=='rect' else self.canvas.create_oval(*coords, **opts)
            elif p['kind'] == 'text':
                anchor = {'start':'w','middle':'center','end':'e'}[p['anchor']]
                pixels = max(8, int(round(p['size'] * s)))
                label=p['text']
                if p.get('max_width'):
                    measure=tkfont.Font(family=self.family,size=-pixels,weight='bold' if p['bold'] else 'normal')
                    maximum=max(10,p['max_width']*s)
                    if measure.measure(label)>maximum:
                        while label and measure.measure(label+'…')>maximum:label=label[:-1]
                        label+='…'
                item = self.canvas.create_text(p['x']*s+ox, p['y']*s+oy, text=label, anchor=anchor,
                                               font=(self.family, -pixels, 'bold' if p['bold'] else 'normal'), fill=p['fill'])
            else:
                points = [v*s+(ox if i==0 else oy) for xy in p['points'] for i,v in enumerate(xy)]
                opts = dict(fill=p['fill'], width=max(1, p['width']*s), joinstyle=tk.ROUND)
                if p.get('dash'):
                    opts['dash'] = (max(2,int(5*s)), max(2,int(4*s)))
                if p.get('arrow'):
                    opts.update(arrow=tk.LAST, arrowshape=(max(5,7*s),max(6,8*s),max(2,3*s)))
                item = self.canvas.create_line(*points, **opts)
            if key:
                self.item_keys[item] = key
        self.scroll_size=(self.scene['width']*s+2*ox,self.scene['height']*s+2*oy)
        self.canvas.configure(scrollregion=(0,0,self.scroll_size[0],self.scroll_size[1]))
        self.on_zoom('%d%%' % round(s*100))

    def hit(self, x, y):
        cx, cy = self.canvas.canvasx(x), self.canvas.canvasy(y)
        for item in reversed(self.canvas.find_overlapping(cx-4,cy-4,cx+4,cy+4)):
            if item in self.item_keys:
                return self.item_keys[item]
        return None

    def press(self, event):
        self.hide_tooltip()
        self._pressed = (event.x,event.y)
        self.canvas.scan_mark(event.x,event.y)

    def drag(self, event):
        self.auto_fit=False
        self.canvas.scan_dragto(event.x,event.y,gain=1)
        self.canvas.configure(cursor='fleur')

    def release(self, event):
        self.canvas.configure(cursor='arrow')
        if self._pressed and abs(event.x-self._pressed[0])+abs(event.y-self._pressed[1])<6:
            self.selected = self.hit(event.x,event.y)
            self.draw()
            self.on_select(self.selected)
        self._pressed = None

    def motion(self, event):
        key = self.hit(event.x,event.y)
        if key == self._hover_key:
            return
        self.hide_tooltip(); self._hover_key = key
        if key:
            self._tooltip_job = self.after(650, lambda: self.show_tooltip(key, event.x_root, event.y_root))

    def show_tooltip(self, key, x, y):
        self._tooltip_job = None
        if self.scene is None:
            return
        if key.startswith('module:'):
            name = key[7:]; b = self.scene['boxes'][name]
            message = name + '\nmodule: ' + b['module'] + '\n归属: ' + (b['owner_scope'] or '范围外')
        elif key in self.scene['pins']:
            p = self.scene['pins'][key]; message = p['name'] + '\n实际层次: ' + p['scope']
        else:
            e = next((e for e in self.scene['connections'] if e['id']==key), None)
            if not e:
                return
            message = self.scene['pins'][e['source']]['name'] + '\n→ ' + self.scene['pins'][e['target']]['name']
            if e['signals']:
                message += '\n信号: ' + ', '.join(s['name'] for s in e['signals'])
        t = tk.Toplevel(self); t.overrideredirect(True); t.geometry('+%d+%d' % (x+14,y+18))
        tk.Label(t,text=message,bg=C['ink'],fg='#ffffff',padx=12,pady=9,justify='left',font=(self.family,10)).pack()
        self.tooltip = t

    def hide_tooltip(self):
        if self._tooltip_job:
            self.after_cancel(self._tooltip_job); self._tooltip_job = None
        if self.tooltip:
            self.tooltip.destroy(); self.tooltip = None


class Studio(tk.Tk):
    def __init__(self, result=None, config=None, environment=None, geometry=None):
        tk.Tk.__init__(self)
        self.title('RTLWire Studio · RTL 穿线与掉电波形检查')
        width=min(1600,self.winfo_screenwidth()-70);height=min(960,self.winfo_screenheight()-100)
        self.geometry(geometry or '%dx%d+30+30'%(max(1180,width),max(760,height))); self.minsize(1180,760)
        self.configure(bg=C['bg'])
        families = set(tkfont.families(self))
        self.family = next((x for x in ['Microsoft YaHei UI','Microsoft YaHei','WenQuanYi Micro Hei','Noto Sans CJK SC','DejaVu Sans'] if x in families), 'TkDefaultFont')
        self.display_family=next((x for x in ['Georgia','Noto Serif','DejaVu Serif'] if x in families),self.family)
        self.font = (self.family,10); self.small = (self.family,9)
        self.option_add('*Font', self.font)
        self.option_add('*TCombobox*Listbox.background','#ffffff')
        self.option_add('*TCombobox*Listbox.foreground',C['ink'])
        self.env = default_environment()
        self.settings_path = Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'rtlwire'/'studio.json'
        if self.settings_path.exists():
            try:
                saved=json.loads(self.settings_path.read_text(encoding='utf-8'))
                self.env.update({k:v for k,v in saved.items() if k in self.env})
            except (OSError,ValueError):
                pass
        if environment:
            self.env.update(environment)
        self.data, self.scene, self.job = None, None, None
        self.wave_panel = None
        self.active_workspace = 'design'
        self.events, self._loading, self._closing = queue.Queue(), False, False
        self.base_config = {}
        self.vars = {name:tk.StringVar() for name in ('database','boundary','sources','modules','mode','traversal')}
        self.status = tk.StringVar(value='就绪 · 设计数据仅来自已编译 elab')
        self.zoom_text = tk.StringVar(value='100%')
        self.breadcrumb = tk.StringVar(value='工作区  /  新建检查')
        self.result_badge = tk.StringVar(value='尚未运行')
        self.env_badge = tk.StringVar(value=self.environment_label())
        self.query_expanded = True
        self.canvas_focused=False
        self._styles(); self._build()
        for value in self.vars.values():
            value.trace('w', lambda *a: self.mark_dirty())
        self.scopes.bind('<<Modified>>', self.text_dirty)
        self.observes.bind('<<Modified>>', self.text_dirty)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.bind('<Control-o>', lambda e:self.open_result())
        self.bind('<Control-s>', lambda e:self.current_workspace().save_config())
        self.bind('<F5>', lambda e:self.current_workspace().start_run())
        self.bind('<Escape>',lambda e:self.toggle_canvas_focus() if self.canvas_focused and self.active_workspace=='design' else None)
        self.after(100,self.poll)
        self.set_config({'design': {'input_kind': 'elab', 'elab_path': ''},
                         'query': {'mode': 'reach'}, 'policy': {'traversal': 'wire_only'}})
        self.result_badge.set('尚未运行')
        if config:self.load_config_path(config)
        if result:
            self.after(100,lambda:self.open_result(result))

    def environment_label(self):
        return '本机 Linux · Verdi / NPI' if self.env.get('verdi_home') else '本机 Linux · 待配置 Verdi'

    def _styles(self):
        install_styles(self)

    def label(self,parent,text,size=10,color=None,bold=False,**kw):
        return tk.Label(parent,text=text,font=(self.family,size,'bold' if bold else 'normal'),
                        bg=parent.cget('bg'),fg=color or C['ink'],**kw)

    def _build(self):
        self.columnconfigure(1,weight=1); self.rowconfigure(0,weight=1)
        nav=tk.Frame(self,bg=C['nav'],width=228); nav.grid(row=0,column=0,sticky='nsew'); nav.grid_propagate(False)
        nav.columnconfigure(0,weight=1); nav.rowconfigure(6,weight=1)
        logo=tk.Canvas(nav,height=77,bg=C['nav'],highlightthickness=0);logo.grid(row=0,column=0,sticky='ew')
        rounded(logo,20,23,47,50,7,fill=C['purple'],outline='')
        logo.create_line(26,30,37,30,37,43,43,43,fill='#ffffff',width=2)
        logo.create_text(60,35,text='RTLWire',anchor='w',fill=C['ink'],font=(self.display_family,22))
        logo.create_text(22,66,text='STUDIO  /  DESIGN CONNECTIVITY',anchor='w',fill=C['muted'],font=(self.family,8))
        links=tk.Frame(nav,bg=C['nav']);links.grid(row=1,column=0,sticky='ew',padx=14,pady=(16,20))
        self.nav_buttons={}
        for title,command,active,icon in [('设计工作区',self.show_design,True,'design'),('掉电波形检查',self.show_wave,False,'wave'),('打开已有结果',self.open_result,False,'folder'),('运行记录',self.show_history,False,'history')]:
            button=Action(links,title,command,self.font,198,nav=True,icon=icon)
            button.set(active=active);button.pack(fill='x',pady=3);self.nav_buttons[title]=button
        self.label(nav,'设计层次',9,C['muted'],bold=True,anchor='w').grid(row=2,column=0,sticky='ew',padx=23)
        self.search=tk.StringVar()
        search=ttk.Entry(nav,textvariable=self.search,font=self.small,style='Nav.TEntry')
        search.grid(row=3,column=0,sticky='ew',padx=18,pady=(10,8));self.search.trace('w',lambda *a:self.populate_tree())
        self.label(nav,'按实例路径 / module 筛选',8,C['muted'],anchor='w').grid(row=4,column=0,sticky='ew',padx=23)
        self.tree=ttk.Treeview(nav,show='tree',style='Nav.Treeview',selectmode='browse');self.tree.grid(row=6,column=0,sticky='nsew',padx=12,pady=10)
        self.nav_design_widgets=[w for w in nav.winfo_children() if int(w.grid_info().get('row',-1)) in (2,3,4,6)]
        self.wave_help=tk.Frame(nav,bg=C['nav'])
        self.label(self.wave_help,'POWER / ISOLATION',9,C['muted'],True,anchor='w').pack(fill='x',padx=22,pady=(8,16))
        self.label(self.wave_help,'01  选择 FSDB\n\n02  输入层次与控制信号\n\n03  自动检查输出口\n\n04  查看周期与异常',10,C['ink'],anchor='nw',justify='left').pack(fill='x',padx=22)
        self.label(self.wave_help,'判定规则',9,C['muted'],True,anchor='w').pack(fill='x',padx=22,pady=(35,12))
        self.label(self.wave_help,'按 RPT 分组检查\n钳 1 / 钳 0 / 不钳位\n掉电时仍要求全 X\n\n同一时刻取最终值\n前后各 5 ns 裕量',9,C['muted'],anchor='nw',justify='left').pack(fill='x',padx=22)
        self.tree.bind('<<TreeviewSelect>>',self.tree_select);self.tree.bind('<Double-1>',self.tree_focus)
        bottom=Surface(nav,bg=C['nav2'],stroke='',radius=15);bottom.grid(row=7,column=0,sticky='ew',padx=14,pady=16)
        self.label(bottom,'运行环境',8,C['muted'],anchor='w').pack(fill='x',padx=12,pady=(10,0))
        tk.Label(bottom,textvariable=self.env_badge,bg=C['nav2'],fg=C['ink'],font=self.small,anchor='w').pack(fill='x',padx=12,pady=(3,6))
        Action(bottom,'环境设置  ›',self.settings,self.small,170,quiet=True).pack(fill='x',padx=8,pady=(0,7))
        self.label(nav,'v'+__version__+'   ·   ELAB + FSDB',8,C['muted']).grid(row=8,column=0,pady=(0,15))

        self.main=tk.Frame(self,bg=C['bg']);self.main.grid(row=0,column=1,sticky='nsew')
        self.main.rowconfigure(3,weight=1);self.main.columnconfigure(0,weight=1)
        header=tk.Frame(self.main,bg=C['bg'],height=86);header.grid(row=0,column=0,sticky='ew');header.grid_propagate(False)
        tk.Label(header,textvariable=self.breadcrumb,bg=C['bg'],fg=C['muted'],font=self.small).place(x=25,y=12)
        self.label(header,'RTL 层次架构与连通性分析',17,bold=True).place(x=24,y=35)
        right=tk.Frame(header,bg=C['bg']);right.pack(side='right',padx=22,pady=23)
        self.open_button=Action(right,'打开配置',self.open_config,self.font,96);self.open_button.pack(side='left',padx=5)
        self.save_button=Action(right,'保存配置',self.save_config,self.font,96);self.save_button.pack(side='left',padx=5)
        self.run_button=Action(right,'运行检查   F5',self.start_run,self.font,140,primary=True);self.run_button.pack(side='left',padx=(12,0))
        self.query_card=Surface(self.main)
        self.query_card.grid(row=1,column=0,sticky='ew',padx=22,pady=(18,12));self.query_card.columnconfigure(0,weight=1)
        qhead=tk.Frame(self.query_card,bg='#ffffff');qhead.grid(row=0,column=0,sticky='ew',padx=16,pady=(8,6))
        self.label(qhead,'用户输入',11,bold=True).pack(side='left',padx=(3,14))
        self.query_toggle=Action(qhead,'收起输入区  −',self.toggle_query,self.small,112,quiet=True);self.query_toggle.pack(side='right')
        self.mode_buttons={}
        for value,title in [('reach','连接检查'),('trace','连接顺序')]:
            b=Action(qhead,title,lambda v=value:self.choose_mode(v),self.small,100,quiet=True)
            b.pack(side='left',padx=3);self.mode_buttons[value]=b
        tk.Label(qhead,textvariable=self.result_badge,bg='#ffffff',fg=C['muted'],font=self.small).pack(side='right',padx=8)
        self.form=tk.Frame(self.query_card,bg='#ffffff');self.form.grid(row=1,column=0,sticky='ew',padx=18,pady=(3,16))
        for col in range(4):self.form.columnconfigure(col,weight=1,uniform='form')
        self.field(self.form,'Elab 数据库路径',self.vars['database'],0,0,span=2,browse=self.browse_elab)
        self.field(self.form,'遍历边界 · 顶层实例路径',self.vars['boundary'],0,2)
        self.label(self.form,'穿越策略',9,C['muted'],anchor='w').grid(row=0,column=3,sticky='ew',padx=(8,0),pady=(9,4))
        traversal=ttk.Combobox(self.form,textvariable=self.vars['traversal'],state='readonly',values=['直接接线','组合依赖'],width=10)
        traversal.grid(row=1,column=3,sticky='ew',padx=(8,0))
        fields=[('scopes','检查层次 · 每行一个实例全路径',None),
                ('module_input','目标 module 名 · 每行一个定义名','modules'),
                ('source_input','待检查 / 起始信号 · 每行一个','sources'),
                ('observes','沿途关注信号 · 可选','observe')]
        for col,(attribute,title,key) in enumerate(fields):
            pad=(0,6) if col==0 else (8,0)
            self.label(self.form,title,9,C['muted'],anchor='w').grid(row=2,column=col,sticky='ew',padx=pad,pady=(11,4))
            holder=Surface(self.form,radius=10);holder.grid(row=3,column=col,sticky='nsew',padx=pad)
            entry=self.bound_list_input(holder,key) if key in self.vars else self.text_input(holder)
            entry.pack(side='left',fill='both',expand=True,padx=(5,0),pady=5)
            scroll=ttk.Scrollbar(holder,orient='vertical',command=entry.yview);scroll.pack(side='right',fill='y',padx=(0,5),pady=7)
            entry.configure(yscrollcommand=scroll.set)
            setattr(self,attribute,entry)
        self.label(self.form,'信号填写“层次.信号名”；可同时检查多根信号。输入 / 输出方向由 elab 中的目标端口确定。',8,C['muted'],anchor='w').grid(row=4,column=0,columnspan=4,sticky='ew',pady=(8,0))
        summary=tk.Frame(self.main,bg=C['bg']);self.summary=summary;summary.grid(row=2,column=0,sticky='ew',padx=22,pady=(0,12))
        self.metrics={}
        for key,title in [('modules','MODULE 实例'),('scopes','检查层次'),('connections','架构连线'),('paths','分支路径')]:
            card=Surface(summary,radius=15)
            card.pack(side='left',fill='x',expand=True,padx=(0,10 if key!='paths' else 0))
            self.label(card,title,9,C['muted'],anchor='w').pack(side='left',padx=(16,8),pady=13)
            var=tk.StringVar(value='—');self.metrics[key]=var
            tk.Label(card,textvariable=var,bg='#ffffff',fg=C['ink'],font=(self.display_family,22),anchor='e').pack(side='right',padx=(0,16),pady=6)

        workspace=tk.Frame(self.main,bg=C['bg']);workspace.grid(row=3,column=0,sticky='nsew',padx=22,pady=(0,14))
        workspace.columnconfigure(0,weight=1);workspace.rowconfigure(0,weight=1)
        middle=Surface(workspace);middle.grid(row=0,column=0,sticky='nsew')
        middle.rowconfigure(1,weight=1);middle.columnconfigure(0,weight=1)
        toolbar=tk.Frame(middle,bg='#ffffff');toolbar.grid(row=0,column=0,sticky='ew',padx=12,pady=9)
        self.label(toolbar,'架构工作台',11,bold=True).pack(side='left',padx=(3,12))
        self.focus_button=Action(toolbar,'专注画布',self.toggle_canvas_focus,self.small,90,quiet=True);self.focus_button.pack(side='left')
        self.zoom_label=tk.Label(toolbar,textvariable=self.zoom_text,bg='#ffffff',fg=C['muted'],font=self.small,width=5)
        self.zoom_label.pack(side='right',padx=3)
        self.export_button=Action(toolbar,'导出 SVG',self.export_svg,self.small,90);self.export_button.pack(side='right',padx=4)
        self.fit_button=Action(toolbar,'适应画布',lambda:self.diagram.fit(),self.small,90,quiet=True);self.fit_button.pack(side='right',padx=3)
        Action(toolbar,'＋',lambda:self.diagram.zoom(1.2),self.font,34,quiet=True).pack(side='right')
        Action(toolbar,'−',lambda:self.diagram.zoom(1/1.2),self.font,34,quiet=True).pack(side='right')
        self.tabs=ttk.Notebook(middle);self.tabs.grid(row=1,column=0,sticky='nsew',padx=8,pady=(0,10))
        self.arch_tab=tk.Frame(self.tabs,bg=C['canvas']);self.tabs.add(self.arch_tab,text='层次架构')
        self.diagram=ArchitectureCanvas(self.arch_tab,self.family,self.inspect,self.zoom_text.set);self.diagram.pack(fill='both',expand=True)
        legend=tk.Frame(self.arch_tab,bg='#ffffff');legend.pack(fill='x')
        for color,title in [(C['purple'],'检查层次'),(C['teal'],'module / 端口'),(C['amber'],'停止边界')]:
            self.label(legend,'● '+title,8,color).pack(side='left',padx=10,pady=8)
        self.label(legend,'滚轮缩放 · 拖动画布 · 点击查看证据',8,C['muted']).pack(side='right',padx=10)
        self.connection_table=self.table_tab('连接检查',('source','instance','module','port','direction','owner','status'),
                                             ('待检查信号','目标完整实例','Module','端口','端口方向','检查归属','结果'),(200,250,100,80,90,180,110))
        self.path_table=self.table_tab('路径顺序',('source','sequence','stop'),('检查 / 起始信号','模块顺序','路径状态'),(210,420,160))
        self.path_table.bind('<<TreeviewSelect>>',self.select_path)
        self.connection_table.bind('<<TreeviewSelect>>',self.select_check)
        log_frame=tk.Frame(self.tabs,bg='#ffffff');self.tabs.add(log_frame,text='运行日志')
        self.log=tk.Text(log_frame,bg=C['soft'],fg=C['muted'],relief='flat',bd=12,font=(self.family,9),wrap='word',state='disabled')
        self.log.pack(fill='both',expand=True)
        self.inspector=Surface(workspace,width=238)
        self.inspector.grid(row=0,column=1,sticky='nsew',padx=(14,0));self.inspector.grid_propagate(False)
        self.inspector.rowconfigure(2,weight=1);self.inspector.columnconfigure(0,weight=1)
        self.label(self.inspector,'对象详情',11,bold=True,anchor='w').grid(row=0,column=0,sticky='ew',padx=18,pady=(19,4))
        self.detail_type=tk.StringVar(value='选择模块、端口或连线')
        tk.Label(self.inspector,textvariable=self.detail_type,bg='#ffffff',fg=C['purple'],font=self.small,anchor='w').grid(row=1,column=0,sticky='ew',padx=18,pady=(0,13))
        self.detail=tk.Text(self.inspector,bg='#ffffff',fg=C['ink'],relief='flat',bd=0,highlightthickness=0,font=self.small,wrap='word',state='disabled',padx=18,pady=3)
        self.detail.grid(row=2,column=0,sticky='nsew')
        self.detail.tag_configure('label',foreground=C['muted'],font=(self.family,8),spacing1=13,spacing3=5)
        self.detail.tag_configure('value',foreground=C['ink'],spacing3=5)
        controls=tk.Frame(self.inspector,bg='#ffffff');controls.grid(row=3,column=0,sticky='ew',padx=16,pady=16)
        self.copy_button=Action(controls,'复制完整路径',self.copy_selection,self.small,220);self.copy_button.pack(fill='x',pady=3)
        self.source_button=Action(controls,'添加为检查信号',self.use_as_source,self.small,220,quiet=True);self.source_button.pack(fill='x',pady=3)
        self.inspect(None)
        footer=tk.Frame(self.main,bg='#ffffff',height=34);footer.grid(row=4,column=0,sticky='ew');footer.grid_propagate(False)
        tk.Label(footer,textvariable=self.status,bg='#ffffff',fg=C['muted'],font=self.small,anchor='w').pack(side='left',padx=23)
        self.progress=ttk.Progressbar(footer,mode='indeterminate',length=130)

    def field(self,parent,label,var,row,col,span=1,browse=None):
        pad=(0,6) if col==0 else (8,0)
        self.label(parent,label,9,C['muted'],anchor='w').grid(row=row,column=col,columnspan=span,sticky='ew',padx=pad,pady=(9,4))
        if browse:
            holder=tk.Frame(parent,bg=parent.cget('bg'));holder.grid(row=row+1,column=col,columnspan=span,sticky='ew',padx=pad)
            entry=ttk.Entry(holder,textvariable=var);entry.pack(side='left',fill='x',expand=True)
            self.browse_button=Action(holder,'浏览…',browse,self.small,72);self.browse_button.pack(side='right',padx=(6,0))
        else:
            entry=ttk.Entry(parent,textvariable=var)
            entry.grid(row=row+1,column=col,columnspan=span,sticky='ew',padx=pad)
        return entry

    def text_input(self,parent):
        entry=tk.Text(parent,height=2,width=1,bg='#ffffff',fg=C['ink'],insertbackground=C['purple'],relief='flat',
                       highlightbackground=C['border'],highlightcolor=C['accent'],highlightthickness=0,
                       font=self.small,wrap='none',padx=9,pady=7,undo=True)
        if isinstance(parent,Surface):
            def focus(value):parent.stroke=C['accent'] if value else C['border'];parent._paint()
            entry.bind('<FocusIn>',lambda e:focus(True));entry.bind('<FocusOut>',lambda e:focus(False))
        return entry

    def bound_list_input(self,parent,key):
        entry=self.text_input(parent);syncing=[False]
        def from_variable(*args):
            if syncing[0]:return
            value='\n'.join(input_names(self.vars[key].get()));syncing[0]=True
            try:
                entry.delete('1.0','end');entry.insert('1.0',value);entry.edit_modified(False)
            finally:syncing[0]=False
        def from_editor(event):
            if syncing[0] or not entry.edit_modified():return
            entry.edit_modified(False);syncing[0]=True
            try:self.vars[key].set(entry.get('1.0','end-1c'))
            finally:syncing[0]=False
        self.vars[key].trace('w',from_variable);entry.bind('<<Modified>>',from_editor)
        return entry

    def table_tab(self,title,cols,headings,widths):
        frame=tk.Frame(self.tabs,bg='#ffffff');self.tabs.add(frame,text=title)
        frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
        table=ttk.Treeview(frame,columns=cols,show='headings',selectmode='browse')
        for col,name,width in zip(cols,headings,widths):
            table.heading(col,text=name);table.column(col,width=width,minwidth=75,anchor='w')
        table.grid(row=0,column=0,sticky='nsew')
        sy=ttk.Scrollbar(frame,orient='vertical',command=table.yview);sy.grid(row=0,column=1,sticky='ns')
        sx=ttk.Scrollbar(frame,orient='horizontal',command=table.xview);sx.grid(row=1,column=0,sticky='ew')
        table.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        table.tag_configure('unknown',foreground=C['amber']);table.tag_configure('ok',foreground=C['green'])
        return table

    def mark_dirty(self):
        if not self._loading:
            self.result_badge.set('配置已修改 · 运行后更新结果')

    def text_dirty(self,event):
        if event.widget.edit_modified():
            self.mark_dirty();event.widget.edit_modified(False)

    def choose_mode(self,mode):
        if self.job:return
        self.vars['mode'].set(mode)
        self.vars['traversal'].set('直接接线' if mode=='reach' else '组合依赖')
        self.paint_modes()

    def paint_modes(self):
        for mode,b in self.mode_buttons.items():
            b.primary=mode==self.vars['mode'].get();b.paint()

    def toggle_canvas_focus(self):
        self.canvas_focused=not self.canvas_focused
        for widget in (self.query_card,self.summary,self.inspector):
            if self.canvas_focused:widget.grid_remove()
            else:widget.grid()
        self.focus_button.set('返回工作区' if self.canvas_focused else '专注画布')
        self.diagram.auto_fit=True;self.after(80,self.diagram.fit)

    def toggle_query(self):
        self.query_expanded=not self.query_expanded
        if self.query_expanded:
            self.form.grid()
        else:
            self.form.grid_remove()
        self.query_toggle.set('收起输入区  −' if self.query_expanded else '展开输入区  ＋')

    def set_config(self,config):
        self._loading=True;self.base_config=copy.deepcopy(config)
        q=config.get('query',{});d=config.get('design',{})
        self.vars['database'].set(d.get('elab_path',''))
        self.vars['boundary'].set(q.get('traversal_boundary',''))
        sources=list(q.get('sources',[]))
        if 'source' in q:
            s=q['source'];name=s['scope']+'.'+s['signal']
            if 'bits' in s:name+='['+str(s['bits'])+']'
            sources.append(name)
        self.vars['sources'].set(', '.join(sources));self.vars['modules'].set(', '.join(q.get('target_modules',[])))
        self.vars['mode'].set(q.get('mode','trace'))
        traversal=config.get('policy',{}).get('traversal','wire_only' if q.get('mode')=='reach' else 'dependency')
        self.vars['traversal'].set('直接接线' if traversal=='wire_only' else '组合依赖')
        observed=[]
        for s in q.get('observe_signals',[]):
            observed.extend([s] if isinstance(s,str) else [s['scope']+'.'+n for n in s['names']])
        for widget,values in [(self.scopes,q.get('check_scopes',[])),(self.observes,observed)]:
            widget.delete('1.0','end');widget.insert('1.0','\n'.join(values));widget.edit_modified(False)
        self.paint_modes();self._loading=False;self.result_badge.set('配置已载入')

    def collect_config(self):
        config=copy.deepcopy(self.base_config)
        config.setdefault('design',{})['elab_path']=self.vars['database'].get().strip()
        config['design']['input_kind']='elab'
        q=config.setdefault('query',{})
        q.pop('source',None)
        q.update(mode=self.vars['mode'].get(),traversal_boundary=self.vars['boundary'].get().strip(),
                 sources=input_names(self.source_input.get('1.0','end')),
                 target_modules=input_names(self.module_input.get('1.0','end')),
                 check_scopes=input_names(self.scopes.get('1.0','end')),
                 observe_signals=input_names(self.observes.get('1.0','end')))
        policy=config.setdefault('policy',{});policy['traversal']='wire_only' if self.vars['traversal'].get()=='直接接线' else 'dependency'
        for value,label in [(config['design']['elab_path'],'elab 数据库路径'),(q['traversal_boundary'],'遍历边界'),(q['sources'],'待检查 / 起始信号'),(q['check_scopes'],'检查层次'),(q['target_modules'],'目标 module')]:
            if not value:raise ValueError('请填写'+label+'。')
        return config

    def open_config(self):
        path=filedialog.askopenfilename(parent=self,title='打开检查配置',filetypes=[('RTLWire 配置','*.json')])
        if path:self.load_config_path(path)

    def browse_elab(self):
        if self.job:return
        path=filedialog.askdirectory(parent=self,title='选择本机已编译的 .elab++ 数据库目录',initialdir=str(Path(self.vars['database'].get()).parent))
        if path:self.vars['database'].set(path)

    def load_config_path(self,path):
        try:
            config=json.loads(Path(path).read_text(encoding='utf-8-sig'))
            if config.get('kind')=='power_wave':
                self.show_wave();self.wave_panel.set_config(config)
            else:self.show_design();self.set_config(config)
        except Exception as exc:messagebox.showerror('配置无法打开',str(exc),parent=self)

    def save_config(self):
        try:config=self.collect_config()
        except ValueError as exc:messagebox.showwarning('配置尚未完整',str(exc),parent=self);return
        path=filedialog.asksaveasfilename(parent=self,title='保存检查配置',defaultextension='.json',filetypes=[('RTLWire 配置','*.json')])
        if path:
            Path(path).write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
            self.status.set('配置已保存 · '+str(path))

    def open_result(self,directory=None):
        if self.job:
            self.status.set('检查运行中，可继续查看当前图；任务完成后可切换结果。');return
        if not directory:directory=filedialog.askdirectory(parent=self,title='选择 RTL 或 FSDB 检查结果目录')
        if not directory:return
        if (Path(directory)/'wave_report.json').is_file():
            self.show_wave();self.wave_panel.open_result(directory);return
        self.show_design()
        try:
            data=load_result(directory);scene=build_architecture(data['graph'],data['report'])
        except Exception as exc:
            messagebox.showerror('结果无法打开',str(exc),parent=self);return
        self.data,self.scene=data,scene
        if data.get('query'):self.set_config(data['query'])
        elif not self.base_config:self.set_config({})
        q=data.get('query',{}).get('query',{})
        self.breadcrumb.set('工作区  /  '+q.get('traversal_boundary',', '.join(scene['roots']))+'  /  '+('连接检查' if data['report'].get('mode')=='reach' else '连接顺序'))
        complete=data['report'].get('complete') and not data.get('paths',{}).get('truncated',False)
        self.result_badge.set('已载入结果 · '+('完整' if complete else '有未知项 / 截断'))
        self.metrics['modules'].set(str(len(scene['boxes'])))
        self.metrics['scopes'].set(str(len(scene['regions'])))
        self.metrics['connections'].set(str(len(scene['connections'])))
        self.metrics['paths'].set(str(len(data.get('paths',{}).get('paths',[]))))
        self.diagram.set_scene(scene);self.populate_tree();self.populate_tables();self.inspect(None)
        self.tabs.select(0)
        if not self.query_expanded:self.toggle_query()
        audit=data.get('audit',{})
        self.status.set(('审计通过 · 输入库未改变 · ' if audit.get('passed') else '未验证提取审计 · ')+'滚轮缩放，拖动平移，双击层次定位')
        log=Path(directory)/'verdi.log'
        if log.exists():self.add_log(log.read_text(encoding='utf-8',errors='replace')[-18000:])

    def populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        if not self.data:return
        insts={k:v for k,v in self.data['graph']['instances'].items() if v['cell']=='npiNlModuleCell'}
        search=self.search.get().strip().lower();visible=set(insts)
        if search:
            visible=set()
            for name,info in insts.items():
                if search in name.lower() or search in info['module'].lower():
                    current=name
                    while current in insts:
                        visible.add(current);current=insts[current]['parent']
        def insert(name):
            if self.tree.exists(name):return
            info=insts[name];parent=info['parent'] if info['parent'] in visible else ''
            if parent:insert(parent)
            label=name[len(parent)+1:] if parent else name
            self.tree.insert(parent,'end',iid=name,text=' '+label,open=True,values=(info['module'],))
        for name in sorted(visible):insert(name)

    def tree_select(self,event=None):
        selection=self.tree.selection()
        if selection and self.scene:
            name=selection[0]
            if name in self.scene['boxes']:
                self.diagram.selected='module:'+name;self.diagram.draw();self.inspect('module:'+name)
            else:
                self.status.set('该实例不在当前连接架构中；可修改查询后运行检查。')

    def tree_focus(self,event=None):
        selection=self.tree.selection()
        if selection:self.diagram.focus_module(selection[0])

    def populate_tables(self):
        self.connection_table.delete(*self.connection_table.get_children());self.path_table.delete(*self.path_table.get_children())
        for i,c in enumerate(self.data['report'].get('checks',[])):
            short_port=c['port'][len(c['instance'])+1:] if c['port'] else '—'
            self.connection_table.insert('','end',iid='check'+str(i),values=(c['source'],c['instance'],c['module'],short_port,port_direction(c['direction']),c['owner_scope'],c['status']),tags=('ok' if c['status']=='CONNECTED' else 'unknown',))
        graph=self.data['graph']
        for i,p in enumerate(self.data.get('paths',{}).get('paths',[])):
            sequence=[]
            for nid in p['nodes']:
                node=graph['nodes'][nid];scope=node['actual_scope']
                if not sequence or sequence[-1]!=scope:sequence.append(scope)
            self.path_table.insert('','end',iid='path'+str(i),values=(p['source'],' → '.join(sequence),p['stop_reason']))
        self.tabs.tab(1,text='连接检查 · '+str(len(self.data['report'].get('checks',[]))))
        self.tabs.tab(2,text='路径顺序 · '+str(len(self.data.get('paths',{}).get('paths',[]))))

    def details(self,kind,fields):
        self.detail_type.set(kind);self.detail.configure(state='normal');self.detail.delete('1.0','end')
        for label,value in fields:
            self.detail.insert('end',label+'\n','label');self.detail.insert('end',str(value or '—')+'\n','value')
        self.detail.configure(state='disabled')

    def inspect(self,key):
        self.selected_key=key;self.selected_path=''
        self.source_button.set(enabled=False);self.copy_button.set(enabled=bool(key))
        if not key or not self.scene:
            self.details('架构阅读', [('包含关系','框内的 module 属于该真实父层次；同一框内的子模块是同级实例。'),
                                    ('检查归属','“检查层次”标签表示用户选择的范围。父范围扣除子范围后，实例仍画在真实父层次内。'),
                                    ('连接证据','点击端口或连线，查看完整信号路径。虚线表示组合依赖；交叉处无圆点表示不相连。'),
                                    ('画布操作','滚轮缩放，拖动平移。专注画布可放大工作区，Esc 返回。')]);return
        if key.startswith('module:'):
            b=self.scene['boxes'][key[7:]];self.selected_path=b['name']
            fields=[('完整实例路径',b['name']),('Module 定义',b['module']),('实际父层次',b['parent'] or '设计顶层'),('检查归属',b['owner_scope'] or '所选范围外'),
                    ('层次角色','已选检查层次' if b['selected'] else '真实中间层次 / module 实例'),('图中直接子实例',len(b['children'])),('图中端口与边界',len(b['pins']))]
            excluded=next((r['excluded_subtrees'] for r in self.scene['regions'] if r['scope']==b['name']),[])
            if excluded:fields.append(('从该检查范围扣除的子树','\n'.join(excluded)))
            self.details('MODULE / HIERARCHY',fields)
        elif key in self.scene['pins']:
            p=self.scene['pins'][key];self.selected_path=p['name']
            self.source_button.set(enabled=p['kind']!='stop' and self.job is None)
            self.details('PORT / SIGNAL', [('完整信号路径',p['name']),('实际层次',p['scope']),('检查归属',p['owner_scope']),
                                          ('对象类型',p['kind']),('端口方向',p['direction'].replace('npiNl','') or '内部信号 / 停止点'),
                                          ('停止原因',', '.join(p['stop_reasons']) or '无'),('原始 NPI 节点',', '.join(p['raw_ids']))])
        else:
            e=next((e for e in self.scene['connections'] if e['id']==key),None)
            if not e:return
            a,b=self.scene['pins'][e['source']],self.scene['pins'][e['target']]
            self.selected_path=a['name']+' → '+b['name']
            self.details('CONNECTION / EVIDENCE',[('来源',a['name']),('到达',b['name']),('连线所在层次',e['scope']),
                                                ('中间信号','\n'.join(s['name']+'  ['+s['scope']+']' for s in e['signals']) or '直接端口连接'),
                                                ('证据类型',', '.join(e['kinds'])),('原始边索引',str(e['evidence']))])

    def copy_selection(self):
        if self.selected_path:self.clipboard_clear();self.clipboard_append(self.selected_path);self.status.set('已复制完整路径')

    def use_as_source(self):
        if self.job:return
        if self.selected_key in self.scene['pins']:
            names=input_names(self.source_input.get('1.0','end'))
            name=self.scene['pins'][self.selected_key]['name']
            if name not in names:names.append(name)
            self.vars['sources'].set('\n'.join(names))
            if not self.query_expanded:self.toggle_query()
            self.status.set('已添加待检查信号 · 运行检查后刷新结果')

    def select_check(self,event=None):
        sel=self.connection_table.selection()
        if sel and self.data:
            c=self.data['report']['checks'][int(sel[0][5:])]
            key='port:'+c['port'] if c['port'] else 'module:'+c['instance']
            self.inspect(key);self.diagram.selected=key
            proof=set(e for w in c.get('witnesses',[]) for e in w['edge_indices'])
            self.diagram.highlight=witness_highlights(self.scene,self.data['graph'],proof)
            self.diagram.draw()
            self.details('CHECK / PORT',[('待检查信号',c['source']),('目标完整实例',c['instance']),('Module 定义',c['module']),
                                        ('目标端口',c['port']),('端口方向',port_direction(c['direction'])),
                                        ('检查归属',c['owner_scope']),('检查结果',c['status'])])

    def select_path(self,event=None):
        sel=self.path_table.selection()
        if not sel or not self.data:return
        p=self.data['paths']['paths'][int(sel[0][4:])];proof=set(p['edge_indices'])
        self.diagram.highlight=witness_highlights(self.scene,self.data['graph'],proof)
        self.diagram.draw()
        names=[]
        for n in p['nodes']:
            name=self.data['graph']['nodes'][n]['name']
            if not names or names[-1]!=name:names.append(name)
        order={'downstream':'顺着信号流向查找输入口','upstream':'反查输出口；下方按实际信号流向排列',
               'mixed':'连通性证据，包含逆向搜索'}.get(p.get('search_direction'),'沿信号流向')
        self.details('PATH / ORDER',[('检查 / 起始信号',p['source']),('路径说明',order),('路径状态',p['stop_reason']),('逐跳路径','\n↓\n'.join(names))])
        self.status.set('当前路径已在架构图中高亮 · 切换“层次架构”查看')

    def export_svg(self):
        if not self.scene:messagebox.showinfo('尚无架构图','先运行检查或打开一个结果目录。',parent=self);return
        path=filedialog.asksaveasfilename(parent=self,title='导出层次架构图',initialfile='architecture.svg',defaultextension='.svg',filetypes=[('SVG 矢量架构图','*.svg')])
        if path:Path(path).write_text(svg_architecture(self.scene),encoding='utf-8');self.status.set('架构图已导出 · '+str(path))

    def add_log(self,message):
        self.log.configure(state='normal');self.log.insert('end',message+'\n');self.log.see('end');self.log.configure(state='disabled')

    def start_run(self):
        if self.job:
            self.job.cancel();self.run_button.set('正在取消…',enabled=False);return
        try:
            config=self.collect_config();validate_environment(self.env)
            self.job=AnalysisJob(config,self.env,self.events).start()
        except Exception as exc:messagebox.showerror('无法开始检查',str(exc),parent=self);return
        self.run_button.set('取消本次检查');self.progress.pack(side='right',padx=20,pady=11);self.progress.start(12)
        self.set_form_enabled(False)
        self.open_button.set(enabled=False);self.save_button.set(enabled=False)
        self.result_badge.set('运行中 · 画布仍显示上次结果')
        self.add_log('开始检查 '+self.job.id+' · '+self.environment_label())
        self.status.set('正在准备检查任务…')

    def poll(self):
        try:
            while True:
                item=self.events.get_nowait();event=item['event']
                if event=='phase':self.status.set(item['message']);self.add_log(item['message'])
                elif event=='log':self.add_log(item['message'])
                elif event in ('done','error'):
                    self.progress.stop();self.progress.pack_forget();self.job=None;self.run_button.set('运行检查   F5',enabled=True)
                    self.set_form_enabled(True)
                    self.open_button.set(enabled=True);self.save_button.set(enabled=True)
                    if event=='error':
                        self.status.set('运行失败 · 查看运行日志');self.result_badge.set('本次运行失败');self.add_log(item['message']);self.tabs.select(3)
                    else:
                        labels={'complete':'检查完成','partial':'检查完成 · 含未知 / 截断','failed':'检查失败','cancelled':'本次检查已取消'}
                        directory=Path(item['directory']) if item.get('directory') else None
                        if directory and (directory/'graph.json').exists():self.open_result(directory)
                        else:self.tabs.select(3)
                        self.status.set(labels[item['status']]+' · '+(item.get('directory') or '未生成结果'))
                        self.result_badge.set(labels[item['status']])
                        self.add_log(labels[item['status']]+'，返回码 '+str(item['returncode']))
                    if self._closing:self.finish_close();return
        except queue.Empty:pass
        self.after(100,self.poll)

    def settings(self):
        if self.job or (self.wave_panel and self.wave_panel.job):
            self.status.set('请在本次检查结束后修改运行环境。');return
        dialog=tk.Toplevel(self);dialog.title('本机 EDA 环境 · RTLWire');dialog.configure(bg='#ffffff');dialog.geometry('700x390');dialog.transient(self)
        dialog.configure(bg=C['bg']);dialog.geometry('720x420')
        body=Surface(dialog,radius=22);body.pack(fill='both',expand=True,padx=12,pady=12)
        body.columnconfigure(1,weight=1)
        self.label(body,'本机 EDA 环境',17,bold=True).grid(row=0,column=0,columnspan=2,sticky='w',padx=24,pady=(24,5))
        self.label(body,'自动识别本机 Verdi；许可证留空时继承本机已有环境变量。',9,C['muted']).grid(row=1,column=0,columnspan=2,sticky='w',padx=24,pady=(0,18))
        variables={k:tk.StringVar(value=str(v)) for k,v in self.env.items()}
        fields=[('Verdi 安装目录','verdi_home'),('许可证服务器（可选）','license'),('结果保存目录','results_dir')]
        for row,(label,key) in enumerate(fields,2):
            self.label(body,label,10,C['muted'],anchor='w').grid(row=row,column=0,sticky='w',padx=24,pady=7)
            w=ttk.Entry(body,textvariable=variables[key])
            w.grid(row=row,column=1,sticky='ew',padx=(0,24),pady=7)
        self.label(body,'设计输入限于已有 elab；结果写入独立目录。',9,C['muted']).grid(row=5,column=0,columnspan=2,sticky='w',padx=24,pady=14)
        actions=tk.Frame(body,bg='#ffffff');actions.grid(row=6,column=0,columnspan=2,sticky='ew',padx=24,pady=16)
        def save():
            env={k:v.get().strip() for k,v in variables.items()}
            try:validate_environment(env)
            except ValueError as exc:messagebox.showwarning('环境配置',str(exc),parent=dialog);return
            self.env=env;self.settings_path.parent.mkdir(parents=True,exist_ok=True)
            self.settings_path.write_text(json.dumps(env,ensure_ascii=False,indent=2),encoding='utf-8')
            self.env_badge.set(self.environment_label());dialog.destroy();self.status.set('运行环境已保存')
        Action(actions,'保存环境',save,self.font,140,primary=True).pack(side='right')
        Action(actions,'取消',dialog.destroy,self.font,90,quiet=True).pack(side='right',padx=10)

    def show_history(self):
        if self.job:
            self.status.set('检查运行中，请完成或取消后切换结果。');return
        dialog=tk.Toplevel(self);dialog.title('运行记录 · RTLWire');dialog.geometry('760x460');dialog.configure(bg='#ffffff');dialog.transient(self)
        dialog.configure(bg=C['bg']);body=Surface(dialog,radius=22);body.pack(fill='both',expand=True,padx=12,pady=12)
        dialog.minsize(660,380);body.columnconfigure(0,weight=1);body.rowconfigure(1,weight=1)
        self.label(body,'运行记录',17,bold=True).grid(row=0,column=0,sticky='w',padx=22,pady=(20,8))
        table=ttk.Treeview(body,columns=('time','mode','status'),show='headings',selectmode='browse')
        for c,title,width in [('time','运行目录',320),('mode','模式',120),('status','提取状态',160)]:table.heading(c,text=title);table.column(c,width=width)
        table.grid(row=1,column=0,sticky='nsew',padx=22,pady=10)
        directories=[]
        root=Path(self.env['results_dir']).expanduser()
        if root.exists():directories=[p/'result' for p in sorted(root.iterdir(),reverse=True) if p.is_dir() and ((p/'result/graph.json').exists() or (p/'result/wave_report.json').exists())][:80]
        for p in [ROOT/'validation/reach_dual_io',ROOT/'validation/trace_chain',ROOT/'validation/reach_nested']:
            if (p/'graph.json').exists():directories.append(p)
        for i,p in enumerate(directories):
            try:
                if (p/'wave_report.json').exists():
                    r=json.loads((p/'wave_report.json').read_text(encoding='utf-8'));mode='掉电波形';state=r['summary']['status']
                else:
                    r=json.loads((p/'report.json').read_text(encoding='utf-8'));mode=r['mode'];state='完整' if r['complete'] else '含未知或停止'
                table.insert('','end',iid=str(i),values=(p.parent.name if p.name=='result' else '验证示例 / '+p.name,mode,state))
            except (OSError,ValueError):continue
        def open_selected(event=None):
            sel=table.selection()
            if sel:self.open_result(directories[int(sel[0])]);dialog.destroy()
        table.bind('<Double-1>',open_selected)
        Action(body,'打开所选结果',open_selected,self.font,160,primary=True).grid(row=2,column=0,sticky='e',padx=22,pady=(4,18))

    def current_workspace(self):
        return self.wave_panel if self.active_workspace=='wave' else self

    def show_design(self):
        self.active_workspace='design'
        if self.wave_panel:self.wave_panel.grid_remove()
        self.main.grid();self.wave_help.grid_remove()
        for w in self.nav_design_widgets:w.grid()
        self.nav_buttons['设计工作区'].set(active=True)
        self.nav_buttons['掉电波形检查'].set(active=False)

    def show_wave(self):
        if self.wave_panel is None:
            from .wave_gui import WavePanel
            self.wave_panel=WavePanel(self)
        self.active_workspace='wave';self.main.grid_remove()
        self.wave_panel.grid(row=0,column=1,sticky='nsew')
        for w in self.nav_design_widgets:w.grid_remove()
        self.wave_help.grid(row=2,column=0,rowspan=5,sticky='nsew')
        self.nav_buttons['设计工作区'].set(active=False)
        self.nav_buttons['掉电波形检查'].set(active=True)

    def finish_close(self):
        if not self.job and not (self.wave_panel and self.wave_panel.job):self.destroy()

    def close(self):
        self._closing=True
        if self.job:
            self.job.cancel();self.status.set('正在取消本次任务并保留审计，随后关闭…');self.run_button.set('正在取消…',enabled=False)
        if self.wave_panel and self.wave_panel.job:
            self.wave_panel.job.cancel();self.wave_panel.status.set('正在取消本次任务并保留审计，随后关闭…')
        self.finish_close()

    def set_form_enabled(self, enabled):
        def visit(widget):
            for child in widget.winfo_children():
                if isinstance(child,ttk.Combobox):child.configure(state='readonly' if enabled else 'disabled')
                elif isinstance(child,(ttk.Entry,tk.Text)):child.configure(state='normal' if enabled else 'disabled')
                visit(child)
        visit(self.form)
        for button in self.mode_buttons.values():button.set(enabled=enabled)
        self.browse_button.set(enabled=enabled)
        if not enabled:self.source_button.set(enabled=False)


def main():
    parser=argparse.ArgumentParser(description='RTLWire Studio — Tk architecture workbench')
    parser.add_argument('--result',help='Open an existing result directory')
    parser.add_argument('--config',help='Initial query JSON')
    parser.add_argument('--geometry',help='Initial window size, for example 1600x960')
    args=parser.parse_args()
    if sys.platform!='linux':
        parser.error('RTLWire Studio 仅在 Linux 本机运行，请在已安装 EDA 工具的 Linux 桌面启动。')
    app=Studio(result=args.result,config=args.config,geometry=args.geometry)
    app.mainloop()


if __name__=='__main__':main()
