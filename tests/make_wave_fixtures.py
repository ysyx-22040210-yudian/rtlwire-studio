"""Generate independent, tiny, real FSDBs with the installed Verdi Writer SDK.

Run on Linux: python3 tests/make_wave_fixtures.py --out validation/wave_030/fixtures
The application never invokes this test-only writer or any RTL compiler.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent.parent
SCOPES=['tb.chip.u_a','tb.chip.u_wrap.u_b']


def make(kind, directory, writer):
    fault=kind=='faults'
    end=175000 if fault else 200000
    variables,events=[],[]
    ids={}

    def var(scope,name,direction,width):
        ident=len(variables)+1
        variables.append(['VAR',scope,name+('[%d:0]'%(width-1) if width>1 else ''),
                          '0' if kind=='no_directions' else str(direction),str(width),str(ident)])
        ids[scope+'.'+name]=ident
        return ident

    def event(t,ident,value):
        if t<=end:
            events.append([t,len(events),ident,value])

    for di,scope in enumerate(SCOPES):
        iso=var(scope,'iso_en',1,1);pd=var(scope,'power_down',1,1)
        event(0,iso,'0');event(0,pd,'1')
        periods=[(20000,35000,70000,90000),(120000,135000,160000,180000)] if di==0 else [(30000,45000,75000,100000),(130000,145000,170000,190000)]
        if fault and di==0:
            periods=periods[:1]
        for a,b,c,d in periods:
            event(a,iso,'1');event(b,pd,'0');event(c,pd,'1');event(d,iso,'0')
        names=[('ack',1),('data_out',8),('valid',1)]
        if fault and di==0:
            names=[('good',1),('idle_bad',1),('clamp_bad',1),('hold_toggle',1),('off_partial',8),('off_z',4),('recovery_bad',1),('delta_only',1)]
        for name,width in names:
            ident=var(scope,name,2,width)
            zero='0'*width;ones='1'*width;xx='x'*width
            event(0,ident,ones if name=='idle_bad' else zero)
            for a,b,c,d in periods:
                event(a,ident,ones if name=='clamp_bad' else zero)
                event(b,ident,('x'*(width-1)+'0') if name=='off_partial' else 'z'*width if name=='off_z' else xx)
                event(c,ident,ones if name=='recovery_bad' else zero)
                event(d,ident,zero)
            if name=='hold_toggle':
                event(25000,ident,ones);event(26000,ident,zero)
            if name=='delta_only' or (not fault and di==0 and name=='data_out'):
                event(25000,ident,ones);event(25000,ident,zero)
        internal=var(scope,'not_an_output',0,1);event(0,internal,'1')
        child=var(scope+'.u_child','child_output',2,1);event(0,child,'1')
    lines=['UNIT\t1ps']+['\t'.join(v) for v in variables]
    lines += ['VALUE\t%d\t%d\t%s'%(t,ident,value) for t,order,ident,value in sorted(events)]
    lines.append('TIME\t'+str(end))
    spec=directory/(kind+'.tsv');spec.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    fsdb=directory/(kind+'.fsdb')
    subprocess.run([str(writer),str(spec),str(fsdb)],check=True)
    config=dict(kind='power_wave',fsdb_path=str(fsdb),padding_ns=5,edge_policy='settled',
                domains=[dict(scope=s,iso_en='iso_en',power_down='power_down') for s in SCOPES])
    (directory/(kind+'.json')).write_text(json.dumps(config,indent=2),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True);args=parser.parse_args()
    directory=Path(args.out).resolve();directory.mkdir(parents=True,exist_ok=True)
    sdk=Path(os.environ['VERDI_HOME'])/'share/FsdbWriter';lib=sdk/'linux64'
    writer=directory/'fixture_writer'
    command=['g++','-std=c++11','-O2','-I'+str(sdk),str(ROOT/'tests/fsdb_fixture_writer.cpp'),
             '-L'+str(lib),'-Wl,-rpath,'+str(lib),'-lnffw','-ldl','-o',str(writer)]
    with (directory/'writer_build.log').open('w') as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    for kind in ('passing','faults','no_directions'):
        make(kind,directory,writer)
    print('Created 3 independent real FSDB fixtures in '+str(directory))


if __name__=='__main__':main()
