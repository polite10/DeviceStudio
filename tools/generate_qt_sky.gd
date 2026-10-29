extends SceneTree

# Bake the same seamless procedural panorama used by the Godot renderer.
# This is an asset generation tool; Studio itself needs only Qt Quick 3D.
func _initialize() -> void:
	var output := OS.get_cmdline_user_args()[0]
	var panorama := Image.create(768, 384, false, Image.FORMAT_RGB8)
	var clouds := FastNoiseLite.new()
	clouds.seed = 34171
	clouds.frequency = 0.022
	clouds.fractal_octaves = 4
	for y in range(384):
		var height := cos(float(y) / 383.0 * PI)
		for x in range(768):
			var color := Color("94bbd0").lerp(Color("2e6da1"), pow(maxf(height, 0.0), 0.45))
			if height < 0.0:
				color = Color("60767b").lerp(Color("38483c"), -height)
			else:
				var longitude := float(x) / 767.0 * TAU
				var radius := sqrt(maxf(0.0, 1.0 - height * height))
				var cloud := smoothstep(0.04, 0.4, clouds.get_noise_3d(cos(longitude) * radius * 160.0, height * 160.0, sin(longitude) * radius * 160.0))
				cloud *= smoothstep(0.025, 0.22, height) * 0.68
				color = color.lerp(Color("e4e9e7"), cloud)
			panorama.set_pixel(x, y, color)
	var result := panorama.save_png(output)
	quit(result)
