"""Read RPT data (never execute it) and resolve user-keyword groups to port bits."""
import hashlib
from pathlib import Path
import re

POLICIES = ('clamp_one', 'clamp_zero', 'no_clamp')
POLICY_LABELS = dict(clamp_one='钳 1', clamp_zero='钳 0', no_clamp='不钳位',
                     mixed='混合', unassigned='未完整分组')
POLICY_BIT = dict(clamp_one='1', clamp_zero='0', no_clamp='-')


def validate_keywords(values):
    keys = {k:str(values.get(k, '')).strip() for k in POLICIES}
    if any(not v or any(c in v for c in '\r\n\t{}') for v in keys.values()):
        raise ValueError('请分别填写钳 1、钳 0、不钳位的分组关键词（不能含换行或花括号）。')
    if len(set(keys.values())) != 3:
        raise ValueError('三种分组的关键词必须互不相同。')
    return keys


def parse_rpt(text, keywords, source='<RPT>'):
    keywords = validate_keywords(keywords)
    # Preserve newlines for diagnostics. Comments have no interpretation as commands.
    clean = re.sub(r'/\*[\s\S]*?\*/|//[^\r\n]*|\#[^\r\n]*',
                   lambda m:'\n' * m.group(0).count('\n'), text.lstrip('\ufeff'))
    groups, pos, tokens = [], 0, 0

    def error(message, at):
        raise ValueError('%s:%d: %s' % (source, clean.count('\n',0,at)+1, message))

    while pos < len(clean):
        while pos < len(clean) and (clean[pos].isspace() or clean[pos] == ';'):
            pos += 1
        if pos == len(clean):
            break
        start = pos
        opening = clean.find('{',pos)
        if opening < 0:
            error('分组缺少左花括号 {',pos)
        name = clean[pos:opening].strip()
        if not name or any(c in name for c in '\r\n}'): 
            error('分组名称必须位于同一行，格式为 组名 {信号列表}',pos)
        close = clean.find('}',opening+1)
        if close < 0:
            error('分组 '+name+' 缺少右花括号 }',opening)
        body = clean[opening+1:close]
        if '{' in body:
            error('不支持嵌套分组，请使用 组名 {信号1, 信号2}',opening)
        matches = [k for k in POLICIES if keywords[k] in name]
        if len(matches) != 1:
            error('分组 '+name+(' 没有匹配任何关键词' if not matches else ' 同时匹配多个关键词：'+', '.join(matches)),start)
        members = [x for x in re.split(r'[,，\s]+',body.strip()) if x]
        if any(any(c in x for c in '{};"\'') for x in members):
            error('信号列表只能包含名称、逗号和空白分隔符',opening)
        groups.append(dict(name=name, policy=matches[0], members=members,
                           line=clean.count('\n',0,start)+1))
        tokens += len(members)
        if len(groups)>10000 or tokens>250000:
            error('RPT 超过 10000 个分组或 250000 个信号条目限制',start)
        pos = close+1
    if not groups:
        error('RPT 中没有任何分组',0)
    return dict(source=source, keywords=keywords, groups=groups,
                counts={k:sum(len(g['members']) for g in groups if g['policy']==k) for k in POLICIES})


def read_rpt(path, keywords):
    path = Path(path).expanduser().resolve()
    if path.suffix.lower()!='.rpt':
        raise ValueError('请选择 .rpt 分组文件：'+str(path))
    if not path.is_file():
        raise ValueError('RPT 文件不存在：'+str(path))
    with path.open('rb') as stream:
        raw = stream.read(16*1024*1024+1)
    if len(raw)>16*1024*1024:
        raise ValueError('RPT 文件超过 16 MiB 限制：'+str(path))
    try:
        text=raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ValueError('RPT 必须为 UTF-8 或 ASCII 编码：'+str(path))
    document = parse_rpt(text,keywords,str(path))
    document.update(sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw))
    return document, raw


def bit_numbers(signal):
    left,right=signal.get('left',0),signal.get('right',0)
    return list(range(left,right+(1 if right>=left else -1),1 if right>=left else -1))


def resolve_groups(scope, outputs, document=None, legacy=False):
    """Exact local/full names; bit/range selects bind by declaration bit index.

    Unknown entries, duplicate assignments, and uncovered bits prevent a PASS.
    '-' is an explicitly un-clamped bit; '?' has no unambiguous group assignment.
    """
    issues, assignments = [], {}
    full = {s['name']:s for s in outputs}
    local = {s['local_name']:s for s in outputs}
    for s in outputs:
        width=len(bit_numbers(s))
        assignments[s['name']] = dict(policy_bits=('0' if legacy else '?')*width,
                                     clamp_policy='clamp_zero' if legacy else 'unassigned',
                                     groups=[], members=[], issues=[])
    if legacy:
        return assignments, issues

    def problem(code,message,signal=None,group=None,member=None):
        item=dict(code=code,message=message,time=None,status='UNKNOWN',signal=signal,group=group,member=member)
        issues.append(item)
        if signal in assignments:
            assignments[signal]['issues'].append(item)

    owners={s['name']:[[] for _ in bit_numbers(s)] for s in outputs}
    for g in document['groups']:
        for member in g['members']:
            signal=full.get(member) or local.get(member)
            selected=None
            if signal is None:
                m=re.fullmatch(r'(.+)\[(-?\d+)(?::(-?\d+))?\]',member)
                if m:
                    signal=full.get(m.group(1)) or local.get(m.group(1))
                    if signal:
                        a,b=int(m.group(2)),int(m.group(3) or m.group(2))
                        # Validate endpoints before constructing a possibly huge range.
                        actual=bit_numbers(signal)
                        if a not in actual or b not in actual:
                            problem('RPT_BIT_OUT_OF_RANGE',member+' 的位索引超出输出口范围',signal['name'],g['name'],member)
                            continue
                        selected=set(range(min(a,b),max(a,b)+1))
            if signal is None:
                problem('RPT_SIGNAL_NOT_OUTPUT',member+' 未匹配到 '+scope+' 的已记录直接输出口',group=g['name'],member=member)
                continue
            name=signal['name'];numbers=bit_numbers(signal)
            positions=[i for i,b in enumerate(numbers) if selected is None or b in selected]
            assignment=assignments[name]
            ref=dict(group=g['name'],policy=g['policy'],member=member,line=g['line'],bits=[numbers[i] for i in positions])
            assignment['members'].append(ref)
            if g['name'] not in assignment['groups']:assignment['groups'].append(g['name'])
            repeated=[]
            for i in positions:
                if owners[name][i]:repeated.append(numbers[i])
                owners[name][i].append(POLICY_BIT[g['policy']])
            if repeated:
                problem('RPT_DUPLICATE_ASSIGNMENT',name+' 的位 '+','.join(map(str,repeated))+' 重复归组',name,g['name'],member)
    reverse={'1':'clamp_one','0':'clamp_zero','-':'no_clamp'}
    for s in outputs:
        name=s['name'];a=assignments[name];numbers=bit_numbers(s)
        a['policy_bits']=''.join(values[0] if len(values)==1 else '?' for values in owners[name])
        missing=[numbers[i] for i,values in enumerate(owners[name]) if not values]
        if missing:
            problem('RPT_OUTPUT_UNASSIGNED',name+' 未分组的位：'+','.join(map(str,missing)),name)
        kinds=set(a['policy_bits'])
        a['clamp_policy']='unassigned' if '?' in kinds else reverse[next(iter(kinds))] if len(kinds)==1 else 'mixed'
    return assignments,issues
