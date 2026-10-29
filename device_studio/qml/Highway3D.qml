pragma ComponentBehavior: Bound
import QtQuick
import QtQuick3D
import QtQuick3D.Helpers

// Six-lane motorway around the ego car at the origin, travelling toward -Z.
// The world scrolls by `distance`: repeating props move in strips whose node
// offset is distance % period, and road/ground shaders scroll their textures.
Node {
    id: road
    objectName: "highway3D"
    property real distance: 0
    // Plant simulation seconds; oncoming traffic freezes while paused.
    property real drivingTime: 0
    readonly property real ahead: 760

    function random(seed) {
        let state = seed >>> 0
        return function() {
            state = (Math.imul(state, 1664525) + 1013904223) >>> 0
            return state / 4294967296
        }
    }
    // Rows every `period` metres, from behind the camera to past the fog.
    function along(period, make) {
        const rows = []
        for (let z = 30; z >= -(road.ahead + period); z -= period)
            make(rows, z)
        return rows
    }
    // Offset in [0, period); `phase` places a rare landmark's first pass.
    function strip(period, phase) { return (road.distance + (phase || 0)) % period }

    function trees(seed, side, period) {
        const next = road.random(seed)
        const out = {trunks: [], crowns: [], cones: [], bushes: []}
        const near = side > 0 ? 14.5 : -29.5
        function tree(x, z, conifer) {
            // Species/season variety: olive, fresh and blue-green crowns.
            const tint = 0.78 + next() * 0.34, shade = next()
            const hue = shade < 0.3 ? [tint * 1.12, tint * 1.04, tint * 0.7] : shade < 0.75 ? [tint, tint, tint * 0.88]
                                    : [tint * 0.82, tint * 0.95, tint * 0.98]
            if (conifer) {
                const h = 4.2 + next() * 4.5, r = 1.3 + next() * 1.1, trunk = 1.0 + next() * 0.6
                out.trunks.push({p: [x, trunk / 2, z], s: [0.28, trunk, 0.28]})
                for (let k = 0; k < 3; ++k) {
                    const scale = 1 - k * 0.27
                    out.cones.push({p: [x, trunk + h * (0.3 + k * 0.24), z], s: [r * 2 * scale, h * 0.62 * scale, r * 2 * scale],
                                    r: [0, next() * 360, 0], c: hue})
                }
            } else {
                const trunk = 2.0 + next() * 1.6, r = 1.7 + next() * 1.4
                out.trunks.push({p: [x, trunk / 2, z], s: [0.36, trunk, 0.36], r: [0, 0, (next() - 0.5) * 6]})
                const lobes = 3 + Math.floor(next() * 3)
                for (let k = 0; k < lobes; ++k) {
                    const a = next() * Math.PI * 2, d = k === 0 ? 0 : r * (0.45 + next() * 0.35)
                    const size = r * (k === 0 ? 2.1 : 1.3 + next() * 0.5)
                    out.crowns.push({p: [x + Math.cos(a) * d, trunk + r * (0.75 + next() * 0.5), z + Math.sin(a) * d],
                                     s: [size, size * (0.82 + next() * 0.2), size], r: [0, next() * 360, 0], c: hue})
                }
            }
        }
        const length = road.ahead + period + 40
        // Irregular roadside rows, then denser woodland patches further out.
        for (let z = 30; z > -length; z -= 7 + next() * 12)
            if (next() < 0.72)
                tree(near + side * next() * 14, z, next() < 0.42)
        for (let patch = 0; patch < 26; ++patch) {
            const cx = near + side * (18 + next() * 70), cz = 30 - next() * length
            const conifers = next() < 0.5
            for (let k = 0, count = 3 + Math.floor(next() * 7); k < count; ++k)
                tree(cx + (next() - 0.5) * 16, cz + (next() - 0.5) * 16, conifers ? next() < 0.85 : next() < 0.15)
        }
        for (let z = 30; z > -length; z -= 9 + next() * 16) {
            const x = (side > 0 ? 12.8 : -26.8) + side * next() * 2.5
            for (let k = 0; k < 2 + Math.floor(next() * 2); ++k) {
                const size = 1.0 + next() * 1.1
                out.bushes.push({p: [x + (next() - 0.5) * 1.6, size * 0.28, z + (next() - 0.5) * 2.4],
                                 s: [size * 1.3, size * 0.75, size * 1.3], r: [0, next() * 360, 0],
                                 c: [0.85 + next() * 0.2, 0.9 + next() * 0.15, 0.8 + next() * 0.15]})
            }
        }
        return out
    }
    readonly property var oncoming: {
        const next = road.random(77)
        const cars = []
        for (let i = 0; i < 9; ++i) {
            const lane = i % 3
            cars.push({lane: lane, offset: i * 97 + next() * 60, speed: (118 - lane * 14 + next() * 10) / 3.6,
                       variant: [0, 1, 5, 3, 1, 2, 0, 4, 5][i], paint: ["#e8eaeb", "#2a2f35", "#b4b9bd", "#f2c12e", "#8e1c22",
                       "#1d3352", "#6b7178", "#d8dadb", "#3a4a3f"][i], metallic: [0.2, 0.6, 0.8, 0.2, 0.6, 0.6, 0.7, 0.2, 0.5][i]})
        }
        return cars
    }

    // Shared geometry, sized in metres for instancing.
    CuboidGeometry { id: box; xExtent: 1; yExtent: 1; zExtent: 1 }
    CylinderGeometry { id: cylinder; radius: 0.5; length: 1; segments: 14; rings: 1 }
    ConeGeometry { id: cone; topRadius: 0; bottomRadius: 0.5; length: 1; segments: 11; rings: 1 }
    SphereGeometry { id: blob; radius: 0.5; rings: 9; segments: 13 }

    Texture {
        id: concreteTexture
        source: "assets/surfaces/concrete.jpg"
        tilingModeHorizontal: Texture.Repeat; tilingModeVertical: Texture.Repeat
        generateMipmaps: true; mipFilter: Texture.Linear
    }
    Texture {
        id: foliageTexture
        source: "assets/surfaces/foliage.jpg"
        tilingModeHorizontal: Texture.Repeat; tilingModeVertical: Texture.Repeat
        scaleU: 2; scaleV: 2
        generateMipmaps: true; mipFilter: Texture.Linear
    }
    Texture {
        id: foliageNormal
        source: "assets/surfaces/foliage_normal.png"
        tilingModeHorizontal: Texture.Repeat; tilingModeVertical: Texture.Repeat
        scaleU: 2; scaleV: 2
        generateMipmaps: true; mipFilter: Texture.Linear
    }
    PrincipledMaterial { id: galvanized; baseColor: "#aab0b4"; metalness: 0.9; roughness: 0.34 }
    PrincipledMaterial { id: darkSteel; baseColor: "#646b70"; metalness: 0.8; roughness: 0.42 }
    PrincipledMaterial { id: concrete; baseColor: "#e4e2dc"; baseColorMap: concreteTexture; roughness: 0.92 }
    PrincipledMaterial { id: barrierConcrete; baseColor: "#bdbab2"; roughness: 0.9 }
    PrincipledMaterial { id: bark; baseColor: "#5a4a3c"; roughness: 0.95 }
    PrincipledMaterial { id: leaves; baseColorMap: foliageTexture; normalMap: foliageNormal; normalStrength: 0.9; roughness: 0.86 }
    PrincipledMaterial { id: needles; baseColor: "#8fa294"; baseColorMap: foliageTexture; normalMap: foliageNormal; normalStrength: 0.9; roughness: 0.9 }
    PrincipledMaterial { id: shrub; baseColor: "#a7b28f"; baseColorMap: foliageTexture; normalMap: foliageNormal; roughness: 0.9 }
    PrincipledMaterial { id: reflector; baseColor: "#ffb23e"; emissiveFactor: Qt.vector3d(0.8, 0.45, 0.06); roughness: 0.3 }
    PrincipledMaterial { id: whitePaint; baseColor: "#eef0ec"; roughness: 0.55 }
    PrincipledMaterial { id: lampGlass; baseColor: "#d9dde0"; roughness: 0.2; metalness: 0.2 }
    CustomMaterial {
        id: groundMaterial
        shadingMode: CustomMaterial.Shaded
        fragmentShader: "shaders/ground.frag"
        property real scroll: road.distance % 1200
        property vector3d groundTint: Qt.vector3d(0.7, 0.74, 0.62)
        property TextureInput grassMap: TextureInput {
            texture: Texture {
                source: "assets/surfaces/grass.jpg"
                tilingModeHorizontal: Texture.Repeat; tilingModeVertical: Texture.Repeat
                generateMipmaps: true; mipFilter: Texture.Linear
            }
        }
        property TextureInput macroMap: TextureInput {
            texture: Texture {
                source: "assets/surfaces/terrain_macro.png"
                tilingModeHorizontal: Texture.Repeat; tilingModeVertical: Texture.Repeat
                generateMipmaps: true; mipFilter: Texture.Linear
            }
        }
    }

    // Paved surface for both carriageways, median and shoulders.
    Model {
        objectName: "roadSurface"
        source: "#Rectangle"
        position: Qt.vector3d(-7.0, 0, -670)
        eulerRotation.x: -90
        scale: Qt.vector3d(0.324, 14.6, 1)
        castsShadows: false
        materials: CustomMaterial {
            shadingMode: CustomMaterial.Shaded
            fragmentShader: "shaders/road.frag"
            property real scroll: road.distance % 72
            property vector3d asphaltTint: Qt.vector3d(0.74, 0.74, 0.76)
            property real paintLevel: 1.0
            property TextureInput asphaltMap: TextureInput {
                texture: Texture {
                    source: "assets/surfaces/asphalt.jpg"
                    tilingModeHorizontal: Texture.Repeat; tilingModeVertical: Texture.Repeat
                    generateMipmaps: true; mipFilter: Texture.Linear
                }
            }
            property TextureInput asphaltNormal: TextureInput {
                texture: Texture {
                    source: "assets/surfaces/asphalt_normal.png"
                    tilingModeHorizontal: Texture.Repeat; tilingModeVertical: Texture.Repeat
                    generateMipmaps: true; mipFilter: Texture.Linear
                }
            }
        }
    }
    // Embankments fall 0.6 m to the surrounding fields.
    Repeater3D {
        model: [[10.7, -11.31], [-24.7, 11.31]]
        delegate: Node {
            required property var modelData
            position: Qt.vector3d(modelData[0], -0.3, -650)
            eulerRotation.z: modelData[1]
            Model {
                source: "#Rectangle"; eulerRotation.x: -90
                scale: Qt.vector3d(0.0306, 17, 1)
                castsShadows: false
                materials: groundMaterial
            }
        }
    }
    Repeater3D {
        model: [[456, 8.88], [-463, 8.74]]
        delegate: Model {
            required property var modelData
            source: "#Rectangle"
            position: Qt.vector3d(modelData[0], -0.6, -650)
            eulerRotation.x: -90
            scale: Qt.vector3d(modelData[1], 17, 1)
            castsShadows: false
            materials: groundMaterial
        }
    }

    // W-beam guardrails on both outer edges: continuous rails, scrolling posts.
    Repeater3D {
        model: [1, -1]
        delegate: Node {
            id: rail
            required property int modelData
            readonly property real face: rail.modelData > 0 ? 8.8 : -22.8
            readonly property real side: rail.modelData
            Model { geometry: box; materials: galvanized; position: Qt.vector3d(rail.face, 0.79, -365); scale: Qt.vector3d(0.06, 0.12, 790) }
            Model { geometry: box; materials: galvanized; position: Qt.vector3d(rail.face + rail.side * 0.03, 0.69, -365); scale: Qt.vector3d(0.05, 0.09, 790) }
            Model { geometry: box; materials: galvanized; position: Qt.vector3d(rail.face, 0.59, -365); scale: Qt.vector3d(0.06, 0.12, 790) }
            Node {
                z: road.strip(4)
                Model {
                    geometry: box; materials: darkSteel
                    instancing: InstanceTable { rows: road.along(4, (rows, z) => rows.push({p: [rail.face + rail.side * 0.2, 0.4, z], s: [0.1, 0.82, 0.06]})) }
                }
                Model {
                    geometry: box; materials: darkSteel
                    instancing: InstanceTable { rows: road.along(4, (rows, z) => rows.push({p: [rail.face + rail.side * 0.1, 0.69, z], s: [0.14, 0.24, 0.1]})) }
                }
            }
            Node {
                z: road.strip(48)
                Model {
                    geometry: box; materials: reflector; castsShadows: false
                    instancing: InstanceTable { rows: road.along(48, (rows, z) => rows.push({p: [rail.face - rail.side * 0.035, 0.69, z], s: [0.02, 0.07, 0.16]})) }
                }
            }
        }
    }

    // Precast concrete median barrier in 6 m segments.
    Node {
        z: road.strip(6)
        Model {
            geometry: box; materials: barrierConcrete
            instancing: InstanceTable { rows: road.along(6, (rows, z) => rows.push({p: [-7.0, 0.13, z - 3], s: [0.64, 0.26, 5.96]})) }
        }
        Model {
            geometry: box; materials: barrierConcrete
            instancing: InstanceTable { rows: road.along(6, (rows, z) => rows.push({p: [-7.0, 0.33, z - 3], s: [0.44, 0.16, 5.96]})) }
        }
        Model {
            geometry: box; materials: barrierConcrete
            instancing: InstanceTable { rows: road.along(6, (rows, z) => rows.push({p: [-7.0, 0.6, z - 3], s: [0.24, 0.42, 5.96]})) }
        }
    }

    // Median lighting columns with arms over both carriageways.
    Node {
        z: road.strip(60)
        Model {
            geometry: cylinder; materials: galvanized
            instancing: InstanceTable { rows: road.along(60, (rows, z) => rows.push({p: [-7.0, 5.4, z], s: [0.2, 10.4, 0.2]})) }
        }
        Model {
            geometry: box; materials: galvanized
            instancing: InstanceTable {
                rows: road.along(60, (rows, z) => {
                    rows.push({p: [-5.55, 10.35, z], s: [2.9, 0.1, 0.1], r: [0, 0, 4]})
                    rows.push({p: [-8.45, 10.35, z], s: [2.9, 0.1, 0.1], r: [0, 0, -4]})
                })
            }
        }
        Model {
            geometry: box; materials: lampGlass
            instancing: InstanceTable {
                rows: road.along(60, (rows, z) => {
                    rows.push({p: [-4.0, 10.4, z], s: [0.75, 0.16, 0.34]})
                    rows.push({p: [-10.0, 10.4, z], s: [0.75, 0.16, 0.34]})
                })
            }
        }
    }

    // Roadside woodland, verges and bushes in a long, irregular strip.
    Node {
        id: woodland
        y: -0.6
        z: road.strip(480)
        readonly property var east: road.trees(91, 1, 480)
        readonly property var west: road.trees(73, -1, 480)
        Model { geometry: cylinder; materials: bark; instancing: InstanceTable { rows: woodland.east.trunks.concat(woodland.west.trunks) } }
        Model { geometry: blob; materials: leaves; instancing: InstanceTable { rows: woodland.east.crowns.concat(woodland.west.crowns) } }
        Model { geometry: cone; materials: needles; instancing: InstanceTable { rows: woodland.east.cones.concat(woodland.west.cones) } }
        Model { geometry: blob; materials: shrub; instancing: InstanceTable { rows: woodland.east.bushes.concat(woodland.west.bushes) } }
    }

    // Overhead direction signs, once every 900 m.
    Node {
        objectName: "signGantry"
        z: -720 + road.strip(900, 430)
        Model { geometry: box; materials: galvanized; position: Qt.vector3d(-7.0, 3.9, 0); scale: Qt.vector3d(0.42, 7.8, 0.42) }
        Model { geometry: box; materials: galvanized; position: Qt.vector3d(10.0, 3.9, 0); scale: Qt.vector3d(0.42, 7.8, 0.42) }
        Model { geometry: box; materials: galvanized; position: Qt.vector3d(1.5, 7.55, 0); scale: Qt.vector3d(17.4, 0.22, 0.22) }
        Model { geometry: box; materials: galvanized; position: Qt.vector3d(1.5, 6.35, 0); scale: Qt.vector3d(17.4, 0.18, 0.18) }
        Model { geometry: box; materials: darkSteel; position: Qt.vector3d(-1.8, 6.95, -0.08); scale: Qt.vector3d(6.9, 2.75, 0.08) }
        Model { geometry: box; materials: darkSteel; position: Qt.vector3d(5.6, 6.95, -0.08); scale: Qt.vector3d(4.6, 2.75, 0.08) }
        Model {
            source: "#Rectangle"
            position: Qt.vector3d(-1.8, 6.95, -0.03)
            scale: Qt.vector3d(0.068, 0.027, 1)
            castsShadows: false
            materials: PrincipledMaterial {
                roughness: 0.55
                baseColorMap: Texture {
                    sourceItem: Rectangle {
                        width: 680; height: 270; color: "#0b6a3d"; radius: 16
                        border.color: "#f4f6f2"; border.width: 9
                        Column {
                            anchors.centerIn: parent; spacing: 18
                            Repeater {
                                model: [["ANKARA", "412"], ["BOLU", "128"]]
                                delegate: Row {
                                    id: destination
                                    required property var modelData
                                    spacing: 28
                                    Text { text: "↑"; color: "#f4f6f2"; font.pixelSize: 78; font.bold: true; width: 60 }
                                    Text { text: destination.modelData[0]; color: "#f4f6f2"; font.pixelSize: 76; font.bold: true; width: 330 }
                                    Text { text: destination.modelData[1]; color: "#f4f6f2"; font.pixelSize: 76; font.bold: true; width: 140; horizontalAlignment: Text.AlignRight }
                                }
                            }
                        }
                    }
                }
            }
        }
        Model {
            source: "#Rectangle"
            position: Qt.vector3d(5.6, 6.95, -0.03)
            scale: Qt.vector3d(0.045, 0.027, 1)
            castsShadows: false
            materials: PrincipledMaterial {
                roughness: 0.55
                baseColorMap: Texture {
                    sourceItem: Rectangle {
                        width: 450; height: 270; color: "#0b6a3d"; radius: 16
                        border.color: "#f4f6f2"; border.width: 9
                        Rectangle {
                            x: 26; y: 24; width: 150; height: 62; radius: 8; color: "#f4f6f2"
                            Text { anchors.centerIn: parent; text: "ÇIKIŞ 23"; color: "#0b6a3d"; font.pixelSize: 36; font.bold: true }
                        }
                        Text { x: 30; y: 104; text: "TEST MERKEZİ"; color: "#f4f6f2"; font.pixelSize: 54; font.bold: true }
                        Text { x: 30; y: 176; text: "↗  1000 m"; color: "#f4f6f2"; font.pixelSize: 54; font.bold: true }
                    }
                }
            }
        }
    }

    // Speed limit sign on the right verge.
    Node {
        z: -640 + road.strip(1100, 480)
        Model { geometry: cylinder; materials: galvanized; position: Qt.vector3d(10.1, 1.25, 0); scale: Qt.vector3d(0.09, 2.5, 0.09) }
        Model {
            source: "#Rectangle"
            position: Qt.vector3d(10.1, 2.85, 0.06)
            eulerRotation.y: -12
            scale: Qt.vector3d(0.0115, 0.0115, 1)
            castsShadows: true
            materials: PrincipledMaterial {
                roughness: 0.5
                alphaMode: PrincipledMaterial.Mask
                alphaCutoff: 0.5
                baseColorMap: Texture {
                    sourceItem: Item {
                        width: 256; height: 256
                        Rectangle {
                            anchors.fill: parent; radius: 128; color: "#f6f6f2"
                            border.color: "#d31f2a"; border.width: 30
                            Text { anchors.centerIn: parent; text: "120"; color: "#141414"; font.pixelSize: 92; font.bold: true }
                        }
                    }
                }
            }
        }
    }

    // Overpass every 1.5 km: deck, parapets and piers in the median and verges.
    Node {
        objectName: "overpass"
        z: -1000 + road.strip(1500, 380)
        Model { geometry: box; materials: concrete; position: Qt.vector3d(-7, 7.0, 0); scale: Qt.vector3d(76, 1.3, 11) }
        Model { geometry: box; materials: concrete; position: Qt.vector3d(-7, 8.15, 5.35); scale: Qt.vector3d(76, 1.0, 0.3) }
        Model { geometry: box; materials: concrete; position: Qt.vector3d(-7, 8.15, -5.35); scale: Qt.vector3d(76, 1.0, 0.3) }
        Repeater3D {
            model: [-7.0, 12.8, -27.0]
            delegate: Model {
                required property real modelData
                geometry: box; materials: concrete
                position: Qt.vector3d(modelData, 3.2, 0)
                scale: Qt.vector3d(1.1, 6.6, 7.5)
            }
        }
    }

    // Distant hills and wind turbines pass slowly with parallax.
    Node {
        z: -1500 + road.strip(2400)
        Repeater3D {
            model: [[-260, -40, 140, 26], [-330, -520, 190, 34], [240, -260, 160, 22], [330, 300, 210, 30], [-210, 520, 120, 18]]
            delegate: Model {
                required property var modelData
                source: "#Sphere"
                position: Qt.vector3d(modelData[0], -modelData[3] * 0.32, modelData[1])
                scale: Qt.vector3d(modelData[2] * 0.02, modelData[3] * 0.01, modelData[2] * 0.016)
                castsShadows: false
                materials: groundMaterial
            }
        }
        Repeater3D {
            model: [[-235, -60], [-270, -150], [-300, -250], [-335, -340], [235, -230], [270, -300]]
            delegate: Node {
                id: turbine
                required property var modelData
                required property int index
                position: Qt.vector3d(modelData[0], -0.6, modelData[1])
                Model { geometry: cylinder; materials: whitePaint; y: 34; scale: Qt.vector3d(2.6, 68, 2.6) }
                Model { geometry: box; materials: whitePaint; y: 68.5; z: -1.5; scale: Qt.vector3d(2.6, 2.8, 7.5) }
                Node {
                    y: 68.5; z: 2.6
                    eulerRotation.y: -18
                    NumberAnimation on eulerRotation.z { from: turbine.index * 47; to: turbine.index * 47 + 360; duration: 7200 + turbine.index * 650; loops: Animation.Infinite }
                    Repeater3D {
                        model: 3
                        delegate: Node {
                            required property int index
                            eulerRotation.z: index * 120
                            Model { geometry: box; materials: whitePaint; y: 15.5; scale: Qt.vector3d(1.5, 31, 0.35) }
                        }
                    }
                }
            }
        }
    }

    // Oncoming traffic behind the median barrier; scenery only, never sensed.
    Repeater3D {
        model: road.oncoming.length
        delegate: Vehicle3D {
            id: oncomingCar
            required property int index
            readonly property var car: road.oncoming[index]
            readonly property real travelled: car.offset - car.speed * road.drivingTime
            readonly property real ahead: ((travelled - road.distance + 60) % 960 + 960) % 960 - 60
            x: -10.4 - car.lane * 3.6
            z: -ahead
            eulerRotation.y: 0
            variant: car.variant
            paint: car.paint
            metallic: car.metallic
            lamps: 0.55
            wheelAngle: (oncomingCar.travelled) * 200
        }
    }
}
