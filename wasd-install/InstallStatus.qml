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

        Item {
            id: copyMark
            objectName: "copySpinner"
            visible: host.installStage === "prepare" || host.installStage === "copy" || host.installStage === "account" || host.installStage === "boot"
            width: 132
            height: 132
            anchors.horizontalCenter: parent.horizontalCenter

            Image {
                id: copyLogo
                anchors.fill: parent
                visible: false
                source: host.art("wasd-icons", "wasd-logo.png")
                fillMode: Image.PreserveAspectFit
                sourceSize: Qt.size(264, 264)
                cache: true
                onStatusChanged: copySweep.requestPaint()
            }

            Canvas {
                id: copySweep
                anchors.fill: parent
                property real angle: -Math.PI / 2
                onAngleChanged: requestPaint()
                onPaint: {
                    var ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)
                    var cx = width / 2
                    var cy = height / 2
                    var outer = Math.min(width, height) * 0.46
                    var thick = Math.min(width, height) * 0.28
                    var inner = outer - thick
                    if (inner < 4)
                        return
                    var start = copySweep.angle
                    var end = start + Math.PI * 0.7
                    ctx.beginPath()
                    ctx.arc(cx, cy, outer - thick / 2, start, end, false)
                    ctx.lineWidth = thick
                    ctx.lineCap = "round"
                    ctx.strokeStyle = "rgba(244, 242, 238, 0.42)"
                    ctx.stroke()
                    if (copyLogo.status !== Image.Ready)
                        return
                    ctx.save()
                    ctx.beginPath()
                    ctx.arc(cx, cy, outer, start, end, false)
                    ctx.arc(cx, cy, inner, end, start, true)
                    ctx.closePath()
                    ctx.clip()
                    ctx.globalAlpha = 0.9
                    var dw = width * 1.15
                    var dh = height * 1.15
                    ctx.drawImage(copyLogo, (width - dw) / 2, (height - dh) / 2, dw, dh)
                    ctx.restore()
                }
            }

            NumberAnimation {
                target: copySweep
                property: "angle"
                from: -Math.PI / 2
                to: Math.PI * 1.5
                duration: 1600
                loops: Animation.Infinite
                running: copyMark.visible
            }
        }

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
            objectName: "copyDetail"
            visible: host.installStage === "copy"
            width: parent.width
            wrapMode: Text.WordWrap
            text: "The system, the desktop, and the programs that come with WASD."
            color: host.muted
            font.family: host.bodyFont
            font.pixelSize: 16
        }

        Text {
            objectName: "restartNote"
            visible: host.restartReady && host.installStage === "failed"
            width: parent.width
            wrapMode: Text.WordWrap
            text: host.restartArmed ? host.pullLine : host.continueLine
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
