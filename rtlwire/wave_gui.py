"""Tk isolation/power workspace, sharing the Studio theme and local job runner."""
import json
from pathlib import Path
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .theme import C, Action, Surface, rounded
from .jobs import WaveAnalysisJob
from .wave_core import normalize_config, RULES, LABELS, ns_text, Series, upgrade_report
from .wave_plot import scene, svg, value_text
from .wave_groups import POLICIES, POLICY_LABELS, read_rpt


class GroupDialog(tk.Toplevel):
    def __init__(self,panel,index):
        tk.Toplevel.__init__(self,panel)
        self.panel,self.index=panel,index
        self.title('层次 %d · RPT 与分组关键词'%(index+1));self.configure(bg='#ffffff')
        self.geometry('880x630+%d+%d'%(panel.studio.winfo_rootx()+max(0,(panel.studio.winfo_width()-880)//2),panel.studio.winfo_rooty()+max(0,(panel.studio.winfo_height()-630)//2)));self.minsize(760,540);self.transient(panel.studio)
        self.configure(bg=C['bg'])
        body=Surface(self,radius=22);body.pack(fill='both',expand=True,padx=12,pady=12)
        body.columnconfigure(1,weight=1);body.rowconfigure(6,weight=1)
        self.path=tk.StringVar(value=panel.inputs[index]['rpt_path'].get())
        self.keywords={k:tk.StringVar(value=panel.keywords[index][k].get()) for k in POLICIES}
        panel.label(body,'按关键词识别输出分组',17,bold=True).grid(row=0,column=0,columnspan=3,sticky='w',padx=24,pady=(22,5))
        panel.label(body,'匹配规则：组名包含关键词，区分大小写；每个组必须且只能匹配一种类型。',9,C['muted']).grid(row=1,column=0,columnspan=3,sticky='w',padx=24,pady=(0,15))
        panel.label(body,'分组 RPT',10,bold=True).grid(row=2,column=0,sticky='w',padx=(24,12))
        self.path_entry=ttk.Entry(body,textvariable=self.path);self.path_entry.grid(row=2,column=1,sticky='ew',pady=5)
        Action(body,'选择文件',self.browse,panel.studio.small,94).grid(row=2,column=2,padx=(12,24))
        keys=tk.Frame(body,bg='#ffffff');keys.grid(row=3,column=0,columnspan=3,sticky='ew',padx=24,pady=12)
        self.keyword_entries={}
        for i,k in enumerate(POLICIES):
            keys.columnconfigure(i,weight=1)
            panel.label(keys,POLICY_LABELS[k]+' · 组名关键词',9,C['purple'],anchor='w').grid(row=0,column=i,sticky='w',padx=(0,12),pady=(0,5))
            entry=ttk.Entry(keys,textvariable=self.keywords[k]);entry.grid(row=1,column=i,sticky='ew',padx=(0,12 if i<2 else 0))
            self.keyword_entries[k]=entry
        self.note=tk.StringVar(value='例如：MY_HIGH {sig_a，sig_b}；填 HIGH 即可将该组识别为钳 1。')
        note_box=Surface(body,bg=C['light'],stroke='',radius=12);note_box.grid(row=4,column=0,columnspan=3,sticky='ew',padx=24)
        tk.Label(note_box,textvariable=self.note,bg=C['light'],fg=C['ink'],font=panel.studio.small,anchor='w',justify='left',wraplength=770).pack(fill='x',padx=12,pady=10)
        toolbar=tk.Frame(body,bg='#ffffff');toolbar.grid(row=5,column=0,columnspan=3,sticky='ew',padx=24,pady=(10,2))
        panel.label(toolbar,'分组预览',10,bold=True).pack(side='left')
        Action(toolbar,'读取并预览',self.preview,panel.studio.small,106).pack(side='right')
        frame=tk.Frame(body,bg='#ffffff');frame.grid(row=6,column=0,columnspan=3,sticky='nsew',padx=24,pady=8)
        self.preview_table=ttk.Treeview(frame,columns=('group','type','count'),show='headings',height=6)
        for col,title,width in [('group','RPT 中的组名',410),('type','识别类型',120),('count','信号条目数',120)]:
            self.preview_table.heading(col,text=title);self.preview_table.column(col,width=width,minwidth=80)
        scroll=ttk.Scrollbar(frame,command=self.preview_table.yview);scroll.pack(side='right',fill='y')
        self.preview_table.configure(yscrollcommand=scroll.set);self.preview_table.pack(fill='both',expand=True)
        footer=tk.Frame(body,bg='#ffffff');footer.grid(row=7,column=0,columnspan=3,sticky='ew',padx=24,pady=(4,18))
        panel.label(footer,'不钳位：跳过钳位相关检查，仍检查掉电全 X。',9,C['muted']).pack(side='left')
        self.apply_button=Action(footer,'应用配置',self.apply,panel.studio.small,110,primary=True);self.apply_button.pack(side='right')
        Action(footer,'取消',self.destroy,panel.studio.small,70,quiet=True).pack(side='right',padx=8)
        self.grab_set()

    def browse(self):
        path=filedialog.askopenfilename(parent=self,title='选择该层次的 RPT',filetypes=[('RPT 分组文件','*.rpt'),('所有文件','*')])
        if path:self.path.set(path)

    def read(self):
        return read_rpt(self.path.get(),{k:v.get() for k,v in self.keywords.items()})[0]

    def show_preview(self,document):
        self.preview_table.delete(*self.preview_table.get_children())
        for i,g in enumerate(document['groups']):
            self.preview_table.insert('','end',iid=str(i),values=(g['name'],POLICY_LABELS[g['policy']],len(g['members'])))
        self.note.set('已读取 %d 个分组。%s。运行时将逐位核对输出口，重复或遗漏会报告未知。'%(len(document['groups']),
                      ' · '.join(POLICY_LABELS[k]+' '+str(document['counts'][k]) for k in POLICIES)))

    def preview(self):
        try:self.show_preview(self.read())
        except (OSError,ValueError) as e:messagebox.showerror('RPT 分组无法识别',str(e),parent=self)

    def apply(self):
        try:
            document=self.read();self.show_preview(document)
        except (OSError,ValueError) as e:messagebox.showerror('RPT 配置无法应用',str(e),parent=self);return
        self.panel.inputs[self.index]['rpt_path'].set(document['source'])
        for k,v in self.panel.keywords[self.index].items():v.set(document['keywords'][k])
        self.panel.entries[self.index]['rpt_path'].icursor('end')
        self.panel.entries[self.index]['rpt_path'].xview_moveto(1)
        self.panel.status.set('层次 %d 已配置 RPT：%s'%(self.index+1,' · '.join(POLICY_LABELS[k]+' '+str(document['counts'][k]) for k in POLICIES)))
        self.destroy()


class WaveCanvas(tk.Frame):
    def __init__(self,parent,studio,on_cursor):
        tk.Frame.__init__(self,parent,bg='#ffffff')
        self.studio,self.on_cursor=studio,on_cursor
        self.canvas=tk.Canvas(self,bg='#ffffff',highlightthickness=0,height=300)
        self.canvas.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        scroll.grid(row=0,column=1,sticky='ns');self.canvas.configure(yscrollcommand=scroll.set)
        self.rowconfigure(0,weight=1);self.columnconfigure(0,weight=1)
        self.report=self.data=self.domain=self.cycle=self.scene=None
        self.window=None;self.selected=None;self.resize_job=None;self.drag_origin=None
        self.focus_only=True
        self.series_cache={}
        self.canvas.bind('<Configure>',self.resize)
        self.canvas.bind('<Motion>',self.cursor)
        self.canvas.bind('<Leave>',lambda e:self.canvas.delete('cursor'))
        self.canvas.bind('<ButtonPress-1>',self.press)
        self.canvas.bind('<B1-Motion>',self.drag)
        self.canvas.bind('<Button-4>',lambda e:self.zoom(1.25,e.x))
        self.canvas.bind('<Button-5>',lambda e:self.zoom(.8,e.x))
        self.canvas.bind('<MouseWheel>',lambda e:self.zoom(1.25 if e.delta>0 else .8,e.x))
        self.empty()

    def empty(self):
        self.canvas.delete('all')
        w,h=max(640,self.canvas.winfo_width()),max(230,self.canvas.winfo_height())
        x,y=w/2,h/2
        rounded(self.canvas,x-90,y-91,x+90,y-31,16,fill=C['soft'],outline='')
        self.canvas.create_line(x-65,y-48,x-40,y-48,x-40,y-73,x+5,y-73,x+5,y-48,x+65,y-48,fill=C['accent'],width=2,joinstyle=tk.ROUND)
        self.canvas.create_text(x,y+2,text='从一次隔离到完整恢复',font=(self.studio.family,18,'bold'),fill=C['ink'])
        self.canvas.create_text(x,y+38,text='选择 FSDB，填写两个层次及控制信号，然后运行检查。',font=self.studio.font,fill=C['muted'])
        self.canvas.create_text(x,y+68,text='A  隔离开启     B  掉电     C  恢复供电     D  解除隔离',font=self.studio.small,fill=C['purple'])

    def resize(self,event=None):
        if self.resize_job:self.after_cancel(self.resize_job)
        self.resize_job=self.after(80,self.draw)

    def set_cycle(self,report,data,domain,cycle):
        if data is not self.data:
            self.series_cache={n:Series(s) for n,s in data['signals'].items() if s.get('selected')}
        self.report,self.data,self.domain,self.cycle=report,data,domain,cycle
        self.window=list(cycle['window'])
        first=next((r for r in cycle['checks'] if r['status']!='PASS'),next(iter(cycle['checks']),{}))
        self.selected=first.get('signal')
        self.canvas.yview_moveto(0);self.draw()

    def fit(self):
        if self.cycle:
            self.window=list(self.cycle['window']);self.draw()

    def zoom(self,factor,x=None):
        if not self.scene:return
        a,b=self.window
        ratio=.5 if x is None else min(1,max(0,(x-self.scene['left'])/(self.scene['right']-self.scene['left'])))
        center=a+round((b-a)*ratio);span=max(2,int((b-a)/factor))
        self.set_window(center-round(span*ratio),span)

    def set_window(self,start,span):
        lo,hi=self.report['file']['begin'],self.report['file']['end']
        span=min(max(1,hi-lo),span);start=max(lo,min(hi-span,start))
        self.window=[start,start+span];self.draw()

    def press(self,event):
        if self.scene:self.drag_origin=(event.x,list(self.window))

    def drag(self,event):
        if not self.drag_origin or not self.scene:return
        x,(a,b)=self.drag_origin
        delta=int((event.x-x)/(self.scene['right']-self.scene['left'])*(b-a))
        self.set_window(a-delta,b-a)

    def select_signal(self,name):
        self.selected=name;self.draw()
        if self.scene:
            index=next((i for i,l in enumerate(self.scene['lanes']) if l['name']==name),0)
            y=self.scene['top']+index*self.scene['row_height']
            view_top=self.canvas.canvasy(0);view_bottom=view_top+self.canvas.winfo_height()
            if y<view_top or y+self.scene['row_height']>view_bottom:
                self.canvas.yview_moveto(max(0,(y-100)/self.scene['height']))

    def draw(self):
        self.resize_job=None
        if not self.cycle:self.empty();return
        self.scene=scene(self.report,self.data,self.domain,self.cycle,max(640,self.canvas.winfo_width()),self.window,self.selected,self.focus_only,self.series_cache)
        self.canvas.delete('all')
        for p in self.scene['primitives']:
            if p['kind']=='rect':
                rounded(self.canvas,p['x'],p['y'],p['x']+p['w'],p['y']+p['h'],radius=p.get('radius',0),fill=p['fill'],outline=p['stroke'])
            elif p['kind']=='text':
                self.canvas.create_text(p['x'],p['y'],text=p['text'],fill=p['fill'],
                                        font=(self.studio.family,-p['size'],'bold' if p['bold'] else 'normal'),
                                        anchor={'start':'w','middle':'center','end':'e'}[p['anchor']])
            elif p['kind']=='polygon':
                self.canvas.create_polygon(*[v for xy in p['points'] for v in xy],fill=p['fill'],outline=p['stroke'],width=1)
            else:
                options=dict(fill=p['fill'],width=p['width'],joinstyle=tk.ROUND,capstyle=tk.ROUND)
                if p['dash']:options['dash']=(3,4)
                self.canvas.create_line(*[v for xy in p['points'] for v in xy],**options)
        self.canvas.configure(scrollregion=(0,0,self.scene['width'],self.scene['height']))

    def cursor(self,event):
        self.canvas.delete('cursor')
        if not self.scene or not self.scene['left']<=event.x<=self.scene['right']:return
        a,b=self.window
        t=a+round((event.x-self.scene['left'])/(self.scene['right']-self.scene['left'])*(b-a))
        self.canvas.create_line(event.x,0,event.x,self.scene['height'],fill=C['purple'],dash=(2,3),tags='cursor')
        row=int((self.canvas.canvasy(event.y)-self.scene['top'])//self.scene['row_height'])
        message=ns_text(t,self.report['file']['scale'])+' ns'
        if 0<=row<len(self.scene['lanes']):
            name=self.scene['lanes'][row]['name']
            series=self.series_cache.get(name) or Series(self.data['signals'].get(name))
            message+='  ·  '+name+' = '+value_text(series.at(t))
        self.on_cursor(message)


class WavePanel(tk.Frame):
    def __init__(self,studio):
        tk.Frame.__init__(self,studio,bg=C['bg'])
        self.studio=studio;self.job=None;self.events=queue.Queue()
        self.report=self.data=self.directory=None;self.cycles={};self.current=None
        self.config_base={};self._loading=False;self.dirty=False
        self.fsdb=tk.StringVar()
        self.inputs=[{k:tk.StringVar(value=k if k in ('iso_en','power_down') else '') for k in ('scope','iso_en','power_down','rpt_path')} for i in range(2)]
        self.keywords=[{k:tk.StringVar() for k in POLICIES} for i in range(2)]
        self.status=tk.StringVar(value='就绪 · 同一时刻最终值 · 默认前后各 5 ns')
        self.badge=tk.StringVar(value='尚未运行')
        self.cursor_text=tk.StringVar(value='滚轮缩放时间轴 · 拖动平移 · 右侧滚动查看全部输出')
        self.detail=tk.StringVar(value='选择一行输出口，查看完整名称、判定值与首次异常时间。')
        self.columnconfigure(0,weight=1);self.rowconfigure(3,weight=1)
        self.build()
        self.compact=False;self.bind('<Configure>',self.responsive)
        for var in [self.fsdb]+[v for d in self.inputs+self.keywords for v in d.values()]:
            var.trace('w',lambda *a:self.mark_dirty())
        self.after(100,self.poll)

    def label(self,parent,text,size=10,color=None,bold=False,**kw):
        return self.studio.label(parent,text,size,color,bold,**kw)

    def build(self):
        header=tk.Frame(self,bg=C['bg'],height=84);header.grid(row=0,column=0,sticky='ew');header.grid_propagate(False)
        self.label(header,'波形工作区  /  FSDB',9,C['muted']).place(x=24,y=10)
        self.label(header,'隔离与掉电波形检查',18,bold=True).place(x=24,y=34)
        actions=tk.Frame(header,bg=C['bg']);actions.pack(side='right',padx=20,pady=23)
        self.config_button=Action(actions,'打开配置',self.open_config,self.studio.small,88);self.config_button.pack(side='left',padx=4)
        self.save_button=Action(actions,'保存配置',self.save_config,self.studio.small,88);self.save_button.pack(side='left',padx=4)
        self.run_button=Action(actions,'运行检查   F5',self.start_run,self.studio.font,142,primary=True);self.run_button.pack(side='left',padx=(12,0))
        self.form=Surface(self,radius=18)
        self.form.grid(row=1,column=0,sticky='ew',padx=20,pady=(12,0))
        for col,weight in [(1,4),(2,2),(3,2),(4,4)]:self.form.columnconfigure(col,weight=weight)
        self.label(self.form,'波形文件',10,bold=True).grid(row=0,column=0,padx=(16,12),pady=6,sticky='w')
        self.file_entry=ttk.Entry(self.form,textvariable=self.fsdb)
        self.file_entry.grid(row=0,column=1,columnspan=4,sticky='ew',padx=(0,110),pady=6)
        self.browse_button=Action(self.form,'选择 FSDB',self.browse,self.studio.small,94)
        self.browse_button.grid(row=0,column=4,sticky='e',padx=12,pady=4)
        for col,title in [(1,'检查层次 · 完整实例路径'),(2,'iso_en · 高电平隔离'),(3,'power_down · 低电平掉电'),(4,'分组 RPT · 用户关键词')]:
            self.label(self.form,title,9,C['muted'],anchor='w').grid(row=1,column=col,sticky='ew',padx=(0,14),pady=(1,3))
        self.entries=[];self.group_buttons=[]
        for row,values in enumerate(self.inputs,2):
            self.label(self.form,'层次 '+str(row-1),9,C['purple'],True).grid(row=row,column=0,padx=16,pady=5)
            widgets={}
            for col,key in enumerate(('scope','iso_en','power_down'),1):
                e=ttk.Entry(self.form,textvariable=values[key],width=23 if col==1 else 15);e.grid(row=row,column=col,sticky='ew',padx=(0,14),pady=3)
                widgets[key]=e
            rpt=tk.Frame(self.form,bg='#ffffff');rpt.grid(row=row,column=4,sticky='ew',padx=(0,14),pady=3);rpt.columnconfigure(0,weight=1)
            entry=ttk.Entry(rpt,textvariable=values['rpt_path'],width=18);entry.grid(row=0,column=0,sticky='ew')
            entry.bind('<Configure>',lambda e:self.after_idle(lambda w=e.widget:w.xview_moveto(1) if w.winfo_exists() else None))
            widgets['rpt_path']=entry
            button=Action(rpt,'RPT 配置',lambda i=row-2:self.edit_groups(i),self.studio.small,82)
            button.grid(row=0,column=1,padx=(6,0));self.group_buttons.append(button)
            self.entries.append(widgets)
        self.label(self.form,'每层独立导入 RPT，并输入钳 1 / 钳 0 / 不钳位的关键词  ·  不钳位仍检查掉电全 X  ·  同一时刻取最终值',9,C['muted'],anchor='w').grid(row=4,column=0,columnspan=5,sticky='ew',padx=16,pady=(4,8))
        cards=tk.Frame(self,bg=C['bg']);self.cards=cards;cards.grid(row=2,column=0,sticky='ew',padx=20,pady=10)
        self.metrics={}
        for col,(key,title,color) in enumerate([('outputs','已记录输出口',C['ink']),('cycles','检测周期',C['ink']),('pass','通过 · 口×周期',C['teal']),('fail','失败 · 口×周期',C['red']),('unknown','未知 · 口×周期',C['amber'])]):
            cards.columnconfigure(col,weight=1)
            card=Surface(cards,radius=15)
            card.grid(row=0,column=col,sticky='ew',padx=(0,12 if col<4 else 0))
            self.label(card,title,9,C['muted'],anchor='w').pack(side='left',padx=(14,4),pady=14)
            var=tk.StringVar(value='—');self.metrics[key]=var
            tk.Label(card,textvariable=var,bg='#ffffff',fg=color,font=(self.studio.display_family,23),anchor='e').pack(side='right',padx=(0,16),pady=6)
        self.tabs=ttk.Notebook(self);self.tabs.grid(row=3,column=0,sticky='nsew',padx=20,pady=(0,14))
        work=Surface(self.tabs,radius=18);self.tabs.add(work,text='周期波形与逐口结果')
        work.columnconfigure(1,weight=1);work.rowconfigure(0,weight=1)
        side=Surface(work,bg=C['soft'],width=200,radius=14,stroke='');side.grid(row=0,column=0,sticky='nsew',padx=(10,0),pady=10);side.grid_propagate(False)
        self.label(side,'检查周期',11,bold=True,anchor='w').pack(fill='x',padx=15,pady=(16,4))
        tk.Label(side,textvariable=self.badge,bg=C['soft'],fg=C['purple'],font=self.studio.small,anchor='w',wraplength=175,justify='left').pack(fill='x',padx=15,pady=(0,12))
        self.cycle_tree=ttk.Treeview(side,show='tree',selectmode='browse',height=5);self.cycle_tree.pack(fill='both',expand=True,padx=7)
        for status,color in [('FAIL',C['red']),('UNKNOWN',C['amber']),('PASS',C['teal'])]:self.cycle_tree.tag_configure(status,foreground=color)
        self.cycle_tree.bind('<<TreeviewSelect>>',self.select_cycle)
        self.label(side,'A  隔离拉高\nB  掉电拉低\nC  供电恢复\nD  隔离解除',9,C['muted'],anchor='w',justify='left').pack(fill='x',padx=16,pady=14)
        Action(side,'打开检查结果',self.open_result,self.studio.small,172).pack(padx=14,pady=(0,13))
        right=tk.Frame(work,bg='#ffffff');right.grid(row=0,column=1,sticky='nsew',padx=(10,10),pady=10);right.columnconfigure(0,weight=1);right.rowconfigure(1,weight=3);right.rowconfigure(3,weight=2)
        toolbar=tk.Frame(right,bg='#ffffff');toolbar.grid(row=0,column=0,sticky='ew',padx=12,pady=(4,0))
        self.padding_label=self.label(toolbar,'周期窗口  ·  前后各 5 ns',9,C['muted'])
        self.padding_label.pack(side='left')
        for title,command,width in [('导出 SVG',self.export_svg,88),('完整周期',lambda:self.wave.fit(),88),('＋',lambda:self.wave.zoom(1.4),34),('−',lambda:self.wave.zoom(1/1.4),34)]:
            Action(toolbar,title,command,self.studio.small,width,quiet=True).pack(side='right',padx=2)
        self.wave=WaveCanvas(right,self.studio,self.cursor_text.set);self.wave.grid(row=1,column=0,sticky='nsew')
        self.show_all=tk.BooleanVar(value=False)
        tk.Checkbutton(toolbar,text='全部输出',variable=self.show_all,command=self.toggle_outputs,
                       bg='#ffffff',fg=C['muted'],activebackground='#ffffff',selectcolor='#ffffff',
                       font=self.studio.small,relief='flat',highlightthickness=0).pack(side='left',padx=16)
        tk.Label(right,textvariable=self.cursor_text,bg=C['soft'],fg=C['muted'],font=self.studio.small,anchor='w',padx=12,pady=6).grid(row=2,column=0,sticky='ew')
        table_frame=tk.Frame(right,bg='#ffffff');table_frame.grid(row=3,column=0,sticky='nsew');table_frame.rowconfigure(0,weight=1);table_frame.columnconfigure(0,weight=1)
        self.table_frame=table_frame;self.wave_expanded=False
        self.expand_button=Action(toolbar,'展开波形',self.expand_wave,self.studio.small,86,quiet=True)
        self.expand_button.pack(side='right',padx=2)
        cols=('signal','group','expected','idle','clamp','equal','stable','off','recovery','status')
        self.table=ttk.Treeview(table_frame,columns=cols,show='headings',height=4,selectmode='browse')
        titles=['输出口','分组','期望钳位','Idle','隔离后值','一致 / 期望','稳定','掉电 X','恢复钳位','结果']
        widths=[160,84,88,75,86,100,70,70,84,82]
        for col,title,width in zip(cols,titles,widths):self.table.heading(col,text=title);self.table.column(col,width=width,minwidth=50,stretch=col=='signal',anchor='w' if col=='signal' else 'center')
        self.table.grid(row=0,column=0,sticky='nsew')
        sy=ttk.Scrollbar(table_frame,orient='vertical',command=self.table.yview);sy.grid(row=0,column=1,sticky='ns')
        sx=ttk.Scrollbar(table_frame,orient='horizontal',command=self.table.xview);sx.grid(row=1,column=0,sticky='ew')
        self.table.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        for status,color in [('FAIL',C['red']),('UNKNOWN',C['amber']),('PASS',C['teal'])]:self.table.tag_configure(status,foreground=color)
        self.table.bind('<<TreeviewSelect>>',self.select_output)
        tk.Label(right,textvariable=self.detail,bg=C['soft'],fg=C['ink'],font=self.studio.small,justify='left',anchor='w',padx=12,pady=8,wraplength=880).grid(row=4,column=0,sticky='ew')
        details=tk.Frame(self.tabs,bg='#ffffff');self.tabs.add(details,text='问题与证据')
        self.evidence=self.text_area(details)
        logs=tk.Frame(self.tabs,bg='#ffffff');self.tabs.add(logs,text='运行日志')
        self.log=self.text_area(logs)
        footer=tk.Frame(self,bg='#ffffff',height=34);footer.grid(row=4,column=0,sticky='ew')
        tk.Label(footer,textvariable=self.status,bg='#ffffff',fg=C['muted'],font=self.studio.small,anchor='w').pack(side='left',padx=20,pady=7)
        self.progress=ttk.Progressbar(footer,mode='indeterminate',length=100)

    def responsive(self,event):
        # On smaller desktops give the waveform the space of the summary strip.
        compact=event.height<880
        if compact!=self.compact:
            self.compact=compact
            if compact:self.cards.grid_remove()
            else:self.cards.grid()

    def reveal_rpt_names(self):
        for row in self.entries:
            row['rpt_path'].icursor('end');row['rpt_path'].xview_moveto(1)

    def text_area(self,parent):
        scroll=ttk.Scrollbar(parent,orient='vertical');scroll.pack(side='right',fill='y')
        t=tk.Text(parent,bg='#ffffff',fg=C['ink'],font=self.studio.font,relief='flat',bd=14,wrap='word',state='disabled',yscrollcommand=scroll.set)
        t.pack(fill='both',expand=True);scroll.configure(command=t.yview)
        return t

    def write_text(self,widget,text,append=False):
        widget.configure(state='normal')
        if not append:widget.delete('1.0','end')
        widget.insert('end',text+'\n');widget.configure(state='disabled')
        if append:widget.see('end')

    def mark_dirty(self):
        if not self._loading:
            self.dirty=True
            self.badge.set('输入已修改 · 结果待更新' if self.report else '尚未运行')

    def config(self):
        domains=[]
        for d,keys in zip(self.inputs,self.keywords):
            item={k:v.get() for k,v in d.items()};item['group_keywords']={k:v.get() for k,v in keys.items()};domains.append(item)
        config=dict(self.config_base,fsdb_path=self.fsdb.get(),domains=domains,grouping_mode='rpt')
        return normalize_config(config)

    def edit_groups(self,index):
        if not self.job:self.group_dialog=GroupDialog(self,index)

    def set_config(self,config):
        if len(config.get('domains',[]))!=2:
            raise ValueError('GUI 需要两个检查层次；更多层次可使用命令行。')
        self._loading=True
        try:
            self.config_base=dict(config);self.fsdb.set(config.get('fsdb_path',''))
            self.padding_label.configure(text='周期窗口  ·  前后各 '+str(config.get('padding_ns',5))+' ns')
            for fields,keys,values in zip(self.inputs,self.keywords,config['domains']):
                for k,v in fields.items():v.set(values.get(k,''))
                for k,v in keys.items():v.set(values.get('group_keywords',{}).get(k,''))
            self.reveal_rpt_names();self.after_idle(self.reveal_rpt_names)
        finally:self._loading=False
        self.mark_dirty()

    def browse(self):
        path=filedialog.askopenfilename(parent=self,title='选择 FSDB 波形',filetypes=[('FSDB 波形','*.fsdb')])
        if path:self.fsdb.set(path)

    def open_config(self,path=None):
        if self.job:return
        path=path or filedialog.askopenfilename(parent=self,title='打开掉电检查配置',filetypes=[('JSON 配置','*.json')])
        if path:
            try:self.set_config(json.loads(Path(path).read_text(encoding='utf-8-sig')))
            except Exception as e:messagebox.showerror('配置无法打开',str(e),parent=self)

    def save_config(self):
        try:config=self.config()
        except ValueError as e:messagebox.showwarning('请完善输入',str(e),parent=self);return
        path=filedialog.asksaveasfilename(parent=self,title='保存掉电检查配置',defaultextension='.json',filetypes=[('JSON 配置','*.json')])
        if path:Path(path).write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8');self.status.set('配置已保存 · '+path)

    def busy(self,enabled):
        self.file_entry.configure(state='disabled' if enabled else 'normal')
        for row in self.entries:
            for widget in row.values():widget.configure(state='disabled' if enabled else 'normal')
        for button in [self.browse_button,self.config_button,self.save_button]+self.group_buttons:button.set(enabled=not enabled)
        self.run_button.set('取消检查' if enabled else '运行检查   F5',enabled=True)
        if enabled:self.progress.pack(side='right',padx=20);self.progress.start(12)
        else:self.progress.stop();self.progress.pack_forget()

    def start_run(self):
        if self.job:self.job.cancel();self.run_button.set('正在取消…',enabled=False);return
        try:
            config=self.config()
            self.job=WaveAnalysisJob(config,self.studio.env,self.events).start()
        except Exception as e:messagebox.showerror('检查无法启动',str(e),parent=self);return
        self.busy(True);self.badge.set('运行中 · 保留上次结果')
        self.status.set('正在读取 FSDB…');self.write_text(self.log,'开始检查 '+self.job.id,True)

    def poll(self):
        try:
            while True:
                item=self.events.get_nowait()
                if item['event']=='phase':self.status.set(item['message']);self.write_text(self.log,item['message'],True)
                elif item['event']=='log':self.write_text(self.log,item['message'],True)
                elif item['event'] in ('done','error'):
                    self.job=None;self.busy(False)
                    directory=Path(item.get('directory') or '.')
                    if item['event']=='done' and item['status']=='complete':
                        self.open_result(directory)
                    else:
                        self.badge.set('已取消' if item.get('status')=='cancelled' else '运行失败')
                        self.status.set(self.badge.get()+' · 日志已保留在 '+str(directory))
                        if item.get('message'):self.write_text(self.log,item['message'],True)
                        self.tabs.select(2)
                    if self.studio._closing:
                        self.studio.finish_close();return
        except queue.Empty:pass
        self.after(100,self.poll)

    def open_result(self,directory=None):
        if self.job:return
        directory=directory or filedialog.askdirectory(parent=self,title='选择包含 wave_report.json 的结果目录')
        if not directory:return
        try:
            directory=Path(directory)
            report=upgrade_report(json.loads((directory/'wave_report.json').read_text(encoding='utf-8')))
            data=json.loads((directory/'wave_data.json').read_text(encoding='utf-8'))
            if report.get('kind')!='power_wave':raise ValueError('这不是掉电波形检查结果。')
            self.set_config(report['config'])
        except Exception as e:messagebox.showerror('结果无法打开',str(e),parent=self);return
        self.directory,self.report,self.data=directory,report,data;self.dirty=False
        s=report['summary'];self.badge.set(s['status']+' · %d 完整 / %d 周期'%(s['complete_cycles'],s['cycles']))
        for key,var in self.metrics.items():var.set(str(s[key]))
        self.cycle_tree.delete(*self.cycle_tree.get_children());self.cycles={}
        lines=['判定：'+s['status'],'输入：'+report['config']['fsdb_path'],
               '覆盖：FSDB 中记录了方向信息的本层 output；未 dump 的端口不能从波形中推断。',
               '同一时刻使用最终值。FSDB 保留的 delta 更新仅提示；未记录的 delta 无法重建。','']
        for di,d in enumerate(report['domains']):
            parent='domain'+str(di)
            self.cycle_tree.insert('', 'end',iid=parent,text=d['config']['scope'].rsplit('.',1)[-1]+'  ·  '+d['status'],open=True,tags=(d['status'],))
            lines.append(d['config']['scope']+'  '+d['status'])
            if d.get('rpt'):
                lines.append('  RPT：'+d['rpt']['source'])
                lines.append('  关键词：'+'；'.join(POLICY_LABELS[k]+' = '+d['rpt']['keywords'][k] for k in POLICIES))
            if d.get('group_counts'):
                lines.append('  输出分组：'+'；'.join(POLICY_LABELS[k]+' '+str(v) for k,v in d['group_counts'].items()))
            for item in d['issues']:lines.append('  '+item['status']+'  '+item['code']+'  '+item['message'])
            for c in d['cycles']:
                key=parent+'_cycle'+str(c['index']);self.cycles[key]=(d,c)
                self.cycle_tree.insert(parent,'end',iid=key,text='周期 %d  ·  %s'%(c['index'],c['status']),tags=(c['status'],))
                lines.append('  周期 %d：%s；窗口 %s–%s ns%s'%(c['index'],c['status'],ns_text(c['window'][0],report['file']['scale']),ns_text(c['window'][1],report['file']['scale']),'，文件边界裁剪裕量' if c['padding_clipped'] else ''))
                for item in c['issues']:lines.append('    '+item['status']+'  '+item['code']+'  '+item['message'])
                for r in c['checks']:
                    lines.append('    '+r['signal']+' | '+POLICY_LABELS[r['clamp_policy']]+' | 期望 '+r['expected_clamp']+' | RPT 组 '+', '.join(r['group_names']))
                    for k in RULES:
                        v=r['checks'][k]
                        if v['status'] not in ('PASS','SKIP'):lines.append('    '+r['signal']+' | '+LABELS[k]+' | '+v['status']+' | '+ns_text(v['time'],report['file']['scale'])+' ns | 位 '+str(v.get('checked_bits','全部'))+' | actual='+str(v['actual'])+' expected='+str(v['expected'])+' '+v['message'])
                for warning in c['delta_warnings']:lines.append('    提示 · '+warning['signal']+' @ '+ns_text(warning['time'],report['file']['scale'])+' ns：'+' → '.join(warning['values'])+'；按最终值判定')
        self.write_text(self.evidence,'\n'.join(lines));self.tabs.select(0)
        if self.cycles:
            key=next(iter(self.cycles));self.cycle_tree.selection_set(key);self.select_cycle()
        else:
            self.current=None;self.wave.cycle=None;self.wave.empty();self.table.delete(*self.table.get_children());self.tabs.select(1)
        if not s['outputs']:self.tabs.select(1)
        self.status.set('检查完成 · '+s['status']+' · '+str(directory))

    def select_cycle(self,event=None):
        selected=self.cycle_tree.selection()
        if not selected:return
        key=selected[0]
        if key not in self.cycles:
            children=self.cycle_tree.get_children(key)
            if children:self.cycle_tree.selection_set(children[0])
            else:self.tabs.select(1)
            return
        d,c=self.cycles[key];self.current=(d,c)
        self.wave.set_cycle(self.report,self.data,d,c)
        self.table.delete(*self.table.get_children())
        short={'PASS':'通过','FAIL':'失败','UNKNOWN':'未知','SKIP':'不适用'}
        for i,r in enumerate(c['checks']):
            check=r['checks']
            equal=short[check['idle_equal']['status']]+' / '+short[check['clamp_expected']['status']]
            expected='—' if r['clamp_policy']=='no_clamp' else r['expected_clamp'] if '?' in r['expected_clamp'] else value_text(r['expected_clamp'])
            self.table.insert('','end',iid='out'+str(i),values=(r['local_name'],POLICY_LABELS[r['clamp_policy']],expected,value_text(r['idle']),value_text(r['clamp']),equal,
                                   short[check['clamp_stable']['status']],short[check['off_x']['status']],short[check['recovery_expected']['status']],r['status']),tags=(r['status'],))
        times='  ·  '.join(letter+' '+ns_text(c[key],self.report['file']['scale'])+' ns' for key,letter in [('iso_rise','A'),('power_fall','B'),('power_rise','C'),('iso_fall','D')])
        self.detail.set(times+('\n周期不完整，不能判定通过。' if not c['complete'] else '')+('\n窗口达到文件边界，5 ns 裕量已裁剪。' if c['padding_clipped'] else ''))
        self.cursor_text.set(d['config']['scope']+'  ·  %d 个输出口  ·  %d 条 delta 提示'%(len(c['checks']),len(c['delta_warnings'])))

    def toggle_outputs(self):
        self.wave.focus_only=not self.show_all.get();self.wave.draw();self.wave.canvas.yview_moveto(0)

    def expand_wave(self):
        self.wave_expanded=not self.wave_expanded
        if self.wave_expanded:self.table_frame.grid_remove()
        else:self.table_frame.grid()
        self.expand_button.set('显示结果表' if self.wave_expanded else '展开波形')

    def select_output(self,event=None):
        selection=self.table.selection()
        if not selection or not self.current:return
        self.table.see(selection[0])
        r=self.current[1]['checks'][int(selection[0][3:])]
        self.wave.select_signal(r['signal'])
        problems=[]
        for k in RULES:
            v=r['checks'][k]
            if v['status'] not in ('PASS','SKIP'):
                problems.append(LABELS[k]+' '+v['status']+' @ '+ns_text(v['time'],self.report['file']['scale'])+' ns：'+value_text(v['actual'])+' / 期望 '+value_text(v['expected']))
        problems += [i['message'] for i in r['group_issues']]
        if r['status']!='PASS' and not problems:
            problems=[i['message'] for i in self.current[1]['issues']] or ['当前周期或数据覆盖不足，不能判定通过。']
        success='不钳位：钳位相关检查不适用；掉电全 X 检查通过。' if r['clamp_policy']=='no_clamp' else '已按 RPT 检查钳位位的 idle、期望值、稳定性和恢复阶段；掉电全 X 检查通过。'
        self.detail.set(r['signal']+'  ·  '+POLICY_LABELS[r['clamp_policy']]+'  ·  '+r['status']+'\n'+('；'.join(problems) if problems else success))

    def export_svg(self):
        if not self.current:return
        path=filedialog.asksaveasfilename(parent=self,title='导出完整周期波形',defaultextension='.svg',filetypes=[('SVG 矢量波形','*.svg')])
        if path:
            d,c=self.current
            Path(path).write_text(svg(scene(self.report,self.data,d,c)),encoding='utf-8')
            self.status.set('完整周期波形已导出 · '+path)
