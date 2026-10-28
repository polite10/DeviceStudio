"""ADASLab scenario panel. Tk stays on the UI thread; serial stays on its worker."""
import csv
import queue
import json
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from .adas_sim import Config,Runner,SCENARIOS

class AdasPanel(ttk.Frame):
    def __init__(self,parent,studio):
        super().__init__(parent,padding=14);self.studio=studio;self.runner=None;self.active=False
        self.snapshots=queue.Queue(maxsize=2);self.history=[]
        ttk.Label(self,text='ADASLab · sanal yol, kart üzerinde kontrol',font=('Segoe UI Semibold',16)).pack(anchor='w')
        controls=ttk.Frame(self);controls.pack(fill='x',pady=8)
        self.scenario=tk.StringVar(value=SCENARIOS['brake'])
        self.scenario_input=ttk.Combobox(controls,textvariable=self.scenario,values=list(SCENARIOS.values()),state='readonly',width=24)
        self.scenario_input.pack(side='left',padx=(0,10))
        ttk.Label(controls,text='Hedef km/sa').pack(side='left')
        self.target=tk.IntVar(value=90);self.target_input=ttk.Spinbox(controls,from_=0,to=200,textvariable=self.target,width=5)
        self.target_input.pack(side='left',padx=6)
        self.acc=tk.BooleanVar(value=True);self.aeb=tk.BooleanVar(value=True);self.noise=tk.BooleanVar();self.repeat=tk.BooleanVar(value=True)
        self.settings=[]
        for label,var in [('ACC',self.acc),('AEB',self.aeb),('Gürültü',self.noise),('Tekrar',self.repeat)]:
            widget=ttk.Checkbutton(controls,text=label,variable=var);widget.pack(side='left',padx=4);self.settings.append(widget)
        row=ttk.Frame(self);row.pack(fill='x')
        self.start_button=ttk.Button(row,text='Deneyi başlat',command=self.start,state='disabled');self.start_button.pack(side='left',padx=(0,8))
        self.stop_button=ttk.Button(row,text='Duraklat',command=studio.cancel.set,state='disabled');self.stop_button.pack(side='left',padx=4)
        self.export_button=ttk.Button(row,text='CSV kaydet',command=self.export);self.export_button.pack(side='left',padx=4)
        self.summary=tk.StringVar(value='ADASLab firmware’ini yükleyip bağlanın.')
        ttk.Label(self,textvariable=self.summary,wraplength=850).pack(anchor='w',pady=9)
        self.canvas=tk.Canvas(self,height=180,bg='#101b2a',highlightthickness=0);self.canvas.pack(fill='x')
        self.canvas.bind('<Configure>',lambda event:self.draw())
        self.detail=tk.StringVar(value='Ölçümler 50 ms simülasyon adımlarıyla gönderilir; seri gecikmesi ayrı ölçülür.')
        ttk.Label(self,textvariable=self.detail,wraplength=850).pack(anchor='w',pady=8)
        self.graph=tk.Canvas(self,height=95,bg='#101b2a',highlightthickness=0);self.graph.pack(fill='x')
        self.graph.bind('<Configure>',lambda event:self.draw_graph())
        self.last=None;self.last_status_at=0.;self.status_file=Path(__file__).resolve().parents[1]/'build/adas-live.json'
        self.after(80,self.poll)
    def available(self,app,busy):
        ready=app=='ADASLab' and not busy
        self.start_button.configure(state='normal' if ready else 'disabled')
        self.stop_button.configure(state='normal' if self.active else 'disabled')
        self.scenario_input.configure(state='disabled' if busy else 'readonly')
        self.target_input.configure(state='disabled' if busy else 'normal')
        for widget in self.settings:widget.configure(state='disabled' if busy else 'normal')
        self.export_button.configure(state='disabled' if self.active else 'normal')
    def emit(self,snapshot):
        try:self.snapshots.put_nowait(snapshot)
        except queue.Full:
            try:self.snapshots.get_nowait()
            except queue.Empty:pass
            try:self.snapshots.put_nowait(snapshot)
            except queue.Full:pass
    def start(self):
        app=self.studio
        if app.busy:return
        if not app.device or not app.device.current or app.device.current.get('app')!='ADASLab':
            messagebox.showerror('ADASLab','Önce ADASLab firmware’ine bağlanın.');return
        try:
            config=Config(scenario=next(k for k,v in SCENARIOS.items() if v==self.scenario.get()),
                          target_kmh=self.target.get(),acc=self.acc.get(),aeb=self.aeb.get(),noise=self.noise.get(),repeat=self.repeat.get())
            if not 0<=config.target_kmh<=200:raise ValueError('Hedef hız 0..200 km/sa olmalı')
        except (ValueError,tk.TclError) as exc:messagebox.showerror('ADASLab',str(exc));return
        self.history=[];self.active=True
        self.runner=Runner(app.device,config,app.cancel,self.emit)
        app.work(self.runner.run,self.finished)
    def finished(self,response):
        self.active=False;self.studio.log('ADASLab deneyi duraklatıldı; CSV ölçümleri hazır.')
    def poll(self):
        latest=None
        while True:
            try:latest=self.snapshots.get_nowait()
            except queue.Empty:break
        if latest:
            self.last=latest;s=latest['response'].get('state',{})
            phase='ÇARPIŞMA' if latest['collision'] else 'VERİ KESİNTİSİ' if latest['data_pause'] else s.get('mode','')
            self.summary.set(f'{phase} · Zaman {latest["seconds"]:.1f} s · Tur {latest["cycle"]} · Biz {s.get("ego",0)*.036:.1f} km/sa · Öndeki {s.get("lead",0)*.036:.1f} km/sa · Mesafe {latest["gap"]:.1f} m')
            self.detail.set(f'İvme {s.get("a",0)/100:.2f} m/s² · RTT {latest["rtt_ms"]:.1f} ms · 50 ms aşımı {latest["overruns"]} · Kontrol en çok {s.get("us",0)} µs · GPU {s.get("gpu",0)} · Kare {s.get("frames",0)} · En uzun kare {s.get("frame_max_ms",0)} ms')
            self.history.append((latest['gap'],s.get('a',0)/100));self.history=self.history[-200:]
            self.draw();self.draw_graph()
            if time.monotonic()-self.last_status_at>=1:
                self.last_status_at=time.monotonic()
                try:
                    self.status_file.parent.mkdir(exist_ok=True)
                    self.status_file.write_text(json.dumps({'active':self.active,'backend':latest['response'].get('backend','STM32_UART'),
                        'summary':self.summary.get(),'detail':self.detail.get(),'sample':latest},ensure_ascii=False,indent=2)+'\n')
                except OSError:pass
        if self.active and not self.studio.busy:self.active=False;self.studio.enable()
        self.after(80,self.poll)
    def draw(self):
        c=self.canvas;c.delete('all');w=max(c.winfo_width(),300)
        for y in (52,126):c.create_line(15,y,w-15,y,fill='#496076',width=2)
        for x in range(10,int(w),45):c.create_line(x,89,x+20,89,fill='#65798b')
        gap=self.last['gap'] if self.last else 70.;lead_x=min(w-65,105+max(0,gap)/120*(w-180))
        c.create_rectangle(35,62,95,113,fill='#46c5bc',outline='');c.create_text(65,39,text='BİZ',fill='#d9edf0')
        c.create_rectangle(lead_x,62,lead_x+60,113,fill='#f3bc67',outline='');c.create_text(lead_x+30,39,text='ÖNDEKİ',fill='#d9edf0')
        c.create_text(w/2,151,text=f'{gap:.1f} m',fill='#d9edf0')
    def draw_graph(self):
        c=self.graph;c.delete('all');w=max(c.winfo_width(),300)
        c.create_text(12,13,anchor='w',text='Son 200 görünüm · takip mesafesi (0–120 m)',fill='#adc3d3')
        if len(self.history)>1:
            points=[]
            for i,(gap,_) in enumerate(self.history):points.extend((12+i*(w-24)/199,85-max(0,min(120,gap))/120*55))
            c.create_line(*points,fill='#46c5bc',width=2)
    def export(self):
        if not self.runner or not self.runner.rows:return
        path=filedialog.asksaveasfilename(title='ADASLab ölçümleri',defaultextension='.csv',filetypes=[('CSV','*.csv')])
        if path:
            rows=list(self.runner.rows)
            with open(path,'w',newline='',encoding='utf-8') as f:
                writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
