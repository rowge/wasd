import QtQuick

Item {
    id: foot
    required property var host
    property string nextText: "Next"
    property bool nextEnabled: true
    property bool showBack: true
    property string note: ""
    property string altText: ""
    property bool showGo: true
    signal back()
    signal go()
    signal alt()

    readonly property int goExtra: foot.showGo ? Math.max(0, goButton.height - 44) : 0
    implicitHeight: (foot.altText !== "" && foot.showGo ? 108 : 64) + foot.goExtra

    Text {
        id: backText
        anchors.left: parent.left
        anchors.leftMargin: 8
        anchors.verticalCenter: goButton.verticalCenter
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
        anchors.verticalCenter: goButton.verticalCenter
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        height: 22
        clip: true
        text: foot.note
        color: host.muted
        font.family: host.bodyFont
        font.pixelSize: 15
        wrapMode: Text.NoWrap
        maximumLineCount: 1
        elide: Text.ElideRight
        horizontalAlignment: Text.AlignRight
    }

    Rectangle {
        id: altButton
        visible: foot.altText !== ""
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.bottomMargin: foot.showGo && foot.altText !== "" ? 52 + foot.goExtra : 10
        width: altLabel.implicitWidth + 36
        height: 44
        radius: 9
        color: "transparent"
        border.width: 1
        border.color: foot.nextEnabled ? Qt.rgba(244 / 255, 242 / 255, 238 / 255, 0.55) : Qt.rgba(244 / 255, 242 / 255, 238 / 255, 0.28)
        antialiasing: true

        Text {
            id: altLabel
            objectName: "chooseGamesLabel"
            anchors.centerIn: parent
            text: foot.altText
            color: foot.nextEnabled ? host.ink : host.muted
            font.family: host.bodyFont
            font.pixelSize: 16
        }

        MouseArea {
            objectName: "chooseGamesButton"
            anchors.fill: parent
            enabled: foot.nextEnabled && foot.altText !== ""
            cursorShape: foot.nextEnabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: foot.alt()
        }
    }

    Rectangle {
        id: goButton
        visible: foot.showGo
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.bottomMargin: foot.altText !== "" && foot.showGo ? 0 : 10
        readonly property int maxWidth: Math.max(160, foot.width - 72)
        width: Math.min(goLabel.implicitWidth + 36, maxWidth)
        height: Math.max(44, goLabel.implicitHeight + 18)
        radius: 9
        color: foot.nextEnabled ? host.button : Qt.rgba(244 / 255, 242 / 255, 238 / 255, 0.35)
        antialiasing: true

        Text {
            id: goLabel
            objectName: "eraseButtonLabel"
            anchors.centerIn: parent
            width: Math.min(implicitWidth, goButton.maxWidth - 36)
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            text: foot.nextText
            color: host.buttonInk
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
