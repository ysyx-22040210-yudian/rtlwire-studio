"""Vendor-independent analysis of NPI records. Python 3.6+, stdlib only."""
from collections import defaultdict, deque


NODE_FIELDS = ('id', 'type', 'name', 'local_name', 'actual_scope', 'instance',
               'module', 'cell', 'direction', 'left', 'right', 'size',
               'base_name', 'base_type', 'literal')


def parse_records(path):
    graph = dict(instances={}, nodes={}, edges=[], signals=[], selections=[],
                 stops=[], unresolved=[], errors=[], metadata={}, extraction_done=False)
    with open(str(path), encoding='utf-8') as stream:
        for line in stream:
            items = line.rstrip('\n').split('\t')
            tag, values = items[0], [bytes.fromhex(v).decode('utf-8') for v in items[1:]]
            if tag == 'I':
                name, parent, module, cell = values
                graph['instances'][name] = dict(name=name, parent=parent, module=module, cell=cell)
            elif tag == 'N':
                node = dict(zip(NODE_FIELDS, values))
                for key in ('left', 'right', 'size', 'literal'):
                    node[key] = int(node[key])
                graph['nodes'][node['id']] = node
            elif tag == 'E':
                graph['edges'].append(dict(zip(('source', 'target', 'kind', 'evidence'), values)))
            elif tag == 'S':
                graph['signals'].append(dict(zip(('name', 'scope', 'local_name', 'type',
                                                 'direction', 'size', 'left', 'right'), values)))
            elif tag == 'Q':
                graph['selections'].append(dict(zip(('role', 'query', 'id', 'source_bit'), values)))
            elif tag == 'T':
                graph['stops'].append(dict(zip(('reason', 'id', 'direction', 'detail'), values)))
            elif tag == 'U':
                graph['unresolved'].append(dict(zip(('role', 'query'), values)))
            elif tag == 'X':
                graph['errors'].append(dict(message=values[0], detail=values[1]))
            elif tag == 'M':
                graph['metadata'][values[0]] = values[1]
            elif tag == 'Z':
                graph['extraction_done'] = True
    return graph


def ancestors(instances, name):
    seen = set()
    while name:
        if name in seen:
            raise ValueError('Hierarchy cycle at ' + name)
        seen.add(name)
        yield name
        name = instances.get(name, {}).get('parent', '')


def assign_owners(graph, selected_scopes):
    instances = graph['instances']
    selected = set(selected_scopes)
    for scope in selected:
        if scope not in instances or instances[scope]['cell'] != 'npiNlModuleCell':
            raise ValueError('CHECK_SCOPE_NOT_FOUND: ' + scope)
    owner_cache = {}

    def owner(name):
        if name not in owner_cache:
            owner_cache[name] = next((x for x in ancestors(instances, name) if x in selected), None)
        return owner_cache[name]

    for inst in instances.values():
        inst['owner_scope'] = owner(inst['name'])
    for node in graph['nodes'].values():
        node['owner_scope'] = owner(node['actual_scope'])
    regions = []
    for scope in sorted(selected):
        parent = next((p for p in ancestors(instances, instances[scope]['parent']) if p in selected), None)
        excluded = []
        for child in selected - {scope}:
            selected_parent = next((p for p in ancestors(instances, instances[child]['parent']) if p in selected), None)
            if selected_parent == scope:
                excluded.append(child)
        regions.append(dict(scope=scope, selected_parent=parent, excluded_subtrees=sorted(excluded)))
    graph['regions'] = regions
    return regions


def adjacency(graph, bidirectional=False):
    adj = defaultdict(list)
    for index, edge in enumerate(graph['edges']):
        adj[edge['source']].append((edge['target'], index))
        if bidirectional:
            adj[edge['target']].append((edge['source'], index))
    return adj


def search(adj, seeds):
    predecessors = {x: None for x in seeds}
    queue = deque(seeds)
    while queue:
        current = queue.popleft()
        for nxt, ei in adj.get(current, []):
            if nxt not in predecessors:
                predecessors[nxt] = (current, ei)
                queue.append(nxt)
    return predecessors


def witness(predecessors, target):
    nodes, edges = [target], []
    while predecessors[target] is not None:
        target, ei = predecessors[target]
        nodes.append(target)
        edges.append(ei)
    return dict(nodes=list(reversed(nodes)), edge_indices=list(reversed(edges)))


def analyze(graph, query):
    if not graph['instances'] and graph['errors']:
        raise ValueError('ELAB_LOAD_OR_EXTRACTION_FAILED: ' + graph['errors'][0]['message'])
    assign_owners(graph, query['check_scopes'])
    unknown_stops = [s for s in graph['stops'] if s['reason'].startswith(('UNSUPPORTED', 'UNRESOLVED'))
                     or s['reason'].endswith('_LIMIT')]
    complete = (graph['extraction_done'] and not graph['errors'] and not unknown_stops
                and not graph['unresolved'])
    modules = set(query.get('target_modules', []))
    focus = set(query.get('focus_scopes', query['check_scopes']))
    if not focus.issubset(set(query['check_scopes'])):
        raise ValueError('focus_scopes must be members of check_scopes')
    candidates = {k: v for k, v in graph['instances'].items()
                  if v['cell'] == 'npiNlModuleCell' and v['module'] in modules and v['owner_scope'] in focus}
    target_nodes = defaultdict(list)
    for node in graph['nodes'].values():
        if node['instance'] in candidates and node['type'].endswith('Port'):
            target_nodes[node['instance']].append(node)
    grouped_seeds = defaultdict(list)
    for selection in graph['selections']:
        if selection['role'] == 'source':
            grouped_seeds[selection['query']].append(selection)
    if query['mode'] != 'inventory' and not grouped_seeds and not graph['unresolved']:
        raise ValueError('NO_RESOLVED_SOURCE')
    adj = adjacency(graph, query['mode'] == 'reach')
    checks = []
    for missing in graph['unresolved']:
        if missing['role'] == 'source':
            for inst, info in sorted(candidates.items()):
                checks.append(dict(source=missing['query'], instance=inst, module=info['module'],
                                   owner_scope=info['owner_scope'], port='', direction='', source_bits=[],
                                   target_bits=[], witnesses=[], status='UNKNOWN'))
    for source, selections in sorted(grouped_seeds.items()):
        searches = [(s, search(adj, [s['id']])) for s in selections]
        for inst, info in sorted(candidates.items()):
            hits = defaultdict(lambda: dict(source_bits=set(), target_bits=set(), witnesses=[]))
            for node in target_nodes[inst]:
                port_key = (node['base_name'], node['direction'])
                for sel, found in searches:
                    if node['id'] in found:
                        item = hits[port_key]
                        item['source_bits'].add(sel['source_bit'] or 'scalar')
                        item['target_bits'].add(str(node['left']) if node['left'] >= 0 else 'scalar')
                        if not item['witnesses']:
                            item['witnesses'].append(witness(found, node['id']))
            if not hits:
                checks.append(dict(source=source, instance=inst, module=info['module'], owner_scope=info['owner_scope'],
                                   port='', direction='', source_bits=[], target_bits=[], witnesses=[],
                                   status='NOT_CONNECTED' if complete else 'UNKNOWN'))
            for (port, direction), item in sorted(hits.items()):
                full = len(item['source_bits']) == len(selections)
                checks.append(dict(source=source, instance=inst, module=info['module'], owner_scope=info['owner_scope'],
                                   port=port, direction=direction, source_bits=sorted(item['source_bits']),
                                   target_bits=sorted(item['target_bits']), witnesses=item['witnesses'],
                                   status='CONNECTED' if full else 'PARTIAL_BITS'))
    all_reachable = search(adj, [s['id'] for group in grouped_seeds.values() for s in group])
    observed = []
    for s in graph['selections']:
        if s['role'] == 'observe':
            observed.append(dict(s, reached=s['id'] in all_reachable))
    for item in graph['unresolved']:
        if item['role'] == 'observe':
            observed.append(dict(item, reached=False, status='UNRESOLVED'))
    return dict(mode=query['mode'], complete=complete, candidate_count=len(candidates),
                completeness_scope='Within traversal_boundary and traversal policy; stops at sequential cells. Not functional equivalence.',
                candidates=list(candidates.values()), checks=checks, observed=observed,
                regions=graph['regions'], stops=graph['stops'], errors=graph['errors'],
                unresolved=graph['unresolved'])


def reach_paths(graph, result, max_paths=500, max_depth=512):
    """Port witnesses for reach, including upstream searches from parent outputs.

    Reverse a wholly upstream witness so displayed arrows keep the real signal
    flow. A mixed-direction reach witness stays a connectivity proof, not a
    claim of unidirectional propagation through a fanout or logic operation.
    """
    paths, truncated = [], False
    for check in result['checks']:
        for witness_ in check.get('witnesses', []):
            if len(paths) >= max_paths:
                truncated = True
                continue
            nodes, edges = list(witness_['nodes']), list(witness_['edge_indices'])
            forward = [graph['edges'][ei]['source'] == nodes[i] for i, ei in enumerate(edges)]
            direction = 'downstream' if all(forward) else 'upstream' if not any(forward) else 'mixed'
            if direction == 'upstream':
                nodes.reverse(); edges.reverse()
            limited = len(nodes) > max_depth
            if limited:
                nodes, edges = nodes[:max_depth], edges[:max(0, max_depth-1)]
                truncated = True
            paths.append(dict(source=check['source'], source_bit=','.join(check['source_bits']),
                              nodes=nodes, edge_indices=edges, target_port=check['port'],
                              port_direction=check['direction'], search_direction=direction,
                              stop_reason='PATH_DEPTH_LIMIT' if limited else 'PORT_CONNECTED'))
    return dict(paths=paths, truncated=truncated,
                semantics='One retained witness per reached port; upstream witnesses are ordered in actual signal flow; mixed witnesses are connectivity evidence.')


def enumerate_paths(graph, max_paths=500, max_depth=512):
    adj = adjacency(graph)
    nodes = graph['nodes']
    paths = []
    truncated = False
    stops = defaultdict(list)
    for item in graph['stops']:
        stops[item['id']].append(item['reason'])
    for selection in graph['selections']:
        if selection['role'] != 'source':
            continue
        stack = [(selection['id'], [selection['id']], [])]
        while stack:
            if len(paths) >= max_paths:
                truncated = True
                break
            current, path, edge_ids = stack.pop()
            outgoing = adj.get(current, [])
            if not outgoing or len(path) >= max_depth:
                reason = 'PATH_DEPTH_LIMIT' if len(path) >= max_depth else ','.join(stops[current]) or 'LEAF'
                if reason == 'PATH_DEPTH_LIMIT':
                    truncated = True
                paths.append(dict(source=selection['query'], source_bit=selection['source_bit'],
                                  nodes=path, edge_indices=edge_ids, stop_reason=reason))
                continue
            for nxt, ei in reversed(outgoing):
                if nxt in path:
                    if len(paths) < max_paths:
                        paths.append(dict(source=selection['query'], source_bit=selection['source_bit'],
                                          nodes=path, edge_indices=edge_ids, stop_reason='CYCLE', cycle_to=nxt))
                    else:
                        truncated = True
                else:
                    stack.append((nxt, path + [nxt], edge_ids + [ei]))
    return dict(paths=paths, truncated=truncated,
                semantics='Finite paths in the extracted directed graph; cycles are explicitly terminated.')


def display_graph(graph):
    """Collapse only unselected intermediate objects; keep raw witnesses for each display edge."""
    selected_ids = {s['id'] for s in graph['selections']}
    stopped = {s['id'] for s in graph['stops']}
    stop_reasons = defaultdict(set)
    for stop in graph['stops']:
        stop_reasons[stop['id']].add(stop['reason'])
    keep = {nid for nid, n in graph['nodes'].items()
            if nid in selected_ids or nid in stopped or n['type'] in ('npiNlPort', 'npiNlPseudoPort')}
    view_nodes, raw_to_view, key_to_id = {}, {}, {}
    source_ids = {s['id'] for s in graph['selections'] if s['role'] == 'source'}
    for nid in sorted(keep, key=lambda x: int(x[1:])):
        node = graph['nodes'][nid]
        key = (node['base_type'], node['base_name'], node['instance'])
        if key not in key_to_id:
            vid = 'v' + str(len(key_to_id) + 1)
            key_to_id[key] = vid
            view_nodes[vid] = dict(node, id=vid, name=node['base_name'], raw_ids=[], bits=[], is_source=False,
                                   is_selected=False, is_stop=False, stop_reasons=[])
        vid = key_to_id[key]
        raw_to_view[nid] = vid
        item = view_nodes[vid]
        item['raw_ids'].append(nid)
        if node['left'] >= 0 and node['left'] not in item['bits']:
            item['bits'].append(node['left'])
        item['is_source'] |= nid in source_ids
        item['is_selected'] |= nid in selected_ids
        item['is_stop'] |= nid in stopped
        item['stop_reasons'] = sorted(set(item['stop_reasons']) | stop_reasons[nid])
    adj = adjacency(graph)
    combined = {}
    for start in keep:
        queue = deque([(start, [], [start])])
        visited = {(start, ())}
        while queue:
            cur, edge_ids, node_ids = queue.popleft()
            for nxt, ei in adj.get(cur, []):
                new_edges = edge_ids + [ei]
                kinds = tuple(sorted({graph['edges'][j]['kind'] for j in new_edges}))
                if nxt in keep:
                    a, b = raw_to_view[start], raw_to_view[nxt]
                    if a != b:
                        key = (a, b, kinds)
                        if key not in combined:
                            combined[key] = dict(source=a, target=b, kinds=list(kinds), witnesses=[])
                        combined[key]['witnesses'].append(dict(nodes=node_ids + [nxt], edge_indices=new_edges))
                elif (nxt, kinds) not in visited:
                    visited.add((nxt, kinds))
                    queue.append((nxt, new_edges, node_ids + [nxt]))
    return dict(nodes=view_nodes, edges=list(combined.values()), regions=graph.get('regions', []))
