pragma ComponentBehavior: Bound
import QtQuick
import QtQuick3D

// A wing mirror: the same scene through a narrow camera looking back along the
// flank. A car close alongside has left it, which is exactly the blind spot, so
// the lamp in the glass stays lit while the mirror is empty. side: -1 left, 1 right.
Item {
    id: mirror
    required property int side
    required property var world
    required property var sky
    required property var probe
    property int level: 0
    property bool flash: false
    property real carX: 0
    property real carHalfWidth: 0.9
    property real carYaw: 0
    readonly property color lamp: level > 1 ? "#ff4a58" : "#ffb52e"
    implicitWidth: 250
    implicitHeight: 118

    Rectangle {
        anchors.fill: parent
        radius: 16
        color: "#101418"
    }
    View3D {
        id: glass
        objectName: mirror.side < 0 ? "mirrorLeftView" : "mirrorRightView"
        anchors.fill: parent
        anchors.margins: 6
        importScene: mirror.world
        camera: view
        // A mirror swaps left and right.
        transform: Scale { origin.x: glass.width / 2; xScale: -1 }
        environment: SceneEnvironment {
            backgroundMode: SceneEnvironment.SkyBoxCubeMap
            skyBoxCubeMap: mirror.sky
            lightProbe: mirror.probe
            probeExposure: 0.78
            tonemapMode: SceneEnvironment.TonemapModeAces
            antialiasingMode: SceneEnvironment.NoAA
            aoEnabled: false
        }
        PerspectiveCamera {
            id: view
            position: Qt.vector3d(mirror.carX + mirror.side * (mirror.carHalfWidth + 0.08), 1.04, -0.75)
            // Looks back along the flank and 14° out, as a mirror set to just lose the car's side.
            eulerRotation: Qt.vector3d(-2.5, 180 + mirror.carYaw + mirror.side * 14, 0)
            fieldOfView: 17
            fieldOfViewOrientation: PerspectiveCamera.Vertical
            clipNear: 0.25
            clipFar: 500
        }
    }
    Rectangle {
        anchors.fill: parent
        radius: 16
        color: "transparent"
        border.width: mirror.level > 0 ? 4 : 2
        border.color: mirror.level > 0 ? mirror.lamp : "#2b333a"
        opacity: mirror.level > 1 && !mirror.flash ? 0.35 : 1
    }
    // The blind spot lamp, in the outer corner of the glass.
    Rectangle {
        objectName: mirror.side < 0 ? "mirrorLeftLamp" : "mirrorRightLamp"
        visible: mirror.level > 0
        anchors.top: parent.top; anchors.topMargin: 12
        x: mirror.side < 0 ? 12 : parent.width - width - 12
        width: lampText.implicitWidth + 18; height: 22; radius: 6
        color: mirror.lamp
        opacity: mirror.level > 1 && !mirror.flash ? 0.45 : 1
        Text {
            id: lampText
            anchors.centerIn: parent
            text: "KÖR NOKTA"
            color: "#1b1006"
            font.pixelSize: 11; font.weight: Font.Black; font.letterSpacing: 0.6
        }
    }
}
