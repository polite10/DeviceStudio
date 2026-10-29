extends Node
## Explicit --qa-only harness. Sends normal Godot UI signals and input events;
## no traffic, actuator or controller state is changed directly by this script.

var game: Node
var checks: Array[String] = []
var report_path := ""
var capture_path := ""
var done := false
var started_at := 0

func _ready() -> void:
	game=get_parent()
	started_at=Time.get_ticks_msec()
	var args := OS.get_cmdline_user_args()
	for index in range(args.size()-1):
		if args[index]=="--qa-report":report_path=args[index+1]
		elif args[index]=="--qa-capture":capture_path=args[index+1]
	_run.call_deferred()

func _finish(passed: bool, message := "") -> void:
	if done:return
	done=true
	var report := {"passed":passed,"checks":checks,"checks_passed":checks.size(),
		"error":message,"backend":str(game.backend),"duration_seconds":float(Time.get_ticks_msec()-started_at)/1000.0,
		"scope":"Real Godot input/UI handlers and TCP client against Studio; synthetic key events, not physical keyboard automation",
		"fps_at_finish":int(Performance.get_monitor(Performance.TIME_FPS)),"rendering_method":RenderingServer.get_current_rendering_method(),"scene_vehicles":game.cars.size()}
	if not report_path.is_empty():
		var file := FileAccess.open(report_path,FileAccess.WRITE)
		if file!=null:
			file.store_string(JSON.stringify(report,"  ")+"\n")
			file.close()
	print("ADAS_DRIVE_QA "+JSON.stringify(report))
	get_tree().quit(0 if passed else 1)

func _check(condition: bool, description: String) -> bool:
	if not condition:
		_finish(false,description+" state="+JSON.stringify(game.state))
		return false
	checks.append(description)
	print("PASS: "+description)
	return true

func _wait(predicate: Callable, description: String, timeout := 5.0) -> bool:
	var deadline := Time.get_ticks_msec()+int(timeout*1000)
	while Time.get_ticks_msec()<deadline and not done:
		if predicate.call():return true
		await get_tree().process_frame
	_finish(false,"Timed out: "+description+" state="+JSON.stringify(game.state))
	return false

func _sleep(seconds: float) -> void:
	await get_tree().create_timer(seconds).timeout

func _key(code: int, pressed: bool, repeated := false) -> void:
	var event := InputEventKey.new()
	event.keycode=code
	event.physical_keycode=code
	event.pressed=pressed
	event.echo=repeated
	Input.parse_input_event(event)

func _start() -> bool:
	game._focus_entered()
	game.start_button.grab_focus()
	game.start_button.pressed.emit()
	if not await _wait(func():return bool(game.state.get("running",false)) and float(game.state.get("elapsed",0.0))>0.1,"Start button starts the ARM-backed simulation"):return false
	return _check(get_viewport().gui_get_focus_owner()==null,"Starting a run releases menu focus so arrow keys reach driving")

func _pause() -> bool:
	_key(KEY_SPACE,true)
	_key(KEY_SPACE,false)
	return await _wait(func():return not bool(game.state.get("running",false)),"Space pauses through the normal input handler")

func _mode(index: int) -> bool:
	# A collision snapshot precedes the final MCU pause acknowledgements.
	# Respect the same enabled state that gates a real mouse click.
	if not await _wait(func():return not game.mode_buttons[index].disabled,"Mode control becomes interactive after worker cleanup"):return false
	game.mode_buttons[index].pressed.emit()
	var expected: String=["active","warn","off"][index]
	return await _wait(func():return str(game.state.get("mode",""))==expected,"Mode button selects "+expected)

func _run() -> void:
	if not await _wait(func():return game.studio_connected and bool(game.state.get("ready",false)),"Authenticated Studio/firmware connection",15.0):return
	game._focus_entered()
	if not _check(game.authenticated,"Real Godot TCP client authenticates with the loopback bridge"):return
	if not _check(not game.start_button.disabled,"Godot Start button enables after ADASLab v2 is ready"):return
	# Keep a real editor draft alive across multiple 20 Hz status snapshots.
	var editor: LineEdit=game.target_spin.get_line_edit()
	editor.grab_focus()
	# SpinBox schedules initial focus formatting. Real typing occurs after that
	# focus event; let it settle before testing later network refreshes.
	await _sleep(0.08)
	editor.text="123"
	editor.caret_column=3
	await _sleep(0.3)
	if not _check(editor.text=="123" and editor.caret_column==3 and editor.has_focus(),"Paused speed draft, caret and focus survive repeated TCP state refresh (text="+editor.text+", caret="+str(editor.caret_column)+", focus="+str(editor.has_focus())+")"):return
	_key(KEY_ENTER,true)
	_key(KEY_ENTER,false)
	if not await _wait(func():return int(game.state.get("targetKmh",0))==123,"Enter commits the speed draft through SpinBox"):return
	if not _check(true,"Committing the preserved editor draft updates the Studio configuration"):return
	game.target_spin.value=90
	if not await _wait(func():return int(game.state.get("targetKmh",0))==90,"Speed configuration restores through value_changed"):return
	if not await _mode(0):return
	if game.acc_button.button_pressed:game.acc_button.button_pressed=false
	game.seed_spin.value=73
	if not await _wait(func():return int(game.state.get("seed",0))==73,"Seed editor reaches Studio"):return
	game.seed_spin.value=42
	if not await _wait(func():return int(game.state.get("seed",0))==42,"Seed editor restores repeatable traffic"):return
	if not _check(true,"Godot seed editor sends settings through its real value_changed signal"):return
	if not await _start():return
	if not _check(true,"Godot Start button starts live traffic controlled by compiled ARM firmware"):return
	var speed := float(game.state.get("egoKmh",0.0))
	_key(KEY_W,true)
	await _sleep(0.65)
	if not _check(float(game.state.get("egoKmh",0.0))>speed+2.0,"Godot W key accelerates the authoritative Studio vehicle"):return
	_key(KEY_UP,true)
	_key(KEY_W,false)
	speed=float(game.state.get("egoKmh",0.0))
	await _sleep(0.4)
	if not _check(float(game.state.get("egoKmh",0.0))>speed+1.0,"Releasing W preserves throttle while Up is held independently"):return
	_key(KEY_UP,false)
	if not await _wait(func():return float(game.state.get("accelMps2",0.0))<0,"Both gas aliases release to coasting"):return
	if not _check(true,"Releasing both aliases stops the throttle"):return
	_key(KEY_A,true)
	_key(KEY_A,false)
	if not await _wait(func():return int(game.state.get("targetLane",1))==0,"A requests the left lane"):return
	_key(KEY_D,true)
	if not await _wait(func():return int(game.state.get("targetLane",0))==1,"D requests the center lane"):return
	for index in range(6):_key(KEY_D,true,true)
	await _sleep(0.15)
	if not _check(int(game.state.get("targetLane",0))==1,"Godot auto-repeat cannot cause repeated lane changes"):return
	_key(KEY_D,false)
	_key(KEY_S,true)
	if not await _wait(func():return float(game.state.get("accelMps2",0.0))<-5.0,"S applies driver braking"):return
	_key(KEY_S,false)
	if not _check(true,"Godot steering and brake keys reach the simulation through TCP"):return
	_key(KEY_C,true)
	_key(KEY_C,false)
	await _sleep(0.1)
	if not _check(game.bonnet_camera,"C switches to the bonnet camera through normal input"):return
	if not capture_path.is_empty() and DisplayServer.get_name()!="headless":
		await _sleep(0.3)
		await RenderingServer.frame_post_draw
		var view := get_viewport().get_texture().get_image()
		if not _check(view.save_png(capture_path.get_basename()+"-bonnet.png")==OK,"Native bonnet camera capture saved"):return
	_key(KEY_F,true)
	_key(KEY_F,false)
	await _sleep(0.1)
	if not _check(not game.bonnet_camera,"F returns to the chase camera through normal input"):return
	if not await _pause():return
	if not _check(str(game.state.get("status",""))=="paused","Space pauses the actual game worker"):return
	var paused_time := float(game.state.get("elapsed",0.0))
	if not await _start():return
	if not _check(float(game.state.get("elapsed",0.0))>=paused_time,"Resume preserves road and simulation time"):return
	_key(KEY_W,true)
	await _sleep(0.15)
	game._focus_exited()
	if not await _wait(func():return not bool(game.state.get("running",false)),"Godot focus loss pauses the game"):return
	if not _check(game.held.is_empty(),"Godot focus loss releases held keys before pausing"):return
	if not await _start():return
	if not await _wait(func():return float(game.state.get("accelMps2",0.0))<0,"Focus-loss resume has no stuck throttle"):return
	if not _check(true,"Returning to Godot after focus loss has no stuck throttle"):return
	if not await _pause():return
	# Every mode uses the same seed and normal UI signal paths. Holding W while
	# ignoring warnings must distinguish active intervention from warn/off.
	for index in [1,2,0]:
		if not await _mode(index):return
		if not await _start():return
		_key(KEY_W,true)
		if index==0:
			if not await _wait(func():return int(game.state.get("interventions",0))>0,"Active AEB overrides held W",10.0):return
			if not _check(not bool(game.state.get("collisions",false)),"Active mode applies ARM emergency braking before collision"):return
			if not capture_path.is_empty() and DisplayServer.get_name()!="headless":
				await RenderingServer.frame_post_draw
				var image := get_viewport().get_texture().get_image()
				if not _check(image.save_png(capture_path)==OK,"Native 3D game viewport capture saved"):return
		else:
			if not await _wait(func():return str(game.state.get("status",""))=="collision","Unassisted held W reaches the defined collision",10.0):return
			if not _check(int(game.state.get("interventions",0))==0,"Warning/off modes never apply automatic braking"):return
			if index==1:
				if not _check(int(game.state.get("warnings",0))>0,"Warning-only mode emits a warning through real ARM decisions"):return
			else:
				if not _check(int(game.state.get("warnings",0))==0 and not bool(game.state.get("warning",false)),"Off mode suppresses ADAS warnings"):return
			_key(KEY_W,false)
	# Exit while an authenticated driving session exists; the Python verifier
	# must observe worker cancellation, cleared keys and final MCU PAUSE.
	if not _check(bool(game.state.get("running",false)),"QA exits an active session to exercise renderer-close cleanup"):return
	_finish(true)
