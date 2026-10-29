// ADAS following-distance carpet in the ego lane: translucent fill, soft side
// rails and chevrons that stay fixed to the asphalt while the car drives.
VARYING vec2 carpet;

void MAIN()
{
    float across = carpet.x;
    float along = carpet.y * span;
    float side = min(across, 1.0 - across) * 2.6;
    float rail = smoothstep(0.2, 0.03, side);
    float fade = smoothstep(0.0, 1.2, along) * (1.0 - smoothstep(span - 3.0, span, along));
    float wave = fract((along + phase) / 3.2 - abs(across - 0.5) * 0.9);
    float chevron = smoothstep(0.0, 0.06, wave) * smoothstep(0.26, 0.2, wave);
    float alpha = (0.07 + rail * 0.38 + chevron * 0.13) * fade * strength;
    FRAGCOLOR = vec4(tint * (1.0 + rail), alpha);
}
