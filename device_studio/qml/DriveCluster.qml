pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Shapes

// Instrument cluster: ADAS telltales, speedometer with ACC set speed, turn
// indicators, following-distance setting and longitudinal acceleration.
Item {
    id: cluster
    property real speedKmh: 0
    property real targetKmh: 0
    property bool accEnabled: false
    property bool warning: false
    property bool emergency: false
    property string mode: "active"
    property real accel: 0
    property real headwayMs: 1800
    property int indicator: 0
    property bool blinkOn: false
    readonly property color accent: "#63dec2"
    readonly property color amber: "#ffc35c"
    readonly property color red: "#ff5a68"
    readonly property color dim: "#4d6170"
    readonly property real maxKmh: 220
    implicitWidth: 430
    implicitHeight: 128

    function angleFor(kmh) { return 135 + 270 * Math.max(0, Math.min(1, kmh / maxKmh)) }

    component Telltale: Rectangle {
        id: telltale
        property string label
        property string value
        property color ink: cluster.dim
        property bool lit: false
        width: 112; height: 30; radius: 8
        color: lit ? Qt.rgba(ink.r, ink.g, ink.b, 0.16) : "#0dffffff"
        border.width: 1
        border.color: lit ? Qt.rgba(ink.r, ink.g, ink.b, 0.55) : "#14ffffff"
        Behavior on color { ColorAnimation { duration: 140 } }
        Row {
            anchors.verticalCenter: parent.verticalCenter
            x: 10; spacing: 8
            Rectangle { width: 6; height: 6; radius: 3; anchors.verticalCenter: parent.verticalCenter; color: telltale.lit ? telltale.ink : "#334552" }
            Text { text: telltale.label; color: telltale.lit ? telltale.ink : "#6f8594"; font.pixelSize: 11; font.weight: Font.Bold; font.letterSpacing: 1 }
        }
        Text {
            anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
            text: telltale.value; color: telltale.lit ? "#e7f0f4" : "#5d7383"; font.pixelSize: 11
            font.features: { "tnum": 1 }
        }
    }

    Rectangle {
        anchors.fill: parent
        radius: 20
        color: "#d40a1219"
        border.width: 1; border.color: "#24ffffff"
        Rectangle {
            anchors.fill: parent; anchors.margins: 1; radius: 19
            gradient: Gradient {
                GradientStop { position: 0; color: "#12ffffff" }
                GradientStop { position: 0.45; color: "#00ffffff" }
            }
        }
    }

    Column {
        x: 16; anchors.verticalCenter: parent.verticalCenter; spacing: 6
        Telltale {
            objectName: "clusterAcc"
            label: "ACC"; value: cluster.accEnabled ? String(Math.round(cluster.targetKmh)) : "kapalı"
            ink: cluster.accent; lit: cluster.accEnabled && cluster.mode === "active"
        }
        Telltale {
            objectName: "clusterFcw"
            label: "FCW"; value: cluster.mode === "off" ? "kapalı" : cluster.warning ? "UYARI" : "hazır"
            ink: cluster.amber; lit: cluster.warning && cluster.mode !== "off"
        }
        Telltale {
            objectName: "clusterAeb"
            label: "AEB"; value: cluster.mode !== "active" ? "kapalı" : cluster.emergency ? "FREN" : "hazır"
            ink: cluster.red; lit: cluster.emergency
            opacity: cluster.emergency && !cluster.blinkOn ? 0.55 : 1
        }
    }

    Item {
        id: gauge
        x: 136; width: 150; height: parent.height
        readonly property real cx: width / 2
        readonly property real cy: 68
        readonly property real radius: 52
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: "#1effffff"; strokeWidth: 7; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                PathAngleArc { centerX: gauge.cx; centerY: gauge.cy; radiusX: gauge.radius; radiusY: gauge.radius; startAngle: 135; sweepAngle: 270 }
            }
            ShapePath {
                strokeColor: cluster.emergency ? cluster.red : cluster.warning ? cluster.amber : cluster.accent
                strokeWidth: 7; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                PathAngleArc {
                    centerX: gauge.cx; centerY: gauge.cy; radiusX: gauge.radius; radiusY: gauge.radius
                    startAngle: 135; sweepAngle: Math.max(0.5, cluster.angleFor(cluster.speedKmh) - 135)
                }
            }
        }
        Repeater {
            model: 12
            delegate: Rectangle {
                required property int index
                readonly property real angle: (135 + index * 270 / 11) * Math.PI / 180
                width: index % 2 === 0 ? 2 : 1.5; height: index % 2 === 0 ? 7 : 4; radius: 1
                color: index * 20 <= cluster.speedKmh ? "#d8e6ee" : "#516878"
                x: gauge.cx + Math.cos(angle) * (gauge.radius - 12) - width / 2
                y: gauge.cy + Math.sin(angle) * (gauge.radius - 12) - height / 2
                rotation: angle * 180 / Math.PI + 90
                antialiasing: true
            }
        }
        Rectangle {
            visible: cluster.accEnabled && cluster.mode === "active"
            readonly property real angle: cluster.angleFor(cluster.targetKmh) * Math.PI / 180
            width: 5; height: 15; radius: 2; color: cluster.accent
            x: gauge.cx + Math.cos(angle) * gauge.radius - width / 2
            y: gauge.cy + Math.sin(angle) * gauge.radius - height / 2
            rotation: angle * 180 / Math.PI + 90
            antialiasing: true
        }
        Text {
            objectName: "driveSpeed"
            anchors.horizontalCenter: parent.horizontalCenter
            y: gauge.cy - 30
            text: Math.round(cluster.speedKmh)
            color: "#f2f7fa"; font.pixelSize: 40; font.weight: Font.DemiBold
            font.features: { "tnum": 1 }
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            y: gauge.cy + 14
            text: "km/sa"; color: "#8aa3b3"; font.pixelSize: 11; font.letterSpacing: 1
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            y: gauge.cy + 38
            text: cluster.emergency ? "ACİL FREN" : cluster.accEnabled && cluster.mode === "active" ? "ACC HAZIR" : cluster.mode === "off" ? "ADAS KAPALI" : "ADAS İZLİYOR"
            color: cluster.emergency ? cluster.red : "#6d8899"; font.pixelSize: 10; font.weight: Font.DemiBold; font.letterSpacing: 1.2
        }
    }

    Column {
        anchors.right: parent.right; anchors.rightMargin: 14
        anchors.verticalCenter: parent.verticalCenter
        width: 122; spacing: 10
        Row {
            spacing: 10
            Text { text: "◀"; font.pixelSize: 16; color: cluster.indicator < 0 && cluster.blinkOn ? "#4ef08d" : "#2b3c47" }
            Text { text: "▶"; font.pixelSize: 16; color: cluster.indicator > 0 && cluster.blinkOn ? "#4ef08d" : "#2b3c47" }
            Item { width: 2; height: 1 }
            Text { text: "TAKİP"; color: "#7e97a7"; font.pixelSize: 10; font.letterSpacing: 1; anchors.verticalCenter: parent.verticalCenter }
            Row {
                spacing: 2; anchors.verticalCenter: parent.verticalCenter
                Repeater {
                    model: 4
                    delegate: Rectangle {
                        required property int index
                        width: 4; height: 6 + index * 2; radius: 1
                        anchors.bottom: parent.bottom
                        color: index < Math.max(1, Math.min(4, Math.round(cluster.headwayMs / 700))) ? cluster.accent : "#2b3c47"
                    }
                }
            }
        }
        Text {
            text: (cluster.headwayMs / 1000).toFixed(1) + " s takip süresi"
            color: "#9fb3c0"; font.pixelSize: 11
        }
        Item {
            width: parent.width; height: 20
            Rectangle { y: 7; width: parent.width; height: 6; radius: 3; color: "#1affffff" }
            Rectangle { x: parent.width * 0.62 - 1; y: 3; width: 2; height: 14; color: "#7e97a7" }
            Rectangle {
                readonly property real centre: parent.width * 0.62
                readonly property real span: cluster.accel >= 0 ? Math.min(1, cluster.accel / 3) * (parent.width - centre)
                                                                   : Math.min(1, -cluster.accel / 9) * centre
                x: cluster.accel >= 0 ? centre : centre - span
                y: 7; height: 6; radius: 3; width: span
                color: cluster.accel >= 0 ? "#4ef08d" : cluster.accel < -6 ? cluster.red : cluster.amber
            }
        }
        Text {
            text: (cluster.accel >= 0 ? "GAZ  +" : "FREN  ") + Math.abs(cluster.accel).toFixed(1) + " m/s²"
            color: cluster.accel < -6 ? cluster.red : "#9fb3c0"; font.pixelSize: 11
            font.features: { "tnum": 1 }
        }
    }
}
