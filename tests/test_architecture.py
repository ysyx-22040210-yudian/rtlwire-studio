import copy
import json
from pathlib import Path
import unittest

from rtlwire.architecture import build_architecture, orthogonal_route, svg_architecture, witness_highlights


ROOT=Path(__file__).resolve().parent.parent


class ArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenes={}
        for case in ('reach_nested','trace_chain'):
            p=ROOT/'validation'/case
            if not (p/'graph.json').exists():
                raise unittest.SkipTest('Recorded NPI fixtures are in the validation package')
            cls.scenes[case]=build_architecture(json.loads((p/'graph.json').read_text(encoding='utf-8')),json.loads((p/'report.json').read_text(encoding='utf-8')))

    def test_exclusive_owner_does_not_reparent_the_instance(self):
        s=self.scenes['reach_nested'];b=s['boxes']['top.u_tile.AAAA_BBB_C0']
        self.assertEqual(b['owner_scope'],'top.u_tile.AAAA_BBB_C0')
        self.assertEqual(b['parent'],'top.u_tile')
        self.assertEqual(s['boxes']['top.u_tile.AAAA_BBB_C1']['parent'],'top.u_tile')
        self.assertEqual(s['boxes']['top.u_tile.AAAA_BBB_C1']['owner_scope'],'top')

    def test_children_are_inside_parents_and_peers_do_not_overlap(self):
        for s in self.scenes.values():
            for b in s['boxes'].values():
                if b['parent']:
                    p=s['boxes'][b['parent']]
                    self.assertGreater(b['x'],p['x']);self.assertGreater(b['y'],p['y'])
                    self.assertLess(b['x']+b['w'],p['x']+p['w'])
                    self.assertLess(b['y']+b['h'],p['y']+p['h'])
                children=[s['boxes'][n] for n in b['children']]
                for i,a in enumerate(children):
                    for c in children[i+1:]:
                        overlap=(max(a['x'],c['x'])<min(a['x']+a['w'],c['x']+c['w']) and
                                 max(a['y'],c['y'])<min(a['y']+a['h'],c['y']+c['h']))
                        self.assertFalse(overlap,(a['name'],c['name']))

    def test_ports_use_module_boundaries_and_every_wire_has_evidence(self):
        for s in self.scenes.values():
            for p in s['pins'].values():
                b=s['boxes'][p['scope']]
                if p['kind']=='port':self.assertIn(p['x'],(b['x'],b['x']+b['w']))
            for e in s['connections']:
                self.assertTrue(e['evidence']);self.assertTrue(any(e['evidence']))
                for a,b in zip(e['points'],e['points'][1:]):
                    self.assertTrue(a[0]==b[0] or a[1]==b[1])
            self.assertFalse(s['warnings'])

    def test_named_nets_are_scope_annotated_connections(self):
        s=self.scenes['trace_chain']
        names={n['name']:n['scope'] for e in s['connections'] for n in e['signals']}
        self.assertEqual(names,{'top.c0':'top','top.b0':'top','top.a0':'top','top.wrong0':'top'})
        self.assertEqual(len(s['boxes']),6)
        self.assertTrue(any('LOGIC_DEP' in e['kinds'] for e in s['connections']))

    def test_router_avoids_unrelated_module_body(self):
        obstacle=(40,-15,80,15)
        route=orthogonal_route((0,0),(120,0),[obstacle])
        self.assertIsNotNone(route)
        for a,b in zip(route,route[1:]):
            if a[1]==b[1] and -15<a[1]<15:
                self.assertFalse(max(a[0],b[0])>40 and min(a[0],b[0])<80)

    def test_svg_preserves_hierarchy_metadata_and_escapes_labels(self):
        s=copy.deepcopy(self.scenes['reach_nested'])
        s['boxes']['top']['module']='a<&b'
        svg=svg_architecture(s)
        self.assertIn('a&lt;&amp;b',svg)
        self.assertIn('module:top.u_tile.AAAA_BBB_C0',svg)
        self.assertNotIn('stroke=""',svg)

    def test_output_witness_highlights_wire_with_coalesced_port_binding(self):
        graph={'nodes':{
            'port':dict(base_name='top.u.q',actual_scope='top.u',left=0,right=0),
            'instport':dict(base_name='top.u.q',actual_scope='top.u',left=0,right=0),
            'net':dict(base_name='top.out',actual_scope='top',left=0,right=0),
            'other':dict(base_name='top.other',actual_scope='top',left=0,right=0)},
            'edges':[dict(source='port',target='instport'),dict(source='instport',target='net'),
                     dict(source='net',target='other')]}
        scene={'connections':[dict(id='output',evidence=[[0,1]]),dict(id='other',evidence=[[2]])]}
        self.assertEqual(witness_highlights(scene,graph,{1}),{'output'})
        self.assertEqual(witness_highlights(scene,graph,{0}),set())
        self.assertEqual(witness_highlights(scene,graph,{1,2}),{'output','other'})


if __name__=='__main__':unittest.main()
