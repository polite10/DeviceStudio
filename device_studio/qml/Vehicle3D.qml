pragma ComponentBehavior: Bound
import QtQuick
import QtQuick3D

Node {
    id: vehicle
    property int variant: 0
    property color paint: "#39bda9"
    property real metallic: 0.5
    property bool braking: false
    property real lamps: 0.35
    property real wheelAngle: 0
    // Yaw of the front wheels in degrees; positive turns them to the car's left.
    property real steerAngle: 0
    property real bodyPitch: 0
    property real bodyRoll: 0
    // -1 left, 1 right. Every car blinks on the shared relay phase.
    property int indicator: 0
    property bool blinkOn: false
    // Flying cars: height above the road (the contact shadow stays down and
    // fades) and a turn about the long axis through the body centre.
    property real altitude: 0
    property real flip: 0
    // Compressed-air nozzles and the pop-up wing of the Roadster (variant 7):
    // lift share, rear and nose pushes, and the signed sideways push.
    property real thrust: 0
    property real boost: 0
    property real retro: 0
    property real side: 0
    property real wing: 0
    readonly property bool jets: variant === 7
    // Traffic (tools/build_traffic_models.py): sedan, SUV, hatchback, taxi, light van;
    // then the player's cars: Şahin, Model 3, Taklacı Güvercin.
    readonly property var sources: ["assets/vehicles/sedan/Sedan.qml", "assets/vehicles/suv/Suv.qml",
        "assets/vehicles/hatch/Hatch.qml", "assets/vehicles/taxi/Taxi.qml", "assets/vehicles/van/Van.qml",
        "assets/vehicles/sahin/Sahin.qml", "assets/vehicles/model3/Model3.qml", "assets/vehicles/roadster/Roadster.qml"]
    // Source bounds in metres (mesh-notes.json and the tools/build_*_model.py reports):
    // length, z centre, half width, height; optionally indicator front/rear height and
    // front/rear x, then front/rear z from the body centre (default ±2.2 after fitting).
    readonly property var specs: [[4.575, -0.004, 0.899, 1.474, 0.730, 0.930, 0.836, 0.859, 2.112, -2.114],
        [4.523, -0.006, 0.934, 1.692, 0.900, 1.040, 0.883, 0.900, 2.051, -2.053],
        [4.074, -0.006, 0.888, 1.443, 0.730, 0.905, 0.773, 0.815, 1.917, -1.878],
        [4.575, -0.004, 0.899, 1.630, 0.730, 0.930, 0.836, 0.859, 2.112, -2.114],
        [4.425, -0.006, 0.968, 1.888, 0.855, 0.915, 0.863, 0.860, 2.088, -2.141],
        [4.53, 0.005, 0.83, 1.395, 0.588, 0.7, 0.775, 0.468],
        [4.708, 0.005, 0.92, 1.443, 0.729, 0.928, 0.776, 0.793, 2.011, -2.14],
        [4.566, 0.019, 0.99, 1.129, 0.31, 0.913, 0.963, 0.9, 2.037, -2.039]]
    readonly property var spec: specs[Math.max(0, Math.min(specs.length - 1, variant))]
    // True lengths, matching the traffic plant's footprints (game_sim.TRAFFIC / VEHICLES).
    readonly property var lengths: [4.55, 4.5, 4.05, 4.55, 4.4, 4.316, 4.72, 4.566]
    readonly property real length: lengths[Math.max(0, Math.min(lengths.length - 1, variant))]
    readonly property real fit: length / spec[0]
    readonly property real halfWidth: spec[2] * fit
    readonly property real height: spec[3] * fit
    // The loaded car model; the Roadster lists its nozzle exits for the jet particles.
    readonly property var loaded: mesh.item
    eulerRotation.y: 180

    Model {
        // Soft contact shadow grounds the car where the sun's shadow is thin.
        source: "#Rectangle"
        y: 0.025
        eulerRotation.x: -90
        scale: Qt.vector3d(vehicle.halfWidth * 2.5 / 100, vehicle.length * 1.12 / 100, 1)
        visible: vehicle.altitude < 5
        castsShadows: false
        receivesShadows: false
        materials: PrincipledMaterial {
            lighting: PrincipledMaterial.NoLighting
            baseColor: "#000000"
            baseColorMap: Texture { source: "assets/fx/contact_shadow.png" }
            alphaMode: PrincipledMaterial.Blend
            opacity: 0.72 * Math.max(0, 1 - vehicle.altitude / 5)
        }
    }
    Node {
        // The pivot also offsets the children, so the position adds it back.
        y: vehicle.altitude + vehicle.height / 2
        pivot: Qt.vector3d(0, vehicle.height / 2, 0)
        eulerRotation.z: vehicle.flip
        Node {
            z: -vehicle.spec[1] * vehicle.fit
            scale: Qt.vector3d(vehicle.fit, vehicle.fit, vehicle.fit)
            Loader3D {
                id: mesh
                source: vehicle.sources[Math.max(0, Math.min(vehicle.sources.length - 1, vehicle.variant))]
            }
        }
        // Indicator lamps: car-local +X is the driver's left after the 180° turn.
        Repeater3D {
            model: [[1, 1], [1, -1], [-1, 1], [-1, -1]]
            delegate: Model {
                required property var modelData
                source: "#Sphere"
                visible: vehicle.blinkOn && vehicle.indicator !== 0 && vehicle.indicator === -modelData[0]
                x: modelData[0] * (vehicle.spec.length > 4 ? vehicle.spec[modelData[1] > 0 ? 6 : 7] * vehicle.fit : vehicle.halfWidth - 0.3)
                y: vehicle.spec.length > 4 ? vehicle.spec[modelData[1] > 0 ? 4 : 5] * vehicle.fit : vehicle.height * (modelData[1] > 0 ? 0.5 : 0.58)
                z: vehicle.spec.length > 8 ? vehicle.spec[modelData[1] > 0 ? 8 : 9] * vehicle.fit : modelData[1] * 2.2
                scale: Qt.vector3d(0.0012, 0.0007, 0.0007)
                castsShadows: false
                materials: amber
            }
        }
    }
    Binding { target: mesh.item; property: "paint"; value: vehicle.paint; when: mesh.item !== null }
    Binding { target: mesh.item; property: "metallic"; value: vehicle.metallic; when: mesh.item !== null }
    Binding { target: mesh.item; property: "braking"; value: vehicle.braking; when: mesh.item !== null }
    Binding { target: mesh.item; property: "lamps"; value: vehicle.lamps; when: mesh.item !== null }
    Binding { target: mesh.item; property: "wheelAngle"; value: vehicle.wheelAngle; when: mesh.item !== null }
    Binding { target: mesh.item; property: "steerAngle"; value: vehicle.steerAngle; when: mesh.item !== null }
    Binding { target: mesh.item; property: "bodyPitch"; value: vehicle.bodyPitch; when: mesh.item !== null }
    Binding { target: mesh.item; property: "bodyRoll"; value: vehicle.bodyRoll; when: mesh.item !== null }
    Binding { target: mesh.item; property: "thrust"; value: vehicle.thrust; when: vehicle.jets && mesh.item !== null && "thrust" in mesh.item }
    Binding { target: mesh.item; property: "boost"; value: vehicle.boost; when: vehicle.jets && mesh.item !== null && "thrust" in mesh.item }
    Binding { target: mesh.item; property: "retro"; value: vehicle.retro; when: vehicle.jets && mesh.item !== null && "thrust" in mesh.item }
    Binding { target: mesh.item; property: "side"; value: vehicle.side; when: vehicle.jets && mesh.item !== null && "thrust" in mesh.item }
    Binding { target: mesh.item; property: "wing"; value: vehicle.wing; when: vehicle.jets && mesh.item !== null && "thrust" in mesh.item }

    PrincipledMaterial {
        id: amber
        baseColor: "#ffb02e"
        emissiveFactor: Qt.vector3d(7, 3.4, 0.35)
        lighting: PrincipledMaterial.NoLighting
    }
}
