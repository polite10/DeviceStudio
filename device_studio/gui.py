import queue
import json
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import serial.tools.list_ports
from .connection import Device
from .protocol import Firmware
from . import programmer
from .adas_ui import AdasPanel

ROOT=Path(__file__).resolve().parents[1]

class Studio:
    def __init__(self,root,auto_adas=False,arm_sim=False):
        self.auto_adas=auto_adas;self.arm_sim=arm_sim
        self.root=root;self.device=None;self.firmware=None;self.busy=False
        self.events=queue.Queue();self.cancel=threading.Event();self.buttons=[];self.control_buttons=[];self.app_buttons=[]
        root.title('Device Studio — Firmware ve uygulama kontrolü');root.geometry('1030x760');root.minsize(900,700)
        root.configure(bg='#101827')
        style=ttk.Style(root);style.theme_use('clam')
        style.configure('.',font=('Segoe UI',10),background='#172337',foreground='#e8eef6')
        style.configure('TFrame',background='#101827');style.configure('Card.TFrame',background='#172337')
        style.configure('TLabel',background='#101827',foreground='#e8eef6')
        style.configure('Muted.TLabel',foreground='#9db0c8')
        style.configure('Title.TLabel',font=('Segoe UI Semibold',25))
        style.configure('TButton',padding=(16,10),background='#263d58',foreground='#f1f5fb')
        style.map('TButton',background=[('active','#36577a'),('disabled','#182539')],foreground=[('disabled','#63748a')])
        style.configure('TNotebook',background='#101827',borderwidth=0)
        style.configure('TNotebook.Tab',padding=(20,11),background='#172337')
        style.map('TNotebook.Tab',background=[('selected','#275469')])
        style.configure('Horizontal.TProgressbar',background='#52c9b5',troughcolor='#23354b')
        frame=ttk.Frame(root,padding=26);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Device Studio',style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame,text='Firmware yükleyin. Cihazı tanıyın. Uygulamanızı kontrol edin.',style='Muted.TLabel').pack(anchor='w',pady=(2,18))
        row=ttk.Frame(frame);row.pack(fill='x')
        self.port=tk.StringVar();self.ports=ttk.Combobox(row,textvariable=self.port,width=38,state='readonly');self.ports.pack(side='left',padx=(0,8))
        self.button(row,'Yenile',self.refresh).pack(side='left',padx=4)
        self.button(row,'Bağlan',self.connect).pack(side='left',padx=4)
        self.button(row,'Bağlantıyı kes',self.disconnect).pack(side='left',padx=4)
        self.boot_text=tk.StringVar(value='Bootloader: henüz tespit edilmedi')
        self.app_text=tk.StringVar(value='Çalışan uygulama: bağlantı bekleniyor')
        self.state_text=tk.StringVar(value='')
        self.app_state_text=tk.StringVar(value='Cihaz bağlantısı bekleniyor')
        ttk.Label(frame,textvariable=self.boot_text).pack(anchor='w',pady=(18,5))
        ttk.Label(frame,textvariable=self.app_text,style='Muted.TLabel').pack(anchor='w')
        self.tabs=ttk.Notebook(frame);self.tabs.pack(fill='both',expand=True,pady=(18,12))
        load=ttk.Frame(self.tabs,padding=20);control=ttk.Frame(self.tabs,padding=20)
        self.tabs.add(load,text='Firmware yükleme');self.tabs.add(control,text='Düello kontrolü')
        generic=ttk.Frame(self.tabs,padding=20);self.tabs.add(generic,text='Uygulama kontrolü')
        self.adas_panel=AdasPanel(self.tabs,self);self.tabs.add(self.adas_panel,text='ADASLab')
        ttk.Label(load,text='Uygulama firmware’i',font=('Segoe UI Semibold',15)).pack(anchor='w')
        ttk.Label(load,text='Uyumlu bir .dfw paketi seçin. Seçilen uygulama cihazdaki önceki uygulamanın yerini alır.',wraplength=820,style='Muted.TLabel').pack(anchor='w',pady=8)
        self.package_text=tk.StringVar(value='Henüz .dfw paketi seçilmedi')
        ttk.Label(load,textvariable=self.package_text,wraplength=800).pack(anchor='w',pady=12)
        actions=ttk.Frame(load);actions.pack(fill='x')
        self.button(actions,'Firmware seç',self.choose).pack(side='left',padx=(0,8))
        self.button(actions,'Yükle ve başlat',self.upload).pack(side='left',padx=4)
        self.cancel_button=ttk.Button(actions,text='İptal',command=self.cancel.set,state='disabled');self.cancel_button.pack(side='left',padx=4)
        self.progress=ttk.Progressbar(load,maximum=100);self.progress.pack(fill='x',pady=(20,6))
        self.progress_text=tk.StringVar(value='Yüklemeye hazır')
        ttk.Label(load,textvariable=self.progress_text,wraplength=810).pack(anchor='w')
        ttk.Separator(load).pack(fill='x',pady=20)
        ttk.Label(load,text='Bootloader yönetimi',font=('Segoe UI Semibold',15)).pack(anchor='w')
        tools=ttk.Frame(load);tools.pack(fill='x',pady=10)
        self.button(tools,'ST-LINK ile kontrol et',self.inspect).pack(side='left',padx=(0,8))
        self.button(tools,'DeviceBoot kur',self.install).pack(side='left',padx=4)
        self.button(tools,'Bootloader moduna geç',self.enter_boot).pack(side='left',padx=4)
        self.button(tools,'Mevcut uygulamayı başlat',self.run_app).pack(side='left',padx=4)
        ttk.Label(load,text='Kurtarma: USER butonunu basılı tutarak kartı yeniden başlatın. İlk DeviceBoot kurulumu tam Flash yedeği alır.',wraplength=800,style='Muted.TLabel').pack(anchor='w',pady=5)
        ttk.Label(control,text='Düello',font=('Segoe UI Semibold',20)).pack(anchor='w')
        ttk.Label(control,text='Karakter ve hedef saat ekranında görünür. Komutlar USB üzerinden gönderilir.',style='Muted.TLabel').pack(anchor='w',pady=8)
        grid=ttk.Frame(control);grid.pack(anchor='w',pady=18)
        for i,(label,cmd) in enumerate([('Silahı çıkar','DRAW'),('Ateş et','FIRE'),('Silahı yerine koy','HOLSTER'),('Yeniden doldur','RELOAD'),('Yürü','WALK'),('Dur','STOP'),('Sahneyi sıfırla','RESET')]):
            b=ttk.Button(grid,text=label,command=lambda c=cmd:self.command(c),state='disabled')
            b.grid(row=i//3,column=i%3,padx=5,pady=6,sticky='ew');self.control_buttons.append(b)
        ttk.Label(control,textvariable=self.state_text,wraplength=800,font=('Segoe UI',12)).pack(anchor='w',pady=10)
        ttk.Label(control,text='Silah belden çıkarılır. Animasyon sürerken firmware yeni eyleme “meşgul” cevabı verebilir.',wraplength=800,style='Muted.TLabel').pack(anchor='w',pady=10)
        ttk.Label(generic,text='Uygulama kontrolü',font=('Segoe UI Semibold',20)).pack(anchor='w')
        ttk.Label(generic,text='Firmware’in desteklediği komutu girin. Durum otomatik güncellenir.',style='Muted.TLabel').pack(anchor='w',pady=8)
        command_row=ttk.Frame(generic);command_row.pack(fill='x',pady=10)
        self.command_text=tk.StringVar()
        self.command_entry=ttk.Entry(command_row,textvariable=self.command_text,width=42,state='disabled');self.command_entry.pack(side='left',padx=(0,8))
        self.command_entry.bind('<Return>',lambda event:self.send_app_command())
        for label,callback in [('Gönder',self.send_app_command),('Durumu sorgula',lambda:self.command('STATUS'))]:
            b=ttk.Button(command_row,text=label,command=callback,state='disabled');b.pack(side='left',padx=4);self.app_buttons.append(b)
        ttk.Label(generic,textvariable=self.app_state_text,wraplength=800,font=('Consolas',11)).pack(anchor='w',pady=12)
        self.log_widget=tk.Text(frame,height=6,bg='#0b1220',fg='#91b6cc',insertbackground='white',relief='flat',font=('Consolas',9),state='disabled')
        self.log_widget.pack(fill='x')
        self.refresh();root.protocol('WM_DELETE_WINDOW',self.close)
        if self.arm_sim:root.title('Device Studio — ADASLab ARM simülasyonu · fiziksel kart kullanılmıyor')
        root.after(80,self.poll);root.after(1200,self.heartbeat)
    def button(self,parent,text,command):
        b=ttk.Button(parent,text=text,command=command);self.buttons.append(b);return b
    def log(self,text):
        self.log_widget.configure(state='normal');self.log_widget.insert('end',str(text)+'\n');self.log_widget.see('end');self.log_widget.configure(state='disabled')
    def refresh(self):
        ports=list(serial.tools.list_ports.comports());self.port_map={f'{p.device} — {p.description}':p.device for p in ports}
        self.ports['values']=list(self.port_map)
        preferred=next((label for label in self.port_map if 'STLINK' in label.upper().replace('-','')),next(iter(self.port_map),''))
        if self.port.get() not in self.port_map:self.port.set(preferred)
    def work(self,fn,success=None):
        if self.busy:return
        self.busy=True;self.cancel.clear()
        for b in self.buttons+self.control_buttons+self.app_buttons:b.configure(state='disabled')
        self.command_entry.configure(state='disabled')
        self.adas_panel.available(None,True)
        def task():
            try:self.events.put(('done',fn(),success))
            except Exception as exc:self.events.put(('error',str(exc),None))
        threading.Thread(target=task,daemon=True).start()
    def update(self,response):
        app=response.get('app','Bilinmiyor')
        if app=='DeviceBoot':
            self.boot_text.set(f'Bootloader: DeviceBoot v{response.get("version")} kurulu ve çalışıyor')
            self.app_text.set('Uygulama: '+('geçerli firmware var' if response.get('valid') else 'yükleme / kurtarma bekleniyor'))
            self.app_state_text.set('Bootloader modunda; uygulama başlatılmayı bekliyor')
        else:
            self.boot_text.set(f'Bootloader: DeviceBoot v{response.get("boot_version",1)} kurulu' if response.get('boot')==1 else 'Bootloader: tanınan DeviceBoot bulunamadı')
            source='ARM simülasyonu · fiziksel kart kullanılmıyor' if response.get('backend')=='ARM_SIM' else 'hazır'
            self.app_text.set(f'Çalışan uygulama: {app} v{response.get("version")} — {source}')
            self.app_state_text.set(json.dumps(response.get('state',{}),ensure_ascii=False,indent=2))
            if app=='Duello':
                s=response.get('state',{});gun={'drawn':'çıkarılmış','holstered':'yerinde'}.get(s.get('gun'),s.get('gun',''))
                action={'idle':'hazır','draw':'silah çıkarılıyor','holster':'silah yerine konuyor','fire':'ateş animasyonu','reload':'yeniden dolduruluyor'}.get(s.get('action'),s.get('action',''))
                self.state_text.set(f'Silah: {gun}  |  Eylem: {action}  |  Mermi: {s.get("ammo",0)} / 6  |  Hedef: {s.get("target_hp",0)} / 3')
                if s.get('error'):self.log('Cihaz: '+s['error'])
    def enable(self):
        for b in self.buttons:b.configure(state='normal')
        app=self.device.current.get('app') if self.device and self.device.current else None
        for b in self.control_buttons:b.configure(state='normal' if app=='Duello' else 'disabled')
        state='normal' if app and app!='DeviceBoot' else 'disabled'
        for b in self.app_buttons:b.configure(state=state)
        self.command_entry.configure(state=state)
        self.cancel_button.configure(state='disabled')
        self.adas_panel.available(app,self.busy)
    def connect(self):
        port=self.port_map.get(self.port.get())
        if not port and not self.arm_sim:messagebox.showerror('Bağlantı','Bir seri port seçin');return
        def fn():
            if self.device:self.device.close()
            if self.arm_sim:
                from .adas_arm import ArmDevice
                self.device=ArmDevice()
            else:self.device=Device(port)
            try:return self.device.detect()
            except Exception:
                self.device.close();self.device=None;raise
        def connected(response):
            self.log('Cihaz bağlantısı doğrulandı')
            if response.get('app')=='ADASLab':
                self.tabs.select(3)
                if self.auto_adas:self.root.after(200,self.adas_panel.start)
        self.work(fn,connected)
    def disconnect(self):
        if self.busy:return
        if self.device:self.device.close();self.device=None
        self.state_text.set('');self.app_state_text.set('Cihaz bağlantısı bekleniyor')
        self.app_text.set('Çalışan uygulama: bağlantı kesildi');self.boot_text.set('Bootloader: bağlantı olmadan durumu güncellenemiyor');self.enable()
    def choose(self):
        path=filedialog.askopenfilename(title='Firmware paketi seç',filetypes=[('Device firmware','.dfw')],initialdir=ROOT/'Firmware')
        if path:
            try:
                self.firmware=Firmware.load(path);m=self.firmware.manifest
                self.package_text.set(f'{m["name"]} v{m["version"]} · ID {m["id"]} · {m["size"]:,} bayt · {Path(path).name}')
            except Exception as exc:messagebox.showerror('Firmware',str(exc))
    def required(self):
        if not self.device:messagebox.showerror('Bağlantı','Önce cihaza bağlanın');return False
        return True
    def upload(self):
        if not self.required():return
        if not self.firmware:messagebox.showerror('Firmware','Önce bir .dfw paketi seçin');return
        if not messagebox.askyesno('Firmware yükleme',f'{self.firmware.manifest["name"]} yüklenecek. Cihazdaki mevcut uygulamanın yerini alacak. Devam edilsin mi?'):return
        self.work(lambda:self.device.upload(self.firmware,lambda p,s:self.events.put(('progress',(p,s),None)),self.cancel),self.upload_done)
        self.cancel_button.configure(state='normal')
    def upload_done(self,response):
        self.log('Firmware başarıyla yüklendi ve uygulama açıldı.')
        if response.get('app')=='Duello':self.tabs.select(1)
        elif response.get('app')=='ADASLab':self.tabs.select(3)
        elif response.get('app')=='Smartwatch':self.tabs.select(0)
        else:self.tabs.select(2)
    def send_app_command(self):
        if self.busy:return
        cmd=self.command_text.get().strip()
        if not cmd or len(cmd)>39 or any(ord(c)<=32 or ord(c)>126 for c in cmd):
            messagebox.showerror('Komut','Komut boşluksuz 1–39 yazdırılabilir ASCII karakter içermeli.');return
        self.command(cmd)
    def command(self,cmd):
        if self.required():self.work(lambda:self.device.runtime(cmd))
    def enter_boot(self):
        if self.required():self.work(self.device.enter_boot)
    def run_app(self):
        if self.required():self.work(self.device.run,self.upload_done)
    def inspect(self):
        def success(r):
            self.boot_text.set(f'Bootloader: DeviceBoot v{r["version"]} Flash üzerinde bulundu' if r['installed'] else 'Bootloader: Flash üzerinde tanınan DeviceBoot yok')
        self.work(lambda:programmer.inspect(log=lambda s:self.events.put(('log',s,None))),success)
    def install(self):
        path=filedialog.askopenfilename(title='DeviceBoot.bin seç',filetypes=[('Bootloader binary','.bin')],initialdir=ROOT.parent/'DeviceBoot'/'Firmware')
        if not path:return
        if not messagebox.askyesno('İlk bootloader kurulumu','Önce tam Flash yedeği alınacak, ardından DeviceBoot kurulacak. Eski adrese derlenmiş firmware, uyumlu paket yüklenene kadar çalışmayacak. Devam edilsin mi?'):return
        self.disconnect()
        def success(r):self.boot_text.set(f'Bootloader: DeviceBoot v{r["version"]} kuruldu');self.log('Geri dönüş yedeği: '+r['backup'])
        self.work(lambda:programmer.install(path,ROOT/'Backup',log=lambda s:self.events.put(('log',s,None))),success)
    def heartbeat(self):
        if self.device and not self.busy and self.device.current and self.device.current.get('app')!='DeviceBoot':
            self.work(lambda:self.device.runtime('STATUS'))
        self.root.after(1200,self.heartbeat)
    def poll(self):
        while True:
            try:kind,value,callback=self.events.get_nowait()
            except queue.Empty:break
            if kind=='progress':self.progress['value']=value[0];self.progress_text.set(value[1])
            elif kind=='log':self.log(value)
            else:
                self.busy=False
                if kind=='error':
                    self.log('Hata: '+value);self.progress_text.set(value)
                    if self.device:self.device.current=None
                    self.app_text.set('Uygulama durumu tespit edilemedi; yeniden bağlanın')
                elif isinstance(value,dict) and value.get('app'):self.update(value)
                if kind=='done' and callback:callback(value)
                self.enable()
        self.root.after(80,self.poll)
    def close(self):
        if self.busy:
            self.log('İşlem sürüyor. Yüklemeyi iptal edip tamamlanmasını bekleyin.');return
        self.disconnect();self.root.destroy()

def main(auto_connect=False,auto_adas=False,arm_sim=False):
    root=tk.Tk();app=Studio(root,auto_adas=auto_adas,arm_sim=arm_sim)
    if auto_connect:root.after(350,app.connect)
    root.mainloop()
