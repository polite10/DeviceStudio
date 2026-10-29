// Motorway surface in world metres: x across the road, s along travel.
// Both carriageways share one cross-section; the oncoming side is mirrored
// around x = -14 m. Markings are procedural so they stay sharp at any range.

float band(float x, float lo, float hi, float w)
{
    return smoothstep(lo - w, lo + w, x) - smoothstep(hi - w, hi + w, x);
}

void MAIN()
{
    vec3 world = VAR_WORLD_POSITION;
    bool oncoming = world.x < -7.0;
    float lx = oncoming ? -14.0 - world.x : world.x;
    float s = scroll - world.z;
    float wx = max(fwidth(lx), 0.0004) * 0.7;
    float ws = max(fwidth(s), 0.0004) * 0.7;

    // Each lane and shoulder is a separate paving strip.
    float strip = floor((lx + 5.4) / 3.6);
    vec2 uv = vec2(lx / 3.6 + 0.5, s / 3.6 + strip * 0.37 + (oncoming ? 0.53 : 0.0));
    vec3 asphalt = pow(texture(asphaltMap, uv).rgb, vec3(2.2)) * asphaltTint;
    vec3 bumps = texture(asphaltNormal, uv).xyz * 2.0 - 1.0;
    float roughness = 0.9;

    // Rubber-darkened, polished wheel paths and an oil line in every lane.
    float inLane = band(lx, -5.4, 5.4, wx);
    float q = mod(lx + 5.4, 3.6) - 1.8;
    float track = exp(-pow((abs(q) - 0.86) / 0.3, 2.0)) * inLane;
    float drip = exp(-pow(q / 0.22, 2.0)) * inLane;
    asphalt *= 1.0 - 0.17 * track - 0.1 * drip;
    roughness -= 0.3 * track;

    // Older, dustier shoulders and median; loose gravel beyond the edge.
    asphalt = mix(asphalt, asphalt * vec3(1.18, 1.16, 1.12), 1.0 - inLane);
    float verge = smoothstep(8.35, 8.5, lx);
    asphalt = mix(asphalt, asphalt * vec3(1.75, 1.68, 1.55), verge);
    roughness = mix(roughness, 0.97, verge);

    // Milled rumble strip on the outer shoulder; averaged where it would alias.
    float rumble = band(lx, 5.95, 6.35, wx);
    float groove = band(mod(s, 0.5), 0.0, 0.18, ws);
    asphalt *= 1.0 - rumble * mix(0.13, 0.4 * groove, smoothstep(0.16, 0.06, ws));

    // Solid edge lines; 4 m dashes every 12 m between lanes.
    float edge = band(lx, -5.6, -5.42, wx) + band(lx, 5.42, 5.62, wx);
    float d = mod(s, 12.0);
    float dash = smoothstep(-ws, ws, d) - smoothstep(4.0 - ws, 4.0 + ws, d) + smoothstep(12.0 - ws, 12.0 + ws, d);
    float divider = (band(lx, -1.875, -1.725, wx) + band(lx, 1.725, 1.875, wx)) * dash;
    float paint = clamp(edge + divider, 0.0, 1.0);
    paint *= 0.8 + 0.2 * smoothstep(0.2, 0.5, texture(asphaltMap, uv * 2.7).g);
    vec3 color = mix(asphalt, vec3(0.8, 0.8, 0.77) * paintLevel, paint);
    roughness = mix(roughness, 0.5, paint);

    float strength = mix(0.6, 0.15, paint);
    NORMAL = normalize(vec3(bumps.x * strength, 1.0, -bumps.y * strength));
    BASE_COLOR = vec4(color, 1.0);
    ROUGHNESS = clamp(roughness, 0.3, 1.0);
    METALNESS = 0.0;
}
