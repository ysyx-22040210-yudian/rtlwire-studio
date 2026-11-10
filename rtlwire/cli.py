import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from . import __version__
from .core import parse_records, analyze, enumerate_paths, reach_paths, display_graph
from .report import dump_json, write_reports


ROOT = Path(__file__).resolve().parent.parent
RTL_EXTENSIONS = {'.v', '.sv', '.vh', '.svh', '.vhd', '.vhdl'}


def package_manifest(database, readonly_root=None):
    records = []
    readonly_root = (readonly_root or database.parent).resolve()
    roots = {str(readonly_root)}
    for path in sorted(database.rglob('*')):
        if path.is_symlink() and not path.exists():
            raise ValueError('ELAB_PACKAGE_BROKEN_SYMLINK: ' + str(path))
        if path.is_file():
            resolved = path.resolve()
            if resolved.suffix.lower() in RTL_EXTENSIONS:
                raise ValueError('RTL_SOURCE_IN_DATABASE_PACKAGE: ' + str(path))
            digest = hashlib.sha256()
            with resolved.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            records.append(dict(path=str(path.relative_to(database)), real_path=str(resolved),
                                size=resolved.stat().st_size, sha256=digest.hexdigest()))
            if not str(resolved).startswith(str(readonly_root) + os.sep):
                roots.add(str(resolved.parent))
    if not records:
        raise ValueError('EMPTY_ELAB_PACKAGE')
    fingerprint = hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()
    return dict(files=records, sha256=fingerprint, readonly_roots=sorted(roots))


def audit_access(path, log_path):
    rtl_reads, compilers = [], []
    if not path.exists():
        return dict(passed=False, error='strace audit missing')
    pending = {}
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        match = re.match(r'^(\d+)\s+(.*)$', line)
        if match:
            pid, body = match.groups()
            if '<unfinished ...>' in body:
                pending[pid] = body.split('<unfinished ...>')[0]
                continue
            resumed = re.match(r'<\.\.\. \w+ resumed>(.*)', body)
            if resumed and pid in pending:
                line = pid + ' ' + pending.pop(pid) + resumed.group(1)
        if re.search(r'\b(?:open|openat|open64)\(', line) and re.search(r'=\s*[0-9]+\s*$', line):
            quoted = re.findall(r'"([^"\n]*)"', line)
            if quoted and Path(quoted[0]).suffix.lower() in RTL_EXTENSIONS:
                rtl_reads.append(line)
        if 'execve(' in line and re.search(r'/(?:vcs|vcs1|vlogan|vhdlan|vericom|elabcom)"', line):
            compilers.append(line)
    blocked = [x for x in log_path.read_text(encoding='utf-8', errors='replace').splitlines()
               if 'RTLWIRE_SOURCE_BLOCKED:' in x]
    return dict(passed=not rtl_reads and not compilers, successful_rtl_source_opens=rtl_reads,
                rtl_compiler_executions=compilers, blocked_source_attempts=blocked,
                enforcement='Private mount namespace: input roots read-only; LD_PRELOAD RTL source guard; strace file/process audit')


def tcl_value(value):
    return '[encoding convertfrom utf-8 [binary decode hex {%s}]]' % str(value).encode('utf-8').hex()


def make_config(query, policy):
    cfg = dict(boundary=query['traversal_boundary'], traversal=policy.get('traversal', 'wire_only' if query['mode'] == 'reach' else 'dependency'),
               max_instances=policy.get('max_instances', 100000), max_nodes=policy.get('max_nodes', 100000),
               max_edges=policy.get('max_edges', 300000), max_depth=policy.get('max_depth', 256),
               max_signal_bits=policy.get('max_signal_bits', 4096))
    if cfg['traversal'] not in ('wire_only', 'dependency'):
        raise ValueError('Unsupported traversal policy')
    sources = list(query.get('sources', []))
    if 'source' in query:
        source = query['source']
        if source.get('direction', 'load') != 'load':
            raise ValueError('trace currently supports downstream (load) direction only; reach automatically checks both directions')
        name = source['scope'] + '.' + source['signal']
        if 'bits' in source:
            name += '[' + str(source['bits']) + ']'
        sources = sources + [name]
    observe = []
    for item in query.get('observe_signals', []):
        if isinstance(item, str):
            observe.append(item)
        else:
            observe += [item['scope'] + '.' + name for name in item['names']]
    cfg['sources'] = list(dict.fromkeys(sources))
    cfg['observe'] = list(dict.fromkeys(observe))
    if query['mode'] != 'inventory' and not sources:
        raise ValueError('At least one source signal is required')
    for key in ('max_instances', 'max_nodes', 'max_edges', 'max_depth', 'max_signal_bits'):
        if not isinstance(cfg[key], int) or cfg[key] < 1:
            raise ValueError(key + ' must be a positive integer')
    cfg['directions'] = ['load', 'driver'] if query['mode'] == 'reach' else ['load']
    lines = ['array set cfg {}']
    for key, value in cfg.items():
        if isinstance(value, list):
            encoded = '[list ' + ' '.join(tcl_value(v) for v in value) + ']'
        else:
            encoded = tcl_value(value)
        lines.append('set cfg(%s) %s' % (key, encoded))
    return '\n'.join(lines) + '\n'


def run(args):
    def progress(phase, message):
        if getattr(args, 'progress_json', False):
            print(json.dumps(dict(event='phase', phase=phase, message=message), ensure_ascii=True), flush=True)
    progress('preparing', '校验配置与输入数据库')
    if sys.platform != 'linux':
        raise ValueError('NPI extraction runs on Linux. Use --analyze-raw for offline report generation.')
    config = json.loads(Path(args.query).read_text(encoding='utf-8-sig'))
    query, design, policy = config['query'], config['design'], config.get('policy', {})
    if query.get('mode') not in ('reach', 'trace', 'inventory'):
        raise ValueError('mode must be reach, trace or inventory')
    if not query.get('check_scopes') or not isinstance(query['check_scopes'], list):
        raise ValueError('check_scopes must be a nonempty list')
    forbidden = {'filelist', 'defines', 'include_dirs', 'rtl_files', 'parameter_overrides'} & set(design)
    if forbidden or design.get('input_kind', 'elab') != 'elab':
        raise ValueError('ELAB_ONLY: raw RTL/compiler inputs are prohibited')
    if design.get('allow_rtl_source') or design.get('allow_compile') or design.get('allow_reelaboration'):
        raise ValueError('ELAB_ONLY: fallback compilation/source loading is prohibited')
    elab = Path(args.elab or design['elab_path']).expanduser().absolute()
    if elab.suffix != '.elab++':
        elab = Path(str(elab) + '.elab++')
    if not elab.is_dir():
        raise ValueError('ELAB_DIRECTORY_NOT_FOUND: ' + str(elab))
    verdi_home = Path(args.verdi_home or os.environ.get('VERDI_HOME', '')).absolute()
    if not (verdi_home / 'bin/verdi').is_file():
        raise ValueError('VERDI_HOME must point to the installed Verdi distribution')
    out = Path(args.out).absolute()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output directory must be empty: ' + str(out))
    out.mkdir(parents=True, exist_ok=True)
    for executable in ('unshare', 'mount', 'strace', 'gcc'):
        if shutil.which(executable) is None:
            raise ValueError('Required executable missing: ' + executable)
    before = package_manifest(elab)
    for r in before['readonly_roots']:
        if str(out).startswith(r + os.sep) or str(out) == r:
            raise ValueError('Output must be outside the read-only input roots')
    dump_json(out / 'input_before.json', before)
    dump_json(out / 'query.json', config)
    (out / 'query.tcl').write_text(make_config(query, policy), encoding='utf-8')
    (out / 'readonly_roots.txt').write_text('\n'.join(before['readonly_roots']) + '\n', encoding='utf-8')
    guard = out / 'source_guard.so'
    build = subprocess.run(['gcc', '-shared', '-fPIC', '-O2', '-Wall', '-o', str(guard), str(ROOT / 'npi/source_guard.c'), '-ldl'],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    (out / 'guard_build.log').write_text(build.stdout, encoding='utf-8')
    if build.returncode:
        raise ValueError('Cannot compile source-access guard; see guard_build.log')
    env = os.environ.copy()
    env.update(VERDI_HOME=str(verdi_home), RTLWIRE_RO_ROOTS=str(out / 'readonly_roots.txt'), RTLWIRE_GUARD=str(guard),
               RTLWIRE_AUDIT=str(out / 'access.log'), RTLWIRE_ELAB_DIR=str(elab),
               RTLWIRE_EXTRACTOR=str(ROOT / 'npi/extract.tcl'), RTLWIRE_QUERY_TCL=str(out / 'query.tcl'),
               RTLWIRE_RAW=str(out / 'network.raw.tsv'))
    command = ['unshare', '-m', '--propagation', 'private', 'bash', str(ROOT / 'npi/readonly_run.sh')]
    start = time.time()
    timed_out = False
    cancelled = False
    progress('extracting', 'Verdi 正在只读加载 elab 并提取 NPI 连接')
    with (out / 'verdi.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, cwd=str(out), env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while True:
                cancelled = bool(getattr(args, 'cancel_file', None) and Path(args.cancel_file).exists())
                if cancelled or time.time() - start >= policy.get('timeout_seconds', 120):
                    raise subprocess.TimeoutExpired(command, policy.get('timeout_seconds', 120))
                try:
                    rc = process.wait(timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    pass
        except subprocess.TimeoutExpired:
            import signal
            os.killpg(process.pid, signal.SIGTERM)
            try:
                rc = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                rc = process.wait()
            timed_out = not cancelled
    progress('auditing', '核对源码访问审计及输入库校验值')
    after = package_manifest(elab)
    dump_json(out / 'input_after.json', after)
    audit = audit_access(out / 'access.log', out / 'verdi.log')
    audit['database_unchanged'] = before['sha256'] == after['sha256']
    audit['passed'] = audit['passed'] and audit['database_unchanged']
    dump_json(out / 'audit.json', audit)
    manifest = dict(tool_version=__version__, elab=str(elab), elab_sha256=before['sha256'],
                    verdi_home=str(verdi_home), load_command=['debImport', '-elab', str(elab)],
                    command=command, elapsed_seconds=round(time.time() - start, 3),
                    process_exit_code=rc, timed_out=timed_out, cancelled=cancelled, audit_passed=audit['passed'])
    version = re.search(r'^Release (.+)$', (out / 'verdi.log').read_text(encoding='utf-8', errors='replace'), re.MULTILINE)
    manifest['verdi_release'] = version.group(1) if version else 'See verdi.log'
    dump_json(out / 'manifest.json', manifest)
    if not audit['passed']:
        raise ValueError('ELAB_ONLY_AUDIT_FAILED: see audit.json')
    raw = out / 'network.raw.tsv'
    if not raw.is_file():
        raise ValueError('ELAB_LOAD_OR_NPI_START_FAILED: see verdi.log')
    graph = parse_records(raw)
    if cancelled:
        graph['errors'].append(dict(message='CANCELLED', detail='Cancelled by the user; extracted data may be incomplete.'))
    if timed_out:
        graph['errors'].append(dict(message='TIMEOUT', detail='The extraction process exceeded the configured time limit.'))
    if rc != 0:
        graph['errors'].append(dict(message='VERDI_EXIT_ERROR', detail=str(rc)))
    progress('rendering', '生成层次架构图、连接表和路径记录')
    return finish(out, graph, query, policy)


def finish(out, graph, query, policy):
    result = analyze(graph, query)
    limits = (policy.get('max_paths', 500), policy.get('max_path_depth', 512))
    paths = reach_paths(graph, result, *limits) if query['mode'] == 'reach' else enumerate_paths(graph, *limits)
    result['paths_complete'] = not paths['truncated']
    view = display_graph(graph)
    write_reports(out, graph, result, paths, view)
    summary = dict(mode=query['mode'], complete=result['complete'], candidates=result['candidate_count'],
                   connected_checks=sum(r['status'] == 'CONNECTED' for r in result['checks']),
                   raw_nodes=len(graph['nodes']), raw_edges=len(graph['edges']), displayed_nodes=len(view['nodes']),
                   paths=len(paths['paths']), paths_truncated=paths['truncated'], report=str(out / 'report.html'))
    dump_json(out / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=True))
    if graph['errors'] or any(x['role'] == 'source' for x in graph['unresolved']):
        return 2
    return 0 if result['complete'] and not paths['truncated'] else 3


def main():
    parser = argparse.ArgumentParser(description='Read compiled Verdi elab, check RTL wiring and export ownership-aware graphs.')
    parser.add_argument('--query', required=True, help='JSON query file')
    parser.add_argument('--out', required=True, help='New output directory')
    parser.add_argument('--elab', help='Override elab directory/prefix')
    parser.add_argument('--verdi-home', help='Verdi installation directory')
    parser.add_argument('--analyze-raw', help='Offline analysis of an existing network.raw.tsv')
    parser.add_argument('--progress-json', action='store_true', help='Emit machine-readable progress events')
    parser.add_argument('--cancel-file', help='Cancel this run when this file exists')
    args = parser.parse_args()
    try:
        if args.analyze_raw:
            config = json.loads(Path(args.query).read_text(encoding='utf-8-sig'))
            out = Path(args.out).absolute()
            out.mkdir(parents=True, exist_ok=True)
            return finish(out, parse_records(Path(args.analyze_raw)), config['query'], config.get('policy', {}))
        return run(args)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print('RTLWIRE_ERROR: ' + str(exc), file=sys.stderr)
        return 2
