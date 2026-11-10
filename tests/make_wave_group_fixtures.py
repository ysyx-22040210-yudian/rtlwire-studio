"""Real FSDB + independent per-domain RPT fixtures for the three clamp policies."""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent.parent
SCOPES=['tb.chip.u_a','tb.chip.u_wrap.u_b']
KEYWORDS=[dict(clamp_one='KEEP1',clamp_zero='KEEP0',no_clamp='BYPASS'),
          dict(clamp_one='FORCE_HIGH',clamp_zero='FORCE_LOW',no_clamp='TRANSPARENT')]


def make(directory,writer,faults=False):
    variables,events=[],[]
    def var(scope,name,direction,width):
        ident=len(variables)+1
        variables.append(['VAR',scope,name+('[%d:0]'%(width-1) if width>1 else ''),str(direction),str(width),str(ident)])
        return ident
    def add(t,ident,value):events.append((t,len(events),ident,value))
    for di,scope in enumerate(SCOPES):
        a,b,c,d=(20000,35000,70000,90000) if di==0 else (30000,45000,75000,100000)
        iso=var(scope,'iso_en',1,1);pd=var(scope,'power_down',1,1)
        for t,v in [(0,'0'),(a,'1'),(d,'0')]:add(t,iso,v)
        for t,v in [(0,'1'),(b,'0'),(c,'1')]:add(t,pd,v)
        for name,width,policy in [('one_out',1,'1'),('one_bus',4,'1'),('zero_out',1,'0'),('zero_bus',4,'0'),('free_out',1,'-'),('free_bus',4,'-'),('mixed_bus',4,'10--')]:
            ident=var(scope,name,2,width)
            if policy in ('0','1'):
                base=policy*width
                initial='1' if faults and di==0 and name=='zero_out' else base
                isolated='0' if faults and di==0 and name=='one_out' else base
                restored='0010' if faults and di==0 and name=='zero_bus' else base
                for t,v in [(0,initial),(a,isolated),(b,'x'*width),(c,restored),(d,base)]:add(t,ident,v)
                if di==0 and name=='one_bus':
                    add(a+5000,ident,'1101' if faults else '0000')
                    add(a+(6000 if faults else 5000),ident,'1111')
            elif name=='free_out':
                for t,v in [(0,'0'),(a,'1'),(a+3000,'0'),(a+8000,'1'),(b,'0' if faults and di==0 else 'x'),(c,'0'),(c+4000,'1'),(c+8000,'0')]:add(t,ident,v)
            elif name=='free_bus':
                for t,v in [(0,'0010'),(a,'1000'),(a+3000,'0110'),(a+8000,'0111'),(b,'xxxx'),(c,'1001'),(c+5000,'0011')]:add(t,ident,v)
            else:
                for t,v in [(0,'1000'),(a,'1011'),(a+5000,'1001'),(b,'xx0x' if faults and di==0 else 'xxxx'),(c,'1010'),(c+6000,'1011')]:add(t,ident,v)
        internal=var(scope,'not_an_output',0,1);add(0,internal,'1')
    stem='group_faults' if faults else 'group_pass'
    text=['UNIT\t1ps']+['\t'.join(v) for v in variables]+['VALUE\t%d\t%d\t%s'%(t,i,v) for t,order,i,v in sorted(events)]+['TIME\t110000']
    spec=directory/(stem+'.tsv');spec.write_text('\n'.join(text)+'\n',encoding='utf-8')
    subprocess.run([str(writer),str(spec),str(directory/(stem+'.fsdb'))],check=True)
    config=dict(kind='power_wave',grouping_mode='rpt',fsdb_path=str(directory/(stem+'.fsdb')),padding_ns=5,edge_policy='settled',domains=[])
    for i,scope in enumerate(SCOPES):
        config['domains'].append(dict(scope=scope,iso_en='iso_en',power_down='power_down',
                                     rpt_path=str(directory/('domain_%d.rpt'%(i+1))),group_keywords=KEYWORDS[i]))
    (directory/(stem+'.json')).write_text(json.dumps(config,indent=2),encoding='utf-8')
    return config


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);args=p.parse_args()
    directory=Path(args.out).resolve();directory.mkdir(parents=True,exist_ok=True)
    sdk=Path(os.environ['VERDI_HOME'])/'share/FsdbWriter';lib=sdk/'linux64';writer=directory/'fixture_writer'
    with (directory/'writer_build.log').open('w') as log:
        subprocess.run(['g++','-std=c++11','-O2','-I'+str(sdk),str(ROOT/'tests/fsdb_fixture_writer.cpp'),'-L'+str(lib),'-Wl,-rpath,'+str(lib),'-lnffw','-ldl','-o',str(writer)],stdout=log,stderr=subprocess.STDOUT,check=True)
    for i in range(2):
        keys=KEYWORDS[i];prefix='ALPHA_' if i==0 else 'BETA_'
        text='# Independent RPT fixture, user-selected keywords\n'
        text+=prefix+keys['clamp_one']+' { one_out，one_bus, mixed_bus[3] }\n'
        text+=prefix+keys['clamp_zero']+' {\n zero_out, zero_bus[3:0], mixed_bus[2]\n}\n'
        text+=prefix+keys['no_clamp']+' { free_out, free_bus, mixed_bus[1:0] }\n'
        (directory/('domain_%d.rpt'%(i+1))).write_text(text,encoding='utf-8')
    passing=make(directory,writer);make(directory,writer,True)
    bad=(directory/'domain_1.rpt').read_text(encoding='utf-8').replace('zero_bus[3:0],','').replace('zero_out,','zero_out, one_out, missing_port,')
    (directory/'bad_members.rpt').write_text(bad,encoding='utf-8')
    passing['domains'][0]['rpt_path']=str(directory/'bad_members.rpt')
    (directory/'group_unknown.json').write_text(json.dumps(passing,indent=2),encoding='utf-8')
    print('Created three-policy FSDB/RPT fixtures in '+str(directory))


if __name__=='__main__':main()
