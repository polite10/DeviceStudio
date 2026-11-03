pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Shapes

// Top-down sensor view: three lanes, the ego car, every tracked vehicle up to
// 110 m ahead and, on a tighter scale, 60 m behind, with the blind zones beside the
// car. Positions are pushed each display frame by Drive3DView.
Item {
    id: radar
    objectName: "driveRadar"
    property color signal: "#63dec2"
    property real egoLane: 1
    property string gapText: "—"
    property string ttcText: "—"
    property string relativeText: "—"
    property int blindLeft: 0
    property int blindRight: 0
    property int rearThreat: 0
    readonly property real range: 110
    readonly property real rearRange: 60
    readonly property real laneWidth: 34
    implicitWidth: 206
    implicitHeight: 262

    // cars: [{lane, ahead (m, centre), lead, braking, watched}] for up to 16 tracked cars.
    property var cars: []
    function place(list) { radar.cars = list }

    Rectangle {
        anchors.fill: parent; radius: 16
        color: "#d40a1219"; border.width: 1; border.color: "#24ffffff"
    }
    Text { x: 14; y: 12; text: "SENSÖR GÖRÜNÜMÜ"; color: "#7e97a7"; font.pixelSize: 10; font.weight: Font.DemiBold; font.letterSpacing: 1.2 }
    Text { anchors.right: parent.right; anchors.rightMargin: 14; y: 12; text: radar.range + " m"; color: "#56707f"; font.pixelSize: 10 }

    Item {
        id: plot
        x: 10; y: 32; width: parent.width - 20; height: parent.height - 92
        clip: true
        readonly property real egoY: height - 42
        readonly property real pxPerMetre: (egoY - 8) / radar.range
        readonly property real pxPerMetreBehind: 42 / radar.rearRange
        function yOf(ahead) { return egoY - ahead * (ahead > 0 ? pxPerMetre : pxPerMetreBehind) }
        Repeater {
            model: [25, 50, 75, 100]
            delegate: Item {
                id: ring
                required property int modelData
                width: plot.width; height: 1
                y: plot.egoY - modelData * plot.pxPerMetre
                Rectangle { width: parent.width; height: 1; color: "#12ffffff" }
                Text { x: 2; y: -12; text: ring.modelData; color: "#46606e"; font.pixelSize: 9 }
            }
        }
        Repeater {
            model: [-1.5, 1.5]
            delegate: Rectangle {
                required property real modelData
                x: plot.width / 2 + modelData * radar.laneWidth - 1; width: 2; height: plot.height
                color: "#3a5361"
            }
        }
        Repeater {
            model: 2 * 14
            delegate: Rectangle {
                required property int index
                x: plot.width / 2 + (index % 2 === 0 ? -0.5 : 0.5) * radar.laneWidth - 1
                y: Math.floor(index / 2) * 13
                width: 2; height: 6; color: "#2c4250"
            }
        }
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: "transparent"
                fillGradient: LinearGradient {
                    x1: 0; y1: plot.egoY; x2: 0; y2: 0
                    GradientStop { position: 0; color: Qt.rgba(radar.signal.r, radar.signal.g, radar.signal.b, 0.26) }
                    GradientStop { position: 1; color: Qt.rgba(radar.signal.r, radar.signal.g, radar.signal.b, 0.0) }
                }
                readonly property real originX: plot.width / 2 + (radar.egoLane - 1) * radar.laneWidth
                startX: originX; startY: plot.egoY - 12
                PathLine { x: plot.width / 2 + (radar.egoLane - 1) * radar.laneWidth - 30; y: 0 }
                PathLine { x: plot.width / 2 + (radar.egoLane - 1) * radar.laneWidth + 30; y: 0 }
                PathLine { x: plot.width / 2 + (radar.egoLane - 1) * radar.laneWidth; y: plot.egoY - 12 }
            }
        }
        Repeater {
            model: [-1, 1]
            delegate: Rectangle {
                required property int modelData
                readonly property int level: modelData < 0 ? radar.blindLeft : radar.blindRight
                readonly property color ink: level > 1 ? "#ff4a58" : "#ffb52e"
                visible: level > 0
                x: plot.width / 2 + (radar.egoLane - 1) * radar.laneWidth + modelData * radar.laneWidth * 0.86 - width / 2
                y: plot.egoY - 12
                width: radar.laneWidth * 0.62; height: 26; radius: 4
                color: Qt.rgba(ink.r, ink.g, ink.b, 0.28)
                border.width: 1; border.color: ink
            }
        }
        Rectangle {
            visible: radar.rearThreat > 0
            x: plot.width / 2 + (radar.egoLane - 1) * radar.laneWidth - width / 2
            y: plot.egoY + 14
            width: 18; height: 28; radius: 4
            readonly property color ink: radar.rearThreat > 1 ? "#ff4a58" : "#ffb52e"
            color: Qt.rgba(ink.r, ink.g, ink.b, 0.28)
            border.width: 1; border.color: ink
        }
        Repeater {
            id: marks
            model: 16
            delegate: Rectangle {
                id: mark
                required property int index
                readonly property var car: radar.cars[index] || null
                visible: car !== null && car.ahead > -radar.rearRange && car.ahead < radar.range
                x: car ? plot.width / 2 + (car.lane - 1) * radar.laneWidth - width / 2 : 0
                y: car ? plot.yOf(car.ahead) - height / 2 : 0
                width: 15; height: 25; radius: 4
                color: car && car.lead ? radar.signal : car && car.watched ? "#ffb52e" : "#8aa2b1"
                border.width: car && car.lead ? 2 : 0
                border.color: Qt.lighter(radar.signal, 1.3)
                Rectangle {
                    visible: mark.car !== null && mark.car.braking
                    anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter
                    width: parent.width - 4; height: 3; radius: 1; color: "#ff4655"
                }
            }
        }
        Rectangle {
            objectName: "radarEgo"
            x: plot.width / 2 + (radar.egoLane - 1) * radar.laneWidth - width / 2
            y: plot.egoY - height / 2
            width: 16; height: 27; radius: 5
            color: "#e9f6f2"
            border.width: 2; border.color: "#63dec2"
        }
    }

    Row {
        anchors.bottom: parent.bottom; anchors.bottomMargin: 12
        x: 14; spacing: 16
        Repeater {
            model: [["TAKİP", radar.gapText], ["TTC", radar.ttcText], ["BAĞIL", radar.relativeText]]
            delegate: Column {
                id: reading
                required property var modelData
                required property int index
                spacing: 3
                Text { text: reading.modelData[0]; color: "#6f8796"; font.pixelSize: 9; font.letterSpacing: 1 }
                Text {
                    text: reading.modelData[1]
                    color: reading.index === 1 ? radar.signal : "#e3edf2"
                    font.pixelSize: 15; font.weight: Font.DemiBold
                    font.features: { "tnum": 1 }
                }
            }
        }
    }
}
