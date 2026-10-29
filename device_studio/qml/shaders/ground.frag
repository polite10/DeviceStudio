// Roadside grass, embankments and distant farmland in world metres.
// The detail texture repeats every 4 m; a 400 m macro map breaks the tiling
// and lays out farmland parcels away from the motorway.

void MAIN()
{
    vec3 world = VAR_WORLD_POSITION;
    vec2 p = vec2(world.x, scroll - world.z);
    vec3 grass = pow(texture(grassMap, p / 4.0).rgb, vec3(2.2));
    vec3 macro = texture(macroMap, p / 400.0).rgb;
    float roadside = world.x > -7.0 ? world.x - 9.2 : -23.2 - world.x;

    grass *= mix(0.78, 1.16, macro.r);
    // Dry, yellowed patches vary over tens of metres instead of per tile.
    grass = mix(grass, grass * vec3(1.35, 1.15, 0.72), smoothstep(0.55, 0.8, macro.b) * 0.6);
    float detail = clamp(dot(grass, vec3(0.3, 0.59, 0.11)) / 0.09, 0.6, 1.45);

    float g = macro.g;
    vec3 crop = g < 0.22 ? vec3(0.11, 0.19, 0.045)
              : g < 0.47 ? vec3(0.42, 0.34, 0.14)
              : g < 0.53 ? vec3(0.19, 0.14, 0.09)
              : g < 0.75 ? vec3(0.17, 0.115, 0.07)
              : vec3(0.08, 0.13, 0.04);
    float rows = 0.9 + 0.1 * sin(p.x * 3.2 + g * 40.0);
    rows = mix(rows, 0.9, smoothstep(0.3, 1.0, fwidth(p.x * 3.2)));
    vec3 field = crop * mix(0.85, 1.15, macro.b) * detail * rows;
    vec3 color = mix(grass, field, smoothstep(40.0, 110.0, roadside));

    // Gravel and dust right next to the paved edge.
    vec3 gravel = vec3(0.2, 0.19, 0.17) * detail;
    color = mix(gravel, color, smoothstep(0.2, 1.1, roadside));

    BASE_COLOR = vec4(color * groundTint, 1.0);
    ROUGHNESS = 0.96;
    METALNESS = 0.0;
}
