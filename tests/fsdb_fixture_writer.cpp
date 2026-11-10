// Independent test-data generator, never used by the application.
#include "ffwAPI.h"
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
static std::vector<std::string> split(const std::string&s,char delimiter) {
    std::vector<std::string> result;std::istringstream stream(s);std::string item;
    while(std::getline(stream,item,delimiter))result.push_back(item);return result;
}
int main(int argc,char **argv) {
    if(argc!=3)return 2;
    try {
        std::ifstream in(argv[1]);std::string line;
        std::vector<std::vector<std::string>> vars,events;std::string unit="1ps";
        while(std::getline(in,line)) {
            auto f=split(line,'\t');if(f.empty())continue;
            if(f[0]=="UNIT")unit=f.at(1);
            else if(f[0]=="VAR")vars.push_back(f);
            else if(f[0]=="VALUE"||f[0]=="TIME")events.push_back(f);
        }
        ffwObject *db=ffw_Open(argv[2],FSDB_FT_VERILOG);if(!db)throw std::runtime_error("writer open failed");
        ffw_CreateTreeByIdcodeScheme(db);ffw_SetScaleUnit(db,const_cast<char*>(unit.c_str()));ffw_SetGlitchNum(db,128);ffw_BeginTree(db);
        std::vector<std::string> current;
        for(const auto &v:vars) {
            auto wanted=split(v.at(1),'.');size_t common=0;
            while(common<current.size()&&common<wanted.size()&&current[common]==wanted[common])++common;
            for(size_t i=current.size();i>common;--i)ffw_CreateUpscope(db);
            for(size_t i=common;i<wanted.size();++i)ffw_CreateScope(db,FSDB_ST_VCD_MODULE,const_cast<char*>(wanted[i].c_str()));
            current=wanted;int width=std::stoi(v.at(4));
            fsdbVarIdcode id=std::stoul(v.at(5));
            auto made=ffw_CreateVarByIdcode(db,FSDB_VT_VCD_WIRE,static_cast<fsdbVarDir>(std::stoi(v.at(3))),
                  FSDB_DT_HANDLE_VERILOG_STANDARD,width-1,0,id,const_cast<char*>(v.at(2).c_str()),FSDB_BYTES_PER_BIT_1B);
            if(made!=id)throw std::runtime_error("variable creation failed");
        }
        for(size_t i=0;i<current.size();++i)ffw_CreateUpscope(db);
        ffw_EndTree(db);
        for(const auto &event:events) {
            unsigned long long t=std::stoull(event.at(1));ffw_CreateXCoorByHnL(db,t>>32,t&0xffffffffu);
            if(event[0]=="TIME")continue;
            std::vector<byte_T> value;
            for(char b:event.at(3))value.push_back(b=='0'?0:b=='1'?1:b=='x'?2:3);
            ffw_CreateVarValueByIdcode(db,std::stoul(event.at(2)),value.data());
        }
        ffw_Close(db);ffw_Destroy(db);return 0;
    }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}
}
