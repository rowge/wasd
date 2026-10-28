import QtQuick

Item {
    id: status
    required property var host

    readonly property var steps: [
        "Preparing the disk.",
        "Copying WASD.",
        "Setting up your account.",
        "Installing the bootloader."
    ]

    Column {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 48
        anchors.rightMargin: 48
        spacing: 22

        Text {
            objectName: "installStatusLine"
            width: parent.width
            wrapMode: Text.WordWrap
            text: host.installLine()
            color: host.installStage === "failed" ? host.danger : host.ink
            font.family: host.titleFont
            font.pixelSize: host.installStage === "done" || host.installStage === "failed" ? 32 : 28
        }

        Text {
            objectName: "removeUsbLine"
            visible: host.restartReady && host.installStage === "failed"
            width: parent.width
            wrapMode: Text.WordWrap
            text: "You can remove the USB stick."
            color: host.ink
            font.family: host.bodyFont
            font.pixelSize: 18
        }

        Rectangle {
            objectName: "restartButton"
            visible: host.restartReady
            width: restartLabel.implicitWidth + 36
            height: 44
            radius: 9
            color: host.button
            antialiasing: true

            Text {
                id: restartLabel
                objectName: "restartButtonLabel"
                anchors.centerIn: parent
                text: "Restart"
                color: host.buttonInk
                font.family: host.bodyFont
                font.pixelSize: 16
                font.bold: true
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: host.restartNow()
            }
        }

        Column {
            visible: host.installStage !== "done" && host.installStage !== "failed"
            width: parent.width
            spacing: 8

            Repeater {
                model: status.steps
                delegate: Text {
                    required property string modelData
                    width: parent.width
                    text: modelData
                    color: host.installLine() === modelData ? host.brass : host.muted
                    opacity: host.stageForLine(modelData) === host.installStage || host.stageSeen(host.stageForLine(modelData)) ? 1 : 0.4
                    font.family: host.bodyFont
                    font.pixelSize: 16
                    font.bold: host.installLine() === modelData
                }
            }
        }
    }
}
