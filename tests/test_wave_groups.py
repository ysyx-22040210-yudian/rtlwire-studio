import copy
import tempfile
from pathlib import Path
import unittest

from rtlwire.wave_groups import parse_rpt, read_rpt, resolve_groups
from rtlwire.wave_core import analyze, normalize_config, RULES, upgrade_report
from rtlwire.wave_plot import scene, svg, value_text
from test_wave import fixture

KEYS=dict(clamp_one='HIGH',clamp_zero='LOW',no_clamp='FREE')


def grouped(text,events=None,mutate=None):
    q,d=fixture();q['grouping_mode']='rpt'
    q['domains'][0].update(rpt_path='test.rpt',group_keywords=KEYS)
    if events is not None:d['signals']['tb.u_a.dout']['events']=events
    if mutate:mutate(q,d)
    document=parse_rpt(text,KEYS)
    report=analyze(q,d,group_documents={'tb.u_a':document})
    return report,report['domains'][0]['cycles'][0]['checks'][0]


class RptParserTests(unittest.TestCase):
    def test_custom_keywords_comments_multiline_and_chinese_commas(self):
        d=parse_rpt('\ufeff# user text\nCHIP_HIGH {a，b\n c[3:0]} // note\nCHIP_LOW { d }\nCHIP_FREE {}',KEYS)
        self.assertEqual(d['groups'][0]['members'],['a','b','c[3:0]'])
        self.assertEqual(d['counts'],dict(clamp_one=3,clamp_zero=1,no_clamp=0))

    def test_keyword_in_group_name_only_not_signal(self):
        with self.assertRaisesRegex(ValueError,'没有匹配'):
            parse_rpt('unrelated {signal_HIGH}',KEYS)

    def test_ambiguous_keywords_rejected(self):
        with self.assertRaisesRegex(ValueError,'多个关键词'):
            parse_rpt('HIGH_LOW {a}',KEYS)

    def test_distinct_nonempty_keywords_required(self):
        for k in [dict(KEYS,no_clamp=''),dict(KEYS,no_clamp='LOW')]:
            with self.assertRaises(ValueError):parse_rpt('LOW {dout}',k)

    def test_keywords_are_literal_and_case_sensitive(self):
        keys=dict(clamp_one='[1]',clamp_zero='[0]',no_clamp='free')
        self.assertEqual(parse_rpt('g[1] {a}',keys)['groups'][0]['policy'],'clamp_one')
        with self.assertRaises(ValueError):parse_rpt('FREE {a}',keys)

    def test_missing_brace_nested_and_trailing_garbage(self):
        for text in ['HIGH {a','HIGH {x {a}}','HIGH {a} garbage','HIGH a}']:
            with self.assertRaises(ValueError):parse_rpt(text,KEYS)

    def test_empty_file_rejected_empty_groups_allowed(self):
        with self.assertRaises(ValueError):parse_rpt('# only comments',KEYS)
        self.assertEqual(parse_rpt('HIGH {} LOW {} FREE {}',KEYS)['counts']['clamp_one'],0)

    def test_file_snapshot_checksum_and_utf8(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'a.rpt';p.write_bytes('HIGH {信号甲}'.encode('utf-8-sig'))
            doc,raw=read_rpt(p,KEYS)
            import hashlib
            self.assertEqual(doc['sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(doc['groups'][0]['members'],['信号甲'])


class GroupCheckTests(unittest.TestCase):
    def test_clamp_one_means_all_ones_bus(self):
        r,row=grouped('HIGH {dout}',[[0,'1111'],[35,'xxxx'],[70,'1111']])
        self.assertEqual(r['summary']['status'],'PASS')
        self.assertEqual(row['expected_clamp'],'1111')
        self.assertEqual(row['clamp_policy'],'clamp_one')

    def test_numeric_one_is_not_all_ones(self):
        r,row=grouped('HIGH {dout}',[[0,'0001'],[35,'xxxx'],[70,'0001']])
        self.assertEqual(row['checks']['clamp_expected']['status'],'FAIL')
        self.assertEqual(row['checks']['recovery_expected']['status'],'FAIL')

    def test_one_idle_mismatch_is_retained(self):
        r,row=grouped('HIGH {dout}',[[0,'0000'],[20,'1111'],[35,'xxxx'],[70,'1111']])
        self.assertEqual(row['checks']['idle_equal']['status'],'FAIL')
        self.assertEqual(row['checks']['clamp_expected']['status'],'PASS')

    def test_zero_group(self):
        r,row=grouped('LOW {tb.u_a.dout}')
        self.assertEqual(row['status'],'PASS')
        self.assertEqual(row['expected_clamp'],'0000')

    def test_no_clamp_allows_activity_and_recovery_changes(self):
        r,row=grouped('FREE {dout}',[[0,'0010'],[20,'0110'],[25,'1111'],[26,'0010'],[35,'xxxx'],[70,'1100'],[75,'0001']])
        self.assertEqual(row['status'],'PASS')
        self.assertEqual(row['checks']['off_x']['status'],'PASS')
        self.assertTrue(all(row['checks'][k]['status']=='SKIP' for k in RULES if k!='off_x'))

    def test_no_clamp_still_requires_full_x(self):
        r,row=grouped('FREE {dout}',[[0,'0010'],[35,'xxx0'],[70,'1100']])
        self.assertEqual(row['status'],'FAIL')
        self.assertEqual(row['checks']['off_x']['time'],35)

    def test_no_clamp_missing_values_are_unknown(self):
        r,row=grouped('FREE {dout}',[])
        self.assertEqual(row['status'],'UNKNOWN')
        self.assertEqual(row['checks']['clamp_expected']['status'],'SKIP')

    def test_mixed_bits_only_compare_clamped_subset(self):
        r,row=grouped('HIGH {dout[3]} LOW {dout[2]} FREE {dout[1:0]}',
                      [[0,'1000'],[20,'1011'],[25,'1001'],[35,'xxxx'],[70,'1010'],[75,'1011']])
        self.assertEqual(row['status'],'PASS')
        self.assertEqual(row['clamp_policy'],'mixed')
        self.assertEqual(row['expected_clamp'],'10--')
        self.assertEqual(row['checks']['idle_equal']['checked_bits'],[3,2])

    def test_ascending_bus_indices(self):
        def change(q,d):d['signals']['tb.u_a.dout'].update(left=0,right=3)
        r,row=grouped('HIGH {dout[0:1]} LOW {dout[2:3]}',[[0,'1100'],[35,'xxxx'],[70,'1100']],change)
        self.assertEqual(row['status'],'PASS')
        self.assertEqual(row['expected_clamp'],'1100')

    def test_duplicate_group_bits_are_unknown_not_last_wins(self):
        for text in ('LOW {dout} HIGH {dout}','LOW {dout,dout}', 'LOW {dout[3:0]} FREE {dout[0]}'):
            r,row=grouped(text)
            self.assertEqual(row['status'],'UNKNOWN')
            self.assertIn('RPT_DUPLICATE_ASSIGNMENT',[i['code'] for i in r['domains'][0]['issues']])

    def test_missing_membership_and_wrong_scope_never_default_zero(self):
        r,row=grouped('LOW {top.other.dout}')
        self.assertEqual(r['summary']['status'],'UNKNOWN')
        self.assertEqual(row['expected_clamp'],'????')
        codes={i['code'] for i in r['domains'][0]['issues']}
        self.assertEqual(codes,{'RPT_SIGNAL_NOT_OUTPUT','RPT_OUTPUT_UNASSIGNED'})
        self.assertIsNone(row['checks']['idle_equal']['actual'])
        self.assertEqual(value_text(''),'—')

    def test_out_of_range_reports_unknown(self):
        r,row=grouped('LOW {dout[99:0]}')
        self.assertEqual(row['status'],'UNKNOWN')
        self.assertIn('RPT_BIT_OUT_OF_RANGE',[i['code'] for i in r['domains'][0]['issues']])

    def test_rpt_required_in_group_mode(self):
        q,d=fixture();q['grouping_mode']='rpt'
        with self.assertRaises(ValueError):normalize_config(q)
        q['domains'][0].update(rpt_path='a.rpt',group_keywords=KEYS)
        with self.assertRaises(ValueError):analyze(q,d)

    def test_old_results_open_with_preserved_verdict(self):
        q,d=fixture();r=analyze(q,d)
        row=r['domains'][0]['cycles'][0]['checks'][0]
        for new,old in [('clamp_expected','clamp_zero'),('recovery_expected','recovery_zero')]:row['checks'][old]=row['checks'].pop(new)
        for k in ('clamp_policy','expected_clamp','group_names'):row.pop(k)
        upgrade_report(r)
        self.assertEqual(row['status'],'PASS');self.assertEqual(row['clamp_policy'],'clamp_zero')
        self.assertEqual(set(row['checks']),set(RULES))

    def test_wave_labels_reflect_one_and_no_clamp(self):
        q,d=fixture();r,row=grouped('HIGH {dout}',[[0,'1111'],[35,'xxxx'],[70,'1111']])
        domain=r['domains'][0]
        text=svg(scene(r,d,domain,domain['cycles'][0]))
        self.assertIn('钳 1',text)
        self.assertNotIn('钳位 0',text)


if __name__=='__main__':unittest.main()
