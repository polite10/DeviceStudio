pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes

FocusScope {
    id: gameView
    objectName: "gameView"
    required property var studio
    property var game: studio ? studio.gameState : ({})
    property string fontFamily: Qt.platform.os === "osx" ? "Helvetica Neue" : "Segoe UI"
    readonly property bool playing: Boolean(game.running)
    readonly property bool available: Boolean(game.connected && game.ready)
    readonly property bool compact: width < 850
    readonly property bool alerting: Boolean(game.warning) && game.mode !== "off"
    readonly property bool emergency: Boolean(game.aeb) && game.mode === "active"
    readonly property color signalColor: emergency || game.status === "collision" ? "#ff7b87" : alerting ? "#efbf70" : "#63dec2"
    implicitHeight: body.implicitHeight
    implicitWidth: 1000

    function number(value, digits) { return Number(value || 0).toFixed(digits) }
    function keyName(key) {
        if (key === Qt.Key_W) return "w"
        if (key === Qt.Key_Up) return "up"
        if (key === Qt.Key_S) return "s"
        if (key === Qt.Key_Down) return "down"
        if (key === Qt.Key_A) return "a"
        if (key === Qt.Key_Left) return "left"
        if (key === Qt.Key_D) return "d"
        if (key === Qt.Key_Right) return "right"
        return ""
    }
    function focusDriving() { if (gameView.playing && gameView.visible) viewport.forceActiveFocus() }
    onPlayingChanged: {
        if (playing) Qt.callLater(focusDriving)
        else if (studio) studio.releaseGameKeys()
    }
    onVisibleChanged: if (!visible && studio) studio.releaseGameKeys()

    component CopyText: Text {
        color: "#e5edf3"; font.family: gameView.fontFamily; font.pixelSize: 12
        wrapMode: Text.WordWrap
    }
    component GameButton: Button {
        id: button
        property bool primary: false
        implicitHeight: 40; implicitWidth: Math.max(85, content.implicitWidth + 30)
        hoverEnabled: true
        background: Rectangle {
            radius: 8
            color: !button.enabled ? "#182631" : button.primary ? (button.hovered ? "#86e9d1" : "#63dec2") : button.hovered ? "#29404e" : "#1c2e3c"
            border.width: button.activeFocus ? 2 : 1
            border.color: button.activeFocus ? "#c5f7eb" : button.primary ? "transparent" : "#324858"
        }
        contentItem: Text {
            id: content
            text: button.text; font.family: gameView.fontFamily; font.pixelSize: 12; font.weight: Font.DemiBold
            color: !button.enabled ? "#657b8b" : button.primary ? "#10251f" : "#dce7ef"
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        }
    }
    component ModeButton: AbstractButton {
        id: modeButton
        property string modeValue
        property string title
        property string description
        readonly property bool selected: gameView.game.mode === modeValue
        Layout.fillWidth: true
        Layout.preferredWidth: 1
        Layout.minimumWidth: 0
        implicitHeight: 69
        enabled: !gameView.playing
        hoverEnabled: true
        leftPadding: 15; rightPadding: 15; topPadding: 12; bottomPadding: 12
        Accessible.name: title + ". " + description
        onClicked: gameView.studio.setGameOption("mode", modeValue)
        background: Rectangle {
            radius: 10
            color: modeButton.selected ? "#173b39" : modeButton.hovered ? "#182c3a" : "#12212e"
            border.width: modeButton.activeFocus ? 2 : 1
            border.color: modeButton.activeFocus ? "#ccf7eb" : modeButton.selected ? "#459f8e" : "#2a3c4b"
            opacity: modeButton.enabled || modeButton.selected ? 1 : .6
        }
        contentItem: Column {
            spacing: 5
            Text { text: modeButton.title; color: modeButton.selected ? "#8cf1d8" : "#d1dfe8"; font.family: gameView.fontFamily; font.pixelSize: 13; font.weight: Font.DemiBold }
            Text { text: modeButton.description; color: modeButton.selected ? "#98c8bf" : "#7b95a8"; font.family: gameView.fontFamily; font.pixelSize: 11; elide: Text.ElideRight; width: parent.width }
        }
    }
    component Readout: Column {
        id: readout
        property string label
        property string value
        property string unit: ""
        Layout.fillWidth: true
        spacing: 6
        CopyText { text: readout.label; color: "#7893a5"; font.pixelSize: 11 }
        Row {
            spacing: 5
            CopyText { text: readout.value; font.pixelSize: 24; font.weight: Font.DemiBold }
            CopyText { text: readout.unit; color: "#819bad"; font.pixelSize: 11; anchors.bottom: parent.bottom; anchors.bottomMargin: 3 }
        }
    }
    component GameToggle: Switch {
        id: toggle
        implicitHeight: 32
        spacing: 8
        indicator: Rectangle {
            implicitWidth: 32; implicitHeight: 19
            x: toggle.leftPadding; y: (toggle.height - height) / 2
            radius: 10; color: toggle.checked ? "#63dec2" : "#344957"
            border.width: toggle.activeFocus ? 1 : 0; border.color: "#d3fff3"
            opacity: toggle.enabled ? 1 : .45
            Rectangle {
                width: 13; height: 13; y: 3
                x: toggle.checked ? 16 : 3
                radius: 7; color: toggle.checked ? "#10251f" : "#a3b2bc"
                Behavior on x { NumberAnimation { duration: 120 } }
            }
        }
        contentItem: Text {
            text: toggle.text; color: toggle.enabled ? "#c9d7e1" : "#687e8e"
            font.family: gameView.fontFamily; font.pixelSize: 12
            leftPadding: toggle.indicator.width + toggle.spacing
            verticalAlignment: Text.AlignVCenter
        }
    }
    component Vehicle: Item {
        id: vehicle
        property color paint: "#63dec2"
        property bool braking: false
        property bool player: false
        width: 50; height: 80
        Rectangle { x: 0; y: 14; width: 6; height: 17; radius: 2; color: "#070e15" }
        Rectangle { x: 44; y: 14; width: 6; height: 17; radius: 2; color: "#070e15" }
        Rectangle { x: 0; y: 55; width: 6; height: 17; radius: 2; color: "#070e15" }
        Rectangle { x: 44; y: 55; width: 6; height: 17; radius: 2; color: "#070e15" }
        Rectangle {
            x: 4; width: 42; height: 80; radius: 11
            color: vehicle.paint; border.width: 1; border.color: Qt.lighter(vehicle.paint, 1.14)
            Rectangle { x: 5; y: 17; width: 32; height: 16; radius: 5; color: "#102735" }
            Rectangle { x: 9; y: 37; width: 24; height: 20; radius: 4; color: Qt.darker(vehicle.paint, 1.14) }
            Rectangle { x: 6; y: 61; width: 30; height: 9; radius: 3; color: "#102735" }
            Rectangle { x: 4; y: 4; width: 9; height: 4; radius: 2; color: "#e6e3ce" }
            Rectangle { x: 29; y: 4; width: 9; height: 4; radius: 2; color: "#e6e3ce" }
            Rectangle { x: 4; y: 74; width: 9; height: 4; radius: 1; color: vehicle.braking ? "#ff4862" : "#733d4c" }
            Rectangle { x: 29; y: 74; width: 9; height: 4; radius: 1; color: vehicle.braking ? "#ff4862" : "#733d4c" }
            Rectangle { visible: vehicle.player; x: 13; y: 8; width: 16; height: 3; radius: 2; color: "#d0fff1" }
        }
    }

    ColumnLayout {
        id: body
        width: parent.width
        spacing: 16
        RowLayout {
            Layout.fillWidth: true; spacing: 12
            ModeButton { objectName: "gameModeActive"; modeValue: "active"; title: "Aktif destek"; description: "Uyarı + otomatik acil fren" }
            ModeButton { objectName: "gameModeWarn"; modeValue: "warn"; title: "Yalnız uyarı"; description: "Gaz ve fren tamamen sende" }
            ModeButton { objectName: "gameModeOff"; modeValue: "off"; title: "Destek kapalı"; description: "Uyarı ve müdahale kapalı" }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 12
            GameButton {
                objectName: "game3DButton"
                text: gameView.game.renderer3dConnected ? "3B sürüş açık" : "3B sürüşü aç"
                primary: true
                enabled: Boolean(gameView.game.renderer3dAvailable) && !gameView.game.renderer3dConnected
                onClicked: gameView.studio.openGame3D()
                ToolTip.visible: hovered
                ToolTip.text: gameView.game.renderer3dMessage || "Godot oyun penceresini aç"
            }
            CopyText {
                text: gameView.game.renderer3dConnected ? "Godot bağlı · WASD / oklar" : "W / ↑ gaz · S / ↓ fren · A–D / ← → şerit"
                color: "#95afbf"; Layout.fillWidth: true
            }
            GameToggle {
                id: accSwitch
                objectName: "gameAccToggle"
                text: "ACC"; checked: Boolean(gameView.game.accEnabled)
                enabled: !gameView.playing && gameView.game.mode === "active"
                onToggled: gameView.studio.setGameOption("accEnabled", checked)
                ToolTip.visible: hovered
                ToolTip.text: "Hedef hızı ve takip mesafesini korur. Oyuncu freni ACC'yi devreden çıkarır."
            }
            CopyText { text: "Hedef"; color: "#7c99ab"; font.pixelSize: 11 }
            SpinBox {
                objectName: "gameTargetSpeed"
                from: 30; to: 160; value: Number(gameView.game.targetKmh || 90)
                editable: true; enabled: !gameView.playing
                implicitHeight: 34; Layout.preferredWidth: 100
                palette.text: "#dce7ef"; palette.base: "#132130"; palette.button: "#213342"; palette.buttonText: "#dce7ef"
                onValueModified: gameView.studio.setGameOption("targetKmh", value)
            }
            CopyText { text: "km/sa"; color: "#7c99ab"; font.pixelSize: 11 }
        }
        FocusScope {
            id: viewport
            objectName: "gameViewport"
            Layout.fillWidth: true
            // Keep the live driving HUD visible above the application footer
            // at the supported 1000×720 window size, without scrolling mid-drive.
            Layout.preferredHeight: gameView.compact ? 315 : Math.max(365, Math.min(465, gameView.width * .43))
            clip: true
            readonly property real horizon: height * .12
            readonly property real egoY: Math.min(height * .76, height - 88)
            readonly property real egoLane: Number(gameView.game.egoLane === undefined ? 1 : gameView.game.egoLane)
            property real lanePhase: 0
            function halfRoad(depth) { return width * (.12 + .32 * Math.max(0, Math.min(1, depth))) }
            function laneX(lane, depth) { return width / 2 + (Number(lane) - 1) * (2 / 3) * halfRoad(depth) }
            Keys.priority: Keys.BeforeItem
            Keys.onPressed: function(event) {
                if (!gameView.playing || !gameView.visible) return
                var key = gameView.keyName(event.key)
                if (key.length) {
                    gameView.studio.gameKey(key, true, event.isAutoRepeat)
                    event.accepted = true
                } else if (event.key === Qt.Key_Space) {
                    if (!event.isAutoRepeat) gameView.studio.pauseGame()
                    event.accepted = true
                }
            }
            Keys.onReleased: function(event) {
                var key = gameView.keyName(event.key)
                if (key.length) {
                    gameView.studio.gameKey(key, false, event.isAutoRepeat)
                    event.accepted = true
                }
            }
            onActiveFocusChanged: {
                if (!activeFocus && gameView.studio) {
                    gameView.studio.focusLost()
                }
            }
            Rectangle { anchors.fill: parent; color: "#0e1a24"; radius: 12; border.width: 1; border.color: viewport.activeFocus ? "#3a776e" : "#293e4d" }
            Shape {
                anchors.fill: parent
                ShapePath {
                    strokeColor: "#42606d"; strokeWidth: 1
                    fillColor: "#172b37"
                    startX: viewport.width * .38; startY: viewport.horizon
                    PathLine { x: viewport.width * .62; y: viewport.horizon }
                    PathLine { x: viewport.width * .94; y: viewport.height + 2 }
                    PathLine { x: viewport.width * .06; y: viewport.height + 2 }
                    PathLine { x: viewport.width * .38; y: viewport.horizon }
                }
            }
            Repeater {
                model: 24
                delegate: Rectangle {
                    required property int index
                    readonly property real p: ((index % 12 + viewport.lanePhase) % 12) / 12
                    readonly property real depth: p * p
                    x: viewport.width / 2 + (index < 12 ? -1 : 1) * viewport.halfRoad(depth) / 3
                    y: viewport.horizon + depth * (viewport.height - viewport.horizon)
                    width: 1 + depth * 2; height: 3 + depth * 20
                    rotation: index < 12 ? 8 : -8
                    color: "#64828e"; opacity: .6
                }
            }
            Timer {
                interval: 33; repeat: true
                running: gameView.playing && Number(gameView.game.egoKmh || 0) > .2
                onTriggered: viewport.lanePhase = (viewport.lanePhase + Number(gameView.game.egoKmh || 0) / 900) % 12
            }
            Repeater {
                // A fixed pool keeps delegates and keyboard focus alive across
                // every telemetry snapshot. Only their numeric data changes.
                model: 12
                delegate: Vehicle {
                    id: trafficCar
                    required property int index
                    readonly property var vehicleInfo: (gameView.game.traffic || [])[index] || ({})
                    readonly property real range: Number(vehicleInfo.relativeZ || 0)
                    readonly property real perspective: 1 / (1 + Math.max(0, range) / 48)
                    readonly property real displayY: range >= 0 ? viewport.horizon + (viewport.egoY - 82 - viewport.horizon) * perspective : viewport.egoY + 92 + Math.abs(range) * 2.2
                    visible: vehicleInfo.id !== undefined && range > -25 && range < 190
                    x: viewport.laneX(Number(vehicleInfo.lane === undefined ? 1 : vehicleInfo.lane), Math.max(0, (displayY - viewport.horizon) / (viewport.height - viewport.horizon))) - width / 2
                    y: displayY
                    scale: range >= 0 ? .42 + perspective * .52 : 1
                    transformOrigin: Item.Bottom
                    z: displayY
                    paint: ["#cfab73", "#7ba6c1", "#b5a1c5", "#d28c7c"][index % 4]
                    braking: Boolean(vehicleInfo.braking)
                    Behavior on x { enabled: gameView.playing; NumberAnimation { duration: 70; easing.type: Easing.Linear } }
                    Behavior on y { enabled: gameView.playing; NumberAnimation { duration: 70; easing.type: Easing.Linear } }
                }
            }
            Vehicle {
                objectName: "gamePlayerCar"
                x: viewport.laneX(viewport.egoLane, .86) - width / 2
                y: viewport.egoY; z: 1000
                player: true; braking: Number(gameView.game.accelMps2 || 0) < -.2
                paint: gameView.emergency ? "#f78a98" : "#63dec2"
                Behavior on x { NumberAnimation { duration: 70; easing.type: Easing.Linear } }
            }
            MouseArea {
                anchors.fill: parent; z: 1500
                onClicked: gameView.focusDriving()
                Accessible.name: "Sürüş alanı. Klavye kontrolü için tıklayın."
            }
            Row {
                anchors.left: parent.left; anchors.leftMargin: 20
                anchors.top: parent.top; anchors.topMargin: 17; spacing: 8; z: 1600
                Rectangle { width: 6; height: 6; radius: 3; color: viewport.activeFocus && gameView.playing ? "#63dec2" : "#6d8293"; anchors.verticalCenter: parent.verticalCenter }
                CopyText { text: viewport.activeFocus && gameView.playing ? "KLAVYE ETKİN" : gameView.playing ? "Klavye için yola tıkla" : "TRAFİK LABORATUVARI"; font.pixelSize: 11; font.letterSpacing: 1.3; color: "#aac3cf" }
            }
            Column {
                anchors.right: parent.right; anchors.rightMargin: 20
                anchors.top: parent.top; anchors.topMargin: 17; spacing: 5; z: 1600
                CopyText { text: Math.max(0, Math.ceil(Number(gameView.game.remaining || 0))) + " sn"; font.pixelSize: 23; font.weight: Font.DemiBold; anchors.right: parent.right }
                CopyText { text: gameView.number(gameView.game.distance, 0) + " m"; color: "#7895a8"; font.pixelSize: 11; anchors.right: parent.right }
            }
            Rectangle {
                visible: gameView.playing && (gameView.emergency || gameView.alerting)
                anchors.horizontalCenter: parent.horizontalCenter; y: 21
                width: alertLabel.implicitWidth + 32; height: 34; radius: 8; z: 1700
                color: gameView.emergency ? "#542b38" : "#4a3c29"
                border.width: 1; border.color: gameView.signalColor
                Text { id: alertLabel; anchors.centerIn: parent; text: gameView.emergency ? "AEB · ACİL FREN" : "ÇARPIŞMA UYARISI"; color: gameView.signalColor; font.family: gameView.fontFamily; font.pixelSize: 12; font.weight: Font.DemiBold }
            }
            Rectangle {
                anchors.fill: parent; radius: 12; z: 1800
                color: "#ce0c1823"
                visible: !gameView.playing
                Column {
                    width: Math.min(430, parent.width - 70); anchors.centerIn: parent; spacing: 12
                    Text {
                        width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                        text: !gameView.available ? "Sürüşe hazırlan" : gameView.game.status === "collision" ? "Çarpışma" : gameView.game.status === "finished" ? "Sürüş tamamlandı" : gameView.game.status === "paused" ? "Sürüş duraklatıldı" : "Direksiyon sende"
                        color: gameView.game.status === "collision" ? "#ff9aa5" : "#e5edf3"; font.family: gameView.fontFamily; font.pixelSize: 25; font.weight: Font.DemiBold
                    }
                    CopyText {
                        width: parent.width; horizontalAlignment: Text.AlignHCenter
                        text: !gameView.available ? "Kartı bağlayın ve ADASLab v2 firmware’ini yükleyin. Sürüş bilgisayarda, ADAS kararları kartta çalışır." : gameView.game.status === "collision" ? "Sonuçlarını karşılaştır. Aynı trafik düzenini başka bir destek moduyla yeniden deneyebilirsin." : "W / ↑ ile gaz, S / ↓ ile fren. A–D / yön tuşlarıyla şerit değiştir."
                        color: "#95b0c2"; font.pixelSize: 13
                    }
                    GameButton {
                        objectName: "gameStartButton"
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: gameView.game.status === "paused" ? "Sürüşe devam et" : "Sürüşü başlat"
                        primary: true; enabled: gameView.available
                        onClicked: gameView.studio.startGame()
                    }
                }
            }
            Row {
                anchors.left: parent.left; anchors.leftMargin: 20
                anchors.bottom: parent.bottom; anchors.bottomMargin: 15; spacing: 10; z: 1700
                CopyText { text: "3 ŞERİT"; color: "#7693a4"; font.pixelSize: 11; font.letterSpacing: 1 }
                CopyText { text: gameView.game.mode === "active" ? "AKTİF DESTEK" : gameView.game.mode === "warn" ? "YALNIZ UYARI" : "DESTEK KAPALI"; color: gameView.game.mode === "off" ? "#a4b3bd" : gameView.signalColor; font.pixelSize: 11; font.letterSpacing: 1 }
            }
            GameButton {
                objectName: "gamePauseButton"
                visible: gameView.playing
                anchors.right: parent.right; anchors.rightMargin: 16
                anchors.bottom: parent.bottom; anchors.bottomMargin: 12
                text: "Duraklat · Boşluk"; implicitHeight: 34; z: 1800
                onClicked: gameView.studio.pauseGame()
            }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 20
            Readout { objectName: "gameSpeedReadout"; label: "HIZ"; value: gameView.number(gameView.game.egoKmh, 1); unit: "km/sa" }
            Readout { objectName: "gameGapReadout"; label: "MESAFE"; value: Number(gameView.game.gap) >= 0 ? gameView.number(gameView.game.gap, 1) : "—"; unit: "m" }
            Readout { objectName: "gameTtcReadout"; label: "TTC"; value: Number(gameView.game.ttc) >= 0 && gameView.game.mode !== "off" ? gameView.number(gameView.game.ttc, 1) : "—"; unit: "sn" }
            Readout { objectName: "gameAccelReadout"; label: "İVME / FREN"; value: gameView.number(gameView.game.accelMps2, 2); unit: "m/s²" }
            Readout { objectName: "gameScoreReadout"; label: "PUAN"; value: gameView.number(gameView.game.score, 0) }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 12
            CopyText { text: gameView.game.hint || "Aynı trafik tohumuyla üç modu karşılaştır. Mod ayarları sürüş duraklatıldığında değiştirilebilir."; color: "#7895a7"; font.pixelSize: 11; Layout.fillWidth: true }
            CopyText { text: "Trafik"; color: "#7e9aaa"; font.pixelSize: 11 }
            SpinBox {
                objectName: "gameSeed"
                from: 1; to: 9999; value: Number(gameView.game.seed || 42)
                editable: true; enabled: !gameView.playing
                implicitHeight: 32; Layout.preferredWidth: 106
                palette.text: "#dce7ef"; palette.base: "#132130"; palette.button: "#213342"; palette.buttonText: "#dce7ef"
                onValueModified: gameView.studio.setGameOption("seed", value)
            }
            GameButton { text: "Yeniden dene"; implicitHeight: 34; enabled: gameView.available && !gameView.playing; onClicked: gameView.studio.restartGame() }
        }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: resultsColumn.implicitHeight + 32
            color: "#111f2b"; radius: 11; border.width: 1; border.color: "#253b49"
            ColumnLayout {
                id: resultsColumn
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                anchors.margins: 16; spacing: 10
                RowLayout {
                    Layout.fillWidth: true
                    CopyText { text: "Sürüş sonuçları"; font.pixelSize: 13; font.weight: Font.DemiBold }
                    Item { Layout.fillWidth: true }
                    CopyText { text: "Aynı trafik, farklı destek modu"; color: "#6f8c9e"; font.pixelSize: 11 }
                }
                CopyText {
                    visible: !(gameView.game.results || []).length
                    text: "Sürüş tamamlandığında mesafe, çarpışma ve ADAS müdahaleleri burada görünür."
                    color: "#7896a7"; font.pixelSize: 11; Layout.fillWidth: true
                }
                Repeater {
                    model: Math.min(3, (gameView.game.results || []).length)
                    delegate: RowLayout {
                        required property int index
                        readonly property var row: (gameView.game.results || [])[(gameView.game.results || []).length - 1 - index] || ({})
                        Layout.fillWidth: true; spacing: 18
                        CopyText { text: parent.row.mode === "active" ? "Aktif destek" : parent.row.mode === "warn" ? "Yalnız uyarı" : "Destek kapalı"; Layout.preferredWidth: 130 }
                        CopyText { text: "Trafik " + (parent.row.seed || "—"); color: "#829eae"; font.pixelSize: 11; Layout.fillWidth: true }
                        CopyText { text: gameView.number(parent.row.distance, 0) + " m"; Layout.preferredWidth: 70 }
                        CopyText { text: (parent.row.collisions || 0) + " çarpışma"; color: Number(parent.row.collisions) > 0 ? "#ed9ca5" : "#aac4cf"; Layout.preferredWidth: 95 }
                        CopyText { text: (parent.row.interventions || 0) + " müdahale"; color: "#aac4cf"; Layout.preferredWidth: 95 }
                        CopyText { text: gameView.number(parent.row.score, 0) + " puan"; color: "#71d9c1"; Layout.preferredWidth: 80 }
                    }
                }
            }
        }
    }
}
