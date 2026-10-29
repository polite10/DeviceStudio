extends SceneTree
const World=preload("res://native_world.gd")
var count:=0
var failures:=0
func check(value:bool,name:String)->void:
	count+=1
	if not value:failures+=1;push_error(name)
	else:print("PASS: "+name)
func world(mode:int=0,acc:bool=false)->RefCounted:return World.new({"mode":mode,"acc":acc,"target":2500,"headway":1800,"seed":42})
func _initialize()->void:
	_watchdog.call_deferred()
	var input={"gas":true,"brake":false};var w=world();var normal={"a":0,"mode":"MONITOR","warn":false,"ttc":-1}
	var command:String=w.command(input);var fields=command.split(":")
	check(command.length()<=39 and fields.size()==7 and int(fields[6])==World.crc16(command.substr(0,command.rfind(":"))),"Native samples obey bounded CRC protocol")
	check(int(fields[4])==6040,"Range is measured between bumpers")
	w.cars.assign([{"id":1,"lane":0.0,"z":8.0,"speed":0.0,"braking":false,"target":-1.0},{"id":2,"lane":1.0,"z":30.0,"speed":0.0,"braking":false,"target":-1.0}])
	check(int(w.front().id)==2,"Adjacent lane excluded from front target")
	w.steer(-1);check(int(w.front().id)==1,"Requested destination lane enters front target")
	w=world();var speed:float=w.ego
	check(w.advance({"a":-850,"mode":"AEB","warn":true,"ttc":1000},input) and w.ego<speed and w.acceleration==-8.5,"MCU emergency brake overrides held gas")
	for mode in [1,2]:
		w=world(mode);w.advance({"a":0,"mode":"WARNING","warn":true,"ttc":1000},input)
		check(w.acceleration==2.8 and w.interventions==0,"Unassisted modes leave actuation to the driver")
	w=world();w.advance(normal,{"gas":true,"brake":true});check(w.acceleration==-8.0,"Driver brake wins over gas")
	w=world(0,true);w.advance({"a":100,"mode":"ACC","warn":false}, {"gas":false,"brake":false});check(w.acceleration==1.0,"ACC applies only MCU acceleration")
	w=world();check(not w.advance({"a":201,"mode":"ACC"},input) and w.tick==0,"Invalid MCU acceleration cannot advance physics")
	w=world();w.ego=59.99;w.cars.clear();w.advance(normal,input);check(w.ego==60.0 and int(w.command(input).split(":")[2])==6000,"Watch maximum speed stays inside protocol limits")
	w=world();w.cars.assign([{"id":1,"lane":1.0,"z":4.0,"speed":0.0,"braking":false,"target":-1.0}]);w.advance(normal,input)
	check(w.collision,"Vehicle footprint collision is detected")
	var tick:int=w.tick;w.advance(normal,input);check(w.tick==tick,"Finished road cannot keep advancing")
	var first=world();var second=world();first.cars.clear();second.cars.clear()
	for i in range(160):first.advance(normal,input);second.advance(normal,input)
	check(first.snapshot(normal)==second.snapshot(normal),"Seeded native traffic replays deterministically")
	print("NATIVE_WORLD_TEST "+JSON.stringify({"passed":failures==0,"checks":count,"failures":failures}))
	quit(0 if failures==0 else 1)

func _watchdog()->void:
	await create_timer(3.0).timeout
	push_error("Native world test did not finish")
	quit(1)
