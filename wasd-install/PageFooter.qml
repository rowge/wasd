import QtQuick

Item {
    id: foot
    required property var host
    property string nextText: "Next"
    property bool nextEnabled: true
    property bool showBack: true
    property string note: ""
    signal back()
    signal go()

    implicitHeight: 64

    Text {
        id: backText
        anchors.left: parent.left
        anchors.leftMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        visible: foot.showBack
        text: "Back"
        color: host.muted
        font.family: host.bodyFont
        font.pixelSize: 16
        opacity: host.page > 0 ? 1 : 0.4

        MouseArea {
            anchors.fill: parent
            anchors.margins: -10
            enabled: foot.showBack && host.page > 0
            cursorShape: Qt.PointingHandCursor
            onClicked: foot.back()
        }
    }

    Text {
        anchors.left: foot.showBack ? backText.right : parent.left
        anchors.right: goButton.left
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        text: foot.note
        color: host.muted
        font.family: host.bodyFont
        font.pixelSize: 15
        elide: Text.ElideRight
        horizontalAlignment: Text.AlignRight
    }

    Rectangle {
        id: goButton
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: goLabel.implicitWidth + 36
        height: 44
        color: foot.nextEnabled ? host.brass : Qt.rgba(196 / 255, 165 / 255, 116 / 255, 0.35)

        Text {
            id: goLabel
            anchors.centerIn: parent
            text: foot.nextText
            color: "#24160e"
            font.family: host.bodyFont
            font.pixelSize: 16
            font.bold: true
        }

        MouseArea {
            anchors.fill: parent
            enabled: foot.nextEnabled
            cursorShape: foot.nextEnabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: foot.go()
        }
    }
}
