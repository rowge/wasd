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
