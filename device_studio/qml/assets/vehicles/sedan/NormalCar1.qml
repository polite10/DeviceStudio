import QtQuick
import QtQuick3D

Node {
    id: root
    objectName: "Root"

    property color paint: "#42bfa7"
    property bool braking: false
    property real wheelAngle: 0
    // Source FBX uses centimetres; the scene uses metres.
    scale: Qt.vector3d(0.01, 0.01, 0.01)

    // Resources
    PrincipledMaterial {
        id: blue_material
        objectName: "Blue"
        baseColor: root.paint
        roughness: 0.25
        metalness: 0.35
        clearcoatAmount: 0.65
    }
    PrincipledMaterial {
        id: black_material
        objectName: "Black"
        baseColor: "#ff030303"
        roughness: 0.690034806728363
    }
    PrincipledMaterial {
        id: windows_material
        objectName: "Windows"
        baseColor: "#294657"
        roughness: 0.16
        metalness: 0.6
    }
    PrincipledMaterial {
        id: headlights_material
        objectName: "Headlights"
        baseColor: "#fff3d2"
        emissiveFactor: Qt.vector3d(0.3, 0.28, 0.2)
        roughness: 0.690034806728363
    }
    PrincipledMaterial {
        id: grey_material
        objectName: "Grey"
        baseColor: "#ff292929"
        roughness: 0.690034806728363
    }
    PrincipledMaterial {
        id: tailLights_material
        objectName: "TailLights"
        baseColor: root.braking ? "#ff2538" : "#831927"
        emissiveFactor: root.braking ? Qt.vector3d(2, 0.03, 0.03) : Qt.vector3d(0.05, 0, 0)
        roughness: 0.690034806728363
    }

    // Nodes:
    Node {
        id: rootNode
        objectName: "RootNode"
        rotation: Qt.quaternion(0, 0, 0.707107, 0.707107)
        Model {
            id: normalCar1
            objectName: "NormalCar1"
            source: "meshes/normalCar1_mesh.mesh"
            materials: [
                blue_material,
                black_material,
                windows_material,
                headlights_material,
                grey_material,
                tailLights_material
            ]
        }
        Model {
            id: normalCar1_BackWheels
            objectName: "NormalCar1_BackWheels"
            eulerRotation.x: root.wheelAngle
            position: Qt.vector3d(-0.086987, -124.326, 26.7922)
            source: "meshes/normalCar1_BackWheels_mesh.mesh"
            materials: [
                black_material,
                grey_material
            ]
        }
        Model {
            id: normalCar1_FrontLeftWheel
            objectName: "NormalCar1_FrontLeftWheel"
            eulerRotation.x: root.wheelAngle
            position: Qt.vector3d(-69.0639, 119.587, 26.7922)
            source: "meshes/normalCar1_FrontLeftWheel_mesh.mesh"
            materials: [
                black_material,
                grey_material
            ]
        }
        Model {
            id: normalCar1_FrontRightWheel
            objectName: "NormalCar1_FrontRightWheel"
            eulerRotation.x: root.wheelAngle
            position: Qt.vector3d(68.8899, 119.587, 26.7922)
            source: "meshes/normalCar1_FrontRightWheel_mesh.mesh"
            materials: [
                black_material,
                grey_material
            ]
        }
    }

    // Animations:
}
