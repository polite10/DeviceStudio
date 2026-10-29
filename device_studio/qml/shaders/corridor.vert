VARYING vec2 carpet;

void MAIN()
{
    carpet = UV0;
    POSITION = MODELVIEWPROJECTION_MATRIX * vec4(VERTEX, 1.0);
}
