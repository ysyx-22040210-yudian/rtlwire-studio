"""Warm, native Tk surfaces. No image/theme package is required on Linux."""
import math
import tkinter as tk
from tkinter import ttk


C = dict(bg='#faf9f5', surface='#ffffff', nav='#f0eee6', nav2='#e8e5dc',
         ink='#292823', muted='#7a786e', border='#e5e2d9', purple='#b56346',
         accent='#b56346', light='#f5e9e1', teal='#38796c', green='#38796c',
         amber='#a27935', red='#b24f4c', canvas='#f8f7f2', soft='#f4f3ee')


def rounded(canvas, x0, y0, x1, y1, radius=12, **kwargs):
    r = max(0, min(radius, (x1-x0)/2, (y1-y0)/2))
    if not r:return canvas.create_rectangle(x0,y0,x1,y1,**kwargs)
    points=[]
    for cx,cy,start in ((x1-r,y0+r,-90),(x1-r,y1-r,0),(x0+r,y1-r,90),(x0+r,y0+r,180)):
        for step in range(9):
            a=math.radians(start+step*90/8)
            points.extend((cx+r*math.cos(a),cy+r*math.sin(a)))
    return canvas.create_polygon(*points,**kwargs)


class Surface(tk.Frame):
    """A normal Frame with a rounded background; child geometry is unchanged."""
    def __init__(self,parent,bg=None,radius=18,stroke=None,outer=None,**kw):
        self.fill=bg or C['surface'];self.radius=radius
        self.stroke=C['border'] if stroke is None else stroke
        tk.Frame.__init__(self,parent,bg=self.fill,**kw)
        try:outside=parent.cget('bg')
        except tk.TclError:outside=C['bg']
        self.back=tk.Canvas(self,bg=outer or outside,bd=0,highlightthickness=0,takefocus=0)
        self.back.place(x=0,y=0,relwidth=1,relheight=1)
        self.tk.call('lower',self.back._w)
        self.back.bind('<Configure>',self._paint)

    def _paint(self,event=None):
        w,h=self.back.winfo_width(),self.back.winfo_height()
        self.back.delete('all')
        rounded(self.back,1,1,w-1,h-1,self.radius,fill=self.fill,outline=self.stroke)


class Action(tk.Canvas):
    def __init__(self,parent,text,command,font,width=100,primary=False,quiet=False,bg=None,nav=False,icon=None):
        tk.Canvas.__init__(self,parent,width=width,height=40 if nav else 36,bg=bg or parent.cget('bg'),
                           highlightthickness=0,bd=0,takefocus=1,cursor='hand2')
        self.label,self.command,self.ui_font=text,command,font
        self.primary,self.quiet,self.enabled,self.hover=primary,quiet,True,False
        self.nav,self.icon,self.active,self.focused,self.pressed=nav,icon,False,False,False
        self.bind('<Enter>',lambda e:self._hover(True))
        self.bind('<Leave>',lambda e:self._hover(False))
        self.bind('<ButtonPress-1>',self._press)
        self.bind('<ButtonRelease-1>',self._release)
        self.bind('<Return>',lambda e:self.invoke())
        self.bind('<space>',lambda e:self.invoke())
        self.bind('<FocusIn>',lambda e:self._focus(True))
        self.bind('<FocusOut>',lambda e:self._focus(False))
        self.bind('<Configure>',lambda e:self.paint())
        self.paint()

    def _hover(self,value):self.hover=value;self.paint()
    def _focus(self,value):self.focused=value;self.paint()
    def _press(self,event):
        if self.enabled:self.focus_set();self.pressed=True;self.paint()
    def _release(self,event):
        was=self.pressed;self.pressed=False;self.paint()
        if was and 0<=event.x<self.winfo_width() and 0<=event.y<self.winfo_height():self.invoke()

    def set(self,text=None,enabled=None,active=None):
        if text is not None:self.label=text
        if enabled is not None:self.enabled=enabled
        if active is not None:self.active=active
        self.configure(cursor='hand2' if self.enabled else 'arrow');self.paint()

    def invoke(self):
        if self.enabled:return self.command()

    def paint(self):
        self.delete('all')
        w=max(self.winfo_width(),int(self.cget('width')));h=int(self.cget('height'))
        if self.nav:
            fill=C['surface'] if self.active else C['nav2'] if self.hover else self.cget('bg')
            fg=C['ink'] if self.active else C['muted'];stroke=C['border'] if self.active else ''
        elif self.primary:
            fill='#994d35' if self.pressed else '#a6573c' if self.hover else C['accent']
            fg='#ffffff';stroke=''
        else:
            fill=C['nav2'] if self.pressed else C['soft'] if self.hover else self.cget('bg') if self.quiet else C['surface']
            fg=C['ink'];stroke='' if self.quiet else C['border']
        if not self.enabled:
            fill=C['nav2'] if self.primary else fill;fg='#a8a59c'
        if self.focused and self.enabled:stroke=C['accent']
        rounded(self,1,1,w-2,h-2,12,fill=fill,outline=stroke,width=1.4 if self.focused else 1)
        self.create_text(42 if self.nav else w/2,h/2,text=self.label,font=self.ui_font,fill=fg,anchor='w' if self.nav else 'center')
        if self.nav:self.draw_icon(22,h/2,C['accent'] if self.active else fg)

    def draw_icon(self,x,y,color):
        options=dict(fill=color,width=1.5,capstyle=tk.ROUND,joinstyle=tk.ROUND)
        if self.icon=='wave':
            self.create_line(x-8,y+4,x-4,y+4,x-4,y-5,x+2,y-5,x+2,y+4,x+8,y+4,**options)
        elif self.icon=='folder':
            self.create_line(x-8,y+5,x-8,y-6,x-2,y-6,x,y-3,x+8,y-3,x+8,y+5,x-8,y+5,**options)
        elif self.icon=='history':
            self.create_oval(x-7,y-7,x+7,y+7,outline=color,width=1.4)
            self.create_line(x,y-4,x,y+1,x+4,y+3,**options)
        else:
            for dx,dy in [(-5,-5),(4,-5),(-5,4),(4,4)]:
                rounded(self,x+dx-2.5,y+dy-2.5,x+dx+2.5,y+dy+2.5,1.6,fill='',outline=color,width=1.2)


def _rounded_image(root,fill,stroke,outer,radius=10,size=28):
    """Antialiased 9-slice image using Tk 8.5 PhotoImage (no PNG/Pillow)."""
    def rgb(value):return tuple(int(value[i:i+2],16) for i in (1,3,5))
    colors=[rgb(v) for v in (outer,stroke,fill)]
    def inside(x,y,inset):
        half=size/2-inset;r=radius-inset
        dx=max(abs(x-size/2)-(half-r),0);dy=max(abs(y-size/2)-(half-r),0)
        return dx*dx+dy*dy<=r*r and abs(x-size/2)<=half and abs(y-size/2)<=half
    rows=[]
    for y in range(size):
        row=[]
        for x in range(size):
            total=[0,0,0]
            for sx,sy in ((.25,.25),(.75,.25),(.25,.75),(.75,.75)):
                c=colors[2 if inside(x+sx,y+sy,1) else 1 if inside(x+sx,y+sy,0) else 0]
                total=[a+b for a,b in zip(total,c)]
            row.append('#%02x%02x%02x'%tuple(v//4 for v in total))
        rows.append('{'+ ' '.join(row)+'}')
    image=tk.PhotoImage(master=root,width=size,height=size);image.put(' '.join(rows))
    return image


def install_styles(root):
    style=ttk.Style(root);style.theme_use('clam')
    style.configure('.',font=root.font,background=C['surface'],foreground=C['ink'])
    root._theme_images=[]
    def element(name,fill,edge,outer,focus=None):
        normal=_rounded_image(root,fill,edge,outer);root._theme_images.append(normal)
        args=[]
        if focus:
            image=_rounded_image(root,fill,focus,outer);root._theme_images.append(image);args=[('focus',image)]
        style.element_create(name,'image',normal,*args,border=11,padding=0,sticky='nsew')
    element('Soft.field',C['surface'],C['border'],C['surface'],C['accent'])
    style.layout('TEntry',[('Soft.field',{'sticky':'nswe','children':[('Entry.padding',{'sticky':'nswe','children':[('Entry.textarea',{'sticky':'nswe'})]})]})])
    element('Nav.field',C['surface'],C['border'],C['nav'],C['accent'])
    entry_layout=style.layout('TEntry');entry_layout[0]=('Nav.field',entry_layout[0][1])
    style.layout('Nav.TEntry',entry_layout)
    style.configure('TEntry',fieldbackground=C['surface'],padding=(10,8),insertcolor=C['ink'],borderwidth=0)
    style.layout('TCombobox',[('Soft.field',{'sticky':'nswe','children':[('Combobox.downarrow',{'side':'right','sticky':'ns'}),('Combobox.padding',{'sticky':'nswe','children':[('Combobox.textarea',{'sticky':'nswe'})]})]})])
    style.configure('TCombobox',fieldbackground=C['surface'],padding=(9,7),borderwidth=0,arrowsize=12,arrowcolor=C['muted'])
    style.map('TCombobox',fieldbackground=[('readonly',C['surface'])],selectbackground=[('readonly',C['surface'])],selectforeground=[('readonly',C['ink'])])
    style.configure('TNotebook',background=C['bg'],borderwidth=0,tabmargins=(3,3,3,5))
    style.configure('TNotebook',bordercolor=C['bg'],lightcolor=C['bg'],darkcolor=C['bg'])
    style.layout('TNotebook',[('Notebook.client',{'sticky':'nswe'})])
    normal=_rounded_image(root,C['bg'],C['bg'],C['bg']);active=_rounded_image(root,C['surface'],C['border'],C['bg'])
    root._theme_images.extend([normal,active])
    style.element_create('Soft.tab','image',normal,('selected',active),border=11,padding=0,sticky='nsew')
    style.layout('TNotebook.Tab',[('Soft.tab',{'sticky':'nswe','children':[('Notebook.padding',{'sticky':'nswe','children':[('Notebook.label',{'sticky':'nswe'})]})]})])
    style.configure('TNotebook.Tab',padding=(18,9),foreground=C['muted'])
    style.map('TNotebook.Tab',foreground=[('selected',C['accent'])])
    style.configure('Treeview',background=C['surface'],fieldbackground=C['surface'],rowheight=32,borderwidth=0,font=root.small)
    style.layout('Treeview',[('Treeview.treearea',{'sticky':'nswe'})])
    style.configure('Treeview.Heading',font=(root.family,9,'bold'),background=C['soft'],foreground=C['muted'],padding=(8,8),relief='flat',borderwidth=0)
    style.map('Treeview',background=[('selected',C['light'])],foreground=[('selected',C['accent'])])
    style.configure('Nav.Treeview',background=C['nav'],fieldbackground=C['nav'],foreground='#625f55',rowheight=30,borderwidth=0)
    style.map('Nav.Treeview',background=[('selected',C['nav2'])],foreground=[('selected',C['ink'])])
    style.configure('Horizontal.TProgressbar',background=C['accent'],troughcolor=C['nav2'],borderwidth=0,lightcolor=C['accent'],darkcolor=C['accent'])
    for orient in ('Vertical','Horizontal'):
        style.configure(orient+'.TScrollbar',gripcount=0,background='#d8d5cb',troughcolor=C['soft'],borderwidth=0,arrowsize=9)
        style.map(orient+'.TScrollbar',background=[('active','#bfb9ac')])
    return style
