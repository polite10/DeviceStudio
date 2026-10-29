extends Node3D
## Imported CC0 vehicle geometry. Only the display is animated here; no physics.

var body: Node3D
var wheel_pivots: Array[Dictionary] = []
var tail_materials: Array[StandardMaterial3D] = []
var last_roll := 0.0
static var scenes: Dictionary = {}

func configure(path: String, paint: Color, player: bool = false) -> void:
	body = Node3D.new()
	body.name = "VehicleModel"
	add_child(body)
	# Dummy/headless protocol QA keeps transform actors without GPU materials.
	if DisplayServer.get_name() == "headless":return
	if not ResourceLoader.exists(path):
		push_error("Vehicle asset is missing: " + path)
		return
	if not scenes.has(path):scenes[path] = load(path)
	var packed: PackedScene = scenes[path] as PackedScene
	var model: Node3D = packed.instantiate() as Node3D
	body.add_child(model)
	var bounds := _bounds(model,Transform3D.IDENTITY)
	var ratio := 4.6/maxf(bounds.size.z,0.1)
	# All supplied CC0 vehicles face +Z. The road direction is -Z.
	body.rotation.y = PI
	body.scale = Vector3.ONE*ratio
	model.position = Vector3(-bounds.get_center().x,-bounds.position.y,-bounds.get_center().z)
	_materials(model,paint)
	_find_wheels(model)
	if player:
		var shadow := MeshInstance3D.new()
		var plane := PlaneMesh.new()
		plane.size = Vector2(1.8,4.2)
		shadow.mesh = plane
		var mat := StandardMaterial3D.new()
		mat.albedo_color = Color(0.01,0.02,0.025,0.15)
		mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		shadow.material_override = mat
		shadow.position.y = 0.015
		shadow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(shadow)

func _bounds(node: Node3D, parent_transform: Transform3D) -> AABB:
	var transform_here := parent_transform*node.transform
	var result := AABB()
	var found := false
	if node is MeshInstance3D:
		result = transform_here*(node as MeshInstance3D).get_aabb()
		found = true
	for child in node.get_children():
		if child is Node3D:
			var part := _bounds(child as Node3D,transform_here)
			if part.size.length_squared()>0:
				result = result.merge(part) if found else part
				found = true
	return result

func _materials(node: Node, paint: Color) -> void:
	if node is MeshInstance3D:
		var item := node as MeshInstance3D
		for i in range(item.mesh.get_surface_count()):
			var original := item.get_active_material(i) as StandardMaterial3D
			if original == null:continue
			var mat := original.duplicate() as StandardMaterial3D
			var title := original.resource_name.to_lower()
			if title.contains("window") or title.contains("glass"):
				mat.albedo_color = Color("263c48")
				mat.metallic = 0.5
				mat.roughness = 0.16
			elif title.contains("taillight") or title.contains("tail_light"):
				mat.emission_enabled = true
				mat.emission = Color("9c1826")
				tail_materials.append(mat)
			elif title.contains("headlight"):
				mat.emission_enabled = true
				mat.emission = Color("fff5d6")*0.35
				mat.roughness = 0.15
			elif title in ["blue","white","orange","red","green","yellow"]:
				mat.albedo_color = paint
				mat.metallic = 0.38
				mat.roughness = 0.32
			elif title.contains("black"):
				mat.roughness = 0.9
			else:
				mat.roughness = minf(mat.roughness,0.55)
			item.set_surface_override_material(i,mat)
	for child in node.get_children():_materials(child,paint)

func _find_wheels(node: Node) -> void:
	# Wheel pivots are recentered on mesh bounds, including the combined rear axle.
	# Rotating the original origin would otherwise swing the axle around the car.
	var children := node.get_children()
	for child in children:
		if child is MeshInstance3D and String(child.name).to_lower().contains("wheel"):
			var mesh := child as MeshInstance3D
			var center := mesh.to_global(mesh.get_aabb().get_center())
			var pivot := Node3D.new()
			body.add_child(pivot)
			pivot.global_position = center
			var front := String(child.name).to_lower().contains("front")
			mesh.reparent(pivot,true)
			wheel_pivots.append({"pivot":pivot,"front":front,"roll":0.0})
		else:_find_wheels(child)

func animate(delta: float, travelled: float, braking: bool, accel: float, steering: float) -> void:
	if body == null:return
	body.rotation.x = lerpf(body.rotation.x,clampf(accel*0.006,-0.045,0.025),1.0-exp(-delta*7.0))
	for data in wheel_pivots:
		var pivot: Node3D = data.pivot
		data.roll = float(data.roll)+travelled/0.32
		pivot.rotation.x = float(data.roll)
		pivot.rotation.y = steering if data.front else 0.0
	for mat in tail_materials:
		mat.emission = Color("ff233c")*(1.7 if braking else 0.12)
