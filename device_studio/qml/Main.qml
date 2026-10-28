pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    // The Python QObject is injected as an initial property, never a global.
    // Its public slots are exercised by the bridge and rendered-UI tests.
    required property var studio
    objectName: "mainWindow"
    visible: true
    width: 1360; height: 900
    minimumWidth: 1000; minimumHeight: 720
    title: "Device Studio"
    color: "#0b121c"
    font.family: Qt.platform.os === "osx" ? "Helvetica Neue" : "Segoe UI"
    font.pixelSize: 13
    property var s: window.studio ? window.studio.state : ({page:"adas", connected:false, busy:false, running:false, operation:"idle", portIndex:-1})
    readonly property var t: window.s.telemetry || ({})
    readonly property bool hasMeasurements: window.s.connected && window.s.app === "ADASLab" && window.t.mode !== "WAITING"
    readonly property color textColor: "#e5edf3"
    readonly property color mutedColor: "#8b9eae"
    readonly property color accentColor: "#63dec2"
    readonly property string monoFont: Qt.platform.os === "osx" ? "Menlo" : "Consolas"
    property bool logsOpen: false
    property string currentPage: window.s.page || "adas"
    onCurrentPageChanged: if (pageScroll && pageScroll.contentItem) pageScroll.contentItem.contentY = 0

    function number(value, precision) { return Number(value || 0).toFixed(precision) }
    function pageTitle() {
        return ({adas:"ADASLab",firmware:"Firmware yönetimi",duello:"Düello",console:"Komut konsolu"})[window.s.page] || "ADASLab"
    }
    function scenarioIndex() {
        var list = window.s.scenarios || []
        for (var i = 0; i < list.length; i++) if (list[i].value === window.s.scenario) return i
        return 0
    }
    function scenarioDescription() {
        var list = window.s.scenarios || [], index = scenarioIndex()
        return list.length ? list[index].description : ""
    }
    onClosing: function(close) { close.accepted = window.studio.requestClose() }

    component Panel: Rectangle {
        color: "#111d29"; radius: 13
        border.width: 1; border.color: "#243341"
    }
    component LabelText: Text {
        color: window.textColor
        font.family: window.font.family
        font.pixelSize: 13
        wrapMode: Text.WordWrap
    }
    component ActionButton: Button {
        id: button
        property bool primary: false
        property bool destructive: false
        implicitHeight: 40
        implicitWidth: Math.max(84, label.implicitWidth + 30)
        hoverEnabled: true
        padding: 12
        background: Rectangle {
            radius: 8
            color: !button.enabled ? "#18232e" : button.destructive ? (button.hovered ? "#4b2a35" : "#36242e") : button.primary ? (button.hovered ? "#86e9d1" : "#63dec2") : button.down ? "#2b4050" : button.hovered ? "#263847" : "#1b2b3a"
            border.width: button.activeFocus ? 2 : 1
            border.color: button.activeFocus ? "#b8f2e4" : button.primary ? "transparent" : "#304454"
            Behavior on color { ColorAnimation { duration: 100 } }
        }
        contentItem: Text {
            id: label
            text: button.text
            font.family: window.font.family; font.pixelSize: 12; font.weight: Font.DemiBold
            color: !button.enabled ? "#637684" : button.primary ? "#10251f" : button.destructive ? "#ffb1b7" : "#dce7ef"
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
    }
    component SelectBox: ComboBox {
        id: box
        implicitHeight: 40
        palette.text: "#dce7ef"
        palette.buttonText: "#dce7ef"
        palette.base: "#132130"
        palette.highlight: "#244b49"
        palette.highlightedText: "#e5edf3"
        background: Rectangle { color: box.enabled ? "#132130" : "#14212b"; radius: 8; border.width: 1; border.color: box.activeFocus ? "#63dec2" : "#304454" }
        contentItem: Text {
            text: box.displayText; color: box.enabled ? "#dce7ef" : "#6d8292"
            font.family: window.font.family; font.pixelSize: 12
            leftPadding: 12; rightPadding: 30; verticalAlignment: Text.AlignVCenter; elide: Text.ElideMiddle
        }
    }
    component Toggle: Switch {
        id: toggle
        implicitHeight: 30
        spacing: 8
        indicator: Rectangle {
            implicitWidth: 32; implicitHeight: 19
            x: toggle.leftPadding; y: (toggle.height - height) / 2
            radius: 10; color: toggle.checked ? "#63dec2" : "#344957"
            border.width: toggle.activeFocus ? 1 : 0; border.color: "#d3fff3"
            opacity: toggle.enabled ? 1 : .4
            Rectangle {
                width: 13; height: 13; y: 3
                x: toggle.checked ? 16 : 3
                radius: 7; color: toggle.checked ? "#10251f" : "#a3b2bc"
                Behavior on x { NumberAnimation { duration: 120 } }
            }
        }
        contentItem: Text {
            text: toggle.text; color: toggle.enabled ? "#c9d7e1" : "#687e8e"
            font.family: window.font.family; font.pixelSize: 12
            leftPadding: toggle.indicator.width + toggle.spacing
            verticalAlignment: Text.AlignVCenter
        }
    }
    component Metric: ColumnLayout {
        id: metric
        Layout.fillWidth: true
        Layout.maximumWidth: 100000
        property string label: ""
        property string value: "—"
        property string unit: ""
        property string note: ""
        spacing: 6
        LabelText { text: metric.label; color: "#91a5b5"; font.pixelSize: 11 }
        RowLayout {
            spacing: 5
            LabelText { text: metric.value; font.pixelSize: 28; font.weight: Font.DemiBold }
            LabelText { text: metric.unit; color: "#8198a9"; font.pixelSize: 11; Layout.alignment: Qt.AlignBottom; Layout.bottomMargin: 5 }
        }
        LabelText { text: metric.note; color: "#70899a"; font.pixelSize: 11; visible: metric.note.length > 0 }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0
        Rectangle {
            Layout.preferredWidth: 200; Layout.fillHeight: true
            color: "#0e1823"
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: "#22313f" }
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 20
                spacing: 8
                RowLayout {
                    Layout.topMargin: 10; Layout.bottomMargin: 33; spacing: 11
                    Rectangle {
                        width: 34; height: 34; radius: 9; color: "#63dec2"
                        Text { anchors.centerIn: parent; text: "DS"; color: "#10251f"; font.pixelSize: 12; font.weight: Font.Bold }
                    }
                    Column {
                        spacing: 2
                        Text { text: "Device Studio"; color: "#e5edf3"; font.family: window.font.family; font.pixelSize: 14; font.weight: Font.DemiBold }
                        Text { text: "STM32 ARAÇLARI"; color: "#698293"; font.family: window.font.family; font.pixelSize: 11; font.letterSpacing: 1.2 }
                    }
                }
                Text { text: "ÇALIŞMA ALANI"; color: "#647d8f"; font.family: window.font.family; font.pixelSize: 11; font.letterSpacing: 1.5; Layout.bottomMargin: 8 }
                Repeater {
                    model: [
                        {page:"adas",title:"ADASLab",subtitle:"Sürüş deneyleri",symbol:"A"},
                        {page:"firmware",title:"Firmware",subtitle:"Yükleme ve kurtarma",symbol:"F"},
                        {page:"duello",title:"Düello",subtitle:"Karakter kontrolü",symbol:"D"},
                        {page:"console",title:"Komut konsolu",subtitle:"Cihazla iletişim",symbol:">"}
                    ]
                    delegate: ItemDelegate {
                        id: navItem
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: 57
                        hoverEnabled: true
                        Accessible.name: modelData.title
                        onClicked: window.studio.navigate(modelData.page)
                        background: Rectangle {
                            radius: 9; color: window.s.page === navItem.modelData.page ? "#1a2d3b" : navItem.hovered ? "#152431" : "transparent"
                            border.width: navItem.activeFocus ? 1 : 0; border.color: "#63dec2"
                            Rectangle { visible: window.s.page === navItem.modelData.page; x: 0; y: 17; width: 3; height: 23; radius: 2; color: "#63dec2" }
                        }
                        contentItem: RowLayout {
                            spacing: 10
                            Text { text: navItem.modelData.symbol; color: window.s.page === navItem.modelData.page ? "#63dec2" : "#7690a3"; font.family: window.monoFont; font.pixelSize: 14; horizontalAlignment: Text.AlignHCenter; Layout.preferredWidth: 22 }
                            Column {
                                Layout.fillWidth: true; spacing: 4
                                Text { text: navItem.modelData.title; color: window.s.page === navItem.modelData.page ? "#e5edf3" : "#a8bdcb"; font.family: window.font.family; font.pixelSize: 12; font.weight: Font.DemiBold }
                                Text { text: navItem.modelData.subtitle; color: "#657f92"; font.family: window.font.family; font.pixelSize: 11 }
                            }
                        }
                    }
                }
                Item { Layout.fillHeight: true }
                Rectangle { Layout.fillWidth: true; height: 1; color: "#22313f"; Layout.bottomMargin: 12 }
                RowLayout {
                    spacing: 8
                    Rectangle { width: 6; height: 6; radius: 3; color: window.s.connected ? "#63dec2" : "#526f82" }
                    Text { text: window.s.connected ? (window.s.app || "Cihaz bağlı") : "Cihaz bağlı değil"; color: "#bdd0dc"; font.family: window.font.family; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                }
                Text { text: "STM32U5A9J-DK"; color: "#698496"; font.family: window.font.family; font.pixelSize: 11; Layout.topMargin: 4 }
                Text { text: window.s.backendLabel || "USB / ST-LINK"; color: "#526c7e"; font.family: window.font.family; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true; Layout.bottomMargin: 6 }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            spacing: 0
            Rectangle {
                objectName: "connectionHeader"
                Layout.fillWidth: true; Layout.preferredHeight: 83
                Layout.minimumHeight: 83; Layout.maximumHeight: 83
                color: "#101b27"
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: "#22313f" }
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 26; anchors.rightMargin: 26
                    spacing: 10
                    Item {
                        objectName: "pageTitleColumn"
                        Layout.fillWidth: true; Layout.fillHeight: true; Layout.maximumWidth: 100000
                        Text { objectName: "pageTitle"; y: window.width > 1210 ? 17 : 27; text: window.pageTitle(); color: window.textColor; font.family: window.font.family; font.pixelSize: 23; font.weight: Font.DemiBold }
                        Text { y: 50; visible: window.width > 1210; text: window.s.page === "adas" ? "Sürüş destek sistemlerini gözlemleyin ve sınayın." : window.s.page === "firmware" ? "Firmware paketleri ve bootloader yönetimi." : window.s.page === "duello" ? "Kart üzerindeki karakteri gerçek zamanlı yönetin." : "Uygulama komutları ve cihazın JSON durumu."; color: window.mutedColor; font.family: window.font.family; font.pixelSize: 11 }
                    }
                    SelectBox {
                        id: portBox
                        objectName: "portSelector"
                        Layout.preferredWidth: window.width > 1210 ? 244 : 187
                        model: window.s.ports || []; textRole: "label"
                        currentIndex: window.s.portIndex === undefined ? -1 : window.s.portIndex
                        enabled: !window.s.busy && !window.s.connected
                        onActivated: function(index) { window.studio.selectPort(index) }
                        ToolTip.visible: hovered; ToolTip.text: "ST-LINK sanal seri portunu seçin"
                    }
                    ActionButton { text: "↻"; implicitWidth: 40; enabled: !window.s.busy && !window.s.connected; onClicked: window.studio.refreshPorts(); ToolTip.visible: hovered; ToolTip.text: "Seri portları yenile"; Accessible.name: "Seri portları yenile" }
                    ActionButton {
                        objectName: "connectionButton"
                        text: window.s.connected ? "Bağlantıyı kes" : window.s.operation === "connecting" ? "Bağlanıyor…" : "Bağlan"
                        primary: !window.s.connected
                        enabled: !window.s.busy
                        onClicked: window.s.connected ? window.studio.disconnectDevice() : window.studio.connectDevice()
                    }
                }
            }
            ScrollView {
                id: pageScroll
                Layout.fillWidth: true; Layout.fillHeight: true
                Layout.minimumHeight: 0
                clip: true; padding: 24
                contentWidth: availableWidth
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                ColumnLayout {
                    width: pageScroll.availableWidth
                    spacing: 22

                    ColumnLayout {
                        visible: window.s.page === "adas"
                        Layout.fillWidth: true; spacing: 20
                        RowLayout {
                            Layout.fillWidth: true; spacing: 20
                            Panel {
                                Layout.fillWidth: true; Layout.preferredHeight: 340
                                clip: true
                                RoadView { anchors.fill: parent; anchors.margins: 1; telemetry: window.t; running: window.s.running; connected: window.s.connected && window.s.app === "ADASLab"; simulated: String(window.s.backendLabel || "").indexOf("simülasyonu") >= 0; fontFamily: window.font.family }
                            }
                            Panel {
                                Layout.preferredWidth: window.width < 1200 ? 250 : 280
                                Layout.preferredHeight: 340
                                ColumnLayout {
                                    anchors.fill: parent; anchors.margins: 20; spacing: 8
                                    LabelText { text: "Deney ayarları"; font.pixelSize: 14; font.weight: Font.DemiBold }
                                    LabelText { text: "SENARYO"; color: "#7893a5"; font.pixelSize: 11; font.letterSpacing: 1.2; Layout.topMargin: 4 }
                                    SelectBox {
                                        objectName: "scenarioSelector"
                                        Layout.fillWidth: true
                                        model: window.s.scenarios || []; textRole: "text"; currentIndex: window.scenarioIndex()
                                        enabled: !window.s.busy
                                        onActivated: function(index) { window.studio.setOption("scenario", window.s.scenarios[index].value) }
                                    }
                                    LabelText { text: window.scenarioDescription(); color: "#839cac"; font.pixelSize: 11; Layout.fillWidth: true; Layout.preferredHeight: 29 }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        LabelText { text: "Hedef hız"; color: "#b5c7d3"; Layout.fillWidth: true; font.pixelSize: 11 }
                                        SpinBox {
                                            objectName: "targetSpeed"
                                            from: 0; to: 200; value: Number(window.s.targetKmh || 0); editable: true
                                            enabled: !window.s.busy; Layout.preferredWidth: 105; implicitHeight: 33
                                            palette.text: "#e5edf3"; palette.base: "#132130"; palette.button: "#213342"; palette.buttonText: "#e5edf3"
                                            onValueModified: window.studio.setOption("targetKmh", value)
                                        }
                                        LabelText { text: "km/sa"; color: "#718d9f"; font.pixelSize: 11 }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Toggle { text: "ACC"; checked: Boolean(window.s.accEnabled); enabled: !window.s.busy; onToggled: window.studio.setOption("accEnabled", checked); ToolTip.visible: hovered; ToolTip.text: "Hedef hızı ve takip mesafesini korur" }
                                        Item { Layout.fillWidth: true }
                                        Toggle { text: "AEB"; checked: Boolean(window.s.aebEnabled); enabled: !window.s.busy; onToggled: window.studio.setOption("aebEnabled", checked); ToolTip.visible: hovered; ToolTip.text: "Acil durumda fren isteği üretir" }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Toggle { text: "Gürültü"; checked: Boolean(window.s.noiseEnabled); enabled: !window.s.busy; onToggled: window.studio.setOption("noiseEnabled", checked) }
                                        Item { Layout.fillWidth: true }
                                        Toggle { text: "Tekrar"; checked: Boolean(window.s.repeatEnabled); enabled: !window.s.busy; onToggled: window.studio.setOption("repeatEnabled", checked) }
                                    }
                                    Item { Layout.fillHeight: true }
                                    ActionButton {
                                        objectName: "experimentButton"
                                        Layout.fillWidth: true
                                        text: window.s.running ? "Deneyi duraklat" : "Deneyi başlat"
                                        primary: !window.s.running
                                        enabled: window.s.running || (!window.s.busy && window.s.connected && window.s.app === "ADASLab")
                                        onClicked: window.s.running ? window.studio.stopOperation() : window.studio.startExperiment()
                                    }
                                }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 24
                            Metric { Layout.fillWidth: true; label: "BİZİM HIZIMIZ"; value: window.hasMeasurements ? window.number(window.t.egoKmh, 1) : "—"; unit: "km/sa"; note: "Hedef " + window.number(window.s.targetKmh, 0) + " km/sa" }
                            Rectangle { width: 1; height: 62; color: "#243341" }
                            Metric { Layout.fillWidth: true; label: "TAKİP MESAFESİ"; value: window.hasMeasurements && window.t.present ? window.number(window.t.gapM, 1) : "—"; unit: "m"; note: window.hasMeasurements && window.t.present ? "Öndeki araç " + window.number(window.t.leadKmh, 1) + " km/sa" : "Önde araç ölçümü yok" }
                            Rectangle { width: 1; height: 62; color: "#243341" }
                            Metric { Layout.fillWidth: true; label: "ÇARPIŞMAYA KALAN"; value: window.hasMeasurements && Number(window.t.ttcSeconds) >= 0 ? window.number(window.t.ttcSeconds, 1) : "—"; unit: "s"; note: !window.hasMeasurements ? "Ölçüm bekleniyor" : Number(window.t.ttcSeconds) >= 0 ? "Sabit hız varsayımı" : "Yaklaşma yok" }
                            Rectangle { width: 1; height: 62; color: "#243341" }
                            Metric { Layout.fillWidth: true; label: "İVME / FREN İSTEĞİ"; value: window.hasMeasurements ? window.number(window.t.accelMps2, 2) : "—"; unit: "m/s²"; note: window.t.mode === "AEB" ? "Acil fren etkin" : Number(window.t.accelMps2) < 0 ? "Yavaşlama isteği" : "Kontrol çıkışı" }
                        }
                        Panel {
                            Layout.fillWidth: true; Layout.preferredHeight: 183
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 18; spacing: 8
                                RowLayout {
                                    Layout.fillWidth: true
                                    LabelText { text: "Takip mesafesi"; font.pixelSize: 13; font.weight: Font.DemiBold }
                                    LabelText { text: "Son 200 görünüm · metre"; color: "#70899b"; font.pixelSize: 11; Layout.leftMargin: 6 }
                                    Item { Layout.fillWidth: true }
                                    ActionButton { text: "CSV kaydet"; implicitHeight: 30; enabled: !window.s.running && (window.s.history || []).length > 0; onClicked: window.studio.exportCsv() }
                                }
                                TrendChart { Layout.fillWidth: true; Layout.fillHeight: true; history: window.s.history || []; fontFamily: window.font.family }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 18
                            LabelText { text: "RTT " + window.number(window.t.rttMs, 1) + " ms"; color: "#7c95a7"; font.pixelSize: 11 }
                            LabelText { text: "Kontrol " + window.number(window.t.computeUs, 0) + " µs"; color: "#7c95a7"; font.pixelSize: 11 }
                            LabelText { text: "GPU " + window.number(window.t.gpu, 0); color: "#7c95a7"; font.pixelSize: 11 }
                            LabelText { text: "Kare " + window.number(window.t.frames, 0); color: "#7c95a7"; font.pixelSize: 11 }
                            LabelText { text: "En uzun kare " + window.number(window.t.frameMaxMs, 0) + " ms"; color: "#7c95a7"; font.pixelSize: 11 }
                            Item { Layout.fillWidth: true }
                            LabelText { text: "50 ms aşımı: " + window.number(window.t.overruns, 0); color: Number(window.t.overruns) > 0 ? "#e9b96d" : "#7c95a7"; font.pixelSize: 11 }
                        }
                        Panel {
                            visible: !window.s.connected || window.s.app !== "ADASLab"
                            Layout.fillWidth: true; Layout.preferredHeight: offlineHint.implicitHeight + 34
                            LabelText {
                                id: offlineHint; anchors.fill: parent; anchors.margins: 17
                                text: !window.s.connected ? "Başlamak için ST-LINK portunu seçip bağlanın. Kartta ADASLab yüklüyse deney kontrolleri etkinleşir." : "Kartta " + (window.s.app || "başka bir uygulama") + " çalışıyor. Firmware sayfasından ADASLab.dfw paketini yükleyin."
                                color: "#a3bac9"; font.pixelSize: 12
                            }
                        }
                    }

                    ColumnLayout {
                        visible: window.s.page === "firmware"
                        Layout.fillWidth: true; spacing: 20
                        RowLayout {
                            Layout.fillWidth: true; spacing: 20
                            Panel {
                                Layout.fillWidth: true; Layout.preferredHeight: 345
                                ColumnLayout {
                                    anchors.fill: parent; anchors.margins: 24; spacing: 16
                                    LabelText { text: "Uygulama paketi"; font.pixelSize: 17; font.weight: Font.DemiBold }
                                    LabelText { text: "Kartınıza yüklemek istediğiniz .dfw paketini seçin."; color: window.mutedColor; font.pixelSize: 12; Layout.fillWidth: true }
                                    Rectangle {
                                        Layout.fillWidth: true; Layout.preferredHeight: 106; radius: 9; color: "#0d1924"; border.width: 1; border.color: "#2b4050"
                                        ColumnLayout {
                                            anchors.fill: parent; anchors.margins: 18; spacing: 8
                                            LabelText { text: window.s.firmwareName || "Henüz paket seçilmedi"; font.pixelSize: 15; font.weight: Font.DemiBold }
                                            LabelText { text: window.s.firmwareSummary || "Smartwatch, Düello veya ADASLab paketlerinden birini seçebilirsiniz."; color: "#7e98aa"; font.pixelSize: 11; Layout.fillWidth: true }
                                        }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true; spacing: 10
                                        ActionButton { text: "Paket seç"; enabled: !window.s.busy; onClicked: window.studio.chooseFirmware() }
                                        ActionButton { text: "Yükle ve başlat"; primary: true; enabled: !window.s.busy && window.s.connected && Boolean(window.s.firmwarePath); onClicked: window.studio.requestUpload() }
                                        ActionButton { text: "İptal"; destructive: true; visible: window.s.operation === "upload"; onClicked: window.studio.stopOperation() }
                                    }
                                    ProgressBar {
                                        id: uploadProgress
                                        Layout.fillWidth: true; from: 0; to: 100; value: Number(window.s.progress || 0)
                                        background: Rectangle { implicitHeight: 5; color: "#233846"; radius: 3 }
                                        contentItem: Item { implicitHeight: 5; Rectangle { width: parent.width * uploadProgress.visualPosition; height: parent.height; color: "#63dec2"; radius: 3 } }
                                    }
                                    LabelText { text: window.s.progressText || "Yüklemeye hazır"; color: "#91a8b8"; font.pixelSize: 11; Layout.fillWidth: true }
                                    Item { Layout.fillHeight: true }
                                }
                            }
                            Panel {
                                Layout.preferredWidth: window.width < 1200 ? 250 : 295; Layout.preferredHeight: 345
                                ColumnLayout {
                                    anchors.fill: parent; anchors.margins: 24; spacing: 15
                                    LabelText { text: "Bağlı cihaz"; font.pixelSize: 15; font.weight: Font.DemiBold }
                                    LabelText { text: "STM32U5A9J-DK"; color: "#99b2c4"; font.pixelSize: 12 }
                                    Rectangle { Layout.fillWidth: true; height: 1; color: "#273a49" }
                                    LabelText { text: "ÇALIŞAN UYGULAMA"; color: "#708b9e"; font.pixelSize: 11; font.letterSpacing: 1 }
                                    LabelText { text: window.s.app ? window.s.app + "  v" + (window.s.appVersion || "1") : "Bağlantı bekleniyor"; font.pixelSize: 17; Layout.fillWidth: true }
                                    LabelText { text: window.s.bootText || "Bootloader henüz tespit edilmedi"; color: "#8fa8ba"; font.pixelSize: 11; Layout.fillWidth: true }
                                    Item { Layout.fillHeight: true }
                                    LabelText { text: "Yeni paket cihazdaki mevcut uygulamanın yerini alır. Saat kayıt alanı yükleme sırasında korunur."; color: "#728d9f"; font.pixelSize: 11; Layout.fillWidth: true }
                                }
                            }
                        }
                        Panel {
                            Layout.fillWidth: true; Layout.preferredHeight: 235
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 24; spacing: 16
                                LabelText { text: "Bootloader ve kurtarma"; font.pixelSize: 16; font.weight: Font.DemiBold }
                                LabelText { text: "ST-LINK ile kurulu bootloader’ı denetleyin veya yeni sürümünü kurun. Kurulum tam Flash yedeği alır."; color: "#8fa7b8"; font.pixelSize: 12; Layout.fillWidth: true }
                                Flow {
                                    Layout.fillWidth: true; spacing: 10
                                    ActionButton { text: "ST-LINK ile kontrol et"; enabled: !window.s.busy; onClicked: window.studio.inspectBootloader() }
                                    ActionButton { text: "DeviceBoot kur / güncelle"; enabled: !window.s.busy; onClicked: window.studio.requestInstallBootloader() }
                                    ActionButton { text: "Bootloader’a geç"; enabled: !window.s.busy && window.s.connected; onClicked: window.studio.enterBootloader() }
                                    ActionButton { text: "Uygulamayı başlat"; enabled: !window.s.busy && window.s.connected; onClicked: window.studio.runApplication() }
                                }
                                Item { Layout.fillHeight: true }
                                LabelText { text: "Kurtarma modu: USER butonuna basılı tutarak kartı yeniden başlatın. Tek seri porta aynı anda yalnız bir uygulama bağlanmalıdır."; color: "#728d9f"; font.pixelSize: 11; Layout.fillWidth: true }
                            }
                        }
                    }

                    ColumnLayout {
                        visible: window.s.page === "duello"
                        Layout.fillWidth: true; spacing: 20
                        Panel {
                            Layout.fillWidth: true; Layout.preferredHeight: 154
                            RowLayout {
                                anchors.fill: parent; anchors.margins: 25; spacing: 35
                                Metric { label: "SİLAH"; value: window.s.app !== "Duello" ? "—" : (window.s.duello || {}).gun === "drawn" ? "Hazır" : "Yerinde"; note: "Karakter kart ekranında görünür"; Layout.fillWidth: true }
                                Metric { label: "MERMİ"; value: window.s.app !== "Duello" ? "—" : String((window.s.duello || {}).ammo); unit: "/ 6"; Layout.fillWidth: true }
                                Metric { label: "HEDEF"; value: window.s.app !== "Duello" ? "—" : String((window.s.duello || {}).targetHp); unit: "/ 3"; Layout.fillWidth: true }
                                Metric { label: "EYLEM"; value: window.s.app !== "Duello" ? "—" : ({idle:"Hazır",draw:"Çıkarılıyor",holster:"Yerleşiyor",fire:"Ateş",reload:"Doluyor"})[(window.s.duello || {}).action] || "Bekliyor"; Layout.fillWidth: true }
                            }
                        }
                        Panel {
                            Layout.fillWidth: true; Layout.preferredHeight: 264
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 24; spacing: 20
                                LabelText { text: "Karakter kontrolü"; font.pixelSize: 16; font.weight: Font.DemiBold }
                                GridLayout {
                                    Layout.fillWidth: true; columns: 3; columnSpacing: 12; rowSpacing: 12
                                    Repeater {
                                        model: [{text:"Silahı çıkar",cmd:"DRAW"},{text:"Ateş et",cmd:"FIRE"},{text:"Silahı yerine koy",cmd:"HOLSTER"},{text:"Yeniden doldur",cmd:"RELOAD"},{text:"Yürü",cmd:"WALK"},{text:"Dur",cmd:"STOP"}]
                                        delegate: ActionButton {
                                            required property var modelData
                                            Layout.fillWidth: true; implicitHeight: 44
                                            text: modelData.text; primary: modelData.cmd === "FIRE"
                                            enabled: window.s.connected && window.s.app === "Duello" && !window.s.busy
                                            onClicked: window.studio.duelloCommand(modelData.cmd)
                                        }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    LabelText { text: "Animasyon sürerken yeni eylem meşgul cevabı verebilir."; color: "#7e99ab"; font.pixelSize: 11; Layout.fillWidth: true }
                                    ActionButton { text: "Sahneyi sıfırla"; enabled: window.s.connected && window.s.app === "Duello" && !window.s.busy; onClicked: window.studio.duelloCommand("RESET") }
                                }
                            }
                        }
                        LabelText { visible: window.s.app !== "Duello"; text: "Kontrollerin açılması için Düello firmware’ini yükleyip cihaza bağlanın."; color: "#8fa7b8"; font.pixelSize: 12; Layout.fillWidth: true }
                    }

                    ColumnLayout {
                        visible: window.s.page === "console"
                        Layout.fillWidth: true; spacing: 20
                        Panel {
                            Layout.fillWidth: true; Layout.preferredHeight: 160
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 24; spacing: 14
                                LabelText { text: "Uygulamaya komut gönderin"; font.pixelSize: 16; font.weight: Font.DemiBold }
                                RowLayout {
                                    Layout.fillWidth: true; spacing: 10
                                    TextField {
                                        id: commandField
                                        objectName: "commandField"
                                        Layout.fillWidth: true; implicitHeight: 40
                                        placeholderText: "Örn. STATUS"; maximumLength: 39
                                        enabled: window.s.connected && window.s.app !== "DeviceBoot" && !window.s.busy
                                        color: "#e5edf3"; placeholderTextColor: "#617f92"; font.family: window.monoFont; font.pixelSize: 12
                                        background: Rectangle { color: "#0d1924"; radius: 8; border.width: 1; border.color: commandField.activeFocus ? "#63dec2" : "#304454" }
                                        onAccepted: if (text.trim().length) window.studio.sendCommand(text)
                                    }
                                    ActionButton { text: "Gönder"; primary: true; enabled: commandField.enabled && commandField.text.trim().length > 0; onClicked: window.studio.sendCommand(commandField.text) }
                                    ActionButton { text: "Durumu sorgula"; enabled: commandField.enabled; onClicked: window.studio.sendCommand("STATUS") }
                                }
                                LabelText { text: "Komut boşluksuz, en fazla 39 ASCII karakter olmalıdır. HELLO ve STATUS ortak uygulama komutlarıdır."; color: "#738e9f"; font.pixelSize: 11; Layout.fillWidth: true }
                            }
                        }
                        Panel {
                            Layout.fillWidth: true; Layout.preferredHeight: 370
                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 20; spacing: 12
                                LabelText { text: "Uygulama durumu"; font.pixelSize: 13; font.weight: Font.DemiBold }
                                ScrollView {
                                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                                    TextArea { text: window.s.appState || "Cihaz bağlantısı bekleniyor."; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: "#a6c7d6"; font.family: window.monoFont; font.pixelSize: 12; background: Item {} }
                                }
                            }
                        }
                    }
                    Item { height: 4; Layout.fillWidth: true }
                }
            }
            Rectangle {
                visible: window.logsOpen
                Layout.fillWidth: true; Layout.preferredHeight: 172
                color: "#0c1721"
                Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: "#293b49" }
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 15; spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        LabelText { text: "İşlem günlüğü"; font.pixelSize: 12; font.weight: Font.DemiBold }
                        Item { Layout.fillWidth: true }
                        ActionButton { text: "Temizle"; implicitHeight: 26; onClicked: window.studio.clearLogs() }
                    }
                    ScrollView {
                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        TextArea { text: (window.s.logs || []).join("\n"); readOnly: true; selectByMouse: true; color: "#8caabc"; font.family: window.monoFont; font.pixelSize: 11; wrapMode: TextEdit.Wrap; background: Item {} }
                    }
                }
            }
            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: 38
                Layout.minimumHeight: 38; Layout.maximumHeight: 38
                color: "#101b27"
                Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: "#22313f" }
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 24; anchors.rightMargin: 17; spacing: 10
                    Rectangle { width: 5; height: 5; radius: 3; color: window.s.statusTone === "error" ? "#ff7b87" : window.s.running ? "#63dec2" : "#6f899a" }
                    LabelText { text: window.s.statusMessage || window.s.connectionText || "Cihaz bağlantısı bekleniyor"; color: window.s.statusTone === "error" ? "#ffacb5" : "#8fa8ba"; font.pixelSize: 11; elide: Text.ElideRight; wrapMode: Text.NoWrap; Layout.fillWidth: true }
                    LabelText { text: window.s.running ? "DENEY ÇALIŞIYOR" : window.s.busy ? "İŞLEM SÜRÜYOR" : "HAZIR"; color: window.s.running ? "#63dec2" : "#647f92"; font.pixelSize: 11; font.letterSpacing: 1 }
                    ActionButton { text: window.logsOpen ? "Günlüğü gizle" : "İşlem günlüğü"; implicitHeight: 27; onClicked: window.logsOpen = !window.logsOpen }
                }
            }
        }
    }
    Dialog {
        id: confirmationDialog
        objectName: "confirmationDialog"
        anchors.centerIn: Overlay.overlay
        width: Math.min(470, window.width - 80)
        modal: true
        visible: Boolean((window.s.confirmation || {}).visible)
        title: (window.s.confirmation || {}).title || "İşlemi onaylayın"
        closePolicy: Popup.CloseOnEscape
        palette.window: "#162534"; palette.windowText: "#e5edf3"; palette.text: "#d4e2eb"
        background: Rectangle { color: "#162534"; radius: 14; border.width: 1; border.color: "#365064" }
        contentItem: LabelText { text: (window.s.confirmation || {}).message || ""; color: "#b6cbd9"; font.pixelSize: 13; wrapMode: Text.WordWrap; width: confirmationDialog.availableWidth; padding: 5 }
        footer: RowLayout {
            spacing: 10
            Item { Layout.fillWidth: true }
            ActionButton { text: "Vazgeç"; onClicked: window.studio.confirmAction(false) }
            ActionButton { text: "Onayla ve devam et"; primary: true; onClicked: window.studio.confirmAction(true); Layout.rightMargin: 16; Layout.bottomMargin: 14 }
        }
        onRejected: window.studio.confirmAction(false)
    }
}
