import copy
import unittest

from rtlwire.core import analyze, assign_owners, enumerate_paths, reach_paths, display_graph
from rtlwire.cli import make_config


def graph_fixture():
    instances = {}
    for name, parent, module in [
            ('top', '', 'top'), ('top.wrap', 'top', 'wrap'),
            ('top.wrap.u0', 'top.wrap', 'target'),
            ('top.wrap.u01', 'top.wrap', 'target'),
            ('top.wrap.u0.deep', 'top.wrap.u0', 'target')]:
        instances[name] = dict(name=name, parent=parent, module=module, cell='npiNlModuleCell')
    return dict(instances=instances, nodes={}, edges=[], signals=[], selections=[],
                stops=[], unresolved=[], errors=[], extraction_done=True)


def node(nid, name, scope, typ='npiNlPort', bit=0, base=None):
    return dict(id=nid, name=name, local_name=name.rsplit('.', 1)[-1], instance=scope,
                actual_scope=scope, type=typ, base_type=typ, base_name=base or name,
                module='target', cell='npiNlModuleCell', direction='npiNlInput',
                left=bit, right=bit, size=1, literal=0)


def selection(nid, bit='', query='top.src'):
    return dict(role='source', query=query, id=nid, source_bit=bit)


class OwnershipTests(unittest.TestCase):
    def test_deep_instance_and_nested_exclusion(self):
        g = graph_fixture()
        regions = assign_owners(g, ['top.wrap.u0', 'top'])
        self.assertEqual(g['instances']['top.wrap.u0.deep']['owner_scope'], 'top.wrap.u0')
        self.assertEqual(g['instances']['top.wrap.u01']['owner_scope'], 'top')
        self.assertEqual(regions[0]['excluded_subtrees'], ['top.wrap.u0'])
        before = copy.deepcopy(g['instances'])
        assign_owners(g, ['top', 'top.wrap.u0', 'top'])
        self.assertEqual(before, g['instances'])

    def test_three_selected_levels(self):
        g = graph_fixture()
        regions = assign_owners(g, ['top', 'top.wrap', 'top.wrap.u0'])
        self.assertEqual(regions[0]['excluded_subtrees'], ['top.wrap'])
        self.assertEqual(regions[1]['excluded_subtrees'], ['top.wrap.u0'])
        self.assertEqual(g['instances']['top.wrap.u01']['owner_scope'], 'top.wrap')


class ConnectivityTests(unittest.TestCase):
    def query(self):
        return dict(mode='trace', check_scopes=['top'], target_modules=['target'])

    def test_two_parent_signals_reach_same_child_input_and_output(self):
        g=graph_fixture()
        g['nodes']={n['id']:n for n in [node('s1','top.data_in','top'),node('s2','top.data_out','top'),
                                        node('i','top.wrap.u0.d','top.wrap.u0'),node('o','top.wrap.u0.q','top.wrap.u0')]}
        g['nodes']['s2']['direction']=g['nodes']['o']['direction']='npiNlOutput'
        g['edges']=[dict(source='s1',target='i',kind='WIRE'),dict(source='o',target='s2',kind='WIRE')]
        g['selections']=[selection('s1',query='top.data_in'),selection('s2',query='top.data_out')]
        q=self.query();q['mode']='reach'
        result=analyze(g,q)
        hits=[c for c in result['checks'] if c['instance']=='top.wrap.u0' and c['status']=='CONNECTED']
        self.assertEqual({(c['source'],c['port'],c['direction']) for c in hits},
                         {('top.data_in','top.wrap.u0.d','npiNlInput'),('top.data_out','top.wrap.u0.q','npiNlOutput')})
        paths=reach_paths(g,result)
        self.assertEqual(len(paths['paths']),2)
        output=next(p for p in paths['paths'] if p['source']=='top.data_out')
        self.assertEqual(output['nodes'],['o','s2'])
        self.assertEqual(output['search_direction'],'upstream')
        self.assertTrue(reach_paths(g,result,max_paths=1)['truncated'])
        self.assertTrue(reach_paths(g,result,max_depth=1)['truncated'])
        self.assertFalse(any(e['source']=='i' and e['target']=='o' for e in g['edges']))

    def test_no_automatic_module_input_output_connection(self):
        g = graph_fixture()
        g['nodes'] = {'n1': node('n1', 'top.wrap.u0.in', 'top.wrap.u0'),
                      'n2': node('n2', 'top.wrap.u0.out', 'top.wrap.u0')}
        g['selections'] = [selection('n1')]
        r = analyze(g, self.query())
        self.assertFalse(any(c['port'].endswith('.out') for c in r['checks']))
        self.assertEqual(display_graph(g)['edges'], [])

    def test_bit_coverage_does_not_promote_partial_to_connected(self):
        g = graph_fixture()
        g['nodes'] = {n['id']: n for n in [node('n1', 'top.src[0]', 'top', bit=0, base='top.src'),
                                          node('n2', 'top.src[1]', 'top', bit=1, base='top.src'),
                                          node('n3', 'top.wrap.u0.in[3]', 'top.wrap.u0', bit=3, base='top.wrap.u0.in')]}
        g['selections'] = [selection('n1', '0'), selection('n2', '1')]
        g['edges'] = [dict(source='n1', target='n3', kind='WIRE')]
        r = analyze(g, self.query())
        hit = next(c for c in r['checks'] if c['port'])
        self.assertEqual(hit['status'], 'PARTIAL_BITS')
        self.assertEqual(hit['source_bits'], ['0'])
        self.assertEqual(hit['target_bits'], ['3'])

    def test_unresolved_is_unknown_not_disconnected(self):
        g = graph_fixture()
        g['unresolved'] = [dict(role='source', query='top.missing')]
        r = analyze(g, self.query())
        self.assertFalse(r['complete'])
        self.assertEqual({c['status'] for c in r['checks']}, {'UNKNOWN'})

    def test_parent_focus_excludes_child_but_retains_graph(self):
        g = graph_fixture()
        g['nodes'] = {'n1': node('n1', 'top.src', 'top'),
                      'n2': node('n2', 'top.wrap.u0.in', 'top.wrap.u0')}
        g['edges'] = [dict(source='n1', target='n2', kind='WIRE')]
        g['selections'] = [selection('n1')]
        q = self.query()
        q.update(check_scopes=['top', 'top.wrap.u0'], focus_scopes=['top'])
        r = analyze(g, q)
        self.assertEqual([c['name'] for c in r['candidates']], ['top.wrap.u01'])
        self.assertEqual(len(g['edges']), 1)

    def test_branch_reconvergence_and_cycle_are_not_lost(self):
        g = graph_fixture()
        g['nodes'] = {n: node(n, 'top.' + n, 'top') for n in ('n1', 'n2', 'n3', 'n4')}
        g['selections'] = [selection('n1')]
        g['edges'] = [dict(source=a, target=b, kind='WIRE') for a, b in
                      [('n1', 'n2'), ('n1', 'n3'), ('n2', 'n4'), ('n3', 'n4'), ('n4', 'n1')]]
        paths = enumerate_paths(g)
        self.assertEqual(len(paths['paths']), 2)
        self.assertEqual({p['stop_reason'] for p in paths['paths']}, {'CYCLE'})
        self.assertFalse(paths['truncated'])
        self.assertTrue(enumerate_paths(g, max_paths=1)['truncated'])

    def test_unknown_stop_prevents_negative_assertion(self):
        g = graph_fixture()
        g['nodes'] = {'n1': node('n1', 'top.src', 'top')}
        g['selections'] = [selection('n1')]
        g['stops'] = [dict(id='n1', reason='UNSUPPORTED_CELL')]
        r = analyze(g, self.query())
        self.assertFalse(r['complete'])
        self.assertEqual({c['status'] for c in r['checks']}, {'UNKNOWN'})


class ConfigTests(unittest.TestCase):
    def test_signal_text_cannot_inject_tcl(self):
        dangerous = 'top.sig]; exec BAD; #'
        generated = make_config(dict(mode='trace', traversal_boundary='top', sources=[dangerous]), {})
        self.assertNotIn('exec BAD', generated)
        self.assertIn(dangerous.encode().hex(), generated)


if __name__ == '__main__':
    unittest.main()
