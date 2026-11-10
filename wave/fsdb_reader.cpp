// RTLWire FSDB reader adapter. Uses the user's installed Reader SDK.
// No HDL parser, elaboration, simulation or waveform conversion is involved.
#include "ffrAPI.h"
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

static std::string quote(const std::string &s) {
    std::ostringstream out; out << '"';
    for (unsigned char c : s) {
        if(c=='"'||c=='\\') out << '\\' << c;
        else if(c<32) { const char *hex="0123456789abcdef"; out<<"\\u00"<<hex[c>>4]<<hex[c&15]; }
        else out<<c;
    }
    return out.str()+'"';
}
template<typename T> static uint64_t ticks(const T &t) { return (uint64_t(t.H)<<32)|t.L; }
static std::string joined(const std::vector<std::string>& v) {
    std::string s; for(const auto &x:v) {if(!s.empty())s+='.';s+=x;} return s;
}
struct Signal {std::string name,scope,local;fsdbVarIdcode id;int left,right,dir,type,bpb;};
struct Context {
    std::set<std::string> scopes,wanted,found_scopes;
    std::vector<std::string> stack;
    std::map<std::string,Signal> signals;
    uint64_t max_events=2000000,max_width=65536,max_signals=10000,max_value_bytes=134217728; bool outputs=true;
    std::ofstream *out;
};
static bool_T tree(fsdbTreeCBType kind,void *client,void *data) {
    Context &c=*static_cast<Context*>(client);
    if(kind==FSDB_TREE_CBT_BEGIN_TREE) c.stack.clear();
    else if(kind==FSDB_TREE_CBT_SCOPE) {
        auto *s=static_cast<fsdbTreeCBDataScope*>(data);
        c.stack.push_back(s->name?s->name:"");
        std::string name=joined(c.stack);
        if(c.scopes.empty()||c.scopes.count(name)) {
            c.found_scopes.insert(name);
            *c.out<<"{\"record\":\"scope\",\"name\":"<<quote(name)<<",\"module\":"<<quote(s->module?s->module:"")<<"}\n";
        }
    } else if(kind==FSDB_TREE_CBT_UPSCOPE) {if(!c.stack.empty())c.stack.pop_back();}
    else if(kind==FSDB_TREE_CBT_VAR) {
        auto *v=static_cast<fsdbTreeCBDataVar*>(data);
        Signal s; s.scope=joined(c.stack);s.local=v->name?v->name:"";
        s.left=v->lbitnum;s.right=v->rbitnum;s.dir=v->direction;s.type=v->type;s.bpb=v->bytes_per_bit;s.id=v->u.idcode;
        std::string suffix="["+std::to_string(s.left)+":"+std::to_string(s.right)+"]";
        if(s.local.size()>=suffix.size() && s.local.compare(s.local.size()-suffix.size(),suffix.size(),suffix)==0) {
            s.local.resize(s.local.size()-suffix.size());while(!s.local.empty()&&s.local.back()==' ')s.local.pop_back();
        }
        s.name=s.scope.empty()?s.local:s.scope+'.'+s.local;
        if(c.scopes.empty()||c.scopes.count(s.scope)||c.wanted.count(s.name)) {
            auto old=c.signals.find(s.name);
            if(old==c.signals.end() || s.dir!=FSDB_VD_IMPLICIT || old->second.dir==FSDB_VD_IMPLICIT)c.signals[s.name]=s;
        }
    }
    return 1;
}
int main(int argc,char **argv) {
    if(argc!=4) {std::cerr<<"usage: fsdb_reader FSDB REQUEST_TSV OUTPUT_JSONL\n";return 2;}
    ffrObject *db=nullptr;
    try {
        Context c;std::ifstream request(argv[2]);if(!request)throw std::runtime_error("REQUEST_NOT_READABLE");
        std::string line;
        while(std::getline(request,line)) {
            auto p=line.find('\t');if(p==std::string::npos)continue;
            std::string key=line.substr(0,p),value=line.substr(p+1);
            if(key=="SCOPE")c.scopes.insert(value);
            else if(key=="SIGNAL")c.wanted.insert(value);
            else if(key=="OUTPUTS")c.outputs=value=="1";
            else if(key=="MAX_EVENTS")c.max_events=std::stoull(value);
            else if(key=="MAX_WIDTH")c.max_width=std::stoull(value);
            else if(key=="MAX_SIGNALS")c.max_signals=std::stoull(value);
            else if(key=="MAX_VALUE_BYTES")c.max_value_bytes=std::stoull(value);
        }
        std::ofstream out(argv[3]);if(!out)throw std::runtime_error("OUTPUT_NOT_WRITABLE");c.out=&out;
        db=ffrObject::ffrOpen3(argv[1]);if(!db)throw std::runtime_error("FSDB_OPEN_FAILED");
        if(db->ffrGetFileType()!=FSDB_FT_VERILOG)throw std::runtime_error("UNSUPPORTED_FSDB_LANGUAGE");
        fsdbTag64 lo,hi;
        if(db->ffrGetMinFsdbTag64(&lo)!=FSDB_RC_SUCCESS||db->ffrGetMaxFsdbTag64(&hi)!=FSDB_RC_SUCCESS)throw std::runtime_error("FSDB_TIME_RANGE_FAILED");
        out<<"{\"record\":\"file\",\"scale\":"<<quote(db->ffrGetScaleUnit())<<",\"begin\":"<<ticks(lo)<<",\"end\":"<<ticks(hi)<<",\"sequence_numbers\":"<<(db->ffrIsThereSeqNum()?"true":"false")<<"}\n";
        uint_T off_count=0;fsdbDumpOffRange *off=nullptr;
        if(db->ffrGetDumpOffRange(off_count,off)==FSDB_RC_SUCCESS)
            for(uint_T i=0;i<off_count;++i)out<<"{\"record\":\"dump_off\",\"begin\":"<<ticks(off[i].begin.hltag)<<",\"end\":"<<ticks(off[i].end.hltag)<<"}\n";
        if(db->ffrReadScopeVarTree2(tree,&c)!=FSDB_RC_SUCCESS)throw std::runtime_error("FSDB_SCOPE_ENUMERATION_FAILED");
        uint64_t events=0,selected=0,value_bytes=0;
        for(const auto &item:c.signals) {
            const Signal &s=item.second;
            bool load=c.wanted.count(s.name)||(c.outputs&&c.scopes.count(s.scope)&&s.dir==FSDB_VD_OUTPUT);
            out<<"{\"record\":\"signal\",\"name\":"<<quote(s.name)<<",\"scope\":"<<quote(s.scope)<<",\"local_name\":"<<quote(s.local)
               <<",\"idcode\":"<<s.id<<",\"direction\":"<<s.dir<<",\"type\":"<<s.type<<",\"left\":"<<s.left<<",\"right\":"<<s.right<<",\"selected\":"<<(load?"true":"false")<<"}\n";
            if(!load)continue;if(++selected>c.max_signals)throw std::runtime_error("FSDB_SIGNAL_LIMIT");
            db->ffrResetSignalList();
            if(db->ffrAddToSignalList(s.id)!=FSDB_RC_SUCCESS||db->ffrLoadSignals()!=FSDB_RC_SUCCESS)throw std::runtime_error("FSDB_SIGNAL_LOAD_FAILED: "+s.name);
            ffrVCTrvsHdl h=db->ffrCreateVCTraverseHandle(s.id);
            if(!h)throw std::runtime_error("FSDB_TRAVERSE_FAILED: "+s.name);
            uint_T width=h->ffrGetBitSize();
            bool supported=h->ffrGetBytesPerBit()==FSDB_BYTES_PER_BIT_1B && width>0 && width<=c.max_width && (s.type&63)!=FSDB_VT_VCD_EVENT;
            if(!supported)out<<"{\"record\":\"unsupported\",\"signal\":"<<quote(s.name)<<",\"reason\":\"UNSUPPORTED_VALUE_TYPE_OR_WIDTH\"}\n";
            else if(h->ffrGotoTheFirstVC()==FSDB_RC_SUCCESS) {
                do {
                    fsdbTag64 t;byte_T *value=nullptr;
                    if(h->ffrGetXTag(&t)!=FSDB_RC_SUCCESS||h->ffrGetVC(&value)!=FSDB_RC_SUCCESS||!value)throw std::runtime_error("FSDB_VALUE_READ_FAILED");
                    if(++events>c.max_events)throw std::runtime_error("FSDB_EVENT_LIMIT");
                    value_bytes+=width;
                    if(value_bytes>c.max_value_bytes)throw std::runtime_error("FSDB_VALUE_BYTES_LIMIT");
                    std::string bits;bits.reserve(width);
                    for(uint_T j=0;j<width;++j)bits.push_back(value[j]<=3?"01xz"[value[j]]:'?');
                    out<<"{\"record\":\"value\",\"signal\":"<<quote(s.name)<<",\"time\":"<<ticks(t)<<",\"value\":"<<quote(bits)<<"}\n";
                }while(h->ffrGotoNextVC()==FSDB_RC_SUCCESS);
            }
            h->ffrFree();db->ffrUnloadSignals();
        }
        out<<"{\"record\":\"complete\",\"signals\":"<<selected<<",\"events\":"<<events<<"}\n";
        db->ffrClose();return 0;
    }catch(const std::exception &e){std::cerr<<"FSDB_READER_ERROR: "<<e.what()<<'\n';if(db)db->ffrClose();return 2;}
}
