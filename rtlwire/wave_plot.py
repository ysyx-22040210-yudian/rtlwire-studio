"""Shared vector waveform scene for Tk and portable SVG exports."""
from html import escape
from .wave_core import Series, ns_text
from .wave_groups import POLICY_LABELS


COLORS = dict(ink='#292823', muted='#827e72', purple='#b56346', teal='#38796c',
              red='#b24f4c', amber='#a27935', border='#e8e4da')


def value_text(bits):
    if bits == '':
        return '—'
    if bits is None or '?' in bits:
        return '无数据'
    if len(bits) == 1:
        return bits.upper()
    if set(bits) == {'x'}:
        return 'X × ' + str(len(bits))
    if set(bits) == {'z'}:
        return 'Z × ' + str(len(bits))
    if set(bits) <= {'0','1'}:
        return "%d'h%s" % (len(bits), format(int(bits, 2), '0%dx' % ((len(bits)+3)//4)).upper())
    return bits.upper()


def scene(report, data, domain, cycle, width=1240, window=None, selected=None, focus_only=False, series_cache=None):
    begin, end = window or cycle['window']
    if end <= begin:
        end = begin + 1
    width = max(640, width)
    left, right, top, row_h = 208, width-24, 102, 44
    outputs = cycle['checks']
    if focus_only and selected:
        outputs = [r for r in outputs if r['signal']==selected]
    lanes = [dict(name=domain['config'][key], role=key, status='CONTROL') for key in ('iso_en','power_down')]
    lanes += [dict(name=r['signal'], role='OUT · %d bit · %s' % (r['width'],POLICY_LABELS.get(r.get('clamp_policy'),'钳 0')), status=r['status']) for r in outputs]
    height = top + len(lanes)*row_h + 26
    p = []

    def rect(x,y,w,h,fill,stroke='',radius=0):
        p.append(dict(kind='rect',x=x,y=y,w=w,h=h,fill=fill,stroke=stroke,radius=radius))

    def text(x,y,label,color=COLORS['ink'],size=11,bold=False,anchor='start'):
        p.append(dict(kind='text',x=x,y=y,text=str(label),fill=color,size=size,bold=bold,anchor=anchor))

    def line(points,color=COLORS['border'],width=1,dash=False):
        p.append(dict(kind='line',points=points,fill=color,width=width,dash=dash))

    def x(t):
        return left + (t-begin)/(end-begin)*(right-left)

    rect(0,0,width,height,'#ffffff')
    text(16,20,domain['config']['scope'],size=14,bold=True)
    text(16,40,'周期 %02d  /  %s  /  同一时刻最终值' % (cycle['index'],cycle['status']),COLORS['muted'],10)
    text(right,20,ns_text(begin,report['file']['scale'])+' — '+ns_text(end,report['file']['scale'])+' ns',COLORS['muted'],11,anchor='end')
    policies={r.get('clamp_policy','clamp_zero') for r in outputs}
    isolation=POLICY_LABELS.get(next(iter(policies)),'按 RPT 分组') if len(policies)==1 else '按 RPT 分组'
    phases = [('iso_rise','power_fall','#edf3ec',isolation),('power_fall','power_rise','#f7efdf','掉电 · X'),('power_rise','iso_fall','#f6eae2','恢复 / '+isolation)]
    for a,b,color,label in phases:
        ta,tb = cycle.get(a),cycle.get(b)
        if ta is not None and tb is not None and tb>ta and ta<end and tb>begin:
            xa,xb=x(max(begin,ta)),x(min(end,tb))
            rect(xa+1,50,max(1,xb-xa-2),22,color,radius=7)
            rect(xa,top,xb-xa,height-top-18,'#f9faf6' if a=='iso_rise' else '#fcf9f2' if a=='power_fall' else '#fcf7f3')
            if xb-xa>65:
                text((xa+xb)/2,61,label,COLORS['ink'],10,anchor='middle')
    for j in range(9):
        t=begin+(end-begin)*j//8
        xx=x(t)
        line([(xx,98),(xx,height-18)],'#e8e4da',dash=True)
        text(xx,92,ns_text(t,report['file']['scale']),COLORS['muted'],10,anchor='middle')
    text(16,83,'SIGNAL / VALUE',COLORS['muted'],9,True)
    for idx,lane in enumerate(lanes):
        y = top+idx*row_h
        rect(6,y+2,left-18,row_h-4,'#f5e9e1' if lane['name']==selected else '#f3f2ed' if idx<2 else '#faf9f5',radius=8)
        name=lane['name'].rsplit('.',1)[-1]
        if len(name)>26:
            name=name[:23]+'…'
        color=COLORS['purple'] if idx<2 else COLORS['red'] if lane['status']=='FAIL' else COLORS['amber'] if lane['status']=='UNKNOWN' else COLORS['teal']
        text(18,y+15,name,color,13,True)
        text(18,y+33,lane['role']+('  ·  '+lane['status'] if idx>=2 else ''),COLORS['muted'],10)
        line([(left,y+row_h),(right,y+row_h)])
        series=series_cache.get(lane['name']) if series_cache is not None else None
        if series is None:
            series=Series(data['signals'].get(lane['name']))
        samples=series.interval(begin,end)
        prior=None
        for n,(t,v) in enumerate(samples):
            stop=samples[n+1][0] if n+1<len(samples) else end
            x1,x2=x(t),x(stop)
            high,low=y+11,y+33
            if series.width==1 and v in ('0','1'):
                yy=high if v=='1' else low
                if prior is not None and prior != yy:
                    line([(x1,prior),(x1,yy)],color,1.8)
                line([(x1,yy),(x2,yy)],color,1.8)
                prior=yy
            else:
                missing=v is None or '?' in v
                unknown=bool(v) and any(c in v for c in 'xz')
                fill='#f6ecd9' if unknown else '#eeece5' if missing else '#f8eae6' if lane['status']=='FAIL' else '#edf3eb'
                edge=COLORS['amber'] if unknown else COLORS['muted'] if missing else color
                cap=min(4,max(0,(x2-x1)/3));mid=(high+low)/2
                p.append(dict(kind='polygon',points=[(x1,mid),(x1+cap,high),(x2-cap,high),(x2,mid),(x2-cap,low),(x1+cap,low)],fill=fill,stroke=edge))
                label=value_text(v)
                if x2-x1>len(label)*7+10:
                    text((x1+x2)/2,y+22,label,edge,12,anchor='middle')
                prior=None
        if lane['name']==selected:
            check=next((r for r in outputs if r['signal']==selected),{})
            times=[r['time'] for r in check.get('checks',{}).values() if r['status']=='FAIL' and r.get('time') is not None]
            if times and begin<=min(times)<=end:
                xx=x(min(times));line([(xx,y+5),(xx,y+38)],COLORS['red'],2.3)
                p.append(dict(kind='polygon',points=[(xx,y+3),(xx+4,y+7),(xx,y+11),(xx-4,y+7)],fill=COLORS['red'],stroke=COLORS['red']))
    for key,letter in [('iso_rise','A'),('power_fall','B'),('power_rise','C'),('iso_fall','D')]:
        t=cycle.get(key)
        if t is not None and begin<=t<=end:
            xx=x(t)
            line([(xx,97),(xx,height-18)],'#bcb3a4',1,dash=True)
            text(xx,79,letter,COLORS['purple'],10,True,anchor='middle')
    return dict(width=width,height=height,primitives=p,lanes=lanes,left=left,right=right,top=top,row_height=row_h,window=[begin,end])


def svg(scene_data):
    chunks=['<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s" viewBox="0 0 %s %s">' %
            (scene_data['width'],scene_data['height'],scene_data['width'],scene_data['height'])]
    chunks.append('<title>RTLWire isolation and power waveform</title>')
    for p in scene_data['primitives']:
        if p['kind']=='rect':
            chunks.append('<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}"/>'.format(**dict(p,stroke=p['stroke'] or 'none')))
        elif p['kind']=='polygon':
            chunks.append('<polygon points="%s" fill="%s" stroke="%s" stroke-linejoin="round"/>' % (' '.join('%s,%s'%tuple(pt) for pt in p['points']),p['fill'],p['stroke']))
        elif p['kind']=='line':
            points=' '.join('%s,%s'%tuple(pt) for pt in p['points'])
            chunks.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="%s"%s/>' % (points,p['fill'],p['width'],' stroke-dasharray="3 4"' if p['dash'] else ''))
        else:
            chunks.append('<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" text-anchor="{anchor}" dominant-baseline="middle" font-family="Noto Sans CJK SC,WenQuanYi Micro Hei,sans-serif" font-weight="{weight}">{label}</text>'.format(**dict(p,weight='bold' if p['bold'] else 'normal',label=escape(p['text']))))
    chunks.append('</svg>')
    return '\n'.join(chunks)
