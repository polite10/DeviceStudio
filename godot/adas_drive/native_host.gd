extends RefCounted
## Direct USB ownership in one worker. No Studio, Python, TCP or PC ADAS settings.
const World=preload("res://native_world.gd")
var lock:=Mutex.new()
var thread:=Thread.new()
var snapshot:Dictionary={"connected":false,"ready":false,"running":false,"status":"ready","hint":"Saati USB ile bağlayın.","mode":"active","accEnabled":false,"targetKmh":90,"headwayMs":1800,"seed":42,"elapsed":0.0,"remaining":120.0,"egoLane":1.0,"traffic":[]}
var focused:=false
var main_tick:=0
var stop_requested:=false
var pause_requested:=false
var restart_requested:=false
var reconnect_requested:=false
var selected_port:=""
var held:Dictionary={}
var lanes:Array[int]=[]
var qa_enabled:=false
var qa_commands:Array[String]=[]
# Worker-only fields below.
var serial:RefCounted
var buffer:=""
var sequence:=0
var error_text:=""
var world:RefCounted
var panel:Dictionary={}
var settings:Dictionary={"mode":0,"acc":false,"target":2500,"headway":1800,"seed":42}
var running:=false
var current_port:=""
var last_control:Dictionary={}
var available_ports:PackedStringArray=[]
func start(port:String="",qa:bool=false)->void:
	selected_port=port;qa_enabled=qa;main_tick=Time.get_ticks_msec();thread.start(_work)
func stop()->void:
	lock.lock();stop_requested=true;held.clear();lanes.clear();lock.unlock()
	if thread.is_started():thread.wait_to_finish()
func heartbeat(active:bool)->void:
	lock.lock();focused=active;main_tick=Time.get_ticks_msec()
	if not active:pause_requested=true;held.clear();lanes.clear()
	lock.unlock()
func key_event(key:String,pressed:bool,repeated:bool=false)->void:
	if repeated:return
	lock.lock()
	if pressed:
		if not held.has(key) and key in ["a","left","d","right"] and lanes.size()<4:lanes.append(-1 if key in ["a","left"] else 1)
		held[key]=true
	else:held.erase(key)
	lock.unlock()
func pause()->void:
	lock.lock();pause_requested=true;held.clear();lanes.clear();lock.unlock()
func restart()->void:
	lock.lock();restart_requested=true;pause_requested=true;held.clear();lanes.clear();lock.unlock()
func reconnect(port:String="")->void:
	lock.lock();selected_port=port;reconnect_requested=true;held.clear();lanes.clear();lock.unlock()
func qa_panel(mode:int,acc:bool=false,target:int=2500,headway:int=1800)->void:
	if not qa_enabled:return
	lock.lock();qa_commands.append("G:%d:%d:%d:%d"%[mode,int(acc),target,headway]);lock.unlock()
func qa_start()->void:
	if not qa_enabled:return
	lock.lock();qa_commands.append("H:1");lock.unlock()
func get_snapshot()->Dictionary:
	lock.lock();var copy=snapshot.duplicate(true);lock.unlock();return copy
func _commands()->Dictionary:
	lock.lock()
	var value={"stop":stop_requested,"focus":focused and Time.get_ticks_msec()-main_tick<350,"pause":pause_requested,"restart":restart_requested,"reconnect":reconnect_requested,"port":selected_port,"qa":qa_commands.duplicate(),"gas":held.has("w") or held.has("up"),"brake":held.has("s") or held.has("down"),"lane":lanes.pop_front() if not lanes.is_empty() else 0}
	pause_requested=false;restart_requested=false;reconnect_requested=false;qa_commands.clear();lock.unlock();return value
func _publish(connected:bool,hint:String="")->void:
	var value:Dictionary=world.snapshot(last_control) if world!=null else {"elapsed":0.0,"remaining":120.0,"egoKmh":0.0,"egoLane":1.0,"traffic":[],"status":"ready"}
	var names:Array[String]=["active","warn","off"]
	value.merge({"connected":connected,"ready":connected,"running":running,"status":"running" if running else "collision" if world!=null and world.collision else "finished" if world!=null and world.finished() else "paused" if world!=null else "ready","hint":hint,"mode":names[clampi(int(settings.mode),0,2)],"accEnabled":bool(settings.acc),"targetKmh":roundi(float(settings.target)*0.036),"headwayMs":int(settings.headway),"seed":42,"devicePanel":connected,"port":current_port,"ports":available_ports,"mcuOutput":last_control.duplicate(true)},true)
	lock.lock();snapshot=value;lock.unlock()
func _request(command:String,timeout:int=450)->Dictionary:
	if command.length()>39:error_text="Komut sınırı aşıldı";return {}
	sequence=(sequence+1)&0x7fffffff
	var bytes=("REQ %d %s\n"%[sequence,command]).to_ascii_buffer();var offset:=0;var end:int=Time.get_ticks_msec()+timeout
	while offset<bytes.size() and Time.get_ticks_msec()<end:
		var sent:int=serial.write_bytes(bytes.slice(offset))
		if sent<=0:error_text="USB yazma hatası: "+serial.get_error();return {}
		offset+=sent
	if offset<bytes.size():error_text="USB yazma zaman aşımı";return {}
	while Time.get_ticks_msec()<end:
		var incoming:PackedByteArray=serial.read_bytes(20)
		if not serial.get_error().is_empty():error_text="USB bağlantısı kesildi: "+serial.get_error();return {}
		buffer+=incoming.get_string_from_ascii()
		if buffer.length()>4096:error_text="USB veri tamponu sınırı aşıldı";return {}
		var newline:int=buffer.find("\n")
		while newline>=0:
			var line:String=buffer.substr(0,newline);buffer=buffer.substr(newline+1)
			var decoder:=JSON.new()
			var parsed:Variant=null
			if line.begins_with("{") and decoder.parse(line)==OK:parsed=decoder.data
			if parsed is Dictionary and int(parsed.get("seq",-1))==sequence:
				if int(parsed.get("protocol",0))!=1 or not str(parsed.get("error","")).is_empty():error_text="Saat protokolü uyuşmuyor";return {}
				return parsed
			newline=buffer.find("\n")
	error_text="Saatten cevap alınamadı";return {}
func _state(command:String,timeout:int=450)->Dictionary:
	var reply=_request(command,timeout)
	if reply.is_empty():return {}
	if str(reply.get("app",""))!="ADASLab" or int(reply.get("id",0))!=3 or int(reply.get("version",0))<2:error_text="Saatte ADASLab v2 gerekli";return {}
	var value=reply.get("state",{})
	if not value is Dictionary or not str(value.get("error","")).is_empty():error_text="Saat komutu reddetti";return {}
	return value
func _pause_watch()->void:
	running=false
	_state("H:0",200)
	var paused=_state("PAUSE",200)
	if not paused.is_empty():last_control=paused
	lock.lock();held.clear();lanes.clear();lock.unlock()
func _panel(value:Dictionary)->bool:
	if not value.has("gmode") or int(value.gmode)<0 or int(value.gmode)>2:error_text="Saat paneli desteklenmiyor";return false
	panel=value
	var next:Dictionary={"mode":int(value.gmode),"acc":bool(value.get("gacc",false)),"target":int(value.get("gtarget",2500)),"headway":int(value.get("gheadway",1800)),"seed":42}
	if not running and next!=settings:world=null
	settings=next;return true
func _work()->void:
	serial=ClassDB.instantiate("NativeSerial")
	var next_attempt:=0
	while true:
		var commands=_commands()
		if commands.stop:break
		if Time.get_ticks_msec()<next_attempt:OS.delay_msec(20);continue
		available_ports=serial.ports();var candidates:PackedStringArray=PackedStringArray([str(commands.port)]) if not str(commands.port).is_empty() else available_ports
		var opened:=false
		for candidate in candidates:
			current_port=candidate;buffer="";error_text=""
			if not serial.open_port(candidate):error_text="USB portu açılamadı: "+serial.get_error();continue
			var hello=_state("HELLO",650)
			if hello.is_empty():serial.close_port();continue
			_pause_watch();var value=_state("J")
			if not value.is_empty() and _panel(value):opened=true;break
			serial.close_port()
		if not opened:
			_publish(false,error_text if not error_text.is_empty() else "Saati USB ile bağlayın.");next_attempt=Time.get_ticks_msec()+1500;continue
		world=null;running=false;last_control={};_publish(true,"Saatten başlatın.")
		while true:
			var started:int=Time.get_ticks_msec();commands=_commands()
			if commands.stop or commands.reconnect:break
			if commands.pause or not commands.focus:
				if running:_pause_watch()
			if commands.restart:world=null;_pause_watch()
			for command in commands.qa:
				if not _state(command).is_empty():continue
				error_text="Test komutu reddedildi";break
			if running:
				world.steer(int(commands.lane));var control=_state(world.command(commands))
				if control.is_empty():break
				last_control=control
				if not bool(control.get("grun",false)):_pause_watch();_panel(control)
				elif int(control.get("ms",-1))!=world.tick or not bool(control.get("fresh",false)) or int(control.get("gmode",-1))!=int(settings.mode):error_text="Ölçüm cevabı doğrulanamadı";break
				elif not world.advance(control,commands):error_text="Geçersiz kontrol cevabı";break
				elif world.finished():_pause_watch()
			else:
				var value=_state("J")
				if value.is_empty() or not _panel(value):break
				if bool(value.get("grun",false)):
					if not commands.focus:_pause_watch()
					else:
						if world==null or world.finished():world=World.new(settings)
						var reset=_state("RESET")
						if reset.is_empty() or _state("H:1").is_empty():break
						running=true
			_publish(true,"" if running else "Saatten başlatın.")
			OS.delay_msec(maxi(0,50-(Time.get_ticks_msec()-started)))
		var message:=error_text
		_pause_watch();serial.close_port();running=false;_publish(false,message if not message.is_empty() else "Saat bağlantısı kapalı.")
		if commands.stop:break
		next_attempt=Time.get_ticks_msec()+500
	serial.close_port()
