// A blind zone on the asphalt beside the car: a soft fill inside a brighter rim.
VARYING vec2 carpet;

void MAIN()
{
    vec2 edge = min(carpet, 1.0 - carpet);
    float rim = smoothstep(0.1, 0.02, min(edge.x, edge.y * 2.2));
    float fade = smoothstep(0.0, 0.03, min(edge.x, edge.y));
    float alpha = (0.14 + rim * 0.5) * fade * strength;
    FRAGCOLOR = vec4(tint * (1.0 + rim * 0.6), alpha);
}
