import QtQuick
import QtQuick.Window

Window {
    id: win
    objectName: "completeWindow"
    width: 720
    height: 520
    visible: true
    title: "Completing the install"
    color: bg
    flags: Qt.Window | Qt.FramelessWindowHint

    property string shareRoot: ""
    property string bodyFont: "Liberation Sans"
    property bool hold: false
    property int stepIndex: 0

    readonly property color bg: "#24160e"
    readonly property color ink: "#f6ead8"
    readonly property color muted: "#e7d3b6"
    readonly property color brass: "#c4a574"
    readonly property var lines: [
        "Setting the desktop.",
        "Installing what you checked.",
        "Finishing up."
    ]
    readonly property string status: lines[Math.min(stepIndex, lines.length - 1)]

    function art(fileName) {
        if (!shareRoot)
            return ""
        return "file://" + shareRoot + "/wasd-icons/" + fileName
    }

    function pickFont(choices, fallback) {
        const families = Qt.fontFamilies()
        for (let i = 0; i < choices.length; i++) {
            if (families.indexOf(choices[i]) >= 0)
                return choices[i]
        }
        return fallback
    }

    function boot() {
        try {
            if (typeof WasdRepo !== "undefined" && WasdRepo)
                shareRoot = WasdRepo
        } catch (e) {
        }
        try {
            if (typeof WasdHold !== "undefined" && WasdHold)
                hold = true
        } catch (e) {
        }
        bodyFont = pickFont(["Segoe UI", "Liberation Sans", "Noto Sans", "DejaVu Sans"], bodyFont)
    }

    Timer {
        interval: 2400
        running: !win.hold
        repeat: true
        onTriggered: {
            if (win.stepIndex >= win.lines.length - 1) {
                Qt.quit()
                return
            }
            win.stepIndex = win.stepIndex + 1
        }
    }

    Component.onCompleted: boot()

    Rectangle {
        anchors.fill: parent
        color: win.bg
        border.color: Qt.rgba(246 / 255, 226 / 255, 196 / 255, 0.16)
        border.width: 1

        Rectangle {
            id: titlebar
            height: 38
            anchors.left: parent.left
            anchors.right: parent.right
            color: "#1a0f0b"

            Text {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: 16
                text: "Completing the install"
                color: win.muted
                font.family: win.bodyFont
                font.pixelSize: 13
            }

            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                anchors.right: parent.right
                anchors.rightMargin: 14
                width: 14
                height: 14
                radius: 7
                color: "transparent"
                border.color: Qt.rgba(246 / 255, 226 / 255, 196 / 255, 0.35)
                border.width: 1

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: Qt.quit()
                }
            }

            MouseArea {
                anchors.fill: parent
                anchors.rightMargin: 40
                onPressed: win.startSystemMove()
            }
        }

        Column {
            anchors.centerIn: parent
            anchors.verticalCenterOffset: 16
            spacing: 28
            width: parent.width - 80

            Image {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 150
                fillMode: Image.PreserveAspectFit
                source: win.art("wasd-logo.png")
                sourceSize: Qt.size(300, 300)
                cache: true
            }

            Item {
                id: spinner
                anchors.horizontalCenter: parent.horizontalCenter
                width: 84
                height: 84

                Repeater {
                    model: 12
                    delegate: Rectangle {
                        required property int index
                        width: 8
                        height: 8
                        radius: 4
                        color: win.brass
                        opacity: 0.22 + (index / 11) * 0.78
                        x: 38 + 30 * Math.cos(index / 12 * Math.PI * 2) - width / 2
                        y: 38 + 30 * Math.sin(index / 12 * Math.PI * 2) - height / 2
                    }
                }

                RotationAnimation on rotation {
                    from: 0
                    to: 360
                    duration: 1100
                    loops: Animation.Infinite
                    running: true
                }
            }

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: win.status
                color: win.ink
                font.family: win.bodyFont
                font.pixelSize: 22
                wrapMode: Text.WordWrap
            }
        }
    }
}
