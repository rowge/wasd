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
    property string titleFont: "Liberation Sans"
    property string bodyFont: "Liberation Sans"
    property int page: 0
    property string lookOpen: ""
    property string loadingChoice: "stained-glass.jpg"
    property string loginChoice: "throne.jpg"
    property string themeChoice: "We10XOS-dark"
    property string wallpaperChoice: "stained-glass.jpg"
    property string avatarChoice: "knight.jpg"
    property bool avatarTouched: false
    property bool avatarReady: false
    property var themes: []
    property string savedLine: ""
    property bool applying: false
    property var files: initialFiles()

    readonly property color bg: "#14161a"
    readonly property color rail: "#101114"
    readonly property color titlebar: "#101114"
    readonly property color card: "#22252b"
    readonly property color ink: "#f4f2ee"
    readonly property color muted: "#a9a59e"
    readonly property color brass: "#7aa2ff"
    readonly property color button: "#f4f2ee"
    readonly property color buttonInk: "#16181c"
    readonly property color navOn: "#2a2d34"
    readonly property color danger: "#ff5c5c"
    readonly property color line: Qt.rgba(1, 1, 1, 0.12)
    readonly property var iconFiles: files.icons || []
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
        titleFont = pickFont(["Noto Sans", "Liberation Sans", "Segoe UI", "DejaVu Sans"], titleFont)
        bodyFont = pickFont(["Segoe UI", "Liberation Sans", "Noto Sans", "DejaVu Sans"], bodyFont)
        if (bridge) {
            avatarReady = true
        } else {
            avatarChoice = ""
            avatarProbe.active = true
        }
        if (!files.loading)
            lister.active = true
    }

    function art(folder, fileName) {
        if (!fileName)
            return ""
        if (shareRoot)
            return "file://" + shareRoot + "/" + folder + "/" + fileName
        if (folder === "wasd-icons")
            return "file:///usr/share/wasd/icons/" + fileName
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
        if (avatarChoice && !safeName(avatarChoice)) {
            savedLine = "Use a picture from the list."
            return
        }
        const payload = {
            loading: loadingChoice,
            login: loginChoice,
            wallpaper: wallpaperChoice
        }
        if (avatarTouched)
            payload.avatar = avatarChoice
        const encoded = JSON.stringify(payload)
        if (bridge) {
            bridge.applyLook(encoded)
            savedLine = "Saved your choices. This computer was not changed."
            return
        }
        applying = true
        savedLine = "Applying."
        applyLoader.active = true
        if (applyLoader.item)
            applyLoader.item.start(wallpaperChoice, loginChoice, loadingChoice, avatarTouched ? avatarChoice : null)
    }

    function listsReady(icons, loading, login, wallpapers) {
        files = {
            icons: icons,
            loading: loading,
            login: login,
            wallpapers: wallpapers
        }
    }

    function avatarFound(name) {
        avatarChoice = /^[A-Za-z0-9._-]+$/.test(name) ? name : ""
        avatarReady = true
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
        id: avatarProbe
        active: false
        source: "AvatarProbe.qml"
        onLoaded: item.current.connect(look.avatarFound)
    }

    Loader {
        id: applyLoader
        active: false
        source: "ApplyHost.qml"
        onLoaded: {
            if (look.applying)
                item.start(look.wallpaperChoice, look.loginChoice, look.loadingChoice, look.avatarTouched ? look.avatarChoice : null)
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
        border.color: Qt.rgba(1, 1, 1, 0.08)
        border.width: 1

        Rectangle {
            id: titlebar
            height: 38
            anchors.left: parent.left
            anchors.right: parent.right
            color: look.titlebar

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
                border.color: Qt.rgba(1, 1, 1, 0.28)
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
                radius: 10
                color: look.navOn
                antialiasing: true

                Text {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    verticalAlignment: Text.AlignVCenter
                    text: "Look"
                    color: look.ink
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
