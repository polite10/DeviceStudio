pragma ComponentBehavior: Bound
import QtQuick
import QtQuick3D

Node {
    id: vehicle
    property int variant: 0
    property color paint: "#39bda9"
    property bool braking: false
    property real wheelAngle: 0
    readonly property var sources: ["assets/vehicles/sedan/NormalCar1.qml", "assets/vehicles/suv/Suv.qml", "assets/vehicles/sports/SportsCar.qml", "assets/vehicles/taxi/Taxi.qml"]
    // All cars share a 4.6 m collision envelope with the firmware traffic plant.
    readonly property var lengths: [4.22071, 4.20935, 3.96871, 4.22072]
    eulerRotation.y: 180
    scale: Qt.vector3d(4.6 / lengths[variant], 4.6 / lengths[variant], 4.6 / lengths[variant])
    Loader3D {
        id: mesh
        source: vehicle.sources[vehicle.variant]
    }
    Binding { target: mesh.item; property: "paint"; value: vehicle.paint; when: mesh.item !== null }
    Binding { target: mesh.item; property: "braking"; value: vehicle.braking; when: mesh.item !== null }
    Binding { target: mesh.item; property: "wheelAngle"; value: vehicle.wheelAngle; when: mesh.item !== null }
}
