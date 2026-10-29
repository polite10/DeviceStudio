pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtQuick3D

FocusScope {
    id: drive
    objectName: "drive3DView"
    required property var studio
    property var game: studio ? studio.gameState : ({})
    readonly property bool playing: Boolean(game.running)
    readonly property bool available: Boolean(game.connected && game.ready)
    readonly property bool emergency: Boolean(game.aeb)
    readonly property color signalColor: emergency ? "#ff6878" : game.warning ? "#ffc977" : "#79ebcc"
    property real sceneDistance: Number(game.distance || 0)
    property real egoX: (Number(game.egoLane === undefined ? 1 : game.egoLane) - 1) * 3.6
    property bool hoodCamera: false
    implicitHeight: 625
    implicitWidth: 1000
    Behavior on sceneDistance { NumberAnimation { duration: 50 } }
    Behavior on egoX { NumberAnimation { duration: 60 } }

    function number(value, digits) { return Number(value || 0).toFixed(digits) }
    function focusDriving() { if (playing && visible) viewport.forceActiveFocus() }
    function keyName(key) {
        return ({[Qt.Key_W]:"w", [Qt.Key_Up]:"up", [Qt.Key_S]:"s", [Qt.Key_Down]:"down",
                 [Qt.Key_A]:"a", [Qt.Key_Left]:"left", [Qt.Key_D]:"d", [Qt.Key_Right]:"right"})[key] || ""
    }
    onPlayingChanged: {
        if (playing) Qt.callLater(focusDriving)
        else if (studio) studio.releaseGameKeys()
    }
    onVisibleChanged: if (!visible && studio) studio.releaseGameKeys()
    component Copy: Text { color: "#e5edf3"; font.pixelSize: 12; elide: Text.ElideRight }
    component Chip: Rectangle {
        id: chip
        property string caption
        property color ink: "#b6c9d5"
        implicitWidth: chipText.implicitWidth + 24; implicitHeight: 31
        radius: 7; color: "#162733"; border.color: "#29414f"
        Copy { id: chipText; anchors.centerIn: parent; text: chip.caption; color: chip.ink; font.pixelSize: 11 }
    }
    ColumnLayout {
        anchors.fill: parent; spacing: 12
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            Chip { objectName: "watchMode"; caption: drive.game.mode === "active" ? "ADAS ETKİN" : drive.game.mode === "warn" ? "YALNIZ UYARI" : "ADAS KAPALI"; ink: drive.signalColor }
            Chip { objectName: "watchAcc"; caption: "ACC " + (drive.game.accEnabled ? "AÇIK" : "KAPALI") }
            Chip { objectName: "watchTarget"; caption: drive.number(drive.game.targetKmh, 0) + " km/sa" }
            Chip { objectName: "watchHeadway"; caption: "Takip " + drive.number(Number(drive.game.headwayMs) / 1000, 1) + " s" }
            Item { Layout.fillWidth: true }
            Copy { text: "AYARLAR SAATTEN"; color: "#748f9e"; font.pixelSize: 10; font.letterSpacing: 1 }
        }
        Rectangle {
            id: viewport
            objectName: "driveViewport"
            Layout.fillWidth: true; Layout.fillHeight: true
            Layout.minimumHeight: 380
            radius: 12; clip: true; color: "#bcd4df"
            focus: true
            border.width: viewport.activeFocus && drive.playing ? 2 : 1
            border.color: drive.playing ? drive.signalColor : "#314a5b"
            Keys.onPressed: function(event) {
                let key = drive.keyName(event.key)
                if (key) { drive.studio.gameKey(key, true, event.isAutoRepeat); event.accepted = true }
                else if (event.key === Qt.Key_Space || event.key === Qt.Key_Escape) {
                    if (!event.isAutoRepeat) drive.studio.pauseGame()
                    event.accepted = true
                } else if (event.key === Qt.Key_C) {
                    if (!event.isAutoRepeat) drive.hoodCamera = !drive.hoodCamera
                    event.accepted = true
                }
            }
            Keys.onReleased: function(event) {
                let key = drive.keyName(event.key)
                if (key) { drive.studio.gameKey(key, false, event.isAutoRepeat); event.accepted = true }
            }
            onActiveFocusChanged: if (!activeFocus && drive.playing) drive.studio.pauseGame()
            View3D {
                id: scene
                objectName: "embeddedDriveScene"
                anchors.fill: parent
                visible: drive.visible
                environment: SceneEnvironment {
                    backgroundMode: SceneEnvironment.SkyBox
                    lightProbe: Texture { source: "assets/sky.png" }
                    probeExposure: 0.9
                    antialiasingMode: SceneEnvironment.MSAA; antialiasingQuality: SceneEnvironment.High
                    tonemapMode: SceneEnvironment.TonemapModeLinear
                    fog: Fog { enabled: true; color: "#94bbd0"; density: 0.65; depthEnabled: true; depthNear: 110; depthFar: 300; depthCurve: 1 }
                }
                camera: chaseCamera
                PerspectiveCamera {
                    id: chaseCamera
                    position: Qt.vector3d(drive.egoX * 0.65, drive.hoodCamera ? 1.3 : 4.7, drive.hoodCamera ? -1.5 : 10.5)
                    eulerRotation.x: drive.hoodCamera ? -3 : -14
                    clipNear: 0.1; clipFar: 500; fieldOfView: drive.hoodCamera ? 74 : 58
                }
                DirectionalLight {
                    eulerRotation: Qt.vector3d(-42, -35, 0)
                    brightness: 1.2; ambientColor: "#303940"
                    castsShadow: true; shadowFactor: 55; shadowMapFar: 160; shadowBias: 0.03; shadowFilter: 2
                    shadowMapQuality: Light.ShadowMapQualityHigh
                }
                Highway3D { distance: drive.sceneDistance }
                Vehicle3D {
                    objectName: "egoVehicle3D"
                    x: drive.egoX; y: 0.15
                    visible: !drive.hoodCamera
                    variant: 0; paint: "#29a99d"
                    braking: Number(drive.game.accelMps2) < -0.8
                    wheelAngle: -drive.sceneDistance * 220
                    eulerRotation.y: 180 + (Number(drive.game.targetLane || 0) - Number(drive.game.egoLane || 0)) * -9
                }
                Repeater3D {
                    model: 12
                    delegate: Vehicle3D {
                        id: traffic
                        required property int index
                        property var car: (drive.game.traffic || [])[index] || null
                        visible: car !== null
                        x: car ? (Number(car.lane) - 1) * 3.6 : 0
                        y: 0.15; z: car ? -Number(car.relativeZ) : -500
                        variant: car ? Number(car.id) % 4 : 0
                        paint: ["#c8d0ce", "#3d7299", "#c67a55", "#e0b756"][variant]
                        braking: car ? Boolean(car.braking) : false
                        wheelAngle: -drive.sceneDistance * 220
                        Behavior on x { NumberAnimation { duration: 50 } }
                        Behavior on z { NumberAnimation { duration: 50 } }
                    }
                }
            }
            MouseArea {
                anchors.fill: parent
                onClicked: viewport.forceActiveFocus()
                cursorShape: drive.playing ? Qt.BlankCursor : Qt.ArrowCursor
            }
            Rectangle {
                anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 18
                width: liveRow.implicitWidth + 32; height: 42; radius: 9; color: "#d9162530"
                Row { id: liveRow; anchors.centerIn: parent; spacing: 15
                    Copy { text: "● " + (drive.playing ? "CANLI SÜRÜŞ" : drive.available ? "SAAT BAĞLI" : "BAĞLANTI BEKLENİYOR"); color: drive.signalColor; font.pixelSize: 11 }
                    Copy { text: "STM32 · USB"; color: "#94acba"; font.pixelSize: 11 }
                }
            }
            Rectangle {
                visible: drive.playing && (drive.emergency || drive.game.warning)
                anchors.top: parent.top; anchors.horizontalCenter: parent.horizontalCenter; anchors.topMargin: 76
                width: warningLabel.implicitWidth + 48; height: 43; radius: 8; color: "#ec162530"; border.color: drive.signalColor
                Copy { id: warningLabel; objectName: "driveWarning"; anchors.centerIn: parent; color: drive.signalColor; text: drive.emergency ? "AEB · ACİL FREN" : "ÇARPIŞMA UYARISI"; font.weight: Font.Bold; font.pixelSize: 14 }
            }
            Rectangle {
                visible: !drive.playing
                anchors.centerIn: parent; width: Math.min(425, parent.width - 64); height: instructions.implicitHeight + 44
                radius: 14; color: "#ed10222e"; border.color: "#44606c"
                Column {
                    id: instructions; anchors.centerIn: parent; width: parent.width - 42; spacing: 12
                    Copy { width: parent.width; text: !drive.available ? "3B sürüş hazır" : drive.game.status === "collision" ? "Sürüş tamamlandı · Çarpışma" : drive.game.status === "finished" ? "Sürüş tamamlandı" : drive.game.status === "paused" ? "Sürüş duraklatıldı" : "Direksiyon sende"; font.pixelSize: 23; font.weight: Font.DemiBold }
                    Text {
                        objectName: "watchStartHint"
                        width: parent.width; wrapMode: Text.WordWrap; color: "#c4d6e0"; font.pixelSize: 13; lineHeight: 1.45
                        text: !drive.available ? "Üstteki Bağlan düğmesiyle ADASLab yüklü saati bağla. Ardından saatte BASLAT’a dokun." : "Modu ve ACC ayarını saatten seç. Saat ekranındaki BASLAT’a dokun; oyun burada başlayacak."
                    }
                    Copy { width: parent.width; text: "W / ↑  Gaz       S / ↓  Fren       A D / ← →  Şerit"; font.pixelSize: 11; color: "#79ebcc" }
                }
            }
            Rectangle {
                anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 18
                width: 151; height: 98; radius: 12; color: "#e310222e"; border.color: "#49616d"
                Column {
                    anchors.centerIn: parent; spacing: 1
                    Copy { objectName: "driveSpeed"; anchors.horizontalCenter: parent.horizontalCenter; text: drive.number(drive.game.egoKmh, 0); font.pixelSize: 39; font.weight: Font.DemiBold }
                    Copy { anchors.horizontalCenter: parent.horizontalCenter; text: "km/sa"; color: "#91aebe"; font.pixelSize: 11 }
                }
            }
            Rectangle {
                anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 18
                width: readings.implicitWidth + 36; height: 76; radius: 10; color: "#e310222e"
                Row {
                    id: readings; anchors.centerIn: parent; spacing: 24
                    Column { spacing: 7; Copy { text: "TAKİP"; color: "#92adbc"; font.pixelSize: 10 } Copy { text: Number(drive.game.gap) >= 0 ? drive.number(drive.game.gap, 1) + " m" : "—"; font.pixelSize: 18 } }
                    Column { spacing: 7; Copy { text: "TTC"; color: "#92adbc"; font.pixelSize: 10 } Copy { text: Number(drive.game.ttc) >= 0 ? drive.number(drive.game.ttc, 1) + " s" : "—"; font.pixelSize: 18; color: drive.signalColor } }
                    Column { spacing: 7; Copy { text: "MESAFE"; color: "#92adbc"; font.pixelSize: 10 } Copy { text: drive.number(drive.game.distance, 0) + " m"; font.pixelSize: 18 } }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Copy { text: "WASD / Yön tuşları   ·   Boşluk: duraklat   ·   C: kamera"; color: "#8aa5b6"; font.pixelSize: 11; Layout.fillWidth: true }
            Copy { text: "Başlat / Duraklat ve ADAS ayarları: saat"; color: "#6d8b9d"; font.pixelSize: 11 }
        }
    }
}
