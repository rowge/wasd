import QtQuick
import QtQuick.Window

Window {
    id: win
    objectName: "installWindow"
    width: 1040
    height: 760
    visible: true
    title: "Install WASD"
    color: bg
    flags: Qt.Window | Qt.FramelessWindowHint

    property string shareRoot: ""
    property bool tool: false
    property bool applying: false
    property var bridge: null
    property string titleFont: "Liberation Serif"
    property string bodyFont: "Liberation Sans"
    property int page: 0
    property int diskIndex: 0
    property string hostname: "wasd"
    property string userName: ""
    property string avatar: "knight.jpg"
    property bool setPassword: false
    property string password: ""
    property string passwordAgain: ""
    property string lookOpen: ""
    property string loadingChoice: "keysketch.jpg"
    property string loginChoice: "camp.png"
    property string themeChoice: "We10XOS-dark"
    property string wallpaperChoice: "wasdsketch.png"
    property string appsOpen: "apps"
    property string appQuery: ""
    property string savedLine: ""
    property bool advancedOpen: false
    property bool installBlocked: false
    property var files: ({})
    property var appOn: ({})
    property var agentOn: ({})
    property var searchHits: []
    property var pickedExtras: []
    property var warnings: [
        "Turn off BitLocker and fast startup in Windows before you install.",
        "Set the firmware to UEFI in the BIOS. The motherboard manual explains how."
    ]

    readonly property color bg: "#24160e"
    readonly property color rail: "#1c100b"
    readonly property color ink: "#f6ead8"
    readonly property color muted: "#e7d3b6"
    readonly property color brass: "#c4a574"
    readonly property color danger: "#ff5c5c"
    readonly property color line: Qt.rgba(246 / 255, 226 / 255, 196 / 255, 0.22)

    readonly property var themes: [
        "Sweet KDE", "Layan", "We10XOS-dark", "Ant-Dark", "Nordic", "ChromeOS",
        "Otto", "Carl", "WhiteSur-Dark", "Edna-Light", "Expose", "Expose Blue",
        "Expose Green", "Expose Metallic", "Expose Dark", "Expose Air", "Expose Air Dark"
    ]
    readonly property var appNames: [
        "Brave", "Discord", "Element", "Heroic", "Bottles", "OBS Studio", "GOverlay",
        "Easy Effects", "Piper", "OpenRGB", "LACT", "Gwenview", "Okular", "Calculator",
        "Haruna", "Kontainer", "Flatseal", "Protontricks", "Warehouse", "ProtonPlus",
        "Firmware", "VLC", "GIMP", "Bitwarden"
    ]
    readonly property var appIds: [
        "com.brave.Browser", "com.discordapp.Discord", "im.riot.Riot",
        "com.heroicgameslauncher.hgl", "com.usebottles.bottles", "com.obsproject.Studio",
        "io.github.benjamimgois.goverlay", "com.github.wwmm.easyeffects",
        "org.freedesktop.Piper", "org.openrgb.OpenRGB", "io.github.ilya_zlobintsev.LACT",
        "org.kde.gwenview", "org.kde.okular", "org.kde.kcalc", "org.kde.haruna",
        "io.github.DenysMb.Kontainer", "com.github.tchx84.Flatseal",
        "com.github.Matoking.protontricks", "io.github.flattool.Warehouse",
        "com.vysp3r.ProtonPlus", "org.gnome.Firmware", "org.videolan.VLC",
        "org.gimp.GIMP", "com.bitwarden.desktop"
    ]
    readonly property var agentNames: [
        "Grok Build", "Grok Bot", "Grok", "Claude Code", "Codex", "OpenCode",
        "Antigravity", "Amp", "Command Code", "Copilot CLI", "Crush", "Cursor CLI",
        "Devin", "DeepSeek Harness", "Freebuff", "Hermes", "Kilo", "Kimi", "Kiro",
        "MiniMax Code", "Muse", "Oh My Pi", "Ori", "Pi", "Qwen", "ChatGPT", "Claude",
        "Hermes Desktop", "OpenClaw", "Perplexity", "T3 Code", "LM Studio", "Ollama"
    ]

    readonly property var iconFiles: files.icons || []
    readonly property var loadingFiles: files.loading || []
    readonly property var loginFiles: files.login || []
    readonly property var wallpaperFiles: files.wallpapers || []
    readonly property bool hostnameOk: /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$/.test(hostname)
    readonly property bool userOk: userName.trim() === "" || (/^[a-z][a-z0-9-]{0,31}$/.test(userName.trim()) && userName.trim() !== "root")
    readonly property bool passwordOk: !setPassword || (password.length > 0 && password === passwordAgain)
    readonly property string eraseLabel: diskIndex >= 0 && diskIndex < disks.count && disks.get(diskIndex).windows
            ? "Erase Windows and install WASD"
            : "Erase the selected disk and install WASD"
    readonly property string appSummary: appCount() + " selected"
    readonly property string agentSummary: selectedAgentNames().join(", ") || "None selected"

    ListModel {
        id: disks
        ListElement { name: "Samsung 990"; kind: ""; size: "2 TB"; windows: false; occupied: false }
        ListElement { name: "WD Black"; kind: "Windows. This drive stays"; size: "1 TB"; windows: true; occupied: true }
    }
    property alias diskModel: disks

    ListModel { id: shownApps }
    property alias shownAppModel: shownApps

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
        const apps = {}
        for (let i = 0; i < appNames.length; i++)
            apps[appNames[i]] = true
        appOn = apps
        const agents = {}
        for (let j = 0; j < agentNames.length; j++) {
            const name = agentNames[j]
            agents[name] = name === "Grok Build" || name === "Grok Bot" || name === "Grok"
        }
        agentOn = agents
        refreshShown()
    }

    function art(folder, fileName) {
        if (!shareRoot || !fileName)
            return ""
        return "file://" + shareRoot + "/" + folder + "/" + fileName
    }

    function diskLine(index) {
        if (index < 0 || index >= disks.count)
            return ""
        const row = disks.get(index)
        if (index === diskIndex && row.windows)
            return "WARNING! This erases Windows."
        if (index === diskIndex)
            return "WARNING! This drive will be wiped."
        return row.kind || ""
    }

    function openLook(which) {
        lookOpen = lookOpen === which ? "" : which
    }

    function openApps(which) {
        if (appsOpen === which)
            appsOpen = which === "apps" ? "agents" : "apps"
        else
            appsOpen = which
    }

    function toggleApp(name, id, extra) {
        if (extra) {
            const next = []
            let found = false
            for (let i = 0; i < pickedExtras.length; i++) {
                if (pickedExtras[i].id === id) {
                    found = true
                    continue
                }
                next.push(pickedExtras[i])
            }
            if (!found)
                next.push({ name: name, id: id })
            pickedExtras = next
            return
        }
        const copy = Object.assign({}, appOn)
        copy[name] = !copy[name]
        appOn = copy
    }

    function extraPicked(id) {
        for (let i = 0; i < pickedExtras.length; i++) {
            if (pickedExtras[i].id === id)
                return true
        }
        return false
    }

    function toggleAgent(name) {
        const copy = Object.assign({}, agentOn)
        copy[name] = !copy[name]
        agentOn = copy
    }

    function appCount() {
        let count = pickedExtras.length
        for (let i = 0; i < appNames.length; i++) {
            if (appOn[appNames[i]])
                count = count + 1
        }
        return count
    }

    function selectedAgentNames() {
        const names = []
        for (let i = 0; i < agentNames.length; i++) {
            if (agentOn[agentNames[i]])
                names.push(agentNames[i])
        }
        return names
    }

    function queryEdited(text) {
        appQuery = text
        searchTimer.restart()
    }

    function refreshShown() {
        const query = appQuery.trim().toLowerCase()
        shownApps.clear()
        for (let i = 0; i < appNames.length; i++) {
            if (query && appNames[i].toLowerCase().indexOf(query) < 0)
                continue
            shownApps.append({ name: appNames[i], id: appIds[i], extra: false })
        }
        if (!query)
            return
        for (let j = 0; j < searchHits.length; j++) {
            const hit = searchHits[j]
            if (!hit || appIds.indexOf(hit.id) >= 0)
                continue
            const name = hit.name || hit.id
            if (name.toLowerCase().indexOf(query) < 0)
                continue
            shownApps.append({ name: name, id: hit.id, extra: true })
        }
    }

    function choicesJson() {
        const apps = []
        for (let i = 0; i < appNames.length; i++) {
            if (appOn[appNames[i]])
                apps.push({ name: appNames[i], id: appIds[i] })
        }
        for (let j = 0; j < pickedExtras.length; j++)
            apps.push(pickedExtras[j])
        const agents = selectedAgentNames()
        let diskName = ""
        if (diskIndex >= 0 && diskIndex < disks.count)
            diskName = disks.get(diskIndex).name
        return JSON.stringify({
            disk: diskName,
            hostname: hostname.toLowerCase(),
            user: userName.trim(),
            avatar: avatar,
            password: setPassword,
            loading: loadingChoice,
            login: loginChoice,
            theme: themeChoice,
            wallpaper: wallpaperChoice,
            apps: apps,
            agents: agents
        }, null, 2)
    }

    function saveChoices() {
        if (installBlocked || diskIndex < 0)
            return
        if (!hostnameOk) {
            savedLine = ""
            page = 0
            return
        }
        if (!userOk) {
            savedLine = ""
            page = 1
            return
        }
        if (!passwordOk) {
            savedLine = ""
            page = 1
            return
        }
        savedLine = "Saved your choices. Nothing was erased."
        if (bridge)
            bridge.save(choicesJson())
    }

    function applyLive(payload) {
        const data = JSON.parse(payload)
        warnings = data.warnings || []
        installBlocked = !!data.blocked
        diskIndex = -1
        disks.clear()
        const rows = data.disks || []
        let pick = -1
        for (let i = 0; i < rows.length; i++) {
            const row = rows[i]
            disks.append({
                name: row.name,
                kind: row.kind || "",
                size: row.size || "",
                windows: !!row.windows,
                occupied: !!row.occupied
            })
            if (pick < 0 && !row.occupied)
                pick = i
        }
        diskIndex = pick
    }

    function diskSnapshot() {
        const rows = []
        for (let i = 0; i < disks.count; i++) {
            const row = disks.get(i)
            rows.push({ name: row.name, windows: !!row.windows, occupied: !!row.occupied })
        }
        return JSON.stringify({ index: diskIndex, blocked: installBlocked, rows: rows })
    }

    Timer {
        id: searchTimer
        interval: 300
        onTriggered: {
            if (win.bridge && win.appQuery.trim().length >= 2)
                win.bridge.search(win.appQuery.trim())
            else {
                win.searchHits = []
                win.refreshShown()
            }
        }
    }

    Connections {
        target: win.bridge
        enabled: win.bridge !== null
        function onFound(payload) {
            win.searchHits = JSON.parse(payload)
            win.refreshShown()
        }
    }

    onAppQueryChanged: refreshShown()

    Component.onCompleted: boot()

    Rectangle {
        id: shell
        objectName: "shell"
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
                text: "Install WASD"
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

        Rectangle {
            id: rail
            anchors.top: titlebar.bottom
            anchors.bottom: parent.bottom
            width: 220
            color: win.rail

            Image {
                id: logo
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.margins: 28
                width: 84
                fillMode: Image.PreserveAspectFit
                source: win.art("wasd-icons", "wasd-logo.png")
                sourceSize: Qt.size(168, 168)
                cache: true
            }

            Column {
                anchors.top: logo.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.topMargin: 28
                anchors.leftMargin: 22
                anchors.rightMargin: 22
                spacing: 6

                Repeater {
                    model: ["Disk", "User", "Look", "Apps & Agents"]
                    delegate: Rectangle {
                        required property string modelData
                        required property int index
                        width: parent.width
                        height: 40
                        color: win.page === index ? win.brass : "transparent"

                        Text {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            verticalAlignment: Text.AlignVCenter
                            text: modelData
                            color: win.page === index ? "#24160e" : win.muted
                            font.family: win.bodyFont
                            font.pixelSize: 16
                            font.bold: win.page === index
                        }
                    }
                }
            }

            Rectangle {
                anchors.right: parent.right
                width: 1
                height: parent.height
                color: win.line
            }
        }

        Item {
            anchors.top: titlebar.bottom
            anchors.bottom: parent.bottom
            anchors.left: rail.right
            anchors.right: parent.right

            Loader {
                anchors.fill: parent
                sourceComponent: win.page === 0 ? diskComp : win.page === 1 ? userComp : win.page === 2 ? lookComp : appsComp
            }
        }
    }

    Component {
        id: diskComp
        DiskPage { host: win }
    }
    Component {
        id: userComp
        UserPage { host: win }
    }
    Component {
        id: lookComp
        LookPage { host: win }
    }
    Component {
        id: appsComp
        AppsPage { host: win }
    }
}
