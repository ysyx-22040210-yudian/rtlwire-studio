"""Portable SVG/DOT/HTML reports; no GUI or external rendering dependency."""
import csv
import html
import json
import textwrap
from collections import defaultdict, deque
from .architecture import build_architecture, svg_architecture


def dump_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def svg_graph(view, title):
    nodes, edges = view['nodes'], view['edges']
    if not nodes:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="140"><text x="24" y="60">No resolved graph nodes; see report.json</text></svg>'
    adj, incoming = defaultdict(list), defaultdict(int)
    for e in edges:
        adj[e['source']].append(e['target'])
        incoming[e['target']] += 1
    ranks = {}
    queue = deque([n for n in nodes if not incoming[n]])
    for n in queue:
        ranks[n] = 0
    while queue:
        n = queue.popleft()
        for nxt in adj[n]:
            ranks[nxt] = max(ranks.get(nxt, 0), ranks[n] + 1)
            incoming[nxt] -= 1
            if incoming[nxt] == 0:
                queue.append(nxt)
    for n in nodes:
        ranks.setdefault(n, 0)
    levels = defaultdict(list)
    for node in nodes.values():
        levels[ranks[node['id']]].append(node)
    col_width, node_width, node_height, stride = 458, 420, 116, 158
    maximum = max(len(v) for v in levels.values())
    content_width = max(700, maximum * col_width + 48)
    width = content_width + 100
    region_lines = []
    for region in view['regions']:
        label = 'Owner %s = subtree minus {%s}' % (region['scope'], ', '.join(region['excluded_subtrees']) or 'none')
        region_lines.extend(textwrap.wrap(label, int((width - 48) / 7)))
    header = 98 + len(region_lines) * 18
    height = header + (max(levels) + 1) * stride + 28
    positions = {}
    parents = defaultdict(list)
    for edge in edges:
        parents[edge['target']].append(edge['source'])
    for rank in sorted(levels):
        def order_key(node):
            parent_x = [positions[p][0] for p in parents[node['id']] if p in positions]
            center = sum(parent_x) / len(parent_x) if parent_x else 0
            return center, node['owner_scope'] or '', node['name'], node['type']
        ordered = sorted(levels[rank], key=order_key)
        for col, node in enumerate(ordered):
            positions[node['id']] = (24 + (content_width - 48 - len(ordered) * col_width) // 2 + col * col_width,
                                     header + rank * stride)
    esc = html.escape
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (width, height, width, height),
             '<rect width="100%" height="100%" fill="#f7f9fc"/>',
             '<g font-family="DejaVu Sans,Arial,sans-serif">',
             '<text x="24" y="32" font-size="20" font-weight="bold" fill="#18283b">' + esc(title) + '</text>',
             '<text x="24" y="56" font-size="12" fill="#52667d">ELAB evidence | yellow: query signal | blue: module port | orange: stop | dashed: logic dependency</text>']
    for index, label in enumerate(region_lines):
        parts.append('<text x="24" y="%d" font-size="12" fill="#20364f">%s</text>' % (82 + index * 18, esc(label)))
    for ei, edge in enumerate(edges):
        sx, sy = positions[edge['source']]
        tx, ty = positions[edge['target']]
        ax, ay = sx + node_width // 2, sy + node_height
        bx, by = tx + node_width // 2, ty - 1
        if ranks[edge['target']] == ranks[edge['source']] + 1:
            middle = (ay + by) // 2
            path = 'M%d,%d C%d,%d %d,%d %d,%d' % (ax, ay, ax, middle, bx, middle, bx, by - 7)
        else:
            lane = content_width + 12 + (ei % 6) * 12
            path = 'M%d,%d L%d,%d L%d,%d L%d,%d L%d,%d L%d,%d' % (ax, ay, ax, ay + 14, lane, ay + 14, lane, by - 17, bx, by - 17, bx, by - 7)
        dashed = ' stroke-dasharray="6 4"' if 'LOGIC_DEP' in edge['kinds'] else ''
        parts.append('<path d="%s" fill="none" stroke="#52667d" stroke-width="1.8"%s><title>%s</title></path>' % (path, dashed, esc(', '.join(edge['kinds']))))
        parts.append('<polygon points="%d,%d %d,%d %d,%d" fill="#52667d"/>' % (bx, by, bx - 4, by - 8, bx + 4, by - 8))
    for node in nodes.values():
        x, y = positions[node['id']]
        fill = '#fff1b9' if node['is_selected'] else '#dceafd' if node['type'].endswith('Port') else '#ffffff'
        if node['is_stop']:
            fill = '#ffe2c3'
        parts.append('<g id="%s"><rect x="%d" y="%d" width="%d" height="%d" rx="8" fill="%s" stroke="#849bb8"/><title>%s</title>' % (node['id'], x, y, node_width, node_height, fill, esc(json.dumps(node, ensure_ascii=False))))
        lines = textwrap.wrap(node['name'], 56, break_long_words=True)[:2]
        for index, line in enumerate(lines):
            parts.append('<text x="%d" y="%d" font-family="DejaVu Sans Mono,monospace" font-size="11" fill="#172c44">%s</text>' % (x + 12, y + 20 + index * 15, esc(line)))
        direction = node['direction'].replace('npiNl', '').lower()
        role = ('SOURCE ' if node['is_source'] else '') + node['base_type'].replace('npiNl', '')
        bits = ','.join(map(str, sorted(node['bits'])))
        detail = '%s | %s | module=%s | bits=%s' % (role, direction or 'net', node['module'] or node['cell'], bits)
        parts.append('<text x="%d" y="%d" font-size="10" fill="#45617d">%s</text>' % (x + 12, y + 58, esc(detail[:78])))
        parts.append('<text x="%d" y="%d" font-size="11" fill="#45617d">Actual scope: %s</text>' % (x + 12, y + 75, esc(node['actual_scope'][:64])))
        parts.append('<text x="%d" y="%d" font-size="11" font-weight="bold" fill="#20364f">Owner: %s</text>' % (x + 12, y + 92, esc((node['owner_scope'] or '(outside selected scopes)')[:64])))
        if node['is_stop']:
            parts.append('<text x="%d" y="%d" font-size="10" fill="#8b3d13">%s</text>' % (x + 12, y + 108, esc(', '.join(node.get('stop_reasons', [])))))
        parts.append('</g>')
    parts.append('</g></svg>')
    return '\n'.join(parts)


def dot_graph(view):
    out = ['digraph rtlwire {', 'rankdir=LR;', 'node [shape=box,fontname="Arial"];']
    owners = sorted({n['owner_scope'] or '(outside)' for n in view['nodes'].values()})
    for idx, owner in enumerate(owners):
        out.extend(['subgraph cluster_%d {' % idx, 'label=' + json.dumps('Owner: ' + owner) + ';'])
        for node in view['nodes'].values():
            if (node['owner_scope'] or '(outside)') == owner:
                label = node['name'] + '\n' + (node['module'] or node['cell'])
                out.append(node['id'] + ' [label=' + json.dumps(label) + '];')
        out.append('}')
    for edge in view['edges']:
        style = 'dashed' if 'LOGIC_DEP' in edge['kinds'] else 'solid'
        out.append('%s -> %s [style=%s];' % (edge['source'], edge['target'], style))
    return '\n'.join(out + ['}'])


def write_reports(out, graph, result, paths, view):
    dump_json(out / 'graph.json', graph)
    dump_json(out / 'report.json', result)
    dump_json(out / 'paths.json', paths)
    dump_json(out / 'display_graph.json', view)
    dump_json(out / 'inventory.json', dict(instances=graph['instances'], signals=graph['signals'], regions=graph['regions']))
    columns = ['source', 'owner_scope', 'instance', 'module', 'port', 'direction', 'source_bits', 'target_bits', 'status']
    with (out / 'checks.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(result['checks'])
    lines = []
    for index, path in enumerate(paths['paths']):
        lines.append('Path %d | source=%s | bit=%s | stop=%s' % (index + 1, path['source'], path['source_bit'], path['stop_reason']))
        if path.get('target_port'):
            lines.append('  target=%s | port_direction=%s | search=%s' % (path['target_port'], path['port_direction'], path['search_direction']))
        for nid in path['nodes']:
            node = graph['nodes'][nid]
            lines.append('  [%s] %s (%s)' % (node['owner_scope'] or 'outside', node['name'], node['type']))
        lines.append('')
    (out / 'paths.txt').write_text('\n'.join(lines), encoding='utf-8')
    architecture = build_architecture(graph, result)
    dump_json(out / 'architecture.json', architecture)
    svg = svg_architecture(architecture)
    (out / 'architecture.svg').write_text(svg, encoding='utf-8')
    (out / 'topology.svg').write_text(svg, encoding='utf-8')
    # DOT is an optional low-level connectivity projection, not the architecture view.
    (out / 'connectivity_evidence.dot').write_text(dot_graph(view), encoding='utf-8')
    esc = html.escape
    rows = ''.join('<tr>' + ''.join('<td>%s</td>' % esc(str(item.get(k, ''))) for k in columns) + '</tr>' for item in result['checks'])
    notes = json.dumps(dict(complete=result['complete'], paths_truncated=paths['truncated'],
                           stops=result['stops'], unresolved=result['unresolved'], errors=result['errors']), ensure_ascii=False, indent=2)
    page = '<!doctype html><meta charset="utf-8"><title>RTL wiring report</title><style>body{font:14px Arial;margin:24px;color:#172c44}table{border-collapse:collapse}td,th{border:1px solid #ccd5e0;padding:7px;text-align:left}th{background:#eaf0f8}.graph{overflow:auto;border:1px solid #ccd5e0}pre{background:#f3f6fa;padding:16px;overflow:auto}</style>'
    page += '<h1>RTLWire · 层次架构 / %s</h1><p>嵌套框表示 elab 中的真实父子层次，同一框内的模块为同级实例。紫色标记表示独立检查范围；检查归属按最深已选祖先确定，不改变实例的真实位置。端口、连线与依赖来自 NPI，设计输入仅为已编译 elab。</p>' % esc(result['mode'])
    page += '<p><button onclick="document.querySelector(\'.graph svg\').style.width=\'100%\'">Fit width</button> <button onclick="document.querySelector(\'.graph svg\').style.width=\'\'">Actual pixels</button> <a href="topology.svg">Open SVG</a> | <a href="paths.txt">Ordered paths</a> | <a href="checks.csv">CSV</a></p>'
    page += '<div class="graph">' + svg + '</div><h2>Connections</h2><table><tr>' + ''.join('<th>' + k + '</th>' for k in columns) + '</tr>' + rows + '</table>'
    page += '<h2>Observed signals</h2><pre>' + esc(json.dumps(result['observed'], ensure_ascii=False, indent=2)) + '</pre>'
    page += '<h2>Completeness and stops</h2><pre>' + esc(notes) + '</pre><p>Raw evidence: graph.json. Ordered paths: paths.txt. Access audit: audit.json.</p>'
    (out / 'report.html').write_text(page, encoding='utf-8')
