extends Node3D
## Geometry is in metres. Longitudinal movement follows acknowledged Studio state.

var road_material: ShaderMaterial
var rolling: Array[Node3D] = []
var rolling_starts: Array[float] = []
var length := 520.0

func _ready() -> void:
	# No GPU resources are created by explicit headless control/protocol QA.
	if DisplayServer.get_name() == "headless":return
	_create_environment()
	_create_road()
	_create_scenery()

func material(color: Color, roughness: float = 0.9) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = roughness
	return mat

func box(size: Vector3, pos: Vector3, mat: Material, parent: Node3D = null) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = size
	var item := MeshInstance3D.new()
	item.mesh = mesh
	item.material_override = mat
	item.position = pos
	if parent == null:parent = self
	parent.add_child(item)
	return item

func _create_environment() -> void:
	# A generated panorama keeps the sky consistent across Metal and GL drivers.
	# The texture is created once; no per-frame image updates or downloaded HDRI.
	var panorama := Image.create(768,384,false,Image.FORMAT_RGB8)
	var clouds := FastNoiseLite.new()
	clouds.seed = 34171
	clouds.frequency = 0.022
	clouds.fractal_octaves = 4
	for y in range(384):
		var height := cos(float(y)/383.0*PI)
		for x in range(768):
			var color := Color("94bbd0").lerp(Color("2e6da1"),pow(maxf(height,0.0),0.45))
			if height<0.0:color=Color("60767b").lerp(Color("38483c"),-height)
			else:
				# Sample a sphere so longitude 0 and 2π match without a sky seam.
				var longitude := float(x)/767.0*TAU
				var radius := sqrt(maxf(0.0,1.0-height*height))
				var cloud := smoothstep(0.04,0.4,clouds.get_noise_3d(cos(longitude)*radius*160.0,height*160.0,sin(longitude)*radius*160.0))
				cloud*=smoothstep(0.025,0.22,height)*0.68
				color=color.lerp(Color("e4e9e7"),cloud)
			panorama.set_pixel(x,y,color)
	var sky_mat := PanoramaSkyMaterial.new()
	sky_mat.panorama = ImageTexture.create_from_image(panorama)
	var sky := Sky.new()
	sky.sky_material = sky_mat
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.32
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.tonemap_exposure = 0.85
	env.fog_enabled = true
	env.fog_light_color = Color("c5d2d6")
	env.fog_light_energy = 0.7
	env.fog_density = 0.0010
	env.fog_sky_affect = 0.08
	var world := WorldEnvironment.new()
	world.environment = env
	add_child(world)
	var sun := DirectionalLight3D.new()
	sun.name = "AfternoonSun"
	sun.rotation_degrees = Vector3(-34.0, -28.0, 0.0)
	sun.light_color = Color("fff1db")
	sun.light_energy = 0.85
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 170.0
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	sun.shadow_bias = 0.025
	sun.shadow_normal_bias = 1.0
	add_child(sun)

func _create_road() -> void:
	var road_surface: Material
	if DisplayServer.get_name() != "headless":
		var shader := Shader.new()
		shader.code = """shader_type spatial;
	render_mode cull_back;
	uniform float travelled = 0.0;
	varying vec3 point;
	float noise(vec2 p) { return fract(sin(dot(p, vec2(12.9898,78.233))) * 43758.5453); }
	void vertex() { point = (MODEL_MATRIX * vec4(VERTEX,1.0)).xyz; }
	void fragment() {
	 vec2 p = vec2(point.x, point.z - travelled);
	 float footprint = max(fwidth(p.x),fwidth(p.y));
	 float detail = 1.0 - smoothstep(0.008,0.06,footprint);
	 float grain = mix(0.5,noise(floor(p * 90.0)),detail);
	 vec3 asphalt = mix(vec3(0.105,0.118,0.126), vec3(0.165,0.172,0.173), grain);
	 float edge = 1.0 - smoothstep(0.055,0.078,abs(abs(p.x)-5.55));
	 float divider = 1.0 - smoothstep(0.055,0.080,abs(abs(p.x)-1.8));
	 float dash = step(6.0,mod(p.y,12.0));
	 float paint = max(edge,divider*dash);
	 ALBEDO = mix(asphalt, vec3(0.88,0.87,0.78),paint*0.94);
	 ROUGHNESS = mix(0.92,0.69,paint);
	}
	"""
		road_material = ShaderMaterial.new()
		road_material.shader = shader
		road_surface = road_material
	else:
		# The dummy renderer has no shader storage; headless QA tests control only.
		road_surface = material(Color("303b40"))
	box(Vector3(13.1,0.14,length),Vector3(0,-0.10,-length/2.0+35.0),road_surface)
	var shoulder := material(Color("555e56"))
	box(Vector3(0.7,0.08,length),Vector3(-6.8,-0.08,-225),shoulder)
	box(Vector3(0.7,0.08,length),Vector3(6.8,-0.08,-225),shoulder)
	var grass := material(Color("354c30"))
	box(Vector3(170,0.1,900),Vector3(-92,-0.18,-340),grass)
	box(Vector3(170,0.1,900),Vector3(92,-0.18,-340),grass)
	var rail_mat := material(Color("8c9898"),0.4)
	rail_mat.metallic = 0.5
	for side in [-1.0,1.0]:
		box(Vector3(0.11,0.30,length),Vector3(side*7.42,0.76,-225),rail_mat)
		box(Vector3(0.08,0.10,length),Vector3(side*7.42,0.41,-225),rail_mat)
		for i in range(44):
			var group := Node3D.new()
			add_child(group)
			group.position = Vector3(side*7.45,0,-float(i)*12.0)
			box(Vector3(0.10,0.94,0.12),Vector3(0,0.40,0),rail_mat,group)
			var reflector := material(Color("ffb859") if side<0 else Color("dce8dc"))
			reflector.emission_enabled = true
			reflector.emission = reflector.albedo_color*0.15
			box(Vector3(0.13,0.11,0.11),Vector3(0,0.86,0),reflector,group)
			rolling.append(group)
			rolling_starts.append(group.position.z)

func _create_scenery() -> void:
	var random := RandomNumberGenerator.new()
	random.seed = 938712
	var bark := material(Color("4e4b3c"))
	var green := [material(Color("1a382b")),material(Color("26452b")),material(Color("324f31"))]
	for i in range(80):
		var group := Node3D.new()
		add_child(group)
		var side := -1.0 if i%2==0 else 1.0
		group.position = Vector3(side*random.randf_range(13,48),0,-random.randf_range(0,length))
		var height := random.randf_range(4.0,8.0)
		var trunk := CylinderMesh.new()
		trunk.top_radius = 0.15
		trunk.bottom_radius = 0.24
		trunk.height = height*0.65
		var stem := MeshInstance3D.new()
		stem.mesh = trunk
		stem.material_override = bark
		stem.position.y = trunk.height/2
		group.add_child(stem)
		for crown_index in range(2):
			var crown := SphereMesh.new()
			crown.radial_segments = 12
			crown.rings = 8
			crown.radius = height*(0.26 if crown_index==0 else 0.21)
			crown.height = crown.radius*2.6
			var canopy := MeshInstance3D.new()
			canopy.mesh = crown
			canopy.material_override = green[i%green.size()]
			canopy.position = Vector3(0,height*(0.63 if crown_index==0 else 0.84),0)
			group.add_child(canopy)
		rolling.append(group)
		rolling_starts.append(group.position.z)
	# Large smooth hills give a stable distant horizon rather than a flat void.
	for i in range(13):
		var hill := SphereMesh.new()
		hill.radial_segments = 32
		hill.rings = 16
		hill.radius = random.randf_range(60,130)
		hill.height = hill.radius*1.5
		var rock := MeshInstance3D.new()
		rock.mesh = hill
		rock.material_override = material(Color("263f42").lerp(Color("5d777b"),float(i)/13.0))
		rock.scale = Vector3(1.7,0.7,1.5)
		rock.position = Vector3((-1.0 if i%2==0 else 1.0)*random.randf_range(160,390),-35.0,-random.randf_range(290,900))
		rock.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(rock)
	var gantry := Node3D.new()
	add_child(gantry)
	gantry.position.z = -145
	var metal := material(Color("596b6b"),0.5)
	for x in [-8.3,8.3]:box(Vector3(0.22,7.5,0.22),Vector3(x,3.7,0),metal,gantry)
	box(Vector3(16.8,0.24,0.24),Vector3(0,7.3,0),metal,gantry)
	box(Vector3(5.0,1.7,0.12),Vector3(0,6.65,-0.08),material(Color("254f49")),gantry)
	if DisplayServer.get_name() != "headless":
		var sign := Label3D.new()
		sign.text = "ADASLAB\nDRIVE  /  3 LANES"
		sign.font_size = 48
		sign.pixel_size = 0.009
		sign.position = Vector3(0,6.7,0.01)
		gantry.add_child(sign)
	rolling.append(gantry)
	rolling_starts.append(gantry.position.z)

func update_distance(distance: float) -> void:
	if road_material != null:road_material.set_shader_parameter("travelled",distance)
	for i in range(rolling.size()):
		rolling[i].position.z = fposmod(rolling_starts[i]+distance+length-35.0,length)-length+35.0
