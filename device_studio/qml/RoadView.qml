import QtQuick

Item {
    id: road
    property var telemetry: ({})
    property bool running: false
    property bool connected: false
    property bool simulated: false
    property string fontFamily: Qt.platform.os === "osx" ? "Helvetica Neue" : "Segoe UI"
    readonly property real speed: Number(road.telemetry.egoKmh || 0)
    readonly property real gap: Math.max(0, Number(road.telemetry.gapM || 0))
    readonly property string mode: road.telemetry.mode || "WAITING"
    readonly property bool danger: mode === "AEB" || Boolean(road.telemetry.collision)
    readonly property bool caution: mode === "WARNING"
    readonly property color signalColor: danger ? "#ff7b87" : caution ? "#e9b96d" : "#63dec2"
    readonly property real leadY: height * .69 - (telemetry.collision ? 55 : 78) - Math.min(100, gap) * (height * .0034)
    property real phase: 0
    clip: true

    Rectangle { anchors.fill: parent; color: "#0c1823" }

    Canvas {
        id: laneCanvas
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var w = width, h = height, center = w * .5
            var top = h * .14, bottom = h + 20
            // The road is a compact perspective field; all cars are data marks.
            ctx.fillStyle = "#142332"
            ctx.beginPath()
            ctx.moveTo(center - w * .12, top)
            ctx.lineTo(center + w * .12, top)
            ctx.lineTo(center + w * .39, bottom)
            ctx.lineTo(center - w * .39, bottom)
            ctx.closePath()
            ctx.fill()
            ctx.lineWidth = 1.5
            ctx.strokeStyle = "#334957"
            for (var side = -1; side <= 1; side += 2) {
                ctx.beginPath()
                ctx.moveTo(center + side * w * .12, top)
                ctx.lineTo(center + side * w * .39, bottom)
                ctx.stroke()
            }
            ctx.strokeStyle = "#45606f"
            ctx.lineWidth = 2
            for (var i = 0; i < 8; i++) {
                var p = ((i + road.phase) % 8) / 8
                var y = top + p * p * (h - top)
                var size = 4 + p * 19
                var half = w * (.04 + p * .08)
                ctx.beginPath()
                ctx.moveTo(center - half, y)
                ctx.lineTo(center - half - 2, y + size)
                ctx.moveTo(center + half, y)
                ctx.lineTo(center + half + 2, y + size)
                ctx.stroke()
            }
            var front = h * .69
            var rear = road.leadY
            if (road.connected && road.telemetry.present !== false) {
                ctx.strokeStyle = road.signalColor
                ctx.lineWidth = 1
                ctx.setLineDash([3, 5])
                ctx.beginPath()
                ctx.moveTo(center, rear + 68)
                ctx.lineTo(center, front - 7)
                ctx.stroke()
                ctx.setLineDash([])
            }
        }
    }

    Timer {
        interval: 33
        running: road.running && road.speed > .5
        repeat: true
        onTriggered: {
            road.phase = (road.phase + road.speed / 1400) % 8
            laneCanvas.requestPaint()
        }
    }
    onTelemetryChanged: laneCanvas.requestPaint()
    onConnectedChanged: laneCanvas.requestPaint()

    component Vehicle: Item {
        id: car
        property color paint: "#63dec2"
        property bool braking: false
        width: 48; height: 76
        Rectangle { x: 0; y: 15; width: 5; height: 16; radius: 2; color: "#080e16" }
        Rectangle { x: 43; y: 15; width: 5; height: 16; radius: 2; color: "#080e16" }
        Rectangle { x: 0; y: 51; width: 5; height: 16; radius: 2; color: "#080e16" }
        Rectangle { x: 43; y: 51; width: 5; height: 16; radius: 2; color: "#080e16" }
        Rectangle {
            x: 4; width: 40; height: 76; radius: 10; color: car.paint
            border.width: 1; border.color: Qt.lighter(car.paint, 1.15)
            Rectangle { x: 5; y: 17; width: 30; height: 14; radius: 5; color: "#142a36" }
            Rectangle { x: 8; y: 35; width: 24; height: 21; radius: 4; color: Qt.darker(car.paint, 1.15) }
            Rectangle { x: 6; y: 59; width: 28; height: 9; radius: 3; color: "#142a36" }
            Rectangle { x: 4; y: 4; width: 8; height: 4; radius: 2; color: "#d8f1eb" }
            Rectangle { x: 28; y: 4; width: 8; height: 4; radius: 2; color: "#d8f1eb" }
            Rectangle { x: 4; y: 69; width: 9; height: 4; radius: 1; color: car.braking ? "#ff5268" : "#6b3e4d" }
            Rectangle { x: 27; y: 69; width: 9; height: 4; radius: 1; color: car.braking ? "#ff5268" : "#6b3e4d" }
        }
    }

    Vehicle {
        id: leadCar
        x: (parent.width - width) / 2
        y: road.leadY
        scale: .77
        transformOrigin: Item.Center
        visible: road.connected && road.telemetry.present !== false
        paint: "#d8ab70"
        Behavior on y { NumberAnimation { duration: 80; easing.type: Easing.OutQuad } }
    }
    Vehicle {
        x: (parent.width - width) / 2
        y: parent.height * .69
        paint: road.danger ? "#f58691" : "#63dec2"
        braking: Number(road.telemetry.accelMps2 || 0) < -.2
        Behavior on paint { ColorAnimation { duration: 180 } }
    }

    Column {
        anchors.left: parent.left; anchors.leftMargin: 22
        anchors.top: parent.top; anchors.topMargin: 20
        spacing: 5
        Text { text: "CANLI YOL GÖRÜNÜMÜ"; color: "#8197a7"; font.family: road.fontFamily; font.pixelSize: 11; font.weight: Font.DemiBold; font.letterSpacing: 1.6 }
        Text {
            text: road.running ? (road.simulated ? "ARM firmware kodu simülasyonda" : "Ölçümler kartta işleniyor") : road.connected ? "Deneye hazır" : "Cihaz bağlantısı bekleniyor"
            color: "#c6d6df"; font.family: road.fontFamily; font.pixelSize: 12
        }
    }
    Row {
        anchors.top: parent.top; anchors.topMargin: 20
        anchors.right: parent.right; anchors.rightMargin: 22
        spacing: 7
        Rectangle { width: 6; height: 6; radius: 3; color: road.running ? road.signalColor : "#607786"; anchors.verticalCenter: parent.verticalCenter }
        Text {
            text: road.telemetry.modeLabel || "Bekleniyor"
            color: road.signalColor; font.family: road.fontFamily; font.pixelSize: 12; font.weight: Font.DemiBold
        }
    }
    Text {
        x: parent.width / 2 + 42; y: parent.height * .69 + 26
        text: "BİZ"; color: "#a5c3c5"; font.family: road.fontFamily; font.pixelSize: 11; font.letterSpacing: 1.5
    }
    Text {
        x: parent.width / 2 + 40; y: leadCar.y + 29
        visible: leadCar.visible
        text: "ÖNDEKİ"; color: "#c4ad8e"; font.family: road.fontFamily; font.pixelSize: 11; font.letterSpacing: 1.2
    }
    Text {
        anchors.left: parent.left; anchors.leftMargin: 22
        anchors.bottom: parent.bottom; anchors.bottomMargin: 17
        text: road.simulated ? "Sanal yol · ARM simülasyonunda karar" : "Sanal yol · gerçek kart üzerinde karar"
        color: "#647f8f"; font.family: road.fontFamily; font.pixelSize: 11
    }
    Text {
        anchors.right: parent.right; anchors.rightMargin: 22
        anchors.bottom: parent.bottom; anchors.bottomMargin: 17
        text: Number(road.telemetry.simSeconds || 0).toFixed(1) + " s  /  TUR " + Number(road.telemetry.cycle || 0)
        color: "#8197a7"; font.family: road.fontFamily; font.pixelSize: 11
    }
}
