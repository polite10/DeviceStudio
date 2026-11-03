pragma ComponentBehavior: Bound
import QtQuick

// A three-spoke steering wheel seen from the driver's seat. angle: degrees, clockwise.
Item {
    id: wheel
    property real angle: 0
    property color ink: "#c8d4dc"
    property color rimColor: "#2f363d"
    property color spokeColor: "#3a424a"
    readonly property real rim: width * 0.085
    implicitWidth: 300
    implicitHeight: 300

    Item {
        anchors.fill: parent
        rotation: wheel.angle
        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: "transparent"
            border.width: wheel.rim
            border.color: wheel.rimColor
            antialiasing: true
        }
        // The lighter inner edge of the grip reads as a padded rim.
        Rectangle {
            anchors.fill: parent
            anchors.margins: wheel.rim - 2
            radius: width / 2
            color: "transparent"
            border.width: 2
            border.color: Qt.rgba(1, 1, 1, 0.09)
            antialiasing: true
        }
        Repeater {
            model: [90, 270, 180]
            delegate: Rectangle {
                required property real modelData
                x: wheel.width / 2 - width / 2
                y: wheel.height / 2
                width: wheel.width * (modelData === 180 ? 0.12 : 0.1)
                height: wheel.height / 2 - wheel.rim / 2
                color: wheel.spokeColor
                antialiasing: true
                transformOrigin: Item.Top
                rotation: modelData
            }
        }
        Rectangle {
            anchors.centerIn: parent
            width: wheel.width * 0.34; height: wheel.height * 0.3
            radius: width * 0.26
            color: "#262c32"
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.08)
            antialiasing: true
            Rectangle {
                anchors.centerIn: parent
                width: parent.width * 0.3; height: width; radius: width / 2
                color: "transparent"; border.width: 2; border.color: wheel.ink
                antialiasing: true
            }
        }
        // Straight-ahead mark at the top of the rim: how far it is turned shows at a glance.
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            width: wheel.width * 0.028; height: wheel.rim
            radius: 1.5
            color: wheel.ink
            antialiasing: true
        }
    }
}
