#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/godot.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>
#include <godot_cpp/variant/packed_string_array.hpp>
#include <algorithm>
#include <string>
#include <cerrno>
#include <cstring>
#ifdef _WIN32
#include <windows.h>
#else
#include <dirent.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <termios.h>
#include <unistd.h>
#endif
using namespace godot;
class NativeSerial : public RefCounted {
    GDCLASS(NativeSerial, RefCounted)
#ifdef _WIN32
    HANDLE handle=INVALID_HANDLE_VALUE;
#else
    int handle=-1;
#endif
    String last_error;
protected:
    static void _bind_methods() {
        ClassDB::bind_static_method("NativeSerial",D_METHOD("ports"),&NativeSerial::ports);
        ClassDB::bind_method(D_METHOD("open_port","path"),&NativeSerial::open_port);
        ClassDB::bind_method(D_METHOD("write_bytes","bytes"),&NativeSerial::write_bytes);
        ClassDB::bind_method(D_METHOD("read_bytes","timeout_ms"),&NativeSerial::read_bytes);
        ClassDB::bind_method(D_METHOD("close_port"),&NativeSerial::close_port);
        ClassDB::bind_method(D_METHOD("get_error"),&NativeSerial::get_error);
    }
public:
    ~NativeSerial() { close_port(); }
    String get_error() const { return last_error; }
    static PackedStringArray ports() {
        PackedStringArray result;
#ifdef _WIN32
        for(int i=1;i<=256;i++) { wchar_t target[1024]; std::wstring name=L"COM"+std::to_wstring(i); if(QueryDosDeviceW(name.c_str(),target,1024))result.append(String("COM")+String::num_int64(i)); }
#else
        DIR *directory=opendir("/dev");
        if(directory) {
            while(auto *entry=readdir(directory)) {
                String name=String::utf8(entry->d_name);
#ifdef __APPLE__
                bool matches=name.begins_with("cu.usbmodem")||name.begins_with("cu.usbserial");
#else
                bool matches=name.begins_with("ttyACM")||name.begins_with("ttyUSB");
#endif
                if(matches)result.append(String("/dev/")+name);
            }
            closedir(directory);
        }
#endif
        result.sort();return result;
    }
    bool open_port(String path) {
        close_port();last_error="";
#ifdef _WIN32
        std::wstring wide; auto text=(String("\\\\.\\")+path).utf16(); for(int64_t i=0;i<text.length();i++)wide.push_back((wchar_t)text[i]);
        handle=CreateFileW(wide.c_str(),GENERIC_READ|GENERIC_WRITE,0,nullptr,OPEN_EXISTING,0,nullptr);
        if(handle==INVALID_HANDLE_VALUE) { last_error="Seri port acilamadi";return false; }
        DCB config={};config.DCBlength=sizeof(config);GetCommState(handle,&config);
        config.BaudRate=115200;config.ByteSize=8;config.Parity=NOPARITY;config.StopBits=ONESTOPBIT;config.fDtrControl=DTR_CONTROL_ENABLE;config.fRtsControl=RTS_CONTROL_DISABLE;config.fOutxCtsFlow=false;config.fOutxDsrFlow=false;config.fOutX=false;config.fInX=false;
        if(!SetCommState(handle,&config)) { last_error="Seri port ayari uygulanamadi";close_port();return false; }
        COMMTIMEOUTS timeout={};timeout.ReadIntervalTimeout=MAXDWORD;timeout.WriteTotalTimeoutConstant=300;SetCommTimeouts(handle,&timeout);PurgeComm(handle,PURGE_RXCLEAR|PURGE_TXCLEAR);
#else
        handle=::open(path.utf8().get_data(),O_RDWR|O_NOCTTY|O_NONBLOCK);
        if(handle<0) { last_error=String::utf8(strerror(errno));return false; }
        if(ioctl(handle,TIOCEXCL)<0) { last_error="Seri port baska uygulamada acik";close_port();return false; }
        termios config={};
        if(tcgetattr(handle,&config)<0) { last_error=String::utf8(strerror(errno));close_port();return false; }
        cfmakeraw(&config);cfsetispeed(&config,B115200);cfsetospeed(&config,B115200);
        config.c_cflag|=(CLOCAL|CREAD);config.c_cflag&=~(PARENB|CSTOPB|CSIZE|CRTSCTS);config.c_cflag|=CS8;
        config.c_cc[VMIN]=0;config.c_cc[VTIME]=0;
        if(tcsetattr(handle,TCSANOW,&config)<0) { last_error=String::utf8(strerror(errno));close_port();return false; }
        tcflush(handle,TCIOFLUSH);
#endif
        return true;
    }
    int64_t write_bytes(PackedByteArray bytes) {
#ifdef _WIN32
        if(handle==INVALID_HANDLE_VALUE)return -1;DWORD written=0;
        if(!WriteFile(handle,bytes.ptr(),(DWORD)bytes.size(),&written,nullptr)) { last_error="Seri port yazma hatasi";return -1; }return written;
#else
        if(handle<0)return -1;
        ssize_t count=::write(handle,bytes.ptr(),bytes.size());
        if(count<0)last_error=String::utf8(strerror(errno));return count;
#endif
    }
    PackedByteArray read_bytes(int timeout_ms) {
        PackedByteArray result;uint8_t buffer[2048];
#ifdef _WIN32
        if(handle==INVALID_HANDLE_VALUE)return result;
        DWORD count=0;COMSTAT stat={};DWORD errors=0;
        for(int elapsed=0;elapsed<=timeout_ms;elapsed+=2) {
            if(!ClearCommError(handle,&errors,&stat)) { last_error="Seri port baglantisi kesildi";return result; }
            if(stat.cbInQue) { if(!ReadFile(handle,buffer,std::min<DWORD>(stat.cbInQue,2048),&count,nullptr))last_error="Seri port okuma hatasi";break; }
            Sleep(2);
        }
#else
        if(handle<0)return result;
        fd_set set;FD_ZERO(&set);FD_SET(handle,&set);
        timeout_ms=std::max(0,std::min(timeout_ms,500));timeval timeout={timeout_ms/1000,(timeout_ms%1000)*1000};
        int ready=select(handle+1,&set,nullptr,nullptr,&timeout);
        if(ready<0) { if(errno!=EINTR)last_error=String::utf8(strerror(errno));return result; }
        if(!ready)return result;
        ssize_t count=::read(handle,buffer,sizeof(buffer));
        if(count<=0) { if(count==0)last_error="Seri port baglantisi kesildi";else if(errno!=EAGAIN&&errno!=EINTR)last_error=String::utf8(strerror(errno));return result; }
#endif
        if(count>0) { result.resize(count);memcpy(result.ptrw(),buffer,count); }
        return result;
    }
    void close_port() {
#ifdef _WIN32
        if(handle!=INVALID_HANDLE_VALUE) { CloseHandle(handle);handle=INVALID_HANDLE_VALUE; }
#else
        if(handle>=0) { ioctl(handle,TIOCNXCL);::close(handle);handle=-1; }
#endif
    }
};
void initialize_serial(ModuleInitializationLevel level) { if(level==MODULE_INITIALIZATION_LEVEL_SCENE)ClassDB::register_class<NativeSerial>(); }
void terminate_serial(ModuleInitializationLevel) {}
extern "C" GDExtensionBool GDE_EXPORT adas_serial_library_init(GDExtensionInterfaceGetProcAddress get_proc_address,GDExtensionClassLibraryPtr library,GDExtensionInitialization *initialization) {
    GDExtensionBinding::InitObject init(get_proc_address,library,initialization);
    init.register_initializer(initialize_serial);init.register_terminator(terminate_serial);init.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE);return init.init();
}
