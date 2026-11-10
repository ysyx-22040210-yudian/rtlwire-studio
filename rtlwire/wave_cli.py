"""Linux-local FSDB SDK extraction, checks and reproducible result artifacts."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from . import __version__
from .cli import audit_access
from .wave_core import normalize_config, load_native, analyze, RULES, ns_text, Series
from .wave_plot import scene, svg
from .wave_groups import read_rpt

ROOT = Path(__file__).resolve().parent.parent


class Cancelled(Exception):
    pass


def dump(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def run(args):
    def progress(phase,message):
        if args.progress_json:
            print(json.dumps(dict(event='phase',phase=phase,message=message)),flush=True)

    def cancelled():
        if args.cancel_file and Path(args.cancel_file).exists():
            raise Cancelled('检查已取消，已有日志保留。')

    def sha(path):
        h=hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):
                cancelled();h.update(block)
        return h.hexdigest()

    def execute(command, log, environment=None):
        cancelled()
        with log.open('w',encoding='utf-8') as stream:
            p=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,env=environment,
                               cwd=str(out),start_new_session=True)
            start=time.monotonic()
            try:
                while p.poll() is None:
                    cancelled()
                    if time.monotonic()-start>args.timeout:
                        raise ValueError('阶段超时，请查看 '+str(log))
                    time.sleep(.1)
                if p.returncode:
                    raise ValueError('命令执行失败，请查看 '+str(log))
            finally:
                if p.poll() is None:
                    os.killpg(p.pid,signal.SIGTERM)
                    try:p.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(p.pid,signal.SIGKILL);p.wait()

    if sys.platform!='linux':
        raise ValueError('FSDB 提取仅在安装了 Verdi 的 Linux 本机运行。')
    config=normalize_config(json.loads(Path(args.query).read_text(encoding='utf-8-sig')))
    fsdb=Path(config['fsdb_path']).expanduser().resolve()
    if not fsdb.is_file() or fsdb.suffix.lower()!='.fsdb':
        raise ValueError('FSDB 文件不存在或扩展名不是 .fsdb: '+str(fsdb))
    config['fsdb_path']=str(fsdb)
    home=Path(args.verdi_home or os.environ.get('VERDI_HOME','')).expanduser().resolve()
    sdk=home/'share/FsdbReader'
    lib=Path(args.reader_lib).expanduser().resolve() if args.reader_lib else sdk/'linux64'
    if not (sdk/'ffrAPI.h').is_file() or not (lib/'libnffr.so').is_file():
        raise ValueError('当前 Verdi 安装未找到 FSDB Reader SDK；请设置 VERDI_HOME 或 --reader-lib。')
    for tool in ('g++','gcc','strace'):
        if not shutil.which(tool):
            raise ValueError('缺少本机依赖: '+tool)
    out=Path(args.out).expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('结果目录必须为空: '+str(out))
    out.mkdir(parents=True,exist_ok=True)
    dump(out/'query.json',config)
    audit=dict(input=str(fsdb),passed=False,finished=False,rtl_source_used=False)
    try:
        progress('preparing','校验 FSDB 与 RPT 分组，构建本机 SDK 适配器')
        group_documents={}
        audit['rpt_inputs']=[]
        if config['grouping_mode']=='rpt':
            (out/'rpt_inputs').mkdir()
            for index,domain in enumerate(config['domains'],1):
                cancelled()
                document,raw=read_rpt(domain['rpt_path'],domain['group_keywords'])
                domain['rpt_path']=document['source']
                group_documents[domain['scope']]=document
                snapshot='rpt_inputs/domain_%d.rpt'%index
                (out/snapshot).write_bytes(raw)
                audit['rpt_inputs'].append(dict(scope=domain['scope'],path=document['source'],
                                                sha256_before=document['sha256'],snapshot=snapshot))
            dump(out/'query.json',config)
            dump(out/'rpt_groups.json',group_documents)
        audit['sha256_before']=sha(fsdb)
        native=out/'fsdb_reader'
        execute(['g++','-std=c++11','-O2','-I'+str(sdk),str(ROOT/'wave/fsdb_reader.cpp'),
                 '-L'+str(lib),'-Wl,-rpath,'+str(lib),'-lnffr','-lnsys','-ldl','-lz','-o',str(native)],out/'reader_build.log')
        guard=out/'source_guard.so'
        execute(['gcc','-shared','-fPIC','-O2',str(ROOT/'npi/source_guard.c'),'-ldl','-o',str(guard)],out/'guard_build.log')
        lines=[]
        for d in config['domains']:
            lines += ['SCOPE\t'+d['scope'],'SIGNAL\t'+d['iso_en'],'SIGNAL\t'+d['power_down']]
        for key in ('max_events','max_width','max_signals','max_value_bytes'):
            lines.append(key.upper()+'\t'+str(config['limits'][key]))
        (out/'request.tsv').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        environment=os.environ.copy()
        environment['LD_PRELOAD']=str(guard)+(':'+environment['LD_PRELOAD'] if environment.get('LD_PRELOAD') else '')
        environment['LD_LIBRARY_PATH']=str(lib)+(':'+environment['LD_LIBRARY_PATH'] if environment.get('LD_LIBRARY_PATH') else '')
        progress('extracting','只读提取所选层次的控制信号和全部已记录输出口')
        execute(['strace','-f','-s','4096','-e','trace=file,process','-o',str(out/'access.log'),
                 str(native),str(fsdb),str(out/'request.tsv'),str(out/'native.jsonl')],out/'reader.log',environment)
        access=audit_access(out/'access.log',out/'reader.log')
        access['enforcement']='FSDB Reader read API; RTL source-open guard; strace file/process audit; input SHA-256 before/after'
        audit.update(access)
        audit['sha256_after']=sha(fsdb)
        audit['input_unchanged']=audit['sha256_before']==audit['sha256_after']
        for item in audit['rpt_inputs']:
            item['sha256_after']=sha(Path(item['path']))
            item['input_unchanged']=item['sha256_before']==item['sha256_after']
        audit['passed']=audit['passed'] and audit['input_unchanged'] and all(r['input_unchanged'] for r in audit['rpt_inputs'])
        if not audit['passed']:
            raise ValueError('输入文件或读取审计不通过，不能发布检查结果。')
        progress('analyzing','按 RPT 分组检查钳 1、钳 0、不钳位及掉电全 X')
        data=load_native(out/'native.jsonl',cancelled);cancelled()
        report=analyze(config,data,cancelled,group_documents);cancelled()
        dump(out/'wave_report.json',report)
        dump(out/'wave_data.json',data)
        with (out/'checks.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.writer(stream)
            writer.writerow(['scope','cycle','signal','group','rpt_groups','expected_clamp','idle','clamp','status']+list(RULES)+['first_failure_ns'])
            for domain in report['domains']:
                for cycle in domain['cycles']:
                    for r in cycle['checks']:
                        failures=[v['time'] for v in r['checks'].values() if v['status']=='FAIL' and v['time'] is not None]
                        writer.writerow([domain['config']['scope'],cycle['index'],r['signal'],r['clamp_policy'],'; '.join(r['group_names']),r['expected_clamp'],r['idle'],r['clamp'],r['status']]+
                                        [r['checks'][k]['status'] for k in RULES]+[ns_text(min(failures),report['file']['scale']) if failures else ''])
        # Export each full requested cycle including the padding; preserve all output lanes.
        progress('reporting','生成逐端口结果、周期波形 SVG 和审计记录')
        series_cache={n:Series(s) for n,s in data['signals'].items() if s.get('selected')}
        for di,domain in enumerate(report['domains']):
            for cycle in domain['cycles']:
                cancelled()
                (out/('domain_%d_cycle_%d.svg'%(di+1,cycle['index']))).write_text(svg(scene(report,data,domain,cycle,series_cache=series_cache)),encoding='utf-8')
        audit['finished']=True
        dump(out/'manifest.json',dict(tool='RTLWire',version=__version__,kind='power_wave',
                                    sdk=str(sdk),library=str(lib),reader_source_sha256=sha(ROOT/'wave/fsdb_reader.cpp'),
                                    edge_policy='settled',source_kind='FSDB',grouping_mode=config['grouping_mode'],summary=report['summary']))
        print(json.dumps(dict(event='result',directory=str(out),summary=report['summary'])),flush=True)
        return 0
    finally:
        if not audit['finished']:audit['passed']=False
        if (out/'access.log').exists() and 'successful_rtl_source_opens' not in audit:
            audit.update(audit_access(out/'access.log',out/'reader.log'))
            audit['passed']=False
            audit['enforcement']='FSDB Reader API; RTL source-open guard; strace file/process audit'
        dump(out/'audit.json',audit)


def main():
    p=argparse.ArgumentParser(description='RTLWire FSDB isolation/power checker')
    p.add_argument('--query',required=True);p.add_argument('--out',required=True)
    p.add_argument('--verdi-home');p.add_argument('--reader-lib')
    p.add_argument('--cancel-file');p.add_argument('--progress-json',action='store_true')
    p.add_argument('--timeout',type=float,default=600)
    args=p.parse_args()
    try:
        return run(args)
    except Cancelled as exc:
        print(str(exc),file=sys.stderr);return 130
    except Exception as exc:
        print('WAVE_CHECK_ERROR: '+str(exc),file=sys.stderr);return 2


if __name__=='__main__':
    sys.exit(main())
