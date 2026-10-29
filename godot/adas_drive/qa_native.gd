extends Node
## Explicit QA of the release app's own serial worker; not used in normal play.
var game:Node
var checks:Array[String]=[]
var path:=""
var capture:=""
var finished:=false
var began:=0
func _ready()->void:
	game=get_parent();began=Time.get_ticks_msec()
	var args=OS.get_cmdline_user_args()
	for index in range(args.size()-1):
		if args[index]=="--qa-report":path=args[index+1]
		elif args[index]=="--qa-capture":capture=args[index+1]
	_run.call_deferred()
func finish(ok:bool,message:String="")->void:
	if finished:return
	finished=true
	var report={"passed":ok,"error":message,"checks":checks,"count":checks.size(),"debug_build":OS.is_debug_build(),"direct_uart":game.direct,"backend":game.backend,"duration":(Time.get_ticks_msec()-began)/1000.0,"fps":Performance.get_monitor(Performance.TIME_FPS),"rendering_method":RenderingServer.get_current_rendering_method()}
	if not path.is_empty():
		var file=FileAccess.open(path,FileAccess.WRITE)
		if file!=null:file.store_string(JSON.stringify(report,"  ")+"\n");file.close()
	print("STANDALONE_QA "+JSON.stringify(report));get_tree().quit(0 if ok else 1)
func check(ok:bool,description:String)->bool:
	if not ok:finish(false,description+" state="+JSON.stringify(game.state));return false
	checks.append(description);print("PASS: "+description);return true
func wait_for(predicate:Callable,description:String,seconds:float=5.0)->bool:
	var end:int=Time.get_ticks_msec()+int(seconds*1000)
	while Time.get_ticks_msec()<end and not finished:
		if predicate.call():return true
		await get_tree().process_frame
	finish(false,"Timed out: "+description+" state="+JSON.stringify(game.state));return false
func key(code:int,pressed:bool,echo:bool=false)->void:
	var event:=InputEventKey.new();event.keycode=code;event.physical_keycode=code;event.pressed=pressed;event.echo=echo;Input.parse_input_event(event)
func sleep(seconds:float)->void:await get_tree().create_timer(seconds).timeout
func card_mode(mode:int)->bool:
	if not await wait_for(func():return not game.state.get("running",false),"Card pause completed"):return false
	game.native_host.qa_panel(mode)
	return await wait_for(func():return game.state.get("mode","")==["active","warn","off"][mode],"Card mode read back")
func card_start()->bool:
	game._focus_entered();game.native_host.qa_start()
	return await wait_for(func():return game.state.get("running",false) and float(game.state.get("elapsed",0))>0.1,"Card start request")
func pause()->bool:
	key(KEY_SPACE,true);key(KEY_SPACE,false)
	return await wait_for(func():return not game.state.get("running",false),"Keyboard pause acknowledgement")
func _run()->void:
	if not await wait_for(func():return game.state.get("ready",false),"Direct USB connection",15):return
	if not check(game.direct and game.native_host!=null,"Game owns native USB without Studio or TCP"):return
	if not check(game.start_button.disabled and game.mode_buttons.is_empty(),"ADAS controls are owned by the watch, not PC menu"):return
	if not await card_mode(1):return
	game._setting("mode","off");await sleep(0.2)
	if not check(game.state.get("mode","")=="warn","PC settings cannot override watch mode"):return
	game.native_host.qa_panel(1,false,3000,2200)
	if not await wait_for(func():return int(game.state.get("targetKmh",0))==108 and int(game.state.get("headwayMs",0))==2200,"Watch speed/headway readback"):return
	if not check(true,"Watch target speed and headway are authoritative"):return
	if not await card_mode(0):return
	if not await card_start():return
	var speed:float=float(game.state.egoKmh)
	key(KEY_W,true);await sleep(0.65)
	if not check(float(game.state.egoKmh)>speed+2,"W accelerates through native USB controller"):return
	key(KEY_UP,true);key(KEY_W,false);speed=float(game.state.egoKmh);await sleep(0.4)
	if not check(float(game.state.egoKmh)>speed+1,"Gas aliases release independently"):return
	key(KEY_UP,false)
	if not await wait_for(func():return float(game.state.accelMps2)<0,"Gas release"):return
	key(KEY_A,true);key(KEY_A,false)
	if not await wait_for(func():return int(game.state.targetLane)==0,"Left lane"):return
	key(KEY_D,true)
	if not await wait_for(func():return int(game.state.targetLane)==1,"Right lane"):return
	for i in range(5):key(KEY_D,true,true)
	await sleep(0.15)
	if not check(int(game.state.targetLane)==1,"Auto-repeat cannot repeat steering"):return
	key(KEY_D,false);key(KEY_S,true)
	if not await wait_for(func():return float(game.state.accelMps2)<-5,"Driver brake"):return
	key(KEY_S,false)
	if not await pause():return
	if not check(int(game.state.get("mcuOutput",{}).get("a",999))==0,"Native pause clears actual MCU output"):return
	game.native_host.qa_panel(0,true)
	if not await wait_for(func():return bool(game.state.get("accEnabled",false)),"Watch ACC readback"):return
	if not await card_start():return
	if not await wait_for(func():return float(game.state.accelMps2)>0 and int(game.state.mcuOutput.a)>0,"Watch ACC acceleration"):return
	if not check(absf(float(game.state.accelMps2)-float(game.state.mcuOutput.a)/100.0)<0.00001,"ACC acceleration comes directly from the watch"):return
	if not await pause():return
	game.native_host.qa_panel(0,false)
	if not await wait_for(func():return not bool(game.state.accEnabled),"Watch ACC disabled for manual driving"):return
	if not await card_start():return
	key(KEY_W,true);await sleep(0.1);game._focus_exited()
	if not await wait_for(func():return not game.state.running,"Focus loss pause"):return
	if not check(not bool(game.state.get("mcuOutput",{}).get("grun",true)),"Focus loss stops the watch run request"):return
	if not await card_start():return
	if not await wait_for(func():return float(game.state.accelMps2)<0,"Focus loss releases throttle"):return
	if not await pause():return
	for mode in [1,2,0]:
		if not await card_mode(mode):return
		if not await card_start():return
		key(KEY_W,true)
		if mode==0:
			if not await wait_for(func():return int(game.state.interventions)>0,"Watch emergency braking",10):return
			if not check(int(game.state.mcuOutput.a)==-850 and not int(game.state.collisions),"Real watch AEB overrides gas in standalone game"):return
			if not capture.is_empty() and DisplayServer.get_name()!="headless":
				await RenderingServer.frame_post_draw
				if not check(get_viewport().get_texture().get_image().save_png(capture)==OK,"Release viewport captured"):return
		else:
			if not await wait_for(func():return str(game.state.status)=="collision","Unassisted collision",10):return
			if not check(int(game.state.interventions)==0 and int(game.state.mcuOutput.a)==0,"Warning/off do not actuate"):return
			if mode==1 and not check(int(game.state.warnings)>0,"Warning mode warns from actual MCU decisions"):return
			if mode==2 and not check(int(game.state.warnings)==0,"Off mode suppresses warnings"):return
			key(KEY_W,false)
	if not await pause():return
	game.native_host.reconnect()
	if not await wait_for(func():return not game.state.get("connected",true),"USB reconnect closes old owner"):return
	if not await wait_for(func():return game.state.get("ready",false),"USB reconnect restores watch",8):return
	if not check(not game.state.running,"Reconnect never resumes a stale run"):return
	if not await card_start():return
	if not check(game.state.running,"Release exits during a run to verify MCU cleanup"):return
	finish(true)
