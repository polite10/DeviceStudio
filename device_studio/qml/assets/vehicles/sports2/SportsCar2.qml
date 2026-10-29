import QtQuick
import QtQuick3D

Node {
    id: root
    objectName: "Root"

    property color paint: "#42bfa7"
    property real metallic: 0.5
    property bool braking: false
    // Daytime running and tail lamp glow; brake lamps are always brighter.
    property real lamps: 0.35
    property real wheelAngle: 0
    // Suspension: the body pitches/rolls around its centre, wheels stay grounded.
    property real bodyPitch: 0
    property real bodyRoll: 0
    // Source FBX uses centimetres; the scene uses metres.
    scale: Qt.vector3d(0.01, 0.01, 0.01)

    // Resources
    PrincipledMaterial {
        id: white_material
        objectName: "White"
        baseColor: root.paint
        metalness: root.metallic
        roughness: 0.42 - root.metallic * 0.12
        clearcoatAmount: 1
        clearcoatRoughnessAmount: 0.04
    }
    PrincipledMaterial {
        id: windows_material
        objectName: "Windows"
        baseColor: "#0d151b"
        roughness: 0.05
        metalness: 0
        specularAmount: 1
        clearcoatAmount: 1
        clearcoatRoughnessAmount: 0.02
    }
    PrincipledMaterial {
        id: grey_material
        objectName: "Grey"
        baseColor: "#8a8f94"
        metalness: 0.8
        roughness: 0.32
    }
    PrincipledMaterial {
        id: headlights_material
        objectName: "Headlights"
        baseColor: "#f6f3ea"
        emissiveFactor: Qt.vector3d(root.lamps * 2.6, root.lamps * 2.5, root.lamps * 2.3)
        roughness: 0.2
    }
    PrincipledMaterial {
        id: tailLights_material
        objectName: "TailLights"
        baseColor: root.braking ? "#ff3340" : "#8a121c"
        emissiveFactor: root.braking ? Qt.vector3d(5.5, 0.18, 0.14) : Qt.vector3d(root.lamps * 0.8, 0.01, 0.01)
        roughness: 0.25
    }
    PrincipledMaterial {
        id: black_material
        objectName: "Black"
        baseColor: "#121314"
        roughness: 0.8
    }

    // Nodes:
    Node {
        id: rootNode
        objectName: "RootNode"
        rotation: Qt.quaternion(0, 0, 0.707107, 0.707107)
        Model {
            id: sportsCar2
            objectName: "SportsCar2"
            position: Qt.vector3d(0, 0, 45)
            pivot: Qt.vector3d(0, 0, 45)
            eulerRotation: Qt.vector3d(root.bodyPitch, root.bodyRoll, 0)
            source: "meshes/sportsCar2_mesh.mesh"
            materials: [
                white_material,
                windows_material,
                grey_material,
                headlights_material,
                tailLights_material
            ]
        }
        Model {
            id: sportsCar2_BackWheels
            objectName: "SportsCar2_BackWheels"
            eulerRotation.x: root.wheelAngle
            position: Qt.vector3d(-0.0948505, -132.076, 26.4656)
            source: "meshes/sportsCar2_BackWheels_mesh.mesh"
            materials: [
                black_material,
                grey_material
            ]
        }
        Model {
            id: sportsCar2_FrontLeftWheel
            objectName: "SportsCar2_FrontLeftWheel"
            eulerRotation.x: root.wheelAngle
            position: Qt.vector3d(-72.5991, 118.592, 26.4656)
            source: "meshes/sportsCar2_FrontLeftWheel_mesh.mesh"
            materials: [
                black_material,
                grey_material
            ]
        }
        Model {
            id: sportsCar2_FrontRightWheel
            objectName: "SportsCar2_FrontRightWheel"
            eulerRotation.x: root.wheelAngle
            position: Qt.vector3d(72.4094, 118.592, 26.4656)
            source: "meshes/sportsCar2_FrontRightWheel_mesh.mesh"
            materials: [
                black_material,
                grey_material
            ]
        }
    }

    // Animations:
}
