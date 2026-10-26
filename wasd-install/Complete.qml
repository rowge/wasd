import QtQuick
import QtQuick.Window

Window {
    id: win
    objectName: "completeWindow"
    width: 720
    height: 560
    visible: true
    title: "Completing the install"
    color: bg
    flags: Qt.Window | Qt.FramelessWindowHint

    function initialRoot() {
        try {
            if (typeof WasdRepo !== "undefined" && WasdRepo)
                return WasdRepo
        } catch (e) {
        }
        return ""
    }

    property string shareRoot: initialRoot()
    property string bodyFont: "Liberation Sans"
    property bool hold: false
    property bool preview: false
    property int helperPort: 0
    property int stepIndex: 0
    property string phase: "work"
    property string passwordDraft: ""
    property string passwordAgainDraft: ""
    property string passwordError: ""
    property bool settingPassword: false

    readonly property color bg: "#24160e"
    readonly property color ink: "#f6ead8"
    readonly property color muted: "#e7d3b6"
    readonly property color brass: "#c4a574"
    readonly property color danger: "#ff5c5c"
    readonly property color line: Qt.rgba(246 / 255, 226 / 255, 196 / 255, 0.22)
    readonly property var lines: [
        "Setting the desktop.",
        "Installing what you checked.",
        "Finishing up."
    ]
    readonly property string status: lines[Math.min(stepIndex, lines.length - 1)]

    function art(fileName) {
        if (shareRoot)
            return "file://" + shareRoot + "/wasd-icons/" + fileName
        return "file:///usr/share/wasd/icons/" + fileName
    }

    function pickFont(choices, fallback) {
        const families = Qt.fontFamilies()
        for (let i = 0; i < choices.length; i++) {
            if (families.indexOf(choices[i]) >= 0)
                return choices[i]
        }
        return fallback
    }

    function argValue(flag) {
        const args = Qt.application.arguments
        for (let i = 0; i < args.length - 1; i++) {
            if (args[i] === flag)
                return args[i + 1]
        }
        return ""
    }

    function boot() {
        let want = argValue("--want-password") === "1"
        const port = parseInt(argValue("--port") || "0", 10)
        helperPort = isNaN(port) ? 0 : port
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
        try {
            if (typeof WasdPreview !== "undefined" && WasdPreview)
                preview = true
        } catch (e) {
        }
        try {
            if (typeof WasdWantPassword !== "undefined" && WasdWantPassword)
                want = true
        } catch (e) {
        }
        try {
            if (typeof WasdPasswordSet !== "undefined" && WasdPasswordSet)
                want = false
        } catch (e) {
        }
        bodyFont = pickFont(["Segoe UI", "Liberation Sans", "Noto Sans", "DejaVu Sans"], bodyFont)
        phase = want ? "password" : "work"
    }

    function confirmPassword() {
        const first = passwordDraft
        const second = passwordAgainDraft
        if (!first || first !== second) {
            passwordError = first ? "Type the same password in both boxes." : "Type a password in both boxes."
            return
        }
        passwordDraft = ""
        passwordAgainDraft = ""
        passwordField.text = ""
        againField.text = ""
        passwordError = ""
        if (preview || helperPort <= 0) {
            phase = "work"
            stepIndex = 0
            return
        }
        settingPassword = true
        const xhr = new XMLHttpRequest()
        xhr.open("POST", "http://127.0.0.1:" + helperPort + "/password")
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE)
                return
            win.settingPassword = false
            if (xhr.status === 200) {
                win.phase = "work"
                win.stepIndex = 0
                return
            }
            const detail = (xhr.responseText || "").trim()
            win.passwordError = detail || "The password was not set."
        }
        xhr.send(first)
    }

    function finish() {
        if (preview || hold || helperPort <= 0) {
            if (!hold)
                Qt.quit()
            return
        }
        const xhr = new XMLHttpRequest()
        xhr.open("POST", "http://127.0.0.1:" + helperPort + "/done")
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE)
                return
            if (xhr.status === 200)
                Qt.quit()
        }
        xhr.send("done")
    }

    Timer {
        interval: 2400
        running: win.phase === "work" && !win.hold
        repeat: true
        onTriggered: {
            if (win.stepIndex >= win.lines.length - 1) {
                win.finish()
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
            visible: win.phase === "password"
            anchors.centerIn: parent
            anchors.verticalCenterOffset: 8
            spacing: 0
            width: Math.min(460, parent.width - 80)

            Image {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 96
                fillMode: Image.PreserveAspectFit
                source: win.art("wasd-logo.png")
                sourceSize: Qt.size(192, 192)
                cache: true
            }

            Text {
                width: parent.width
                topPadding: 18
                horizontalAlignment: Text.AlignHCenter
                text: "Set a password"
                color: win.ink
                font.family: win.bodyFont
                font.pixelSize: 28
            }

            Text {
                width: parent.width
                topPadding: 8
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: "This password is also the administrator password. The next boot asks for it."
                color: win.ink
                font.family: win.bodyFont
                font.pixelSize: 16
            }

            Text {
                topPadding: 16
                text: "Password"
                color: win.muted
                font.family: win.bodyFont
                font.pixelSize: 14
            }

            Rectangle {
                width: parent.width
                height: 48
                color: Qt.rgba(0, 0, 0, 0.28)
                border.width: 1
                border.color: win.line

                TextInput {
                    id: passwordField
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    verticalAlignment: TextInput.AlignVCenter
                    color: win.ink
                    font.pixelSize: 18
                    font.family: win.bodyFont
                    echoMode: TextInput.Password
                    selectByMouse: true
                    selectionColor: win.brass
                    selectedTextColor: "#24160e"
                    onTextEdited: win.passwordDraft = text
                }
            }

            Text {
                topPadding: 12
                text: "Again"
                color: win.muted
                font.family: win.bodyFont
                font.pixelSize: 14
            }

            Rectangle {
                width: parent.width
                height: 48
                color: Qt.rgba(0, 0, 0, 0.28)
                border.width: 1
                border.color: win.line

                TextInput {
                    id: againField
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    verticalAlignment: TextInput.AlignVCenter
                    color: win.ink
                    font.pixelSize: 18
                    font.family: win.bodyFont
                    echoMode: TextInput.Password
                    selectByMouse: true
                    selectionColor: win.brass
                    selectedTextColor: "#24160e"
                    onTextEdited: win.passwordAgainDraft = text
                }
            }

            Text {
                width: parent.width
                visible: win.passwordError.length > 0
                topPadding: 8
                wrapMode: Text.WordWrap
                text: win.passwordError
                color: win.danger
                font.family: win.bodyFont
                font.pixelSize: 16
            }

            Item {
                width: 1
                height: 18
            }

            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                width: setLabel.implicitWidth + 36
                height: 44
                enabled: !win.settingPassword
                color: enabled ? win.brass : Qt.rgba(196 / 255, 165 / 255, 116 / 255, 0.35)

                Text {
                    id: setLabel
                    anchors.centerIn: parent
                    text: win.settingPassword ? "Setting the password." : "Set password"
                    color: "#24160e"
                    font.family: win.bodyFont
                    font.pixelSize: 16
                    font.bold: true
                }

                MouseArea {
                    anchors.fill: parent
                    enabled: !win.settingPassword
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: win.confirmPassword()
                }
            }
        }

        Column {
            visible: win.phase === "work"
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
                    running: win.phase === "work"
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
