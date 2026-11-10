"""Hierarchy-preserving architecture model, orthogonal routing and SVG export.

An instance is always drawn inside its REAL parent. Ownership is an annotation,
never a replacement for the elaborated parent relation. No connectivity is inferred.
"""
from collections import defaultdict, deque
import heapq
import html
import json
import math

from .core import ancestors, display_graph


COLORS = dict(ink='#292823', muted='#827e72', wire='#73877e', accent='#b56346',
              teal='#38796c', amber='#a27935', border='#ddd8cb', surface='#ffffff',
              background='#f8f7f2')


def _local(name, scope):
    return name[len(scope) + 1:] if name.startswith(scope + '.') else name


def witness_highlights(scene, graph, edge_indices):
    """Match visible wires even when a witness ends at a coalesced InstPort.

    Net/Port/InstPort bindings drawn as one pin have no visible segment. Every
    other constituent edge must still belong to the selected NPI witness.
    """
    proof=set(edge_indices);selected=set()
    for wire in scene['connections']:
        for witness in wire['evidence']:
            visible=set()
            for index in witness:
                edge=graph['edges'][index]
                a,b=graph['nodes'][edge['source']],graph['nodes'][edge['target']]
                alias=all(a.get(k)==b.get(k) for k in ('base_name','actual_scope','left','right'))
                if not alias:visible.add(index)
            if visible and visible.issubset(proof):
                selected.add(wire['id']);break
    return selected


def build_architecture(graph, result=None):
    """Build a visual projection with raw witnesses attached to every connection."""
    result = result or {}
    view = display_graph(graph)
    insts = graph['instances']
    module_insts = {k: v for k, v in insts.items() if v['cell'] == 'npiNlModuleCell'}
    port_inventory = {s['name']: s for s in graph.get('signals', []) if s['type'] == 'npiNlPort'}
    pins, anchors = {}, {}
    needed = {r['scope'] for r in graph.get('regions', [])}
    targets = {i['name'] for i in result.get('candidates', [])}
    needed.update(targets)
    for vid, node in view['nodes'].items():
        scope = node['actual_scope']
        if scope not in module_insts:
            continue
        needed.add(scope)
        declaration = port_inventory.get(node['base_name'])
        is_port = node['base_type'] == 'npiNlPort' or declaration is not None
        if is_port:
            key = 'port:' + node['base_name']
            kind = 'port'
            direction = (declaration or {}).get('direction') or node['direction']
        elif node['is_stop']:
            key, kind, direction = 'stop:' + node['base_name'], 'stop', ''
        elif node['is_source']:
            key, kind, direction = 'signal:' + node['base_name'], 'signal', ''
        else:
            # Named nets become labels on wires, not independent graph boxes.
            continue
        anchors[vid] = key
        if key not in pins:
            pins[key] = dict(id=key, kind=kind, name=node['base_name'], label=_local(node['base_name'], scope),
                             scope=scope, direction=direction, raw_ids=[], selected=False, source=False,
                             owner_scope=node.get('owner_scope'), stop_reasons=[], bits=[])
        pin = pins[key]
        pin['raw_ids'].extend(node['raw_ids'])
        pin['selected'] |= node['is_selected']
        pin['source'] |= node['is_source']
        pin['stop_reasons'] = sorted(set(pin['stop_reasons']) | set(node.get('stop_reasons', [])))
        pin['bits'] = sorted(set(pin['bits']) | set(node['bits']))
    # Isolated selected nets still appear at their actual scope, without inventing a port.
    incident = {e[k] for e in view['edges'] for k in ('source', 'target')}
    for vid, node in view['nodes'].items():
        if vid not in anchors and node['is_selected'] and vid not in incident:
            key = 'signal:' + node['base_name']
            anchors[vid] = key
            pins[key] = dict(id=key, kind='signal', name=node['base_name'], label=node['local_name'],
                             scope=node['actual_scope'], direction='', raw_ids=node['raw_ids'],
                             selected=True, source=False, owner_scope=node.get('owner_scope'),
                             stop_reasons=[], bits=node['bits'])
    adj = defaultdict(list)
    for i, edge in enumerate(view['edges']):
        adj[edge['source']].append((edge['target'], i))
    combined = {}
    for start in anchors:
        queue = deque([(start, [], [], [start])])
        visited = set()
        while queue:
            current, traversed, labels, chain = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            for nxt, ei in adj.get(current, []):
                path = traversed + [ei]
                signal_labels = list(labels)
                n = view['nodes'][nxt]
                if nxt not in anchors:
                    signal_labels.append(dict(name=n['base_name'], scope=n['actual_scope'],
                                              local_name=_local(n['base_name'], n['actual_scope']),
                                              owner_scope=n.get('owner_scope'), selected=n['is_selected']))
                if nxt in anchors:
                    a, b = anchors[start], anchors[nxt]
                    if a == b:
                        queue.append((nxt, path, signal_labels, chain + [nxt]))
                        continue
                    kinds = sorted({k for j in path for k in view['edges'][j]['kinds']})
                    key = (a, b, tuple(kinds), tuple(s['name'] for s in signal_labels))
                    if key not in combined:
                        combined[key] = dict(id='wire:' + str(len(combined) + 1), source=a, target=b,
                                             kinds=kinds, signals=signal_labels, evidence=[], raw_ids=[])
                    connection = combined[key]
                    proof = []
                    for j in path:
                        for witness in view['edges'][j].get('witnesses', [])[:1]:
                            proof.extend(witness['edge_indices'])
                            connection['raw_ids'].extend(witness['nodes'])
                    connection['evidence'].append(sorted(set(proof)))
                else:
                    queue.append((nxt, path, signal_labels, chain + [nxt]))
    for name in list(needed):
        needed.update(p for p in ancestors(insts, name) if p in module_insts)
    selected = {r['scope'] for r in graph.get('regions', [])}
    boxes = {}
    for name in sorted(needed):
        if name not in module_insts:
            continue
        info = module_insts[name]
        parent = next((a for a in ancestors(insts, info['parent']) if a in needed and a in module_insts), '')
        boxes[name] = dict(id=name, name=name, label=_local(name, parent) if parent else name,
                           parent=parent, module=info['module'], owner_scope=info.get('owner_scope'),
                           selected=name in selected, target=name in targets, children=[], pins=[],
                           depth=sum(1 for _ in ancestors(insts, name)) - 1)
    for name, box in boxes.items():
        if box['parent'] in boxes:
            boxes[box['parent']]['children'].append(name)
    for pid, pin in pins.items():
        if pin['scope'] in boxes:
            boxes[pin['scope']]['pins'].append(pid)
    roots = [n for n, b in boxes.items() if b['parent'] not in boxes]
    connections = sorted(combined.values(), key=lambda e: (e['source'], e['target'], e['kinds']))
    for i, connection in enumerate(connections):
        connection['id'] = 'wire:' + str(i + 1)
    scene = dict(schema_version=1, boxes=boxes, pins=pins, connections=connections, roots=roots,
                 regions=graph.get('regions', []), warnings=[], source='NPI elaborated design',
                 semantics='Physical containment uses actual parents; check ownership is annotation only.')
    layout(scene)
    return scene


def _chain(scene, scope):
    while scope in scene['boxes']:
        yield scope
        scope = scene['boxes'][scope]['parent']


def _lca(scene, a, b):
    second = set(_chain(scene, b))
    return next((n for n in _chain(scene, a) if n in second), '')


def _branch(scene, parent, scope):
    last = scope
    for item in _chain(scene, scope):
        if item == parent:
            return last if last != parent else None
        last = item
    return None


def layout(scene):
    boxes, pins, connections = scene['boxes'], scene['pins'], scene['connections']

    def measure(name):
        box = boxes[name]
        inputs = [p for p in box['pins'] if pins[p]['kind'] == 'port' and pins[p]['direction'] != 'npiNlOutput']
        outputs = [p for p in box['pins'] if pins[p]['kind'] == 'port' and pins[p]['direction'] == 'npiNlOutput']
        others = [p for p in box['pins'] if pins[p]['kind'] != 'port']
        box['inputs'], box['outputs'], box['others'] = inputs, outputs, others
        for child in box['children']:
            measure(child)
        if not box['children']:
            box['w'] = 258
            box['h'] = max(154, 94 + max(len(inputs), len(outputs)) * 25 + len(others) * 26)
            return
        adjacency, incoming, ranks = defaultdict(set), defaultdict(int), {}
        for e in connections:
            a = _branch(scene, name, pins[e['source']]['scope'])
            b = _branch(scene, name, pins[e['target']]['scope'])
            if a and b and a != b and b not in adjacency[a]:
                adjacency[a].add(b)
                incoming[b] += 1
        queue = deque(sorted(c for c in box['children'] if not incoming[c]))
        for child in queue:
            ranks[child] = 0
        while queue:
            current = queue.popleft()
            for nxt in sorted(adjacency[current]):
                ranks[nxt] = max(ranks.get(nxt, 0), ranks[current] + 1)
                incoming[nxt] -= 1
                if not incoming[nxt]:
                    queue.append(nxt)
        for child in box['children']:
            ranks.setdefault(child, 0)  # A feedback group remains a peer group.
        columns = defaultdict(list)
        for child in box['children']:
            columns[ranks[child]].append(child)
        layout_columns=[]
        for rank in sorted(columns):
            items=sorted(columns[rank])
            rows=1 if len(box['children'])<=3 or any(boxes[c]['children'] for c in items) else 2
            layout_columns.extend(items[i:i+rows] for i in range(0,len(items),rows))
        x = 80
        maximum_h = 0
        for items in layout_columns:
            col_h = sum(boxes[c]['h'] for c in items) + 52 * (len(items) - 1)
            maximum_h = max(maximum_h, col_h)
            col_w = max(boxes[c]['w'] for c in items)
            y = 108
            for child in items:
                boxes[child]['rx'], boxes[child]['ry'] = x, y
                y += boxes[child]['h'] + 52
            x += col_w + 104
        box['w'] = max(420, x - 104 + 80)
        box['h'] = max(170 + maximum_h, 108 + max(len(inputs), len(outputs)) * 28)
        # Center shorter columns vertically in the parent for easier peer comparison.
        for items in layout_columns:
            col_h = sum(boxes[c]['h'] for c in items) + 52 * (len(items) - 1)
            for child in items:
                boxes[child]['ry'] += (maximum_h - col_h) / 2

    def place(name, x, y):
        box = boxes[name]
        box['x'], box['y'] = x, y
        for side, ids in [('left', box['inputs']), ('right', box['outputs'])]:
            for i, pid in enumerate(sorted(ids, key=lambda p: pins[p]['name'])):
                pin = pins[pid]
                pin['x'] = x if side == 'left' else x + box['w']
                pin['y'] = y + 94 + i * 25
                pin['side'] = side
        stop_ids={pid for pid in box['others'] if pins[pid]['kind']=='stop'}
        input_stops=sorted(stop_ids & {e['target'] for e in connections})
        output_stops=sorted(stop_ids & {e['source'] for e in connections})
        split_stops=bool(input_stops and output_stops and not set(input_stops)&set(output_stops))
        for i, pid in enumerate(box['others']):
            pin = pins[pid]
            pin['x'] = x + box['w'] / 2 if pin['kind'] == 'stop' else x + 30
            pin['y'] = y + box['h'] - 30 - i * 26
            pin['side'] = 'inside'
            if split_stops and pid in stop_ids:
                incoming=pid in input_stops;group=input_stops if incoming else output_stops
                pin['badge_width']=(box['w']-48)/2
                pin['x']=x+24+pin['badge_width']/2 if incoming else x+box['w']-24-pin['badge_width']/2
                pin['y']=y+box['h']-30-group.index(pid)*26
                pin['stop_side']='input' if incoming else 'output'
        for child in box['children']:
            c = boxes[child]
            place(child, x + c['rx'], y + c['ry'])

    x = 48
    for root in scene['roots']:
        measure(root)
        place(root, x, 90)
        x += boxes[root]['w'] + 72
    scene['width'] = max(800, x - 24)
    scene['height'] = max([320] + [boxes[r]['y'] + boxes[r]['h'] + 48 for r in scene['roots']])
    occupied = []
    for index, e in enumerate(connections):
        a, b = pins[e['source']], pins[e['target']]
        lca = _lca(scene, a['scope'], b['scope'])
        e['scope'] = lca
        e['internal'] = a['scope'] == b['scope'] and not boxes[a['scope']]['children']
        if e['internal']:
            # Internal evidence stays inside its module, distinct from inter-instance wires.
            reserve=lambda p:min(102,max(24,len(p['label'])*7+18))
            start=(a['x']+reserve(a) if a['side']=='left' else a['x']-reserve(a),a['y'])
            end=(b['x']-reserve(b) if b['side']=='right' else b['x'],b['y'])
            if a['kind']=='stop':
                start=(a['x'],a['y']-11)
                e['points']=simplify([start,(start[0],end[1]),end])
            elif b['kind']=='stop':
                end=(b['x'],b['y']-11)
                e['points']=simplify([start,(end[0],start[1]),end])
            else:
                mid=(start[0]+end[0])/2
                e['points']=simplify([start,(mid,start[1]),(mid,end[1]),end])
        else:
            start, end = (a['x'], a['y']), (b['x'], b['y'])
            def stub(p, at_source):
                if p['side'] == 'inside':
                    return p['x'] + (18 if at_source else -18), p['y']
                inward = p['scope'] == lca
                direction = 1 if p['side'] == 'right' else -1
                if inward:
                    direction *= -1
                return p['x'] + direction * 22, p['y']
            sa, sb = stub(a, True), stub(b, False)
            obstacles = []
            if lca:
                for child in boxes[lca]['children']:
                    c = boxes[child]
                    rect = (c['x'] - 7, c['y'] - 7, c['x'] + c['w'] + 7, c['y'] + c['h'] + 7)
                    if not (_inside(sa, rect) or _inside(sb, rect)):
                        obstacles.append(rect)
            group = tuple(s['name'] for s in e['signals']) or (e['source'],)
            route = orthogonal_route(sa, sb, obstacles, [segment for g, segment in occupied if g != group])
            if route is None:
                e['routing_warning'] = True
                scene['warnings'].append('Route requires review: ' + e['id'])
                route = [sa, (sa[0], min(sa[1], sb[1]) - 28), (sb[0], min(sa[1], sb[1]) - 28), sb]
            e['points'] = simplify([start] + route + [end])
            occupied.extend((group, segment) for segment in zip(e['points'], e['points'][1:]))
        if e['signals']:
            segments = list(zip(e['points'], e['points'][1:]))
            horizontal = [s for s in segments if s[0][1] == s[1][1]]
            segment = max(horizontal or segments, key=lambda s: abs(s[0][0] - s[1][0]) + abs(s[0][1] - s[1][1]))
            e['label_at'] = ((segment[0][0] + segment[1][0]) / 2, (segment[0][1] + segment[1][1]) / 2 - 11)
            e['label'] = ', '.join(s['local_name'] if s['scope'] == lca else s['name'] for s in e['signals'])


def _inside(point, rect):
    return rect[0] < point[0] < rect[2] and rect[1] < point[1] < rect[3]


def simplify(points):
    out = []
    for p in points:
        if out and p == out[-1]:
            continue
        if len(out) >= 2 and ((out[-2][0] == out[-1][0] == p[0]) or (out[-2][1] == out[-1][1] == p[1])):
            out[-1] = p
        else:
            out.append(p)
    return out


def orthogonal_route(start, end, obstacles, occupied=()):
    xs = sorted({x + d for x in (start[0], end[0]) for d in (-12, 0, 12)} |
                {x + d for r in obstacles for x, sign in ((r[0], -1), (r[2], 1)) for d in (8 * sign, 20 * sign, 32 * sign)})
    ys = sorted({y + d for y in (start[1], end[1]) for d in (-12, 0, 12)} |
                {y + d for r in obstacles for y, sign in ((r[1], -1), (r[3], 1)) for d in (8 * sign, 20 * sign, 32 * sign)})
    source, target = (xs.index(start[0]), ys.index(start[1])), (xs.index(end[0]), ys.index(end[1]))
    def blocked(a, b):
        for x0, y0, x1, y1 in obstacles:
            if a[1] == b[1] and y0 < a[1] < y1 and max(a[0], b[0]) > x0 and min(a[0], b[0]) < x1:
                return True
            if a[0] == b[0] and x0 < a[0] < x1 and max(a[1], b[1]) > y0 and min(a[1], b[1]) < y1:
                return True
        return False
    initial = source + (-1,)
    costs, previous = {initial: 0}, {}
    queue = [(0, initial)]
    while queue:
        _, state = heapq.heappop(queue)
        ix, iy, direction = state
        if (ix, iy) == target:
            route = [(xs[ix], ys[iy])]
            while state in previous:
                state = previous[state]
                route.append((xs[state[0]], ys[state[1]]))
            return simplify(list(reversed(route)))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = ix + dx, iy + dy
            if not (0 <= nx < len(xs) and 0 <= ny < len(ys)):
                continue
            a, b = (xs[ix], ys[iy]), (xs[nx], ys[ny])
            if blocked(a, b):
                continue
            nd = 0 if dx else 1
            ns = (nx, ny, nd)
            distance = abs(a[0] - b[0]) + abs(a[1] - b[1]) + (18 if direction not in (-1, nd) else 0)
            for c, d in occupied:
                if a[0] == b[0] == c[0] == d[0]:
                    distance += 30 * max(0, min(max(a[1], b[1]), max(c[1], d[1])) - max(min(a[1], b[1]), min(c[1], d[1])))
                elif a[1] == b[1] == c[1] == d[1]:
                    distance += 30 * max(0, min(max(a[0], b[0]), max(c[0], d[0])) - max(min(a[0], b[0]), min(c[0], d[0])))
            cost = costs[state] + distance
            if cost < costs.get(ns, float('inf')):
                costs[ns], previous[ns] = cost, state
                heuristic = abs(b[0] - end[0]) + abs(b[1] - end[1])
                heapq.heappush(queue, (cost + heuristic, ns))
    return None


def _short(text, width, font_size):
    budget, value = width / font_size, ''
    used = 0
    for ch in text:
        used += 1 if ord(ch) > 255 else .57
        if used > budget - 1:
            return value + '…'
        value += ch
    return value


def soften_route(points, radius=8):
    """Round only the corner's local envelope; retain the routed endpoints."""
    if len(points)<3:return points
    out=[points[0]]
    for a,b,c in zip(points,points[1:],points[2:]):
        d1=math.hypot(b[0]-a[0],b[1]-a[1]);d2=math.hypot(c[0]-b[0],c[1]-b[1])
        if not d1 or not d2:continue
        r=min(radius,d1/2,d2/2)
        start=(b[0]+(a[0]-b[0])*r/d1,b[1]+(a[1]-b[1])*r/d1)
        stop=(b[0]+(c[0]-b[0])*r/d2,b[1]+(c[1]-b[1])*r/d2)
        out.append(start)
        for n in range(1,7):
            t=n/6
            out.append(((1-t)**2*start[0]+2*(1-t)*t*b[0]+t*t*stop[0],
                        (1-t)**2*start[1]+2*(1-t)*t*b[1]+t*t*stop[1]))
    return out+[points[-1]]


def primitives(scene, selected=None, highlight_edges=None):
    """Shared vector primitives keep the Tk canvas and exported SVG consistent."""
    items = []
    def rect(x, y, w, h, fill, stroke='', radius=8, width=1, key=None):
        items.append(dict(kind='rect', x=x, y=y, w=w, h=h, fill=fill, stroke=stroke, radius=radius, width=width, key=key))
    def text(x, y, value, size=12, color=None, anchor='start', bold=False, key=None):
        maximum=None
        if key and key.startswith('module:'):
            box=scene['boxes'][key[7:]]
            maximum=box['w']-38
            if size==15:maximum=box['w']-(105 if box['selected'] else 38)
            elif size==9:maximum=box['w']-42
            elif anchor=='middle':maximum=64
        elif key in scene['pins']:
            pin=scene['pins'][key]
            maximum=pin.get('badge_width',scene['boxes'][pin['scope']]['w']-44) if pin['kind']=='stop' else 100
        elif key and key.startswith('wire:'):
            maximum=max(24,len(value)*6.4+10)
        items.append(dict(kind='text', x=x, y=y, text=value, size=size, fill=color or COLORS['ink'], anchor=anchor, bold=bold, key=key,max_width=maximum))
    text(48, 29, 'DESIGN  /  ARCHITECTURE', 12, COLORS['accent'], bold=True)
    text(48, 53, '层次包含与端口连接', 18, COLORS['ink'], bold=True)
    text(scene['width']-48, 52, '%d 个实例  /  %d 条连接' % (len(scene['boxes']),len(scene['connections'])), 11, COLORS['muted'], 'end')
    for box in sorted(scene['boxes'].values(), key=lambda b: b['depth']):
        x, y, w, h = (box[k] for k in ('x', 'y', 'w', 'h'))
        key = 'module:' + box['name']
        container = bool(box['children'])
        if selected==key:rect(x-5,y-5,w+10,h+10,'#f0ddcf',radius=22)
        if not container:
            rect(x,y+5,w,h,'#e8e4da',radius=16)
            rect(x,y+2,w,h,'#f0ede5',radius=16)
        fill = ('#efede5' if box['depth'] % 2 == 0 else '#f6f4ee') if container else '#ffffff'
        border = '#c89982' if box['selected'] else '#d7d2c5' if container else '#c9d4cc'
        rect(x,y,w,h,fill,border,18 if container else 14,2 if selected==key else 1.2,key)
        if not container:
            rect(x+9,y+9,w-18,49,'#f4f7f3',radius=9,key=key)
    for edge in scene['connections']:
        dim = highlight_edges is not None and edge['id'] not in highlight_edges
        color = '#dedbd2' if dim else COLORS['teal'] if 'LOGIC_DEP' in edge['kinds'] else COLORS['wire']
        if selected == edge['id']:
            color = COLORS['accent']
        route=soften_route(edge['points'])
        if not edge['internal']:
            items.append(dict(kind='line', points=route, fill=COLORS['background'], width=5, key=edge['id']))
        items.append(dict(kind='line', points=route, fill=color,
                          width=2.6 if selected == edge['id'] or (highlight_edges and edge['id'] in highlight_edges) else 1.8,
                          dash='LOGIC_DEP' in edge['kinds'], arrow=True, key=edge['id']))
        if edge.get('label'):
            lx, ly = edge['label_at']
            label = _short(edge['label'], 220, 11)
            lw = min(235, max(35, len(label) * 6.4 + 16))
            rect(lx-lw/2,ly-11,lw,22,'#ffffff','#e5e2d9',radius=7,key=edge['id'])
            text(lx, ly, label, 11, COLORS['teal'] if not dim else COLORS['muted'], 'middle', key=edge['id'])
    for box in scene['boxes'].values():
        x, y, w, h = (box[k] for k in ('x', 'y', 'w', 'h'))
        key = 'module:' + box['name']
        container = bool(box['children'])
        title = box['name'] if container else box['label']
        text(x + 19, y + 26, _short(title, w - (105 if box['selected'] else 38), 15), 15, bold=True, key=key)
        text(x + 19, y + 49, 'module  ' + _short(box['module'], w - 80, 11), 11, COLORS['muted'], key=key)
        if box['selected']:
            rect(x+w-85,y+14,68,23,'#ead7c7',radius=10,key=key)
            text(x + w - 51, y + 25, '检查层次', 10, COLORS['accent'], 'middle', True, key)
        if container:
            text(x + w - 20, y + 50, '%d 个同级实例' % len(box['children']), 10, COLORS['muted'], 'end', key=key)
        else:
            owner = box.get('owner_scope') or '所选范围外'
            text(x + 19, y + h - 14, '归属  ' + _short(owner, w - 64, 9), 9, COLORS['muted'], key=key)
        items.append(dict(kind='line', points=[(x + 16, y + 65), (x + w - 16, y + 65)], fill='#dfdbcf', width=1, key=key))
    for pin in scene['pins'].values():
        x, y, key = pin['x'], pin['y'], pin['id']
        if pin['kind'] == 'stop':
            box = scene['boxes'][pin['scope']]
            width=pin.get('badge_width',box['w']-36)
            rect(x-width/2,y-10,width,21,'#f5ecd9',radius=8,key=key)
            label = '时序边界 · 停止' if 'STOP_SEQUENTIAL' in pin['stop_reasons'] else '追踪停止 · 查看详情'
            if pin.get('stop_side'):label='输入侧停止' if pin['stop_side']=='input' else '输出侧停止'
            text(x, y, label, 10, COLORS['amber'], 'middle', key=key)
            continue
        color = COLORS['accent'] if pin['selected'] else COLORS['teal']
        items.append(dict(kind='oval',x=x-5,y=y-5,w=10,h=10,fill='#ffffff',stroke=color,width=1.8,key=key))
        items.append(dict(kind='oval',x=x-2,y=y-2,w=4,h=4,fill=color,stroke='',width=0,key=key))
        side = pin['side']
        px = x + 12 if side in ('left', 'inside') else x - 12
        label = _short(pin['label'], 100, 11)
        lw = min(102, len(label) * 7 + 6)
        rect(px-4 if side!='right' else px-lw+4,y-10,lw,20,'#f8eee6' if pin['selected'] else '#ffffff',radius=6,key=key)
        text(px, y, label, 11, color, 'end' if side == 'right' else 'start', pin['source'], key)
    return items


def svg_architecture(scene, title='RTLWire | Design architecture'):
    esc = html.escape
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s" viewBox="0 0 %s %s">' %
           (scene['width'], scene['height'], scene['width'], scene['height']), '<title>' + esc(title) + '</title>',
           '<rect width="100%" height="100%" fill="#f8f7f2"/>',
           '<g font-family="Microsoft YaHei UI,WenQuanYi Micro Hei,DejaVu Sans,sans-serif">']
    for p in primitives(scene):
        key = esc(p.get('key') or '')
        out.append('<g data-object="%s"><title>%s</title>' % (key, key))
        if p['kind'] in ('rect', 'oval'):
            if p['kind'] == 'rect':
                attrs = dict(p, stroke=p['stroke'] or 'none')
                out.append('<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>'.format(**attrs))
            else:
                out.append('<ellipse cx="%s" cy="%s" rx="%s" ry="%s" fill="%s" stroke="%s" stroke-width="%s"/>' %
                           (p['x'] + p['w'] / 2, p['y'] + p['h'] / 2, p['w'] / 2, p['h'] / 2, p['fill'], p['stroke'] or 'none', p['width']))
        elif p['kind'] == 'text':
            out.append('<text x="%s" y="%s" dy="0.35em" font-size="%s" text-anchor="%s" fill="%s" font-weight="%s">%s</text>' %
                       (p['x'], p['y'], p['size'], p['anchor'], p['fill'], '600' if p['bold'] else '400', esc(p['text'])))
        else:
            pts = ' '.join('%s,%s' % tuple(v) for v in p['points'])
            out.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="%s" stroke-linejoin="round"%s/>' %
                       (pts, p['fill'], p['width'], ' stroke-dasharray="5 4"' if p.get('dash') else ''))
            if p.get('arrow') and len(p['points']) > 1:
                a, b = p['points'][-2:]
                angle = math.atan2(b[1] - a[1], b[0] - a[0])
                corners = [b, (b[0] - 7 * math.cos(angle) + 3 * math.sin(angle), b[1] - 7 * math.sin(angle) - 3 * math.cos(angle)),
                           (b[0] - 7 * math.cos(angle) - 3 * math.sin(angle), b[1] - 7 * math.sin(angle) + 3 * math.cos(angle))]
                out.append('<polygon points="%s" fill="%s"/>' % (' '.join('%s,%s' % v for v in corners), p['fill']))
        out.append('</g>')
    return '\n'.join(out + ['</g></svg>'])
