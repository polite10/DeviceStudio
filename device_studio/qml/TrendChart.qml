import QtQuick

Item {
    id: chart
    property var history: []
    property string fontFamily: Qt.platform.os === "osx" ? "Helvetica Neue" : "Segoe UI"
    Canvas {
        id: canvas
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var left = 35, right = width - 10, top = 9, bottom = height - 22
            if (right <= left || bottom <= top) return
            var data = chart.history || []
            var max = 20
            for (var i = 0; i < data.length; i++) max = Math.max(max, Number(data[i].gap || 0))
            max = Math.ceil(max / 20) * 20
            ctx.font = "11px '" + chart.fontFamily + "'"
            ctx.fillStyle = "#778d9e"
            ctx.strokeStyle = "#233443"
            ctx.lineWidth = 1
            for (var line = 0; line < 3; line++) {
                var y = top + (bottom - top) * line / 2
                ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke()
                ctx.textAlign = "right"; ctx.fillText(String(Math.round(max * (1 - line / 2))), left - 10, y + 3)
            }
            ctx.textAlign = "right"; ctx.fillText("Şimdi", right, height - 3)
            if (data.length < 2) return
            ctx.beginPath()
            for (var j = 0; j < data.length; j++) {
                var x = left + j / (data.length - 1) * (right - left)
                var point = bottom - Math.max(0, Number(data[j].gap || 0)) / max * (bottom - top)
                if (j === 0) ctx.moveTo(x, point); else ctx.lineTo(x, point)
            }
            ctx.lineTo(right, bottom); ctx.lineTo(left, bottom); ctx.closePath()
            var gradient = ctx.createLinearGradient(0, top, 0, bottom)
            gradient.addColorStop(0, "#205045"); gradient.addColorStop(1, "#10252b")
            ctx.fillStyle = gradient; ctx.fill()
            ctx.beginPath()
            for (var k = 0; k < data.length; k++) {
                var px = left + k / (data.length - 1) * (right - left)
                var py = bottom - Math.max(0, Number(data[k].gap || 0)) / max * (bottom - top)
                if (k === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py)
            }
            ctx.strokeStyle = "#63dec2"; ctx.lineWidth = 2; ctx.stroke()
        }
    }
    Text {
        anchors.centerIn: parent
        visible: !chart.history || chart.history.length < 2
        text: "Deney başladığında mesafe grafiği burada görünür."
        color: "#778d9e"; font.family: chart.fontFamily; font.pixelSize: 12
    }
    onHistoryChanged: canvas.requestPaint()
}
