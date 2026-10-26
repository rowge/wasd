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

    function initialRoot() {
        try {
            if (typeof WasdRepo !== "undefined" && WasdRepo)
                return WasdRepo
        } catch (e) {
        }
        return ""
    }

    property string shareRoot: initialRoot()
    property bool tool: false
    property bool applying: false
    property bool avatarReady: true
    property var bridge: null
    property string titleFont: "Liberation Serif"
    property string bodyFont: "Liberation Sans"
    property int page: 0
    property int diskIndex: 0
    property string hostname: "wasd"
    property string userName: ""
    property string avatar: "knight.jpg"
    property bool setPassword: false
    property bool liveSession: false
    property bool erasing: false
    property string encodedChoices: ""
    property string lookOpen: ""
    property string loadingChoice: "stained-glass.jpg"
    property string loginChoice: "throne.jpg"
    property string themeChoice: "We10XOS-dark"
    property string wallpaperChoice: "stained-glass.jpg"
    property string appsOpen: "apps"
    property string appQuery: ""
    property string savedLine: ""
    property bool advancedOpen: false
    property bool gamesOpen: false
    property string gamesMode: "off"
    property int gamesDiskIndex: -1
    property int osGb: 128
    property int gamesGb: 32
    property string osGbText: "128"
    property string gamesGbText: "32"
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
    readonly property string eraseLabel: diskIndex >= 0 && diskIndex < disks.count && disks.get(diskIndex).windows
            ? "Erase Windows and install WASD"
            : "Erase the selected disk and install WASD"
    readonly property string appSummary: appCount() + " selected"
    readonly property string agentSummary: selectedAgentNames().join(", ") || "None selected"
    property bool networkConnected: true
    property string networkDetail: "Wired"
    property bool networkOpen: false
    property bool networkBusy: false
    property string networkLine: ""
    property string wifiSsid: ""
    property string wifiPass: ""
    property string tcpMode: "auto"
    property string tcpAddress: ""
    property string tcpNetmask: ""
    property string tcpGateway: ""
    property string tcpDns: ""
    property var wifiNetworks: [
        { ssid: "Home", signal: 84, security: "WPA2" },
        { ssid: "Shop", signal: 42, security: "WPA2" }
    ]
    readonly property string networkStatus: networkConnected
            ? ("Connected." + (networkDetail ? " " + networkDetail + "." : ""))
            : "No connection detected, expand to configure."

    ListModel {
        id: disks
        ListElement { name: "Samsung 990"; kind: ""; size: "2 TB"; windows: false; occupied: false; device: ""; bytes: 2000000000000.0; games: false; part: ""; fstype: ""; uuid: "" }
        ListElement { name: "WD Black"; kind: "Windows. This drive stays"; size: "1 TB"; windows: true; occupied: true; device: ""; bytes: 1000000000000.0; games: false; part: ""; fstype: ""; uuid: "" }
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
            if (typeof WasdBridge !== "undefined" && WasdBridge)
                bridge = WasdBridge
        } catch (e) {
        }
        if (!bridge) {
            liveSession = true
            installBlocked = true
            diskIndex = -1
            disks.clear()
            warnings = ["Reading the disks."]
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
        if (liveSession) {
            networkConnected = false
            networkDetail = ""
            wifiNetworks = []
            refreshNetwork(false)
        }
    }

    function refreshNetwork(rescan) {
        networkRequest("GET", rescan ? "/status?rescan=1" : "/status", "")
    }

    function connectWifi() {
        const ssid = wifiSsid.trim()
        const passphrase = wifiPass
        wifiPass = ""
        if (!ssid) {
            networkLine = "Type the network name."
            return
        }
        if (!liveSession) {
            networkConnected = true
            networkDetail = ssid
            networkLine = "This computer was not changed."
            return
        }
        let listed = false
        for (let i = 0; i < wifiNetworks.length; i++) {
            if (wifiNetworks[i].ssid === ssid)
                listed = true
        }
        networkBusy = true
        networkLine = "Connecting."
        networkRequest("POST", "/wifi", JSON.stringify({
            ssid: ssid,
            passphrase: passphrase,
            hidden: !listed
        }))
    }

    function applyTcp() {
        if (tcpMode === "manual" && (!tcpAddress.trim() || !tcpNetmask.trim() || !tcpGateway.trim() || !tcpDns.trim())) {
            networkLine = "Fill in the address, netmask, gateway, and DNS."
            return
        }
        if (!liveSession) {
            networkLine = "This computer was not changed."
            return
        }
        networkBusy = true
        networkLine = "Applying."
        networkRequest("POST", "/tcp", JSON.stringify({
            mode: tcpMode,
            address: tcpAddress.trim(),
            netmask: tcpNetmask.trim(),
            gateway: tcpGateway.trim(),
            dns: tcpDns.trim()
        }))
    }

    function networkRequest(method, path, body) {
        const xhr = new XMLHttpRequest()
        xhr.timeout = 25000
        xhr.open(method, "http://127.0.0.1:8765" + path)
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE)
                return
            win.networkBusy = false
            if (xhr.status === 200) {
                let data = {}
                try {
                    data = JSON.parse(xhr.responseText || "{}")
                } catch (e) {
                    win.networkLine = "The network helper is not available."
                    return
                }
                win.networkConnected = !!data.connected
                win.networkDetail = data.detail || ""
                if (data.networks && data.networks.length)
                    win.wifiNetworks = data.networks
                if (path.indexOf("/status") !== 0)
                    win.networkLine = data.connected ? "Connected." : win.networkLine
                return
            }
            const detail = (xhr.responseText || "").trim()
            win.networkLine = detail || "The network helper is not available."
        }
        xhr.send(body)
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

    function utf8Base64(str) {
        const bytes = []
        for (let i = 0; i < str.length; i++) {
            let code = str.charCodeAt(i)
            if (code >= 0xd800 && code <= 0xdbff && i + 1 < str.length) {
                const next = str.charCodeAt(++i)
                code = 0x10000 + ((code & 0x3ff) << 10) + (next & 0x3ff)
                bytes.push(0xf0 | (code >> 18), 0x80 | ((code >> 12) & 0x3f), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f))
            } else if (code < 0x80) {
                bytes.push(code)
            } else if (code < 0x800) {
                bytes.push(0xc0 | (code >> 6), 0x80 | (code & 0x3f))
            } else {
                bytes.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f))
            }
        }
        return Qt.btoa(bytes)
    }

    function encodeChoices() {
        encodedChoices = utf8Base64(choicesJson())
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

    function usableGb() {
        if (diskIndex < 0 || diskIndex >= disks.count)
            return 0
        const bytes = disks.get(diskIndex).bytes || 0
        const gib = Math.floor(bytes / (1024 * 1024 * 1024))
        return Math.max(0, gib - 4)
    }

    function onlyDrive() {
        if (diskIndex < 0 || disks.count < 1)
            return false
        for (let i = 0; i < disks.count; i++) {
            if (i !== diskIndex && !disks.get(i).windows)
                return false
        }
        return true
    }

    function splitFits() {
        return onlyDrive() && usableGb() >= 96
    }

    function gamesHeading() {
        let extra = ""
        if (gamesMode === "split")
            extra = "Leaving the rest of this drive for games."
        else if ((gamesMode === "keep" || gamesMode === "format") && gamesDiskIndex >= 0 && gamesDiskIndex < disks.count)
            extra = disks.get(gamesDiskIndex).name
        else {
            for (let i = 0; i < disks.count; i++) {
                if (i !== diskIndex && disks.get(i).games) {
                    extra = "A drive already has your games."
                    break
                }
            }
        }
        return extra ? "Games drive. " + extra : "Games drive"
    }

    function gamesLine(index) {
        if (index < 0 || index >= disks.count)
            return ""
        const row = disks.get(index)
        if (row.windows)
            return "The Windows drive stays."
        if (row.games)
            return "This drive has your games. WASD will use it and will not erase it."
        if (!row.occupied)
            return "Use this drive for games. This formats the drive, names it games, and mounts it at /games."
        return "Use this drive for games. WASD will use it and will not erase it."
    }

    function clearGames() {
        gamesMode = "off"
        gamesDiskIndex = -1
    }

    function chooseSplit() {
        if (!splitFits())
            return
        const usable = usableGb()
        const os = Math.min(128, usable - 32)
        osGb = os
        gamesGb = usable - os
        osGbText = String(os)
        gamesGbText = String(gamesGb)
        gamesMode = "split"
        gamesDiskIndex = -1
    }

    function toggleSplit() {
        if (gamesMode === "split")
            clearGames()
        else
            chooseSplit()
    }

    function setOsGb(value) {
        if (!splitFits())
            return
        let n = parseInt(value, 10)
        if (!isFinite(n)) {
            osGbText = String(osGb)
            return
        }
        const usable = usableGb()
        if (n < 64)
            n = 64
        if (n > usable - 32)
            n = usable - 32
        osGb = n
        gamesGb = usable - n
        osGbText = String(n)
        gamesGbText = String(gamesGb)
        gamesMode = "split"
        gamesDiskIndex = -1
    }

    function setGamesGb(value) {
        if (!splitFits())
            return
        let n = parseInt(value, 10)
        if (!isFinite(n)) {
            gamesGbText = String(gamesGb)
            return
        }
        const usable = usableGb()
        if (n < 32)
            n = 32
        if (n > usable - 64)
            n = usable - 64
        gamesGb = n
        osGb = usable - n
        gamesGbText = String(n)
        osGbText = String(osGb)
        gamesMode = "split"
        gamesDiskIndex = -1
    }

    function chooseGames(index) {
        if (index < 0 || index >= disks.count || index === diskIndex)
            return
        const row = disks.get(index)
        if (row.windows)
            return
        if (gamesDiskIndex === index && gamesMode !== "off" && gamesMode !== "split") {
            clearGames()
            return
        }
        gamesMode = row.games || row.occupied ? "keep" : "format"
        gamesDiskIndex = index
    }

    function reconcileGames() {
        if (gamesMode === "off")
            return
        if (gamesMode === "split") {
            if (!splitFits())
                clearGames()
            else if (osGb < 64 || gamesGb < 32 || osGb + gamesGb > usableGb())
                chooseSplit()
            return
        }
        if (gamesDiskIndex < 0 || gamesDiskIndex >= disks.count || gamesDiskIndex === diskIndex)
            clearGames()
        else if (disks.get(gamesDiskIndex).windows)
            clearGames()
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

    function selectAllApps() {
        const copy = Object.assign({}, appOn)
        for (let i = 0; i < appNames.length; i++)
            copy[appNames[i]] = true
        appOn = copy
    }

    function selectNoneApps() {
        const copy = Object.assign({}, appOn)
        for (let i = 0; i < appNames.length; i++)
            copy[appNames[i]] = false
        appOn = copy
        pickedExtras = []
    }

    function selectAllAgents() {
        const copy = {}
        for (let i = 0; i < agentNames.length; i++)
            copy[agentNames[i]] = true
        agentOn = copy
    }

    function selectNoneAgents() {
        const copy = {}
        for (let i = 0; i < agentNames.length; i++)
            copy[agentNames[i]] = false
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
        let device = ""
        let diskBytes = 0
        if (diskIndex >= 0 && diskIndex < disks.count) {
            diskName = disks.get(diskIndex).name
            device = disks.get(diskIndex).device || ""
            diskBytes = Math.round(disks.get(diskIndex).bytes || 0)
        }
        const payload = {
            disk: diskName,
            device: device,
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
        }
        if (gamesMode === "split") {
            payload.games = {
                mode: "split",
                osGb: osGb,
                gamesGb: gamesGb,
                bytes: diskBytes
            }
        } else if ((gamesMode === "keep" || gamesMode === "format") && gamesDiskIndex >= 0 && gamesDiskIndex < disks.count) {
            const grow = disks.get(gamesDiskIndex)
            const games = {
                mode: gamesMode,
                device: grow.device || "",
                disk: grow.name
            }
            if (gamesMode === "keep") {
                games.part = grow.part || ""
                games.fstype = grow.fstype || ""
                games.uuid = grow.uuid || ""
            }
            payload.games = games
        }
        return JSON.stringify(payload, null, 2)
    }

    function saveChoices() {
        if (installBlocked || diskIndex < 0)
            return
        if (!hostnameOk) {
            savedLine = ""
            page = 3
            return
        }
        if (userName.trim() === "") {
            savedLine = "Choose a username first."
            page = 0
            return
        }
        if (!userOk) {
            savedLine = ""
            page = 0
            return
        }
        if (bridge || !liveSession) {
            savedLine = "Saved your choices. Nothing was erased."
            if (bridge)
                bridge.save(choicesJson())
            return
        }
        const device = disks.get(diskIndex).device || ""
        if (!/^(nvme[0-9]+n[0-9]+|sd[a-z]+|vd[a-z]+|mmcblk[0-9]+|hd[a-z]+)$/.test(device)) {
            savedLine = "Choose a disk again. Nothing was erased."
            return
        }
        if (!liveLoader.item) {
            savedLine = "The installer is not ready. Nothing was erased."
            return
        }
        erasing = true
        savedLine = "Starting the install."
        liveLoader.item.erase(utf8Base64(choicesJson()))
    }

    function applyLive(payload) {
        const data = JSON.parse(payload)
        warnings = data.warnings || []
        installBlocked = !!data.blocked
        clearGames()
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
                occupied: !!row.occupied,
                device: row.device || "",
                bytes: row.bytes || 0,
                games: !!row.games,
                part: row.part || "",
                fstype: row.fstype || "",
                uuid: row.uuid || ""
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
            rows.push({ name: row.name, windows: !!row.windows, occupied: !!row.occupied, device: row.device || "", games: !!row.games })
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
    onDiskIndexChanged: reconcileGames()

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
                    model: ["User", "Look", "Apps & Agents", "System", "Disk"]
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
                sourceComponent: win.page === 0 ? userComp : win.page === 1 ? lookComp : win.page === 2 ? appsComp : win.page === 3 ? systemComp : diskComp
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
    Component {
        id: systemComp
        SystemPage { host: win }
    }

    Loader {
        id: liveLoader
        active: win.liveSession
        source: "LiveHost.qml"
        onLoaded: item.probe()
    }

    Connections {
        target: liveLoader.item
        enabled: liveLoader.item !== null
        function onDisks(payload) {
            if (!payload) {
                win.installBlocked = true
                win.warnings = ["The disks could not be read."]
                return
            }
            win.applyLive(payload)
        }
        function onFilesReady(payload) {
            win.files = JSON.parse(payload)
        }
        function onEraseFinished(code, line) {
            win.erasing = false
            win.savedLine = line || (code === 0 ? "The installer finished." : "Nothing was erased.")
        }
    }
}
