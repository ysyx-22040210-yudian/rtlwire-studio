import copy
import json
from pathlib import Path
import tempfile
import unittest
from rtlwire.wave_core import analyze, normalize_config, load_native, scale_ns, ns_text
from rtlwire.wave_plot import scene, svg


def fixture():
    scope='tb.u_a'
    def s(name,direction,width,events):
        return dict(name=scope+'.'+name,scope=scope,local_name=name,direction=direction,
                    left=width-1,right=0,events=events,deltas=[])
    signals=[s('iso_en',1,1,[[0,'0'],[20,'1'],[90,'0']]),
             s('power_down',1,1,[[0,'1'],[35,'0'],[70,'1']]),
             s('dout',2,4,[[0,'0000'],[35,'xxxx'],[70,'0000']])]
    data=dict(file=dict(scale='1ns',begin=0,end=100),scopes={scope:{}},
              signals={s['name']:s for s in signals},dump_off=[],complete=True)
    config=dict(fsdb_path='test.fsdb',domains=[dict(scope=scope,iso_en='iso_en',power_down='power_down')])
    return config,data


class WaveTests(unittest.TestCase):
    def check(self,mutate=None):
        q,d=fixture()
        if mutate:mutate(q,d,d['signals']['tb.u_a.dout'])
        r=analyze(q,d)
        c=r['domains'][0]['cycles'][0]
        return r,c,c['checks'][0]

    def test_good_full_cycle_padding(self):
        r,c,row=self.check()
        self.assertEqual(r['summary']['status'],'PASS')
        self.assertEqual(c['window'],[15,95])
        self.assertEqual(row['idle'],'0000')
        self.assertEqual(row['clamp'],'0000')

    def test_idle_before_edge_not_final_at_edge(self):
        r,c,row=self.check(lambda q,d,s:s.update(events=[[0,'1111'],[20,'0000'],[35,'xxxx'],[70,'0000']]))
        self.assertEqual(row['checks']['idle_equal']['status'],'FAIL')
        self.assertEqual(row['checks']['clamp_expected']['status'],'PASS')

    def test_clamp_nonzero_but_stable(self):
        r,c,row=self.check(lambda q,d,s:s.update(events=[[0,'1111'],[35,'xxxx'],[70,'0000']]))
        self.assertEqual(row['checks']['idle_equal']['status'],'PASS')
        self.assertEqual(row['checks']['clamp_stable']['status'],'PASS')
        self.assertEqual(row['checks']['clamp_expected']['status'],'FAIL')

    def test_hold_transition_and_return(self):
        r,c,row=self.check(lambda q,d,s:s.update(events=[[0,'0000'],[25,'0001'],[26,'0000'],[35,'xxxx'],[70,'0000']]))
        self.assertEqual(row['checks']['clamp_stable']['time'],25)
        self.assertEqual(row['status'],'FAIL')

    def test_boundary_power_off_has_priority(self):
        r,c,row=self.check()
        self.assertEqual(row['checks']['clamp_stable']['status'],'PASS')
        self.assertEqual(row['checks']['off_x']['status'],'PASS')

    def test_partial_x_and_z_are_not_all_x(self):
        for value in ('xxx0','zzzz','xxzx'):
            r,c,row=self.check(lambda q,d,s:s['events'].__setitem__(1,[35,value]))
            self.assertEqual(row['checks']['off_x']['status'],'FAIL')

    def test_recovery_remains_clamped(self):
        r,c,row=self.check(lambda q,d,s:s['events'].__setitem__(2,[70,'0001']))
        self.assertEqual(row['checks']['recovery_expected']['status'],'FAIL')

    def test_empty_values_are_unknown_not_x(self):
        r,c,row=self.check(lambda q,d,s:s.update(events=[]))
        self.assertEqual(row['status'],'UNKNOWN')
        self.assertEqual(row['checks']['off_x']['status'],'UNKNOWN')

    def test_initial_idle_missing(self):
        r,c,row=self.check(lambda q,d,s:s.update(events=[[20,'0000'],[35,'xxxx'],[70,'0000']]))
        self.assertEqual(row['checks']['idle_equal']['status'],'UNKNOWN')

    def test_incomplete_cycle(self):
        def change(q,d,s):
            d['signals']['tb.u_a.iso_en']['events'].pop()
            d['file']['end']=80
        r,c,row=self.check(change)
        self.assertEqual(c['status'],'UNKNOWN')
        self.assertFalse(c['complete'])
        self.assertTrue(c['padding_clipped'])
        self.assertEqual(c['window'],[15,80])

    def test_no_cycle_no_pass(self):
        q,d=fixture();d['signals']['tb.u_a.iso_en']['events']=[[0,'0']]
        r=analyze(q,d)
        self.assertNotEqual(r['summary']['status'],'PASS')

    def test_control_x_no_pass(self):
        def change(q,d,s):
            d['signals']['tb.u_a.iso_en']['events']=[[0,'0'],[20,'1'],[50,'x'],[55,'1'],[90,'0']]
        r,c,row=self.check(change)
        self.assertEqual(r['summary']['status'],'UNKNOWN')

    def test_simultaneous_edges_fail(self):
        def change(q,d,s):
            d['signals']['tb.u_a.power_down']['events'][1][0]=20
        r,c,row=self.check(change)
        self.assertEqual(c['status'],'FAIL')

    def test_dump_off_invalidates_pass(self):
        r,c,row=self.check(lambda q,d,s:d['dump_off'].append(dict(begin=40,end=50)))
        self.assertEqual(row['status'],'UNKNOWN')

    def test_stale_value_after_dump_off_is_not_failure(self):
        def change(q,d,s):
            d['dump_off']=[dict(begin=10,end=19)]
            s['events']=[[0,'1111'],[35,'xxxx'],[70,'0000']]
        r,c,row=self.check(change)
        self.assertEqual(row['checks']['clamp_expected']['status'],'UNKNOWN')
        self.assertEqual(row['checks']['idle_equal']['status'],'UNKNOWN')

    def test_known_failure_before_gap_is_preserved(self):
        def change(q,d,s):
            d['dump_off']=[dict(begin=40,end=50)]
            s['events']=[[0,'0000'],[25,'0001'],[35,'xxxx'],[70,'0000']]
        r,c,row=self.check(change)
        self.assertEqual(row['checks']['clamp_expected']['status'],'FAIL')

    def test_output_direction_required(self):
        q,d=fixture();d['signals']['tb.u_a.dout']['direction']=0
        r=analyze(q,d)
        self.assertEqual(r['summary']['status'],'UNKNOWN')
        self.assertEqual(r['summary']['outputs'],0)

    def test_direct_outputs_only_nested_domains(self):
        q,d=fixture()
        s=copy.deepcopy(d['signals']['tb.u_a.dout']);s.update(name='tb.u_a.child.dout',scope='tb.u_a.child')
        d['signals'][s['name']]=s;d['scopes']['tb.u_a.child']={}
        q['domains'].append(dict(scope='tb.u_a.child',iso_en='tb.u_a.iso_en',power_down='tb.u_a.power_down'))
        r=analyze(q,d)
        self.assertEqual([len(x['outputs']) for x in r['domains']],[1,1])
        self.assertEqual(r['summary']['status'],'PASS')

    def test_fsdb_raw_delta_collapses_final(self):
        records=[dict(record='file',scale='1ps',begin=0,end=100),
                 dict(record='signal',name='s',scope='',local_name='s',direction=2,left=0,right=0)]
        records += [dict(record='value',signal='s',time=t,value=v) for t,v in [(0,'0'),(20,'1'),(20,'0'),(30,'1')]]
        records.append(dict(record='complete',signals=1,events=4))
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'raw';p.write_text('\n'.join(json.dumps(r) for r in records),encoding='utf-8')
            data=load_native(p)
        self.assertEqual(data['signals']['s']['events'],[[0,'0'],[20,'0'],[30,'1']])
        self.assertEqual(data['signals']['s']['deltas'],[dict(time=20,values=['1','0'])])

    def test_units_exact_integer_timing(self):
        self.assertEqual(ns_text(12345,'1ps'),'12.345')
        self.assertEqual(ns_text(15,'0.01n'),'0.15')
        self.assertEqual(str(scale_ns('1fs')),'0.000001')

    def test_empty_and_ambiguous_config_rejected(self):
        q,d=fixture();q['domains']*=2
        with self.assertRaises(ValueError):normalize_config(q)

    def test_waveform_svg_all_outputs_and_x(self):
        q,d=fixture();r=analyze(q,d);domain=r['domains'][0];c=domain['cycles'][0]
        s=scene(r,d,domain,c)
        self.assertEqual(len(s['lanes']),3)
        self.assertIn('X × 4',svg(s))
        self.assertEqual(s['window'],[15,95])


if __name__=='__main__':unittest.main()
