pragma ComponentBehavior: Bound
import QtQuick
import QtQuick3D

Node {
    id: road
    property real distance: 0
    component Block: Model {
        id: block
        property vector3d size: Qt.vector3d(1, 1, 1)
        property color tint: "#ffffff"
        source: "#Cube"
        scale: Qt.vector3d(size.x / 100, size.y / 100, size.z / 100)
        materials: PrincipledMaterial { baseColor: block.tint; roughness: 0.85 }
    }
    Block { position: Qt.vector3d(0, -0.22, -160); size: Qt.vector3d(700, 0.3, 600); tint: "#7d9860" }
    Block { position: Qt.vector3d(0, -0.05, -140); size: Qt.vector3d(14.4, 0.15, 440); tint: "#7a807d" }
    Model {
        position: Qt.vector3d(0, 0.04, -140)
        source: "#Cube"; scale: Qt.vector3d(0.112, 0.001, 4.4)
        materials: PrincipledMaterial {
            baseColor: "#909496"; roughness: 0.96
            baseColorMap: Texture { source: "assets/asphalt.png"; scaleU: 5; scaleV: 180; tilingModeHorizontal: Texture.Repeat; tilingModeVertical: Texture.Repeat }
        }
    }
    Repeater3D {
        model: 2
        delegate: Node {
            id: edge
            required property int index
            x: index === 0 ? -5.3 : 5.3
            Block { position: Qt.vector3d(0, 0.11, -140); size: Qt.vector3d(0.12, 0.025, 440); tint: "#eee4bd" }
            Block { position: Qt.vector3d(edge.index === 0 ? -1.2 : 1.2, 0.72, -140); size: Qt.vector3d(0.15, 0.24, 440); tint: "#aab7ba" }
            Repeater3D {
                model: 38
                delegate: Block {
                    required property int index
                    x: edge.index === 0 ? -1.2 : 1.2; y: 0.35
                    z: 24 - index * 10 + road.distance % 10
                    size: Qt.vector3d(0.1, 0.7, 0.1); tint: "#78878a"
                }
            }
        }
    }
    Repeater3D {
        model: 86
        delegate: Block {
            required property int index
            x: index % 2 === 0 ? -1.8 : 1.8
            y: 0.115; z: 28 - Math.floor(index / 2) * 8 + road.distance % 8
            size: Qt.vector3d(0.13, 0.025, 3.2); tint: "#f4f0dd"
        }
    }
    Repeater3D {
        model: 44
        delegate: Node {
            id: tree
            required property int index
            x: (index % 2 === 0 ? -1 : 1) * (11 + index % 5 * 2.7)
            z: 35 - Math.floor(index / 2) * 17 + road.distance % 17
            Block { y: 1.25; size: Qt.vector3d(0.35, 2.5, 0.35); tint: "#706551" }
            Model {
                y: 3.7; source: "#Cone"
                scale: Qt.vector3d(0.046, 0.065, 0.046)
                materials: PrincipledMaterial { baseColor: tree.index % 3 === 0 ? "#466d57" : "#547b57"; roughness: 1 }
            }
        }
    }
    Repeater3D {
        model: 10
        delegate: Model {
            required property int index
            x: (index % 2 === 0 ? -1 : 1) * (175 + index % 3 * 65)
            y: -12; z: -220 - Math.floor(index / 2) * 90
            source: "#Sphere"; scale: Qt.vector3d(2.5, 0.8 + index % 3 * 0.3, 2.1)
            materials: PrincipledMaterial { baseColor: "#7b9782"; roughness: 1 }
        }
    }
    Node {
        z: -185 + road.distance % 260
        Block { x: -7.7; y: 4; size: Qt.vector3d(0.25, 8, 0.25); tint: "#8b989c" }
        Block { x: 7.7; y: 4; size: Qt.vector3d(0.25, 8, 0.25); tint: "#8b989c" }
        Block { y: 7.8; size: Qt.vector3d(15.6, 0.2, 0.2); tint: "#8b989c" }
        Block { y: 7.1; size: Qt.vector3d(8, 1.6, 0.2); tint: "#34756a" }
        // Lane arrows are physical geometry, so they stay readable in perspective.
        Repeater3D {
            model: 3
            delegate: Node {
                required property int index
                x: (index - 1) * 2.4; y: 7.1; z: 0.13
                Block { size: Qt.vector3d(0.09, 0.75, 0.025); tint: "#edf3df" }
                Block { x: -0.12; y: 0.22; eulerRotation.z: -40; size: Qt.vector3d(0.09, 0.4, 0.025); tint: "#edf3df" }
                Block { x: 0.12; y: 0.22; eulerRotation.z: 40; size: Qt.vector3d(0.09, 0.4, 0.025); tint: "#edf3df" }
            }
        }
    }
}
