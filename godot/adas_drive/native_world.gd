extends RefCounted
## Fixed-step traffic only. Every acceleration request comes from the watch.
var config: Dictionary
var rng := RandomNumberGenerator.new()
var tick := 0
var ego := 50.0/3.6
var distance := 0.0
var lane := 1.0
var target_lane := 1
var collision := false
var acceleration := 0.0
var cars: Array[Dictionary] = []
var next_id := 5
var next_spawn := 6000
var cutin := false
var warnings := 0
var interventions := 0
var near_misses: Dictionary = {}
var warning_before := false
var aeb_before := false
var hard_brakes := 0
const LENGTH := 4.6
const DT := 0.05
func _init(options: Dictionary) -> void:
	config=options.duplicate(true);rng.seed=int(config.get("seed",42))
	cars=[_car(1,1.0,65.0,55.0/3.6),_car(2,0.0,38.0,65.0/3.6),_car(3,2.0,100.0,48.0/3.6),_car(4,2.0,170.0,70.0/3.6)]
func _car(id:int,row:float,z:float,speed:float)->Dictionary:
	return {"id":id,"lane":row,"z":z,"speed":speed,"braking":false,"target":-1.0}
func finished()->bool:return collision or tick>=120000
func steer(delta:int)->void:target_lane=clampi(target_lane+delta,0,2)
func front()->Dictionary:
	var nearest:Dictionary={}
	for car in cars:
		if float(car.z)<distance:continue
		if absf(float(car.lane)-lane)>=0.56 and not (absf(lane-target_lane)>0.01 and absf(float(car.lane)-target_lane)<0.56):continue
		if nearest.is_empty() or float(car.z)<float(nearest.z):nearest=car
	return nearest
static func crc16(body:String)->int:
	var crc:int=65535
	for byte in body.to_ascii_buffer():
		crc^=int(byte)<<8
		for bit in range(8):crc=((crc<<1)^(0x1021 if crc&0x8000 else 0))&65535
	return crc
func command(pedals:Dictionary)->String:
	var car=front();var gap:float=maxf(0.0,float(car.z)-distance-LENGTH) if not car.is_empty() else 1000.0
	var acc:bool=bool(config.acc) and int(config.mode)==0 and not pedals.gas and not pedals.brake
	var flags:int=int(not car.is_empty())+int(acc)*2+8
	var body:String="T:%d:%d:%d:%d:%d"%[tick,roundi(ego*100.0),roundi(float(car.speed)*100.0) if not car.is_empty() else 0,roundi(minf(gap,1000.0)*100.0),flags]
	return body+":"+str(crc16(body))
func advance(control:Dictionary,pedals:Dictionary)->bool:
	if finished():return true
	var value=control.get("a")
	if not (value is int or value is float) or float(value)!=floor(float(value)) or float(value)<-850 or float(value)>200:return false
	var warning:bool=bool(control.get("warn",false)) and int(config.mode)!=2
	var aeb:bool=int(config.mode)==0 and str(control.get("mode",""))=="AEB"
	if warning and not warning_before:warnings+=1
	if aeb and not aeb_before:interventions+=1
	warning_before=warning;aeb_before=aeb
	var manual:float=-8.0 if pedals.brake else 2.8 if pedals.gas else -0.35
	if int(config.mode)==0 and config.acc and not pedals.gas and not pedals.brake:manual=float(value)/100.0
	var applied:float=minf(manual,float(value)/100.0) if aeb else manual
	if applied<-5.0 and acceleration>=-5.0:hard_brakes+=1
	acceleration=applied
	var old_distance:float=distance;var old_lane:float=lane;var old_speed:float=ego
	ego=clampf(ego+applied*DT,0.0,60.0);distance+=(old_speed+ego)*0.5*DT
	lane+=clampf(target_lane-lane,-2.4*DT,2.4*DT)
	if tick>=10000 and not cutin:
		cutin=true
		for car in cars:
			if int(car.id)==3 and float(car.z)-distance>15.0:car.target=1.0
	for car in cars:
		var old_z:float=float(car.z);var old_row:float=float(car.lane)
		car.braking=int(car.id)==1 and tick>=3000 and tick<7000 and float(car.speed)>2.0
		if car.braking:car.speed=maxf(2.0,float(car.speed)-6.0*DT)
		car.z=float(car.z)+float(car.speed)*DT
		if float(car.target)>=0:car.lane=float(car.lane)+clampf(float(car.target)-float(car.lane),-0.6*DT,0.6*DT)
		for fraction in [0.25,0.5,0.75,1.0]:
			var ez:float=lerpf(old_distance,distance,fraction);var el:float=lerpf(old_lane,lane,fraction)
			if absf(lerpf(old_z,float(car.z),fraction)-ez)<LENGTH and absf(lerpf(old_row,float(car.lane),fraction)-el)<0.52:collision=true
		var gap:float=float(car.z)-distance-LENGTH
		if not collision and gap>0 and gap<8.0 and absf(float(car.lane)-lane)<0.56:near_misses[int(car.id)]=true
	tick+=50
	var keep:Array[Dictionary]=[]
	for car in cars:
		if float(car.z)-distance>-45.0:keep.append(car)
	cars=keep
	if tick>=next_spawn and cars.size()<12:
		next_spawn+=6000
		var row:int=rng.randi_range(0,2);var z:float=distance+rng.randf_range(145.0,210.0);var clear:=true
		for car in cars:
			if absf(float(car.z)-z)<=30.0 and absf(float(car.lane)-row)<=0.6:clear=false
		if clear:cars.append(_car(next_id,row,z,rng.randf_range(45.0,85.0)/3.6));next_id+=1
	return true
func snapshot(control:Dictionary)->Dictionary:
	var traffic:Array[Dictionary]=[]
	for car in cars:traffic.append({"id":car.id,"lane":car.lane,"relativeZ":float(car.z)-distance,"speedKmh":float(car.speed)*3.6,"braking":car.braking})
	var lead=front();var gap:float=maxf(0,float(lead.z)-distance-LENGTH) if not lead.is_empty() else -1.0
	return {"elapsed":tick/1000.0,"remaining":maxf(0,120-tick/1000.0),"distance":distance,"egoKmh":ego*3.6,"egoLane":lane,"targetLane":target_lane,"accelMps2":acceleration,"gap":gap,"ttc":float(control.get("ttc",-1))/1000.0 if float(control.get("ttc",-1))>=0 and int(config.mode)!=2 else -1.0,"warning":bool(control.get("warn",false)) and int(config.mode)!=2,"aeb":str(control.get("mode",""))=="AEB" and int(config.mode)==0,"traffic":traffic,"score":maxi(0,roundi(distance*2)-near_misses.size()*50-int(collision)*500-hard_brakes*5),"collisions":int(collision),"nearMisses":near_misses.size(),"warnings":warnings,"interventions":interventions,"reactionMs":-1}
