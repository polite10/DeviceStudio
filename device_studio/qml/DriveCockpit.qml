pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Shapes

// The driver's seat for the pilot camera: the top of the dashboard and the steering
// wheel, which turns with the driver and with what the firmware asks of it.
Item {
    id: cockpit
    objectName: "driveCockpit"
    property real wheel: 0          // -1.5 .. 1.5, right positive
    property color ink: "#c8d4dc"
    property int indicator: 0
    property bool blinkOn: false
    readonly property real dashTop: height - wheelBox.height * 0.58

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: "transparent"
            fillColor: "#e6111417"
            startX: 0; startY: cockpit.height
            PathLine { x: 0; y: cockpit.dashTop + 34 }
            PathQuad { x: cockpit.width; y: cockpit.dashTop + 34; controlX: cockpit.width / 2; controlY: cockpit.dashTop - 34 }
            PathLine { x: cockpit.width; y: cockpit.height }
            PathLine { x: 0; y: cockpit.height }
        }
    }
    DriveSteering {
        id: wheelBox
        objectName: "driveSteeringWheel"
        anchors.horizontalCenter: parent.horizontalCenter
        y: cockpit.height - height * 0.7
        width: Math.min(cockpit.width * 0.34, cockpit.height * 0.62); height: width
        angle: cockpit.wheel * 95
        ink: cockpit.ink
    }
    Repeater {
        model: [-1, 1]
        delegate: Text {
            required property int modelData
            x: cockpit.width / 2 + modelData * wheelBox.width * 0.62 - width / 2
            y: cockpit.dashTop + 8
            text: modelData < 0 ? "◀" : "▶"
            font.pixelSize: 24
            color: cockpit.indicator === modelData && cockpit.blinkOn ? "#4ef08d" : "#2b3c47"
        }
    }
}
