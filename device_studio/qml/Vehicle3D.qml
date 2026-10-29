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
    property real bodyPitch: 0
    property real bodyRoll: 0
    // -1 left, 1 right. Every car blinks on the shared relay phase.
    property int indicator: 0
    property bool blinkOn: false
    readonly property var sources: ["assets/vehicles/sedan/NormalCar1.qml", "assets/vehicles/suv/Suv.qml",
        "assets/vehicles/sports/SportsCar.qml", "assets/vehicles/taxi/Taxi.qml", "assets/vehicles/sports2/SportsCar2.qml"]
    // Source bounds in metres (mesh-notes.json): length, z centre, half width, height.
    readonly property var specs: [[4.22071, 0.003, 0.904, 1.183], [4.20935, 0.0, 1.056, 1.51], [3.96871, 0.0, 0.902, 1.145],
        [4.22072, 0.1035, 0.904, 1.3], [3.92700, -0.0655, 0.936, 1.187]]
    readonly property var spec: specs[Math.max(0, Math.min(specs.length - 1, variant))]
    // All cars share a 4.6 m collision envelope with the firmware traffic plant.
    readonly property real fit: 4.6 / spec[0]
    readonly property real halfWidth: spec[2] * fit
    readonly property real height: spec[3] * fit
    eulerRotation.y: 180

    Model {
        // Soft contact shadow grounds the car where the sun's shadow is thin.
        source: "#Rectangle"
        y: 0.025
        eulerRotation.x: -90
        scale: Qt.vector3d(vehicle.halfWidth * 2.5 / 100, 5.15 / 100, 1)
        castsShadows: false
        receivesShadows: false
        materials: PrincipledMaterial {
            lighting: PrincipledMaterial.NoLighting
            baseColor: "#000000"
            baseColorMap: Texture { source: "assets/fx/contact_shadow.png" }
            alphaMode: PrincipledMaterial.Blend
            opacity: 0.72
        }
    }
    Node {
        z: -vehicle.spec[1] * vehicle.fit
        scale: Qt.vector3d(vehicle.fit, vehicle.fit, vehicle.fit)
        Loader3D {
            id: mesh
            source: vehicle.sources[Math.max(0, Math.min(vehicle.sources.length - 1, vehicle.variant))]
        }
    }
    Binding { target: mesh.item; property: "paint"; value: vehicle.paint; when: mesh.item !== null }
    Binding { target: mesh.item; property: "metallic"; value: vehicle.metallic; when: mesh.item !== null }
    Binding { target: mesh.item; property: "braking"; value: vehicle.braking; when: mesh.item !== null }
    Binding { target: mesh.item; property: "lamps"; value: vehicle.lamps; when: mesh.item !== null }
    Binding { target: mesh.item; property: "wheelAngle"; value: vehicle.wheelAngle; when: mesh.item !== null }
    Binding { target: mesh.item; property: "bodyPitch"; value: vehicle.bodyPitch; when: mesh.item !== null }
    Binding { target: mesh.item; property: "bodyRoll"; value: vehicle.bodyRoll; when: mesh.item !== null }

    PrincipledMaterial {
        id: amber
        baseColor: "#ffb02e"
        emissiveFactor: Qt.vector3d(7, 3.4, 0.35)
        lighting: PrincipledMaterial.NoLighting
    }
    // Indicator lamps: car-local +X is the driver's left after the 180° turn.
    Repeater3D {
        model: [[1, 1], [1, -1], [-1, 1], [-1, -1]]
        delegate: Model {
            required property var modelData
            source: "#Sphere"
            visible: vehicle.blinkOn && vehicle.indicator !== 0 && vehicle.indicator === -modelData[0]
            x: modelData[0] * (vehicle.halfWidth - 0.3)
            y: vehicle.height * (modelData[1] > 0 ? 0.5 : 0.58)
            z: modelData[1] * 2.2
            scale: Qt.vector3d(0.0012, 0.0007, 0.0007)
            castsShadows: false
            materials: amber
        }
    }
}
