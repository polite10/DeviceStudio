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
        id: orange_material
        objectName: "Orange"
        baseColor: root.paint
        roughness: 0.25
        metalness: 0.35
        clearcoatAmount: 0.65
    }
    PrincipledMaterial {
        id: darkOrange_material
        objectName: "DarkOrange"
        baseColor: "#ff8e3b13"
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
    PrincipledMaterial {
        id: black_material
        objectName: "Black"
        baseColor: "#ff030303"
        roughness: 0.690034806728363
    }

    // Nodes:
    Node {
        id: rootNode
        objectName: "RootNode"
        rotation: Qt.quaternion(0, 0, 0.707107, 0.707107)
        Model {
            id: sportsCar
            objectName: "SportsCar"
            source: "meshes/sportsCar_mesh.mesh"
            materials: [
                orange_material,
                darkOrange_material,
                windows_material,
                headlights_material,
                grey_material,
                tailLights_material
            ]
        }
        Model {
            id: sportsCar_BackWheels
            objectName: "SportsCar_BackWheels"
            eulerRotation.x: root.wheelAngle
            position: Qt.vector3d(-0.289182, -125.461, 24.961)
            source: "meshes/sportsCar_BackWheels_mesh.mesh"
            materials: [
                black_material,
                grey_material
            ]
        }
        Model {
            id: sportsCar_FrontLeftWheel
            objectName: "SportsCar_FrontLeftWheel"
            eulerRotation.x: root.wheelAngle
            position: Qt.vector3d(-71.9753, 118.804, 24.961)
            source: "meshes/sportsCar_FrontLeftWheel_mesh.mesh"
            materials: [
                black_material,
                grey_material
            ]
        }
        Model {
            id: sportsCar_FrontRightWheel
            objectName: "SportsCar_FrontRightWheel"
            eulerRotation.x: root.wheelAngle
            position: Qt.vector3d(71.3969, 118.804, 24.961)
            source: "meshes/sportsCar_FrontRightWheel_mesh.mesh"
            materials: [
                black_material,
                grey_material
            ]
        }
    }

    // Animations:
}
