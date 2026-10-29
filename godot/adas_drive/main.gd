extends Node3D
## GPU display + input client. The authoritative world and UART stay in Studio.

const Highway = preload("res://highway.gd")
const Vehicle = preload("res://vehicle.gd")
const MODE_NAMES := ["Aktif destek","Yalnız uyarı","ADAS kapalı"]
const MODE_VALUES := ["active","warn","off"]
const VEHICLES := ["NormalCar1","SUV","NormalCar2","SportsCar","Taxi","SportsCar2"]
const PAINTS := [Color("236e67"),Color("e1e6e4"),Color("d5a04c"),Color("697e9d"),Color("b75246"),Color("647a60")]

var peer := StreamPeerTCP.new()
var port := 0
var token := ""
var authenticated := false
var buffer := PackedByteArray()
var last_connect_attempt := -2000
var last_state_time := 0
var last_heartbeat := 0
var active := true
var held: Dictionary = {}
var state: Dictionary = {}
var previous: Dictionary = {}
var current: Dictionary = {}
var state_received := 0
var sample_period := 50.0
var last_elapsed := -1.0
var studio_connected := false
var backend := ""
var network_message := "Studio bağlantısı bekleniyor"
var demo := false
var demo_clock := 0.0
var demo_running := true
var qa_enabled := false
var styled_mode := -1
var styled_alert := -1
var frame_count := 0
var capture_path := ""
var capture_after := 100
var exit_after_capture := false
var capture_done := false
var bonnet_camera := false
var old_visual_distance := 0.0
var old_visual_lane := 1.0
var wheel_speed := 0.0
var car_world_positions: Dictionary = {}
var sync_ui := false
var was_running := false

var highway: Node3D
var player: Node3D
var cars: Dictionary = {}
var camera: Camera3D
var hud: CanvasLayer
var connection_label: Label
var mode_label: Label
var timer_label: Label
var speed_label: Label
var gap_label: Label
var ttc_label: Label
var accel_label: Label
var score_label: Label
var alert_label: Label
var alert_panel: PanelContainer
var pause_panel: PanelContainer
var pause_title: Label
var pause_description: Label
var start_button: Button
var restart_button: Button
var mode_buttons: Array[Button] = []
var acc_button: CheckButton
var target_spin: SpinBox
var seed_spin: SpinBox
var pause_button: Button

func _ready() -> void:
	_parse_args()
	get_window().title = "ADASLab Drive · 3B Sürüş"
	get_window().focus_entered.connect(_focus_entered)
	get_window().focus_exited.connect(_focus_exited)
	active = get_window().has_focus() or qa_enabled
	highway = Highway.new()
	add_child(highway)
	player = Vehicle.new()
	player.name = "PlayerCar"
	add_child(player)
	player.configure(_asset("NormalCar1"),PAINTS[0],true)
	camera = Camera3D.new()
	camera.name = "ChaseCamera"
	camera.current = true
	camera.fov = 59.0
	camera.near = 0.15
	camera.far = 1100.0
	camera.position = Vector3(0,3.35,8.8)
	add_child(camera)
	camera.look_at(Vector3(0,1.0,-15.0))
	_build_hud()
	if demo:
		backend = "DEMO · fiziksel kart kullanılmıyor"
		studio_connected = true
		_demo_update()
	else:
		_connect()
	if qa_enabled and ResourceLoader.exists("res://qa.gd"):
		var qa_node := Node.new()
		qa_node.set_script(load("res://qa.gd"))
		add_child(qa_node)

func _asset(model: String) -> String:
	return "res://assets/vehicles/quaternius/"+model+".fbx"

func _parse_args() -> void:
	var args := OS.get_cmdline_user_args()
	var index := 0
	while index<args.size():
		var arg := args[index]
		if arg=="--demo":demo = true
		elif arg=="--qa":qa_enabled = true
		elif arg=="--exit-after-capture":exit_after_capture = true
		elif arg.begins_with("--bridge-port="):port = int(arg.get_slice("=",1))
		elif arg.begins_with("--bridge-token="):token = arg.get_slice("=",1)
		elif arg.begins_with("--capture="):capture_path = arg.trim_prefix("--capture=")
		elif arg.begins_with("--capture-after="):capture_after = int(arg.get_slice("=",1))
		elif index+1<args.size():
			if arg=="--bridge-port":index+=1;port=int(args[index])
			elif arg=="--bridge-token":index+=1;token=args[index]
			elif arg=="--capture":index+=1;capture_path=args[index]
		index+=1

func _connect() -> void:
	if port<=0 or token.is_empty():
		network_message = "Studio’da 3B sürüşü açın"
		return
	last_connect_attempt = Time.get_ticks_msec()
	peer = StreamPeerTCP.new()
	peer.connect_to_host("127.0.0.1",port)
	authenticated = false
	buffer.clear()

func _poll_network(now: int) -> void:
	peer.poll()
	var status := peer.get_status()
	if status==StreamPeerTCP.STATUS_CONNECTED:
		if not authenticated:
			peer.set_no_delay(true)
			_send({"type":"hello","protocol":1,"token":token})
			authenticated = true
			last_state_time = now
			_send({"type":"heartbeat","active":active})
		var available := peer.get_available_bytes()
		if available>0:
			if available+buffer.size()>65536:
				_disconnect("Studio paketi sınırı aşıldı")
				return
			var data := peer.get_data(available)
			if int(data[0])!=OK:
				_disconnect("Studio bağlantısı kesildi")
				return
			buffer.append_array(data[1])
			var split := buffer.find(10)
			while split>=0:
				var packet := buffer.slice(0,split).get_string_from_utf8()
				buffer = buffer.slice(split+1)
				var parsed: Variant = JSON.parse_string(packet)
				if parsed is Dictionary:
					var message: Dictionary = parsed
					if message.get("type")=="state" and int(message.get("protocol",0))==1:
						studio_connected = bool(message.get("connected",false))
						backend = String(message.get("backend","STM32 · USB / UART"))
						var incoming: Variant = message.get("state",{})
						if incoming is Dictionary:_accept_state(incoming,now)
					elif message.get("type")=="error":
						network_message = String(message.get("message","Studio komutu reddetti"))
				split = buffer.find(10)
		if now-last_heartbeat>=100:
			last_heartbeat = now
			_send({"type":"heartbeat","active":active})
		if now-last_state_time>1500:
			_disconnect("Studio’dan güncel veri alınamıyor")
	else:
		if authenticated:_disconnect("Studio bağlantısı kesildi")
		if now-last_connect_attempt>2000:_connect()

func _disconnect(message: String) -> void:
	_release_keys()
	peer.disconnect_from_host()
	authenticated = false
	studio_connected = false
	network_message = message
	state["running"] = false
	_refresh_ui()

func _send(message: Dictionary) -> void:
	if demo:return
	if peer.get_status()==StreamPeerTCP.STATUS_CONNECTED:
		peer.put_data((JSON.stringify(message)+"\n").to_utf8_buffer())

func _accept_state(incoming: Dictionary, now: int) -> void:
	last_state_time = now
	var elapsed := float(incoming.get("elapsed",0.0))
	if current.is_empty() or elapsed<last_elapsed or absf(elapsed-last_elapsed)>0.3:
		previous = incoming.duplicate(true)
		current = incoming.duplicate(true)
		old_visual_distance = float(incoming.get("distance",0.0))
		old_visual_lane = float(incoming.get("egoLane",1.0))
	elif elapsed>last_elapsed:
		previous = current
		current = incoming.duplicate(true)
		sample_period = clampf((elapsed-last_elapsed)*1000.0,20.0,150.0)
		state_received = now
	else:
		# Panel/status updates must not restart motion interpolation.
		for key in incoming:current[key] = incoming[key]
	last_elapsed = elapsed
	state = incoming.duplicate(true)
	if was_running and not bool(state.get("running",false)):_release_keys()
	if not was_running and bool(state.get("running",false)):
		get_viewport().gui_release_focus()
	was_running = bool(state.get("running",false))
	network_message = ""
	_refresh_ui()

func _process(delta: float) -> void:
	frame_count+=1
	var now := Time.get_ticks_msec()
	if demo:
		if demo_running:demo_clock+=delta
		if now-last_state_time>=50:_demo_update()
	else:_poll_network(now)
	_render_world(delta,now)
	if not capture_done and not capture_path.is_empty() and frame_count>=capture_after:
		capture_done = true
		_capture.call_deferred()

func _render_world(delta: float, now: int) -> void:
	if current.is_empty():return
	var alpha := clampf(float(now-state_received)/sample_period,0.0,1.0)
	var distance := lerpf(float(previous.get("distance",0.0)),float(current.get("distance",0.0)),alpha)
	var lane := lerpf(float(previous.get("egoLane",1.0)),float(current.get("egoLane",1.0)),alpha)
	var step := distance-old_visual_distance
	var moving := bool(state.get("running",false)) and studio_connected
	if not moving:step = 0.0
	var lane_velocity := (lane-old_visual_lane)/maxf(delta,0.001)
	var steering := clampf(-atan(lane_velocity*3.6/maxf(float(state.get("egoKmh",0))/3.6,3.0)),-0.17,0.17)
	player.position.x = (lane-1.0)*3.6
	player.rotation.y = lerpf(player.rotation.y,steering,1.0-exp(-delta*10.0))
	player.animate(delta,step,bool(state.get("aeb",false)) or float(state.get("accelMps2",0.0))<-1.0,float(state.get("accelMps2",0.0)),steering)
	highway.update_distance(distance)
	old_visual_distance = distance
	old_visual_lane = lane
	var seen: Dictionary = {}
	var old_cars: Dictionary = {}
	for value in previous.get("traffic",[]):
		if value is Dictionary:old_cars[int(value.get("id",0))] = value
	for value in current.get("traffic",[]):
		if not value is Dictionary:continue
		var car: Dictionary = value
		var identity := int(car.get("id",0))
		seen[identity] = true
		if not cars.has(identity):
			var model := Vehicle.new()
			add_child(model)
			model.configure(_asset(VEHICLES[identity%VEHICLES.size()]),PAINTS[(identity+1)%PAINTS.size()])
			cars[identity] = model
		var model: Node3D = cars[identity]
		var before: Dictionary = old_cars.get(identity,car)
		model.position.x = (lerpf(float(before.get("lane",1)),float(car.get("lane",1)),alpha)-1.0)*3.6
		var relative := lerpf(float(before.get("relativeZ",0)),float(car.get("relativeZ",0)),alpha)
		model.position.z = -relative
		var world_position := distance+relative
		var car_step := world_position-float(car_world_positions.get(identity,world_position))
		car_world_positions[identity] = world_position
		model.visible = model.position.z<18 and model.position.z>-450
		var turn := clampf(-(float(car.get("lane",1))-float(before.get("lane",1)))*2.5,-0.15,0.15)
		model.rotation.y = lerpf(model.rotation.y,turn,1.0-exp(-delta*8.0))
		model.animate(delta,car_step if moving else 0.0,bool(car.get("braking",false)),-3.0 if bool(car.get("braking",false)) else 0.0,turn)
	for identity in cars.keys():
		if not seen.has(identity):
			cars[identity].queue_free()
			cars.erase(identity)
			car_world_positions.erase(identity)
	var desired: Vector3
	var target: Vector3
	if bonnet_camera:
		desired = Vector3(player.position.x,1.36,-0.1)
		target = Vector3(player.position.x,1.3,-35)
		player.visible = false
	else:
		desired = Vector3(player.position.x*0.82,3.35,8.8)
		target = Vector3(player.position.x*0.88,0.98,-15)
		player.visible = true
	camera.position = camera.position.lerp(desired,1.0-exp(-delta*5.0))
	camera.look_at(target)

func _focus_entered() -> void:
	active = true
	_send({"type":"heartbeat","active":true})

func _focus_exited() -> void:
	active = false
	_release_keys()
	_send({"type":"action","name":"pause"})
	_send({"type":"heartbeat","active":false})

func _notification(what: int) -> void:
	if what==NOTIFICATION_WM_CLOSE_REQUEST:
		_release_keys()
		_send({"type":"action","name":"pause"})
		_send({"type":"heartbeat","active":false})

func _release_keys() -> void:
	for key in held:_send({"type":"input","key":key,"pressed":false,"repeat":false})
	held.clear()

func _unhandled_key_input(event: InputEvent) -> void:
	if not event is InputEventKey:return
	var key_event := event as InputEventKey
	if key_event.echo:return
	var name := _key_name(key_event.keycode)
	if not name.is_empty():
		if key_event.pressed and bool(state.get("running",false)) and active:
			held[name] = true
			_send({"type":"input","key":name,"pressed":true,"repeat":false})
		elif not key_event.pressed:
			held.erase(name)
			_send({"type":"input","key":name,"pressed":false,"repeat":false})
		get_viewport().set_input_as_handled()
	elif key_event.pressed:
		if key_event.keycode in [KEY_ESCAPE,KEY_SPACE]:
			_send({"type":"action","name":"pause"})
			_release_keys()
			get_viewport().set_input_as_handled()
		elif key_event.keycode in [KEY_C,KEY_F]:bonnet_camera = not bonnet_camera

func _key_name(key: int) -> String:
	match key:
		KEY_W:return "w"
		KEY_UP:return "up"
		KEY_S:return "s"
		KEY_DOWN:return "down"
		KEY_A:return "a"
		KEY_LEFT:return "left"
		KEY_D:return "d"
		KEY_RIGHT:return "right"
	return ""

func _action(name: String) -> void:
	if demo:
		if name=="start" or name=="restart":demo_running = true
		if name=="restart":demo_clock = 0.0
		elif name=="pause":demo_running = false
		_demo_update()
		return
	_release_keys()
	_send({"type":"action","name":name})

func _setting(key: String, value: Variant) -> void:
	if sync_ui:return
	if demo:
		state[key] = value
		_demo_update()
		return
	_send({"type":"setting","key":key,"value":value})

func _capture() -> void:
	await RenderingServer.frame_post_draw
	var picture := get_viewport().get_texture().get_image()
	var result := picture.save_png(capture_path)
	print("ADAS_DRIVE_CAPTURE "+capture_path+" result="+str(result)+" models="+str(cars.size())+" frame="+str(frame_count))
	if exit_after_capture:get_tree().quit(0 if result==OK else 2)

func _demo_update() -> void:
	var phase := demo_clock
	var incoming := {"running":demo_running,"ready":true,"mode":state.get("mode","active"),"accEnabled":state.get("accEnabled",false),"targetKmh":state.get("targetKmh",90),"seed":state.get("seed",42),"status":"running" if demo_running else "paused","egoKmh":88.0,"distance":phase*24.4,"elapsed":phase,"remaining":120.0-phase,"egoLane":1.0,"accelMps2":0.0,"ttc":5.8,"gap":36.0,"score":int(phase*40),"warning":false,"aeb":false,"traffic":[{"id":1,"lane":1.0,"relativeZ":36.0,"speedKmh":78,"braking":false},
		 {"id":2,"lane":0.0,"relativeZ":17.0,"speedKmh":81,"braking":false},
		 {"id":3,"lane":2.0,"relativeZ":65.0,"speedKmh":92,"braking":false},
		 {"id":4,"lane":0.0,"relativeZ":115.0,"speedKmh":80,"braking":false},
		 {"id":5,"lane":2.0,"relativeZ":146.0,"speedKmh":89,"braking":false}]}
	_accept_state(incoming,Time.get_ticks_msec())

func _panel_style(color: Color, radius: int = 12) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = color
	style.corner_radius_top_left = radius
	style.corner_radius_top_right = radius
	style.corner_radius_bottom_left = radius
	style.corner_radius_bottom_right = radius
	style.content_margin_left = 20
	style.content_margin_right = 20
	style.content_margin_top = 16
	style.content_margin_bottom = 16
	style.border_width_bottom = 1
	style.border_width_top = 1
	style.border_width_left = 1
	style.border_width_right = 1
	style.border_color = Color(0.75,0.87,0.9,0.13)
	return style

func _label(text: String, font_size: int, color := Color("e7eff2")) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size",font_size)
	label.add_theme_color_override("font_color",color)
	return label

func _button(text: String, primary := false) -> Button:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size = Vector2(0,44)
	button.add_theme_font_size_override("font_size",15)
	button.add_theme_stylebox_override("normal",_panel_style(Color("51c8b3") if primary else Color("243b49"),8))
	button.add_theme_stylebox_override("hover",_panel_style(Color("82e7cf") if primary else Color("3b5664"),8))
	button.add_theme_stylebox_override("pressed",_panel_style(Color("3ea38e"),8))
	button.add_theme_color_override("font_color",Color("102829") if primary else Color("e7eff2"))
	return button

func _readout(parent: HBoxContainer, title: String, value: String) -> Label:
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation",4)
	parent.add_child(column)
	column.add_child(_label(title,12,Color("91abb5")))
	var readout := _label(value,30)
	column.add_child(readout)
	return readout

func _build_hud() -> void:
	hud = CanvasLayer.new()
	add_child(hud)
	var root := Control.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	hud.add_child(root)
	var top := PanelContainer.new()
	top.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	top.offset_left=24;top.offset_right=-24;top.offset_top=22;top.offset_bottom=104
	top.add_theme_stylebox_override("panel",_panel_style(Color(0.055,0.09,0.12,0.86)))
	root.add_child(top)
	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation",24)
	top.add_child(header)
	var brand := VBoxContainer.new()
	brand.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	header.add_child(brand)
	brand.add_child(_label("ADASLab  /  DRIVE",23,Color("80e2cd")))
	connection_label = _label("Studio bağlantısı bekleniyor",12,Color("a7bcc5"))
	brand.add_child(connection_label)
	var right := VBoxContainer.new()
	right.alignment=BoxContainer.ALIGNMENT_CENTER
	header.add_child(right)
	mode_label=_label("AKTİF DESTEK",14,Color("a4e6d7"))
	right.add_child(mode_label)
	timer_label=_label("120 sn",13,Color("acbec7"))
	right.add_child(timer_label)
	pause_button=_button("Duraklat  /  Boşluk")
	pause_button.focus_mode=Control.FOCUS_NONE
	pause_button.pressed.connect(func():_action("pause"))
	header.add_child(pause_button)
	alert_panel=PanelContainer.new()
	alert_panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER_TOP)
	alert_panel.offset_left=-220;alert_panel.offset_right=220;alert_panel.offset_top=125;alert_panel.offset_bottom=177
	alert_panel.add_theme_stylebox_override("panel",_panel_style(Color(0.53,0.15,0.2,0.95),9))
	root.add_child(alert_panel)
	alert_label=_label("AEB  ·  ACİL FREN",20)
	alert_label.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER
	alert_panel.add_child(alert_label)
	var bottom := PanelContainer.new()
	bottom.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	bottom.offset_left=24;bottom.offset_right=-24;bottom.offset_top=-132;bottom.offset_bottom=-24
	bottom.add_theme_stylebox_override("panel",_panel_style(Color(0.055,0.09,0.12,0.91)))
	root.add_child(bottom)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation",22)
	bottom.add_child(row)
	speed_label=_readout(row,"HIZ","0 km/sa")
	gap_label=_readout(row,"TAKİP MESAFESİ","— m")
	ttc_label=_readout(row,"TTC","— sn")
	accel_label=_readout(row,"İVME / FREN","0 m/s²")
	score_label=_readout(row,"SÜRÜŞ PUANI","0")
	var help := _label("W / ↑  gaz     S / ↓  fren     A–D / ← →  şerit     C  kamera     Boşluk  duraklat",12,Color("e1e9e6"))
	help.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	help.offset_left=32;help.offset_top=-21
	root.add_child(help)
	pause_panel=PanelContainer.new()
	pause_panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	pause_panel.offset_left=-245;pause_panel.offset_right=245;pause_panel.offset_top=-170;pause_panel.offset_bottom=205
	pause_panel.add_theme_stylebox_override("panel",_panel_style(Color(0.055,0.09,0.12,0.95),15))
	root.add_child(pause_panel)
	var options := VBoxContainer.new()
	options.add_theme_constant_override("separation",12)
	pause_panel.add_child(options)
	pause_title=_label("Direksiyon sende",27)
	options.add_child(pause_title)
	pause_description=_label("ADAS kararları kartta, sürüş dünyası Studio’da.",13,Color("9eb6c2"))
	pause_description.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART
	options.add_child(pause_description)
	var mode_row := HBoxContainer.new()
	mode_row.add_theme_constant_override("separation",7)
	options.add_child(mode_row)
	for i in range(3):
		var button := _button(MODE_NAMES[i])
		button.size_flags_horizontal=Control.SIZE_EXPAND_FILL
		button.add_theme_font_size_override("font_size",13)
		button.pressed.connect(_setting.bind("mode",MODE_VALUES[i]))
		mode_row.add_child(button)
		mode_buttons.append(button)
	var target_row := HBoxContainer.new()
	target_row.add_theme_constant_override("separation",14)
	options.add_child(target_row)
	acc_button=CheckButton.new()
	acc_button.text="ACC"
	acc_button.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	acc_button.toggled.connect(func(value:bool):_setting("accEnabled",value))
	target_row.add_child(acc_button)
	target_row.add_child(_label("Hedef km/sa",13,Color("9eb6c2")))
	target_spin=SpinBox.new()
	target_spin.min_value=0;target_spin.max_value=200;target_spin.step=1
	target_spin.value=90
	target_spin.value_changed.connect(func(value:float):_setting("targetKmh",int(value)))
	target_row.add_child(target_spin)
	var seed_row := HBoxContainer.new()
	options.add_child(seed_row)
	var seed_label := _label("Trafik tohumu",13,Color("9eb6c2"))
	seed_label.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	seed_row.add_child(seed_label)
	seed_spin=SpinBox.new()
	seed_spin.min_value=1;seed_spin.max_value=9999;seed_spin.value=42
	seed_spin.value_changed.connect(func(value:float):_setting("seed",int(value)))
	seed_row.add_child(seed_spin)
	start_button=_button("Sürüşü başlat",true)
	start_button.pressed.connect(func():_action("start"))
	options.add_child(start_button)
	restart_button=_button("Aynı trafikle yeniden dene")
	restart_button.pressed.connect(func():_action("restart"))
	options.add_child(restart_button)
	_refresh_ui()

func _refresh_ui() -> void:
	if connection_label==null:return
	var running := bool(state.get("running",false)) and studio_connected
	var mode := String(state.get("mode","active"))
	var mode_index := MODE_VALUES.find(mode)
	mode_index=maxi(mode_index,0)
	var backend_label := "ARM simülasyonu · fiziksel kart kullanılmıyor" if backend == "ARM_SIM" else ("Kart bağlı · ADASLab v2" if bool(state.get("ready",false)) else "Kart bağlı · ADASLab v2 bekleniyor") if backend == "STM32_UART" else backend
	connection_label.text = backend_label if studio_connected else network_message
	connection_label.add_theme_color_override("font_color",Color("e2bc76") if demo else Color("9db7bf"))
	mode_label.text = MODE_NAMES[mode_index].to_upper()
	timer_label.text="%d sn  ·  %d m"%[int(ceil(float(state.get("remaining",120)))),int(state.get("distance",0))]
	speed_label.text="%.0f km/sa"%float(state.get("egoKmh",0))
	var gap := float(state.get("gap",-1))
	gap_label.text="%.1f m"%gap if gap>=0 else "— m"
	var ttc := float(state.get("ttc",-1))
	ttc_label.text="%.1f sn"%ttc if ttc>=0 and mode!="off" else "— sn"
	accel_label.text="%.2f m/s²"%float(state.get("accelMps2",0))
	score_label.text=str(int(state.get("score",0)))
	var emergency := bool(state.get("aeb",false)) and mode=="active"
	var warning := bool(state.get("warning",false)) and mode!="off"
	alert_panel.visible=running and (emergency or warning)
	alert_label.text="AEB  ·  ACİL FREN" if emergency else "ÖN ÇARPIŞMA UYARISI"
	var alert_style := 2 if emergency else 1 if warning else 0
	if styled_alert != alert_style:
		styled_alert = alert_style
		alert_panel.add_theme_stylebox_override("panel",_panel_style(Color(0.53,0.15,0.2,0.95) if emergency else Color(0.53,0.37,0.12,0.95),9))
	pause_panel.visible=not running
	pause_button.visible=running
	var status := String(state.get("status","ready"))
	pause_title.text="Çarpışma" if status=="collision" else "Sürüş tamamlandı" if status=="finished" else "Sürüş duraklatıldı" if status=="paused" else "Direksiyon sende"
	var game_ready := studio_connected and bool(state.get("ready",false))
	pause_description.text=("W / ↑ gaz · S / ↓ fren · A–D / oklar şerit. C ile kamera değiştir." if game_ready else String(state.get("hint","ADASLab v2 firmware’ine bağlanın."))) if studio_connected else network_message
	start_button.text="Sürüşe devam et" if status=="paused" else "Sürüşü başlat"
	start_button.disabled=not studio_connected or not bool(state.get("ready",false))
	restart_button.disabled=start_button.disabled
	sync_ui=true
	for i in range(mode_buttons.size()):
		mode_buttons[i].disabled=not game_ready or running
		if styled_mode != mode_index:
			mode_buttons[i].add_theme_stylebox_override("normal",_panel_style(Color("276459") if i==mode_index else Color("243b49"),8))
	styled_mode = mode_index
	acc_button.disabled=not game_ready or running or mode!="active"
	acc_button.button_pressed=bool(state.get("accEnabled",false))
	var settings_editable := game_ready and not running
	if target_spin.editable != settings_editable:target_spin.editable=settings_editable
	if not target_spin.get_line_edit().has_focus() and target_spin.value != float(state.get("targetKmh",90)):
		target_spin.value=float(state.get("targetKmh",90))
	if seed_spin.editable != settings_editable:seed_spin.editable=settings_editable
	if not seed_spin.get_line_edit().has_focus() and seed_spin.value != float(state.get("seed",42)):
		seed_spin.value=float(state.get("seed",42))
	sync_ui=false
