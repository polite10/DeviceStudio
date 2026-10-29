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
        id: white_material
        objectName: "White"
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
        id: grey_material
        objectName: "Grey"
        baseColor: "#ff292929"
        roughness: 0.690034806728363
    }
    PrincipledMaterial {
        id: headlights_material
        objectName: "Headlights"
        baseColor: "#fff3d2"
        emissiveFactor: Qt.vector3d(0.3, 0.28, 0.2)
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
            id: suv
            objectName: "SUV"
            source: "meshes/suv_mesh.mesh"
            materials: [
                white_material,
                black_material,
                windows_material,
                grey_material,
                headlights_material,
                tailLights_material
            ]
        }
        Model {
            id: suv_BackWheels
            objectName: "SUV_BackWheels"
            eulerRotation.x: root.wheelAngle
            position: Qt.vector3d(-0.514352, -125.11, 30.9136)
            source: "meshes/suv_BackWheels_mesh.mesh"
            materials: [
                black_material,
                grey_material
            ]
        }
        Model {
            id: suv_FrontLeftWheel
            objectName: "SUV_FrontLeftWheel"
            eulerRotation.x: root.wheelAngle
            position: Qt.vector3d(-77.266, 131.695, 30.9136)
            source: "meshes/suv_FrontLeftWheel_mesh.mesh"
            materials: [
                black_material,
                grey_material
            ]
        }
        Model {
            id: suv_FrontRightWheel
            objectName: "SUV_FrontRightWheel"
            eulerRotation.x: root.wheelAngle
            position: Qt.vector3d(76.2373, 131.695, 30.9136)
            source: "meshes/suv_FrontRightWheel_mesh.mesh"
            materials: [
                black_material,
                grey_material
            ]
        }
    }

    // Animations:
}
