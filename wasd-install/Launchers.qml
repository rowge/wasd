import QtQuick
import QtQuick.Dialogs
import QtQuick.Window

Window {
    id: win
    objectName: "launchersWindow"
    width: 780
    height: 760
    visible: true
    title: "WASD Launchers"
    color: bg
    flags: Qt.Window | Qt.FramelessWindowHint

    property bool preview: false
    property int helperPort: 0
    property string bodyFont: "Liberation Sans"
    property string titleFont: "Liberation Sans"
    property var readyMap: ({})
    property var preparedMap: ({})
    property string pending: ""
    property string confirmName: ""
    property string rowError: ""
    property string programFor: ""
    property bool rockstarWarn: false
    property bool starCitizenWarn: false
    readonly property string rockstarWarnBody: "Click OK on the final error in the Rockstar installation. It still works."
    readonly property string starCitizenWarnBody: "Click No on the two errors that ask if you want to see more information. The launcher still works."

    readonly property color bg: "#14161a"
    readonly property color titlebar: "#101114"
    readonly property color card: "#22252b"
    readonly property color ink: "#f4f2ee"
    readonly property color muted: "#a9a59e"
    readonly property color brass: "#7aa2ff"
    readonly property color button: "#f4f2ee"
    readonly property color buttonInk: "#16181c"
    readonly property color line: Qt.rgba(1, 1, 1, 0.12)
    readonly property color danger: "#ff5c5c"

    ListModel {
        id: launcherModel
    }

    function fillDefaults() {
        launcherModel.clear()
        const rows = [
            ["Battle.net", "battlenet"],
            ["Ubisoft Connect", "ubisoft"],
            ["Rockstar Launcher", "rockstar"],
            ["Java Minecraft", "minecraft"],
            ["Minecraft Bedrock", "minecraft-bedrock"],
            ["Modded Minecraft", "minecraft-modded"],
            ["MultiMC", "multimc"],
            ["CurseForge", "curseforge"],
            ["FTB App", "ftb"],
            ["Star Citizen", "starcitizen"]
        ]
        for (let i = 0; i < rows.length; i++) {
            launcherModel.append({
                name: rows[i][0],
                launcherId: rows[i][1],
                custom: false,
                reinstall: keepsReinstall(rows[i][1], false),
                folder: "/games/" + rows[i][1]
            })
        }
    }

    function localPath(value) {
        if (!value)
            return ""
        let text = value.toString()
        if (text.indexOf("file://") === 0)
            text = decodeURIComponent(text.slice(7))
        return text
    }

    function fileTitle(path) {
        if (!path)
            return ""
        const slash = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"))
        return slash >= 0 ? path.slice(slash + 1) : path
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

    function hasFlag(flag) {
        const args = Qt.application.arguments
        for (let i = 0; i < args.length; i++) {
            if (args[i] === flag)
                return true
        }
        return false
    }

    function boot() {
        titleFont = pickFont(["Noto Sans", "Liberation Sans", "Segoe UI", "DejaVu Sans"], titleFont)
        bodyFont = pickFont(["Segoe UI", "Liberation Sans", "Noto Sans", "DejaVu Sans"], bodyFont)
        preview = hasFlag("--preview")
        const port = parseInt(argValue("--port") || "0", 10)
        helperPort = isNaN(port) ? 0 : port
        fillDefaults()
        if (!preview && helperPort > 0)
            refresh()
    }

    function applyStatus(text) {
        let data = {}
        try {
            data = JSON.parse(text || "{}")
        } catch (e) {
            return
        }
        const rows = data.rows || []
        if (rows.length === 0)
            return
        const ready = {}
        const prepared = {}
        launcherModel.clear()
        for (let i = 0; i < rows.length; i++) {
            ready[rows[i].name] = !!rows[i].ready
            prepared[rows[i].name] = !!rows[i].prepared
            const custom = !!rows[i].custom
            let reinstall = rows[i].reinstall
            if (reinstall !== true && reinstall !== false)
                reinstall = win.keepsReinstall(rows[i].id || "", custom)
            launcherModel.append({
                name: rows[i].name || "",
                launcherId: rows[i].id || "",
                custom: custom,
                reinstall: reinstall,
                folder: rows[i].folder || ""
            })
        }
        readyMap = ready
        preparedMap = prepared
    }

    function refresh() {
        if (preview || helperPort <= 0)
            return
        const xhr = new XMLHttpRequest()
        xhr.open("POST", "http://127.0.0.1:" + helperPort + "/status")
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE || xhr.status !== 200)
                return
            win.applyStatus(xhr.responseText || "")
        }
        xhr.send("")
    }

    function keepsReinstall(launcherId, custom) {
        if (custom)
            return false
        return launcherId === "battlenet"
            || launcherId === "ubisoft"
            || launcherId === "rockstar"
            || launcherId === "minecraft"
            || launcherId === "starcitizen"
    }

    function showInstall(name, reinstall) {
        return readyMap[name] !== true || reinstall === true
    }

    function startInstall(name) {
        if (name === "Rockstar Launcher") {
            rockstarWarn = true
            return
        }
        if (name === "Star Citizen") {
            starCitizenWarn = true
            return
        }
        act("/install", name)
    }

    function dismissRockstarWarn() {
        rockstarWarn = false
        act("/install", "Rockstar Launcher")
    }

    function dismissStarCitizenWarn() {
        starCitizenWarn = false
        act("/install", "Star Citizen")
    }

    function act(path, name) {
        if (preview || helperPort <= 0 || pending.length > 0)
            return
        pending = name
        rowError = ""
        confirmName = ""
        const xhr = new XMLHttpRequest()
        xhr.timeout = 0
        xhr.open("POST", "http://127.0.0.1:" + helperPort + path)
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE)
                return
            win.pending = ""
            if (xhr.status !== 200)
                win.rowError = (xhr.responseText || "Could not open that launcher.").trim()
            win.refresh()
        }
        xhr.onerror = function() {
            win.pending = ""
            win.rowError = "Could not open that launcher."
        }
        xhr.send(name)
    }

    function postCustom(payload, pendingName) {
        if (preview || helperPort <= 0 || pending.length > 0)
            return
        pending = pendingName
        rowError = ""
        const xhr = new XMLHttpRequest()
        xhr.timeout = 0
        xhr.open("POST", "http://127.0.0.1:" + helperPort + "/custom")
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE)
                return
            win.pending = ""
            if (xhr.status === 200) {
                if (!payload.program)
                    customNameField.text = ""
            } else
                win.rowError = (xhr.responseText || "Could not add that game.").trim()
            win.refresh()
        }
        xhr.onerror = function() {
            win.pending = ""
            win.rowError = "Could not add that game."
        }
        xhr.send(JSON.stringify(payload))
    }

    function addCustom() {
        const name = customNameField.text.trim()
        if (name.length === 0)
            return
        postCustom({name: name}, name)
    }

    function attachProgram(name, path) {
        if (!name || !path)
            return
        postCustom({name: name, program: path}, name)
    }

    Component.onCompleted: boot()

    Rectangle {
        anchors.fill: parent
        color: win.bg

        Rectangle {
            id: titlebar
            height: 38
            anchors.left: parent.left
            anchors.right: parent.right
            color: win.titlebar

            Text {
                anchors.left: parent.left
                anchors.leftMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                text: "WASD Launchers"
                color: win.ink
                font.family: win.titleFont
                font.pixelSize: 14
                font.weight: Font.DemiBold
            }

            Rectangle {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.rightMargin: 8
                width: 28
                height: 28
                radius: 6
                color: closeArea.containsMouse ? Qt.rgba(1, 1, 1, 0.08) : "transparent"

                Text {
                    anchors.centerIn: parent
                    text: "×"
                    color: win.muted
                    font.pixelSize: 16
                }

                MouseArea {
                    id: closeArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: Qt.quit()
                }
            }

            MouseArea {
                anchors.fill: parent
                anchors.rightMargin: 44
                onPressed: win.startSystemMove()
            }
        }

        Column {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: titlebar.bottom
            anchors.margins: 28
            spacing: 18

            Text {
                width: parent.width
                text: "Launchers"
                color: win.ink
                font.family: win.titleFont
                font.pixelSize: 28
                font.weight: Font.DemiBold
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "WASD opens the launcher's own window. You finish it there."
                color: win.muted
                font.family: win.bodyFont
                font.pixelSize: 15
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Nuke/Fix rebuilds the launcher only. Saved games stay. Browse opens that folder."
                color: win.muted
                font.family: win.bodyFont
                font.pixelSize: 15
            }

            Item {
                id: listFrame
                width: parent.width
                height: 500

                Flickable {
                    id: listFlick
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.right: parent.right
                    anchors.rightMargin: 14
                    contentWidth: width
                    contentHeight: listColumn.height
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    flickableDirection: Flickable.VerticalFlick
                    interactive: contentHeight > height

                Column {
                    id: listColumn
                    width: parent.width
                    spacing: 0

                Rectangle {
                    width: parent.width
                    height: 1
                    color: win.line
                }

                Repeater {
                    model: launcherModel
                    delegate: Column {
                        required property string name
                        required property string launcherId
                        required property bool custom
                        required property bool reinstall
                        required property string folder
                        width: listColumn.width

                        Item {
                            width: parent.width
                            height: 96

                        Column {
                            anchors.left: parent.left
                            anchors.leftMargin: 16
                            anchors.right: buttonRow.left
                            anchors.rightMargin: 12
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2

                            Text {
                                width: parent.width
                                text: name
                                color: win.ink
                                font.family: win.bodyFont
                                font.pixelSize: 16
                                elide: Text.ElideRight
                            }

                            Text {
                                width: parent.width
                                text: win.pending === name
                                        ? "Working…"
                                        : (win.readyMap[name] ? "Installed" : "Not set up yet")
                                color: win.muted
                                font.family: win.bodyFont
                                font.pixelSize: 13
                                elide: Text.ElideRight
                            }

                            Text {
                                width: parent.width
                                visible: folder.length > 0
                                text: folder
                                color: win.muted
                                font.family: win.bodyFont
                                font.pixelSize: 13
                                elide: Text.ElideRight
                            }
                        }

                        Row {
                            id: buttonRow
                            anchors.right: parent.right
                            anchors.rightMargin: 12
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 8

                            Rectangle {
                                objectName: "nuke" + launcherId
                                width: nukeLabel.implicitWidth + 28
                                height: 34
                                radius: 8
                                color: "transparent"
                                border.width: 1
                                border.color: win.line

                                Text {
                                    id: nukeLabel
                                    anchors.centerIn: parent
                                    text: "Nuke/Fix"
                                    color: win.ink
                                    font.family: win.bodyFont
                                    font.pixelSize: 14
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    enabled: win.pending.length === 0
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: win.confirmName = name
                                }
                            }

                            Rectangle {
                                objectName: "install" + launcherId
                                visible: win.showInstall(name, reinstall)
                                width: installLabel.implicitWidth + 28
                                height: 34
                                radius: 8
                                color: win.readyMap[name] ? "transparent" : win.button
                                border.width: win.readyMap[name] ? 1 : 0
                                border.color: win.line

                                Text {
                                    id: installLabel
                                    anchors.centerIn: parent
                                    text: win.readyMap[name] ? "Reinstall" : "Install"
                                    color: win.readyMap[name] ? win.ink : win.buttonInk
                                    font.family: win.bodyFont
                                    font.pixelSize: 14
                                    font.bold: !win.readyMap[name]
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    enabled: win.pending.length === 0
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        if (custom && win.readyMap[name] !== true) {
                                            win.programFor = name
                                            if (!win.preview)
                                                programDialog.open()
                                            return
                                        }
                                        win.startInstall(name)
                                    }
                                }
                            }

                            Rectangle {
                                objectName: "browse" + launcherId
                                width: browseLabel.implicitWidth + 28
                                height: 34
                                radius: 8
                                color: "transparent"
                                border.width: 1
                                border.color: win.line

                                Text {
                                    id: browseLabel
                                    anchors.centerIn: parent
                                    text: "Browse"
                                    color: win.ink
                                    font.family: win.bodyFont
                                    font.pixelSize: 14
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    enabled: win.pending.length === 0
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: win.act("/browse", name)
                                }
                            }

                            Rectangle {
                                objectName: "launch" + launcherId
                                visible: win.readyMap[name] === true
                                width: launchLabel.implicitWidth + 28
                                height: 34
                                radius: 8
                                color: win.button

                                Text {
                                    id: launchLabel
                                    anchors.centerIn: parent
                                    text: "Launch"
                                    color: win.buttonInk
                                    font.family: win.bodyFont
                                    font.pixelSize: 14
                                    font.bold: true
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    enabled: win.pending.length === 0
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: win.act("/launch", name)
                                }
                            }
                        }
                        }

                        Rectangle {
                            width: parent.width
                            height: 1
                            color: win.line
                        }
                    }
                }

                Item {
                    width: parent.width
                    height: 68

                    Rectangle {
                        id: nameBox
                        anchors.left: parent.left
                        anchors.leftMargin: 12
                        anchors.right: plusButton.left
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        height: 42
                        radius: 8
                        color: Qt.rgba(0, 0, 0, 0.28)
                        border.width: 1
                        border.color: win.line

                        TextInput {
                            id: customNameField
                            objectName: "customNameField"
                            z: 1
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            verticalAlignment: TextInput.AlignVCenter
                            color: win.ink
                            font.pixelSize: 16
                            font.family: win.bodyFont
                            selectByMouse: true
                            clip: true
                            maximumLength: 40
                            onAccepted: win.addCustom()
                        }

                        Text {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            verticalAlignment: Text.AlignVCenter
                            visible: customNameField.text.length === 0
                            text: "Name a game"
                            color: win.muted
                            font.family: win.bodyFont
                            font.pixelSize: 16
                        }
                    }

                    Rectangle {
                        id: plusButton
                        objectName: "addCustomGame"
                        anchors.right: parent.right
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        width: 42
                        height: 42
                        radius: 8
                        opacity: customNameField.text.trim().length > 0 ? 1 : 0.45
                        color: win.button

                        Text {
                            anchors.centerIn: parent
                            text: "+"
                            color: win.buttonInk
                            font.family: win.bodyFont
                            font.pixelSize: 22
                            font.bold: true
                        }

                        MouseArea {
                            anchors.fill: parent
                            enabled: customNameField.text.trim().length > 0 && win.pending.length === 0
                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: win.addCustom()
                        }
                    }
                }

                Rectangle {
                    width: parent.width
                    height: 1
                    color: win.line
                }
                }
                }

                Rectangle {
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    width: 8
                    radius: 4
                    color: Qt.rgba(1, 1, 1, 0.08)
                    visible: listFlick.contentHeight > listFlick.height
                }

                Rectangle {
                    id: listBar
                    objectName: "launcherScroll"
                    visible: listFlick.contentHeight > listFlick.height
                    width: 8
                    radius: 4
                    color: win.brass
                    anchors.right: parent.right
                    height: Math.min(parent.height, Math.max(36, listFlick.visibleArea.heightRatio * parent.height))
                    Binding on y {
                        when: !listBarMouse.drag.active
                        value: {
                            var span = listFrame.height - listBar.height
                            var maxY = listFlick.contentHeight - listFlick.height
                            if (span <= 0 || maxY <= 0)
                                return 0
                            return listFlick.contentY / maxY * span
                        }
                    }

                    MouseArea {
                        id: listBarMouse
                        anchors.fill: parent
                        drag.target: parent
                        drag.axis: Drag.YAxis
                        drag.minimumY: 0
                        drag.maximumY: Math.max(0, listFrame.height - listBar.height)
                        cursorShape: Qt.PointingHandCursor
                        onPositionChanged: {
                            if (!drag.active)
                                return
                            var span = listFrame.height - listBar.height
                            var maxY = listFlick.contentHeight - listFlick.height
                            if (span <= 0 || maxY <= 0)
                                return
                            listFlick.contentY = Math.max(0, Math.min(maxY, listBar.y / span * maxY))
                        }
                    }
                }
            }

            Text {
                width: parent.width
                visible: win.rowError.length > 0
                text: win.rowError
                color: win.danger
                font.family: win.bodyFont
                font.pixelSize: 14
                wrapMode: Text.WordWrap
            }
        }

        Rectangle {
            anchors.fill: parent
            visible: win.confirmName.length > 0
            color: Qt.rgba(0, 0, 0, 0.62)

            Rectangle {
                anchors.centerIn: parent
                width: Math.min(460, parent.width - 80)
                height: confirmColumn.height + 36
                radius: 14
                color: win.card
                border.width: 1
                border.color: win.line

                Column {
                    id: confirmColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 18
                    spacing: 14

                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: "Nuke/Fix " + win.confirmName + "?"
                        color: win.ink
                        font.family: win.bodyFont
                        font.pixelSize: 22
                    }

                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: "This rebuilds that launcher. Saved games stay."
                        color: win.muted
                        font.family: win.bodyFont
                        font.pixelSize: 15
                    }

                    Row {
                        spacing: 12

                        Rectangle {
                            objectName: "confirmNuke"
                            width: yesLabel.implicitWidth + 28
                            height: 34
                            radius: 8
                            color: win.button

                            Text {
                                id: yesLabel
                                anchors.centerIn: parent
                                text: "Nuke/Fix"
                                color: win.buttonInk
                                font.family: win.bodyFont
                                font.pixelSize: 14
                                font.bold: true
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    const name = win.confirmName
                                    win.confirmName = ""
                                    win.act("/remake", name)
                                }
                            }
                        }

                        Rectangle {
                            width: noLabel.implicitWidth + 28
                            height: 34
                            radius: 8
                            color: "transparent"
                            border.width: 1
                            border.color: win.line

                            Text {
                                id: noLabel
                                anchors.centerIn: parent
                                text: "Cancel"
                                color: win.ink
                                font.family: win.bodyFont
                                font.pixelSize: 14
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: win.confirmName = ""
                            }
                        }
                    }
                }
            }
        }

    }

    FileDialog {
        id: programDialog
        title: "Choose the program"
        fileMode: FileDialog.OpenFile
        nameFilters: ["Programs (*.exe *.msi)", "All files (*)"]
        onAccepted: {
            const path = win.localPath(programDialog.selectedFile)
            const name = win.programFor
            win.programFor = ""
            win.attachProgram(name, path)
        }
        onRejected: win.programFor = ""
    }

    Rectangle {
        anchors.fill: parent
        visible: win.rockstarWarn
        z: 20
        color: Qt.rgba(0, 0, 0, 0.62)

        MouseArea {
            anchors.fill: parent
        }

        Rectangle {
            objectName: "rockstarInstallWarn"
            anchors.centerIn: parent
            width: Math.min(520, parent.width - 80)
            height: rockstarInstallColumn.height + 36
            radius: 14
            color: win.card
            border.width: 1
            border.color: win.line

            MouseArea {
                anchors.fill: parent
            }

            Column {
                id: rockstarInstallColumn
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 18
                spacing: 12

                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: "Rockstar Launcher"
                    color: win.ink
                    font.family: win.titleFont
                    font.pixelSize: 26
                }

                Text {
                    objectName: "rockstarInstallWarnBody"
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: win.rockstarWarnBody
                    color: win.ink
                    font.family: win.bodyFont
                    font.pixelSize: 16
                }

                Rectangle {
                    objectName: "rockstarInstallWarnOk"
                    width: rockstarInstallOkLabel.implicitWidth + 28
                    height: 36
                    radius: 9
                    color: win.button

                    Text {
                        id: rockstarInstallOkLabel
                        anchors.centerIn: parent
                        text: "OK"
                        color: win.buttonInk
                        font.family: win.bodyFont
                        font.pixelSize: 16
                        font.bold: true
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: win.dismissRockstarWarn()
                    }
                }
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        visible: win.starCitizenWarn
        z: 21
        color: Qt.rgba(0, 0, 0, 0.62)

        MouseArea {
            anchors.fill: parent
        }

        Rectangle {
            objectName: "starCitizenInstallWarn"
            anchors.centerIn: parent
            width: Math.min(520, parent.width - 80)
            height: starCitizenInstallColumn.height + 36
            radius: 14
            color: win.card
            border.width: 1
            border.color: win.line

            MouseArea {
                anchors.fill: parent
            }

            Column {
                id: starCitizenInstallColumn
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 18
                spacing: 12

                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: "Star Citizen"
                    color: win.ink
                    font.family: win.titleFont
                    font.pixelSize: 26
                }

                Text {
                    objectName: "starCitizenInstallWarnBody"
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: win.starCitizenWarnBody
                    color: win.ink
                    font.family: win.bodyFont
                    font.pixelSize: 16
                }

                Rectangle {
                    objectName: "starCitizenInstallWarnOk"
                    width: starCitizenInstallOkLabel.implicitWidth + 28
                    height: 36
                    radius: 9
                    color: win.button

                    Text {
                        id: starCitizenInstallOkLabel
                        anchors.centerIn: parent
                        text: "OK"
                        color: win.buttonInk
                        font.family: win.bodyFont
                        font.pixelSize: 16
                        font.bold: true
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: win.dismissStarCitizenWarn()
                    }
                }
            }
        }
    }
}
