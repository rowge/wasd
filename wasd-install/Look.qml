import QtQuick
import QtQuick.Window

Window {
    id: look
    objectName: "lookWindow"
    width: 1040
    height: 760
    visible: true
    title: "WASD Look"
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

    function initialFiles() {
        try {
            if (typeof WasdFilesJson !== "undefined" && WasdFilesJson)
                return JSON.parse(WasdFilesJson)
        } catch (e) {
        }
        return ({})
    }

    property bool tool: true
    property string shareRoot: initialRoot()
    property var bridge: null
    property string titleFont: "Liberation Serif"
    property string bodyFont: "Liberation Sans"
    property int page: 0
    property string lookOpen: ""
    property string loadingChoice: "stained-glass.jpg"
    property string loginChoice: "camp.png"
    property string themeChoice: "We10XOS-dark"
    property string wallpaperChoice: "stained-glass.jpg"
    property var themes: []
    property string savedLine: ""
    property bool applying: false
    property var files: initialFiles()

    readonly property color bg: "#24160e"
    readonly property color rail: "#1c100b"
    readonly property color ink: "#f6ead8"
    readonly property color muted: "#e7d3b6"
    readonly property color brass: "#c4a574"
    readonly property color danger: "#ff5c5c"
    readonly property color line: Qt.rgba(246 / 255, 226 / 255, 196 / 255, 0.22)
    readonly property var loadingFiles: files.loading || []
    readonly property var loginFiles: files.login || []
    readonly property var wallpaperFiles: files.wallpapers || []

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
            if (typeof WasdBridge !== "undefined")
                bridge = WasdBridge
        } catch (e) {
        }
        try {
            if (typeof WasdFilesJson !== "undefined" && WasdFilesJson)
                files = JSON.parse(WasdFilesJson)
        } catch (e) {
        }
        titleFont = pickFont(["Palatino Linotype", "Palatino", "TeX Gyre Pagella", "Liberation Serif", "Noto Serif", "FreeSerif"], titleFont)
        bodyFont = pickFont(["Segoe UI", "Liberation Sans", "Noto Sans", "DejaVu Sans"], bodyFont)
        if (!files.loading)
            lister.active = true
    }

    function art(folder, fileName) {
        if (!fileName)
            return ""
        if (shareRoot)
            return "file://" + shareRoot + "/" + folder + "/" + fileName
        if (folder === "wasd-icons")
            return "file:///usr/share/wasd/wasd-logo.png"
        if (folder === "wasd-loading-screens")
            return "file:///usr/share/wasd/loading/" + fileName
        if (folder === "wasd-login-screens")
            return "file:///usr/share/wasd/login/" + fileName
        if (folder === "wasd-wallpapers")
            return "file:///usr/share/wallpapers/wasd/" + fileName
        return ""
    }

    function openLook(which) {
        lookOpen = lookOpen === which ? "" : which
    }

    function safeName(name) {
        return /^[A-Za-z0-9._-]+$/.test(name)
    }

    function applyLook() {
        if (applying)
            return
        if (!safeName(loadingChoice) || !safeName(loginChoice) || !safeName(wallpaperChoice)) {
            savedLine = "Use a picture from the list."
            return
        }
        const payload = JSON.stringify({
            loading: loadingChoice,
            login: loginChoice,
            wallpaper: wallpaperChoice
        })
        if (bridge) {
            bridge.applyLook(payload)
            savedLine = "Saved your choices. This computer was not changed."
            return
        }
        applying = true
        savedLine = "Applying."
        applyLoader.active = true
        if (applyLoader.item)
            applyLoader.item.start(wallpaperChoice, loginChoice, loadingChoice)
    }

    function listsReady(loading, login, wallpapers) {
        files = {
            loading: loading,
            login: login,
            wallpapers: wallpapers
        }
    }

    Loader {
        id: lister
        active: false
        source: "Lister.qml"
        onLoaded: {
            item.provide.connect(look.listsReady)
            item.publish()
        }
    }

    Loader {
        id: applyLoader
        active: false
        source: "ApplyHost.qml"
        onLoaded: {
            if (look.applying)
                item.start(look.wallpaperChoice, look.loginChoice, look.loadingChoice)
        }
    }

    Connections {
        target: applyLoader.item
        enabled: applyLoader.item !== null
        function onFinished(line) {
            look.applying = false
            look.savedLine = line
        }
    }

    Component.onCompleted: boot()

    Rectangle {
        id: shell
        anchors.fill: parent
        color: look.bg
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
                text: "WASD Look"
                color: look.muted
                font.family: look.bodyFont
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
                onPressed: look.startSystemMove()
            }
        }

        Rectangle {
            id: rail
            anchors.top: titlebar.bottom
            anchors.bottom: parent.bottom
            width: 220
            color: look.rail

            Image {
                id: logo
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.margins: 28
                width: 84
                fillMode: Image.PreserveAspectFit
                source: look.shareRoot.length >= 0 ? look.art("wasd-icons", "wasd-logo.png") : ""
                sourceSize: Qt.size(168, 168)
                cache: true
            }

            Rectangle {
                anchors.top: logo.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.topMargin: 28
                anchors.leftMargin: 22
                anchors.rightMargin: 22
                height: 40
                color: look.brass

                Text {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    verticalAlignment: Text.AlignVCenter
                    text: "Look"
                    color: "#24160e"
                    font.family: look.bodyFont
                    font.pixelSize: 16
                    font.bold: true
                }
            }

            Rectangle {
                anchors.right: parent.right
                width: 1
                height: parent.height
                color: look.line
            }
        }

        Item {
            anchors.top: titlebar.bottom
            anchors.bottom: parent.bottom
            anchors.left: rail.right
            anchors.right: parent.right

            LookPage { anchors.fill: parent; host: look }
        }
    }
}
