# Embedded 3D cars

All cars are original models built in Blender with no logos or badges, then
converted with the installed PySide6 Balsam importer. Every wrapper QML shares
one contract: clear-coated `paint`, `metallic`, `lamps`, `braking`,
`wheelAngle` and body `bodyPitch`/`bodyRoll`. Models face +Z in metres;
Vehicle3D turns them toward the road's -Z.

Traffic: `hatch/`, `sedan/`, `suv/`, `van/` and `taxi/` are the body styles of
the plant's traffic mix at their real sizes (Renault Clio, Fiat Egea sedan,
Togg T10X / Hyundai Tucson, Fiat Doblo classes and a yellow Istanbul taxi).
`tools/traffic_blender.py` models them from each style's dimensions and side
lines; `tools/build_traffic_models.py` converts them and writes the QML.

`sahin/` and `model3/` are the selectable ego cars, a boxy 1980s Turkish saloon
and a Tesla Model 3 style electric saloon. `tools/sahin_blender.py` and
`tools/model3_blender.py` build them in Blender; `tools/build_sahin_model.py`
and `tools/build_model3_model.py` write `Sahin.qml` and `Model3.qml`. Both also
drive in traffic.

`roadster/` is the flying ego car (Tesla Taklacı Güvercin), an original model of
the 2028 Tesla Roadster as revealed in October 2026. `tools/roadster_blender.py`
builds it and `tools/build_roadster_model.py` writes `Roadster.qml`, which adds
`thrust`, `boost`, `retro`, `side` (frosting nozzles), `wing` (pop-up tail wing)
and the nozzle exits that Drive3DView emits its compressed-air jets from. It is
not used in traffic.
