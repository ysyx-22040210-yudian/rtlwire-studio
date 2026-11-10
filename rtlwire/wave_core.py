"""Four-state power checks on settled FSDB events; integer timestamps throughout.

This module has no EDA or Tk dependencies. Missing data is never an X value.
"""
from bisect import bisect_left, bisect_right
from decimal import Decimal, ROUND_CEILING
import json
import re
from .wave_groups import validate_keywords, resolve_groups, bit_numbers, POLICIES


RULES = ('idle_equal', 'clamp_expected', 'clamp_stable', 'off_x', 'recovery_expected')
LABELS = dict(idle_equal='钳位位的 idle / 钳位一致', clamp_expected='符合 RPT 钳位值',
              clamp_stable='钳位位保持稳定', off_x='掉电期间全 X', recovery_expected='恢复后符合钳位值')


def scale_ns(scale):
    m = re.fullmatch(r'\s*([0-9]+(?:\.[0-9]+)?)\s*(s|ms|us|ns|ps|fs|m|u|n|p|f)\s*', scale)
    if not m:
        raise ValueError('不支持的 FSDB 时间单位: ' + scale)
    factors = dict(s='1e9', ms='1e6', us='1e3', ns='1', ps='.001', fs='.000001',
                   m='1e6', u='1e3', n='1', p='.001', f='.000001')
    value = Decimal(m.group(1)) * Decimal(factors[m.group(2)])
    if value <= 0:
        raise ValueError('FSDB 时间精度必须大于零')
    return value


def ns_text(tick, scale):
    if tick is None:
        return '—'
    s = format(Decimal(tick) * scale_ns(scale), 'f')
    return s.rstrip('0').rstrip('.') if '.' in s else s


def normalize_config(config):
    path = str(config.get('fsdb_path', '')).strip()
    if not path:
        raise ValueError('请选择 FSDB 波形文件。')
    domains = []
    mode=config.get('grouping_mode') or ('rpt' if any('rpt_path' in d or 'group_keywords' in d for d in config.get('domains',[])) else 'legacy_zero')
    if mode not in ('rpt','legacy_zero'):
        raise ValueError('grouping_mode 必须是 rpt 或 legacy_zero。')
    for d in config.get('domains', []):
        scope = str(d.get('scope', '')).strip().strip('.')
        if not scope:
            raise ValueError('请填写每个检查层次的完整实例路径。')
        item = dict(scope=scope)
        for key in ('iso_en', 'power_down'):
            name = str(d.get(key, '')).strip()
            if not name:
                raise ValueError(scope + ': 请填写 ' + key + ' 信号名。')
            # A short leaf name is relative; a hierarchical name is absolute.
            item[key] = scope + '.' + name if '.' not in name else name
        if item['iso_en'] == item['power_down']:
            raise ValueError(scope + ': iso_en 与 power_down 必须是不同信号。')
        if any(any(c in v for c in '\t\r\n') for v in item.values()):
            raise ValueError('层次及信号名不能含制表符或换行。')
        if mode == 'rpt':
            item['rpt_path']=str(d.get('rpt_path','')).strip()
            if not item['rpt_path']:
                raise ValueError(scope+'：请导入该层次的分组 RPT 文件。')
            item['group_keywords']=validate_keywords(d.get('group_keywords',{}))
        domains.append(item)
    if not domains or len(domains) > 64 or len({d['scope'] for d in domains}) != len(domains):
        raise ValueError('请提供 1–64 个互不重复的检查层次。')
    if config.get('edge_policy', 'settled') != 'settled':
        raise ValueError('本版本按同一时刻最终值检查。')
    padding = Decimal(str(config.get('padding_ns', 5)))
    if not padding.is_finite() or padding < 0 or padding > 1000000:
        raise ValueError('波形前后裕量必须在 0–1000000 ns 之间。')
    limits = dict(max_events=2000000, max_width=65536, max_signals=10000, max_cycles=1000,
                  max_value_bytes=134217728)
    for k in limits:
        limits[k] = int(config.get('limits', {}).get(k, limits[k]))
        if limits[k] <= 0:
            raise ValueError(k + ' 必须大于零。')
    return dict(kind='power_wave', fsdb_path=path, domains=domains,
                padding_ns=str(padding), edge_policy='settled', limits=limits, grouping_mode=mode)


def load_native(path, check_cancel=None):
    data = dict(file={}, scopes={}, signals={}, dump_off=[], complete=False)
    with open(str(path), encoding='utf-8') as stream:
        for index,line in enumerate(stream):
            if check_cancel and index % 4096 == 0:
                check_cancel()
            r = json.loads(line)
            kind = r.pop('record')
            if kind == 'file':
                data['file'] = r
            elif kind == 'scope':
                data['scopes'][r['name']] = r
            elif kind == 'dump_off':
                data['dump_off'].append(r)
            elif kind == 'signal':
                r.update(events=[], deltas=[])
                data['signals'][r['name']] = r
            elif kind == 'value':
                s = data['signals'][r['signal']]
                events = s['events']
                t, v = int(r['time']), r['value'].lower()
                if events and t < events[-1][0]:
                    raise ValueError('FSDB 事件时间逆序: ' + r['signal'])
                if events and t == events[-1][0]:
                    if v != events[-1][1]:
                        if not s['deltas'] or s['deltas'][-1]['time'] != t:
                            s['deltas'].append(dict(time=t, values=[events[-1][1]]))
                        s['deltas'][-1]['values'].append(v)
                    events[-1][1] = v
                else:
                    events.append([t, v])
            elif kind == 'unsupported':
                data['signals'][r['signal']]['unsupported'] = r['reason']
            elif kind == 'complete':
                data['complete'], data['counts'] = True, r
    if not data['file'] or not data['complete']:
        raise ValueError('FSDB 提取未完整结束，不能使用部分数据判定通过。')
    scale_ns(data['file']['scale'])
    return data


class Series:
    def __init__(self, signal=None):
        self.signal = signal or {}
        self.events = self.signal.get('events', [])
        self.times = [e[0] for e in self.events]
        self.width = abs(self.signal.get('left', 0) - self.signal.get('right', 0)) + 1

    def at(self, t, before=False):
        i = (bisect_left(self.times, t) if before else bisect_right(self.times, t)) - 1
        return self.events[i][1] if i >= 0 else None

    def interval(self, a, b):
        if a is None or b is None or b <= a:
            return []
        return [[a, self.at(a)]] + self.events[bisect_right(self.times, a):bisect_left(self.times, b)]


def status_of(statuses):
    values = list(statuses)
    return 'FAIL' if 'FAIL' in values else 'UNKNOWN' if not values or 'UNKNOWN' in values else 'SKIP' if all(v=='SKIP' for v in values) else 'PASS'


def issue(code, message, time=None, status='FAIL'):
    return dict(code=code, message=message, time=time, status=status)


def find_cycles(domain, data, max_cycles):
    iso = Series(data['signals'].get(domain['iso_en']))
    power = Series(data['signals'].get(domain['power_down']))
    issues, cycles = [], []
    for key, series in [('iso_en', iso), ('power_down', power)]:
        if not series.signal or not series.events or series.width != 1 or series.signal.get('unsupported'):
            issues.append(issue('CONTROL_UNAVAILABLE', key + ' 必须是具有波形的一位控制信号', status='UNKNOWN'))
    if issues:
        return cycles, issues
    times = sorted(set(iso.times + power.times))
    previous, active = (None, None), None

    def finish(c, end):
        c['end'] = end
        c['complete'] = all(c.get(k) is not None for k in ('iso_rise','power_fall','power_rise','iso_fall'))
        if c['complete'] and not (c['iso_rise'] < c['power_fall'] < c['power_rise'] < c['iso_fall']):
            c['issues'].append(issue('EDGE_ORDER', '四个控制边沿必须按顺序发生且时间严格递增', end))
        if not c['complete']:
            c['issues'].append(issue('INCOMPLETE_CYCLE', '波形缺少完整的隔离、掉电或恢复边沿', end, 'UNKNOWN'))
        c['index'] = len(cycles) + 1
        cycles.append(c)
        if len(cycles) > max_cycles:
            raise ValueError('周期数超过 max_cycles 限制，请缩小输入波形范围或提高限制。')

    for t in times:
        current = (iso.at(t), power.at(t))
        pi, pp = previous
        i, p = current
        unknown = i not in ('0', '1') or p not in ('0', '1')
        if unknown:
            item = issue('CONTROL_UNKNOWN', '控制信号含 X/Z 或缺少值', t, 'UNKNOWN')
            if active:
                active['issues'].append(item)
            issues.append(item)
        rise_i, fall_i = pi == '0' and i == '1', pi == '1' and i == '0'
        fall_p, rise_p = pp == '1' and p == '0', pp == '0' and p == '1'
        if rise_i:
            if active:
                active['issues'].append(issue('REPEATED_ISOLATION', '前一周期未结束便再次隔离', t))
                finish(active, t)
            active = dict(start=t, iso_rise=t, power_fall=None, power_rise=None, iso_fall=None, issues=[])
            if pp != '1' or p != '1':
                active['issues'].append(issue('ISOLATION_NOT_BEFORE_POWER', '隔离拉高时应仍处于上电状态', t))
        elif not active and i == '1' and (pi is None or pi not in ('0','1')):
            active = dict(start=t, iso_rise=None, power_fall=None, power_rise=None, iso_fall=None, issues=[])
        if active:
            if fall_p:
                if active['power_fall'] is not None or active['power_rise'] is not None:
                    active['issues'].append(issue('REPEATED_POWER_FALL', '隔离周期内出现重复掉电', t))
                else:
                    active['power_fall'] = t
            if rise_p:
                if active['power_fall'] is None or active['power_rise'] is not None:
                    active['issues'].append(issue('POWER_ORDER', '上电边沿没有对应的掉电边沿', t))
                else:
                    active['power_rise'] = t
            if fall_i:
                active['iso_fall'] = t
                if active['power_rise'] is None or p != '1':
                    active['issues'].append(issue('EARLY_RELEASE', '供电恢复前解除隔离', t))
                finish(active, t)
                active = None
        elif fall_p:
            issues.append(issue('POWER_WITHOUT_ISOLATION', '未先拉高隔离便掉电', t))
        previous = current
    if active:
        finish(active, data['file']['end'])
    if not cycles:
        issues.append(issue('NO_CYCLE', '没有找到隔离拉高及其后续周期', status='UNKNOWN'))
    return cycles, issues


def _missing(v):
    return v is None or '?' in v


def check_output(signal, cycle, data, series=None, assignment=None):
    series = series or Series(signal)
    t1, t2, t3, t4 = [cycle.get(k) for k in ('iso_rise','power_fall','power_rise','iso_fall')]
    assignment=assignment or dict(policy_bits='0'*series.width,clamp_policy='clamp_zero',groups=[],members=[],issues=[])
    pattern=assignment['policy_bits']
    numbers=bit_numbers(signal)
    indices=[i for i,v in enumerate(pattern) if v in '01']
    unresolved='?' in pattern
    all_x = 'x' * series.width
    gaps = data.get('dump_off', [])

    def covered_value(t, before=False):
        if t is None:
            return None
        index = (bisect_left(series.times, t) if before else bisect_right(series.times, t)) - 1
        if index < 0:
            return None
        last = series.times[index]
        for gap in gaps:
            # A pre-gap sample is stale until the signal is recorded again after dump-on.
            entered = gap['begin'] < t if before else gap['begin'] <= t
            if entered and last < gap['end']:
                return None
        return series.events[index][1]

    idle = covered_value(t1, before=True)
    clamp = covered_value(t1)
    checks = {}

    def result(name, status, first=None, actual=None, expected=None, message='', positions=None):
        positions=indices if positions is None else positions
        checks[name] = dict(status=status, time=first, actual=actual, expected=expected, message=message,
                            checked_bits=[numbers[i] for i in positions])

    def project(value, positions):
        if not positions or value is None or len(value)!=series.width:
            return None
        return ''.join(value[i] for i in positions)

    idle_bits,clamp_bits=project(idle,indices),project(clamp,indices)
    equal = 'UNKNOWN' if _missing(idle_bits) or _missing(clamp_bits) else 'PASS' if idle_bits == clamp_bits else 'FAIL'
    if not indices:
        equal='UNKNOWN' if unresolved else 'SKIP'
    elif unresolved and equal=='PASS':
        equal='UNKNOWN'
    result('idle_equal',equal,t1,idle_bits,clamp_bits,
           '不钳位组不检查 idle 与钳位值' if equal=='SKIP' else '存在未明确分组的位' if unresolved else '')

    def interval_rule(name, a, b, expected, positions=None, require_group=True):
        positions=indices if positions is None else positions
        if require_group and not positions:
            result(name,'UNKNOWN' if unresolved else 'SKIP',message='存在未明确分组的位' if unresolved else '不钳位组不执行此项检查')
            return
        samples = series.interval(a, b)
        if not samples or expected is None:
            result(name, 'UNKNOWN', message='边沿缺失、区间为空或初始值不可用',positions=positions)
            return
        unknown = require_group and unresolved
        if any(g['begin'] < b and g['end'] > a for g in gaps):
            unknown = True
        for t, value in samples:
            value = project(covered_value(t),positions)
            if _missing(value):
                unknown = True
            elif value != expected:
                result(name, 'FAIL', t, value, expected,positions=positions)
                return
        result(name, 'UNKNOWN' if unknown else 'PASS', expected=expected,positions=positions,
               message='存在未明确分组的位' if require_group and unresolved else '')

    expected=''.join(pattern[i] for i in indices)
    interval_rule('clamp_expected', t1, t2, expected)
    interval_rule('clamp_stable', t1, t2, clamp_bits)
    interval_rule('off_x', t2, t3, all_x,positions=list(range(series.width)),require_group=False)
    interval_rule('recovery_expected', t3, t4, expected)
    # Missing dump data invalidates a pass, including a stale value spanning a dump gap.
    overlaps = [g for g in gaps if g['begin'] <= cycle['end'] and g['end'] >= cycle['start']]
    if overlaps:
        for r in checks.values():
            if r['status'] not in ('FAIL','SKIP'):
                r.update(status='UNKNOWN', message='检查周期与 dump-off 数据空洞重叠')
    if signal.get('unsupported'):
        for r in checks.values():
            if r['status']!='SKIP':r.update(status='UNKNOWN', message=signal['unsupported'])
    status = status_of([r['status'] for r in checks.values()] + [i['status'] for i in cycle['issues']] +
                       [i['status'] for i in assignment['issues']])
    return dict(signal=signal['name'], local_name=signal['local_name'], width=series.width,
                idle=idle, clamp=clamp, checks=checks, status=status,clamp_policy=assignment['clamp_policy'],
                expected_clamp=pattern,group_names=assignment['groups'],rpt_members=assignment['members'],
                group_issues=assignment['issues'])


def analyze(config, data, check_cancel=None, group_documents=None):
    config = normalize_config(config)
    scale = scale_ns(data['file']['scale'])
    pad = int((Decimal(config['padding_ns']) / scale).to_integral_value(rounding=ROUND_CEILING))
    if config['grouping_mode']=='rpt' and group_documents is None:
        raise ValueError('RPT 分组配置尚未加载，不能进行分组检查。')
    report = dict(kind='power_wave', version=2, config=config, file=data['file'], domains=[],
                  policy=dict(edge='settled', idle='strictly_before_iso_rise',
                              intervals='[iso_rise,power_fall), [power_fall,power_rise), [power_rise,iso_fall)',
                              coverage='Direct output ports declared in the FSDB; omitted ports cannot be inferred.',
                              delta='Recorded same-timestamp updates are warnings, not failures.',
                              grouping=config['grouping_mode'],no_clamp='Skip clamp rules; still require all X during power-off.'))
    all_rows, all_statuses = [], []
    for domain in config['domains']:
        cycles, issues = find_cycles(domain, data, config['limits']['max_cycles'])
        if data.get('dump_off'):
            issues.append(issue('DUMP_OFF_COVERAGE', 'FSDB 含 dump-off 区间，无法保证未记录区间内的控制周期覆盖', status='UNKNOWN'))
        outputs = sorted((s for s in data['signals'].values() if s['scope'] == domain['scope'] and s['direction'] == 2), key=lambda s:s['name'])
        if domain['scope'] not in data['scopes']:
            issues.append(issue('SCOPE_NOT_FOUND', 'FSDB 中没有该层次', status='UNKNOWN'))
        if not outputs:
            issues.append(issue('NO_OUTPUT_PORT_METADATA', 'FSDB 中没有记录该层次的输出口方向信息，无法自动枚举输出口', status='UNKNOWN'))
        if len(outputs) > config['limits']['max_signals']:
            raise ValueError('输出口数超过 max_signals 限制。')
        document=(group_documents or {}).get(domain['scope'])
        if config['grouping_mode']=='rpt' and document is None:
            raise ValueError(domain['scope']+'：缺少已加载的 RPT 分组。')
        assignments,group_issues=resolve_groups(domain['scope'],outputs,document,legacy=config['grouping_mode']=='legacy_zero')
        issues.extend(group_issues)
        names = {s['name'] for s in outputs} | {domain['iso_en'], domain['power_down']}
        series_by_name = {s['name']:Series(s) for s in outputs}
        for c in cycles:
            if check_cancel:
                check_cancel()
            c['scope'] = domain['scope']
            c['window'] = [max(data['file']['begin'], c['start']-pad), min(data['file']['end'], c['end']+pad)]
            c['padding_clipped'] = c['window'] != [c['start']-pad, c['end']+pad]
            c['checks'] = []
            for s in outputs:
                if check_cancel:
                    check_cancel()
                c['checks'].append(check_output(s, c, data, series_by_name[s['name']],assignments[s['name']]))
            c['delta_warnings'] = [dict(signal=n, **d) for n in sorted(names) for d in data['signals'].get(n, {}).get('deltas', [])
                                   if c['window'][0] <= d['time'] <= c['window'][1]]
            c['status'] = status_of([r['status'] for r in c['checks']] + [i['status'] for i in c['issues']] + ([] if outputs else ['UNKNOWN']))
            all_rows.extend(c['checks'])
        status = status_of([c['status'] for c in cycles] + [i['status'] for i in issues] + ([] if outputs and cycles else ['UNKNOWN']))
        group_counts={p:sum(a['clamp_policy']==p for a in assignments.values()) for p in POLICIES+('mixed','unassigned')}
        report['domains'].append(dict(config=domain, outputs=[s['name'] for s in outputs], cycles=cycles, issues=issues, status=status,
                                      rpt=document,group_counts=group_counts,output_groups=assignments))
        all_statuses.append(status)
    summary = dict(status=status_of(all_statuses), domains=len(report['domains']),
                   outputs=sum(len(d['outputs']) for d in report['domains']),
                   cycles=sum(len(d['cycles']) for d in report['domains']),
                   complete_cycles=sum(c['complete'] for d in report['domains'] for c in d['cycles']),
                   output_cycle_checks=len(all_rows),
                   delta_warnings=sum(len(c['delta_warnings']) for d in report['domains'] for c in d['cycles']))
    summary.update({s.lower():sum(r['status']==s for r in all_rows) for s in ('PASS','FAIL','UNKNOWN')})
    report['summary'] = summary
    return report


def upgrade_report(report):
    """Display older saved results without re-reading design files or changing their verdict."""
    for domain in report.get('domains',[]):
        for cycle in domain['cycles']:
            for row in cycle['checks']:
                for old,new in [('clamp_zero','clamp_expected'),('recovery_zero','recovery_expected')]:
                    if old in row['checks']:
                        row['checks'][new]=row['checks'].pop(old)
                row.setdefault('clamp_policy','clamp_zero')
                row.setdefault('expected_clamp','0'*row['width'])
                row.setdefault('group_names',['旧版全 0 规则'])
                row.setdefault('group_issues',[])
    return report
