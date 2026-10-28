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
    property string titleFont: "Liberation Sans"
    property string bodyFont: "Liberation Sans"
    property int page: 0
    property int diskIndex: 0
    property string hostname: "wasd"
    property string userName: ""
    property string avatar: "knight.jpg"
    property bool setPassword: false
    property bool liveSession: false
    property bool erasing: false
    property string installStage: ""
    readonly property bool restartReady: installStage === "done" || (installStage === "failed" && savedLine.indexOf("WASD was copied.") === 0)
    property string stagesSeen: ""
    property bool restartAsked: false
    property bool restartSent: false
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
    property bool gamesConfirmed: false
    property bool systemConfirmed: false
    property int actionIndex: -1
    property int confirmStep: 0
    property int confirmIndex: -1
    property string confirmAction: ""
    property bool confirmStartsInstall: false
    property var wipeDrives: []
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

    readonly property var themes: [
        "Sweet KDE", "Layan", "We10XOS-dark", "Ant-Dark", "Nordic", "ChromeOS",
        "Otto", "Carl", "WhiteSur-Dark", "Edna-Light", "Expose", "Expose Blue",
        "Expose Green", "Expose Metallic", "Expose Dark", "Expose Air", "Expose Air Dark"
    ]
    readonly property var appNames: [
        "Discord", "Element", "Heroic", "Bottles", "OBS Studio", "GOverlay",
        "Easy Effects", "Piper", "OpenRGB", "LACT", "Gwenview", "Okular", "Calculator",
        "Haruna", "Kontainer", "Flatseal", "Protontricks", "Warehouse", "ProtonPlus",
        "Firmware", "VLC", "GIMP", "Bitwarden"
    ]
    readonly property var appIds: [
        "com.discordapp.Discord", "im.riot.Riot",
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
    readonly property bool gamesChosen: gamesMode === "split" || gamesMode === "keep" || gamesMode === "format"
    readonly property bool showEraseButton: !gamesOpen || gamesChosen
    readonly property string gamesAltLabel: gamesOpen
            ? "I changed my mind. Use the whole drive."
            : "Set up /games"
    readonly property string eraseLabel: {
        const windows = diskIndex >= 0 && diskIndex < disks.count && disks.get(diskIndex).windows
        if (gamesChosen)
            return windows
                    ? "Erase Windows and install with the games partition"
                    : "Erase the disk and install with the games partition"
        return windows
                ? "Erase Windows and install WASD"
                : "Erase the selected disk and install WASD"
    }
    readonly property string appSummary: appCount() + " selected"
    readonly property string agentSummary: selectedAgentNames().join(", ") || "None selected"
    property bool networkConnected: true
    property string networkDetail: "Wired"
    property int networkSerial: 0
    property bool networkOpen: false
    property bool networkBusy: false
    property string networkLine: ""
    property string wifiSsid: ""
    readonly property bool wifiNameOk: {
        const name = wifiSsid.trim()
        return name.length > 0 && !name.startsWith("-") && name.indexOf("\n") < 0 && name.length <= 32
    }
    readonly property string wifiNote: {
        const name = wifiSsid.trim()
        if (!name)
            return ""
        if (!wifiNameOk)
            return "That network name cannot be used."
        return "Saved. The first boot asks for the passphrase."
    }
    property string tcpMode: "auto"
    property string tcpAddress: ""
    property string tcpNetmask: ""
    property string tcpGateway: ""
    property string tcpDns: ""
    property string tcpInterface: ""
    property string tcpKind: ""
    property bool networkLineOk: true
    property var tcpDevices: [
        { device: "wlp3s0", kind: "wifi", label: "Wi-Fi" },
        { device: "enp4s0", kind: "ethernet", label: "Ethernet" }
    ]
    readonly property string tcpNote: tcpNoteFor(tcpMode, tcpAddress, tcpNetmask, tcpGateway, tcpDns, tcpInterface, tcpKind, wifiNameOk)
    readonly property bool tcpReady: tcpMode === "manual" && tcpNote.indexOf("Saved for the installed system.") === 0
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
        ListElement { name: "WD Black"; kind: "Windows is on this drive."; size: "1 TB"; windows: true; occupied: true; device: ""; bytes: 1000000000000.0; games: false; part: ""; fstype: ""; uuid: "" }
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
        titleFont = pickFont(["Noto Sans", "Liberation Sans", "Segoe UI", "DejaVu Sans"], titleFont)
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
            tcpDevices = []
            refreshNetwork(false)
            refreshDevices()
        }
    }

    function refreshDevices() {
        if (!liveSession)
            return
        const xhr = new XMLHttpRequest()
        xhr.timeout = 8000
        xhr.open("GET", "http://127.0.0.1:8765/devices")
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE || xhr.status !== 200)
                return
            let data = {}
            try {
                data = JSON.parse(xhr.responseText || "{}")
            } catch (e) {
                return
            }
            if (data.devices)
                win.tcpDevices = data.devices
        }
        xhr.send()
    }

    function refreshNetwork(rescan) {
        const serial = ++networkSerial
        const xhr = new XMLHttpRequest()
        xhr.timeout = rescan ? 25000 : 8000
        xhr.open("GET", "http://127.0.0.1:8765" + (rescan ? "/status?rescan=1" : "/status"))
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE || serial !== win.networkSerial)
                return
            if (xhr.status !== 200)
                return
            let data = {}
            try {
                data = JSON.parse(xhr.responseText || "{}")
            } catch (e) {
                return
            }
            win.networkConnected = !!data.connected
            win.networkDetail = data.detail || ""
            if (data.networks && data.networks.length)
                win.wifiNetworks = data.networks
        }
        xhr.send()
    }

    function chooseWifi(name) {
        wifiSsid = wifiSsid === name ? "" : name
    }

    function wifiChoice() {
        if (!wifiNameOk)
            return null
        const name = wifiSsid.trim()
        let security = ""
        let hidden = true
        for (let i = 0; i < wifiNetworks.length; i++) {
            if (wifiNetworks[i].ssid === name) {
                security = wifiNetworks[i].security || ""
                hidden = false
                break
            }
        }
        return { ssid: name, security: security, hidden: hidden }
    }

    function ipv4Ok(value) {
        const parts = value.split(".")
        if (parts.length !== 4)
            return false
        for (let i = 0; i < 4; i++) {
            const part = parts[i]
            if (!/^\d+$/.test(part))
                return false
            if (part.length > 1 && part.charAt(0) === "0")
                return false
            if (parseInt(part, 10) > 255)
                return false
        }
        return true
    }

    function netmaskOk(mask) {
        if (!ipv4Ok(mask))
            return false
        const parts = mask.split(".")
        let bits = ""
        for (let i = 0; i < 4; i++)
            bits += ("00000000" + parseInt(parts[i], 10).toString(2)).slice(-8)
        return bits.indexOf("01") < 0
    }

    function dnsOk(value) {
        const parts = value.trim().split(/[\s,]+/)
        if (!parts.length)
            return false
        for (let i = 0; i < parts.length; i++) {
            if (!parts[i] || !ipv4Ok(parts[i]))
                return false
        }
        return true
    }

    function adapterOk(iface, kind) {
        return /^[A-Za-z][A-Za-z0-9._-]{0,15}$/.test(iface) && (kind === "wifi" || kind === "ethernet")
    }

    function tcpFieldsProblem(address, netmask, gateway, dns, iface, kind) {
        if (!address.trim() || !netmask.trim() || !gateway.trim() || !dns.trim() || !iface)
            return "Fill in the address, netmask, gateway, DNS, and choose an adapter."
        if (!ipv4Ok(address.trim()))
            return "Use an IP address like 192.168.1.20."
        if (!netmaskOk(netmask.trim()))
            return "Use a netmask like 255.255.255.0."
        if (!ipv4Ok(gateway.trim()))
            return "Use a gateway like 192.168.1.1."
        if (!dnsOk(dns.trim()))
            return "Use a DNS address like 1.1.1.1."
        if (!adapterOk(iface, kind))
            return "Choose an adapter."
        return ""
    }

    function tcpNoteFor(mode, address, netmask, gateway, dns, iface, kind, wifiOk) {
        if (mode !== "manual")
            return ""
        const problem = tcpFieldsProblem(address, netmask, gateway, dns, iface, kind)
        if (problem)
            return problem + " These settings are not saved until then."
        if (kind === "wifi" && !wifiOk)
            return "Saved for the installed system. Choose a Wi-Fi network too, or this address is not used."
        if (kind === "wifi")
            return "Saved for the installed system. The first boot uses this address when that network connects."
        return "Saved for the installed system."
    }

    function chooseAdapter(device) {
        if (tcpInterface === device) {
            tcpInterface = ""
            tcpKind = ""
            return
        }
        let kind = ""
        for (let i = 0; i < tcpDevices.length; i++) {
            if (tcpDevices[i].device === device) {
                kind = tcpDevices[i].kind || ""
                break
            }
        }
        tcpInterface = device
        tcpKind = kind
    }

    function tcpChoice() {
        if (tcpMode !== "manual")
            return null
        if (tcpFieldsProblem(tcpAddress, tcpNetmask, tcpGateway, tcpDns, tcpInterface, tcpKind))
            return null
        return {
            mode: "manual",
            interface: tcpInterface,
            kind: tcpKind,
            address: tcpAddress.trim(),
            netmask: tcpNetmask.trim(),
            gateway: tcpGateway.trim(),
            dns: tcpDns.trim()
        }
    }

    function applyTcp() {
        if (tcpMode !== "manual") {
            networkLineOk = true
            networkLine = "Automatic uses the address the network offers."
            return
        }
        const problem = tcpFieldsProblem(tcpAddress, tcpNetmask, tcpGateway, tcpDns, tcpInterface, tcpKind)
        if (problem) {
            networkLineOk = false
            networkLine = problem
            return
        }
        if (!liveSession) {
            networkLineOk = true
            networkLine = "Saved for the installed system. This computer was not changed."
            return
        }
        const choice = tcpChoice()
        if (!choice) {
            networkLineOk = false
            networkLine = "Choose an adapter."
            return
        }
        networkBusy = true
        networkLineOk = true
        networkLine = "Saving."
        networkRequest("POST", "/tcp", JSON.stringify(choice))
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
                if (path === "/tcp") {
                    win.networkLineOk = true
                    win.networkLine = data.message || "Saved for the installed system."
                    return
                }
                if (path.indexOf("/status") !== 0)
                    win.networkLine = data.connected ? "Connected." : win.networkLine
                return
            }
            const detail = (xhr.responseText || "").trim()
            win.networkLineOk = false
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

    function splitFits() {
        return diskIndex >= 0 && usableGb() >= 96
    }

    function focusIndex() {
        if (actionIndex >= 0 && actionIndex < disks.count)
            return actionIndex
        return diskIndex
    }

    function canKeep(index) {
        if (index < 0 || index >= disks.count)
            return false
        const row = disks.get(index)
        return !!(row.part && row.uuid)
    }

    function gamesHeading() {
        let extra = ""
        if ((gamesMode === "keep" || gamesMode === "format") && gamesDiskIndex >= 0 && gamesDiskIndex < disks.count)
            extra = disks.get(gamesDiskIndex).name
        else {
            for (let i = 0; i < disks.count; i++) {
                if (i !== diskIndex && disks.get(i).games) {
                    extra = "A drive already has your games."
                    break
                }
            }
        }
        return extra ? "/games. " + extra : "/games"
    }

    function gamesLine(index) {
        if (index < 0 || index >= disks.count)
            return ""
        if (index === diskIndex) {
            if (!splitFits())
                return "This drive is too small to leave room for games."
            if (gamesMode === "split")
                return "WASD keeps the first part. The rest is mounted at /games."
            return "Use part of this drive for /games."
        }
        const row = disks.get(index)
        if (gamesDiskIndex === index && gamesMode === "format")
            return "This drive will be erased and used for games."
        if (gamesDiskIndex === index && gamesMode === "keep")
            return "WASD will use this drive and will not erase it."
        if (row.windows && !canKeep(index))
            return "BitLocker is on. Turn it off in Windows before this drive can be used without erasing it."
        if (row.windows)
            return "Windows is on this drive."
        if (row.games)
            return "This drive has your games. WASD will use it and will not erase it."
        if (!row.occupied)
            return "Use this drive for games. This formats the drive, names it games, and mounts it at /games."
        return "Use this drive for games. WASD will use it and will not erase it."
    }

    function clearGames() {
        gamesMode = "off"
        gamesDiskIndex = -1
        gamesConfirmed = false
    }

    function wipeHas(row) {
        if (!row)
            return false
        for (let i = 0; i < wipeDrives.length; i++) {
            const item = wipeDrives[i]
            if (row.device && item.device === row.device)
                return true
            if (!row.device && item.disk === row.name)
                return true
        }
        return false
    }

    function removeWipe(row) {
        const next = []
        for (let i = 0; i < wipeDrives.length; i++) {
            const item = wipeDrives[i]
            if (row.device && item.device === row.device)
                continue
            if (!row.device && item.disk === row.name)
                continue
            next.push(item)
        }
        wipeDrives = next
    }

    function addWipe(row) {
        removeWipe(row)
        const next = wipeDrives.slice()
        next.push({ device: row.device || "", disk: row.name || "" })
        wipeDrives = next
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
        gamesConfirmed = false
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

    function pickGamesDrive(index) {
        if (index < 0 || index >= disks.count || diskIndex < 0)
            return
        if (index === diskIndex) {
            if (gamesMode === "split")
                clearGames()
            else
                chooseSplit()
            return
        }
        if (gamesDiskIndex === index && (gamesMode === "keep" || gamesMode === "format")) {
            clearGames()
            return
        }
        const row = disks.get(index)
        if (canKeep(index))
            beginConfirm("gamesKeep", index, false)
        else if (!row.occupied && !row.windows)
            beginConfirm("gamesWipe", index, false)
    }

    function useWholeDrive() {
        clearGames()
        gamesOpen = false
    }

    function openGamesSection() {
        if (diskIndex < 0 || disks.count < 1 || gamesOpen)
            return
        gamesOpen = true
        if (disks.count === 1 && splitFits())
            chooseSplit()
    }

    function toggleGamesOpen() {
        if (!gamesOpen)
            openGamesSection()
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
    }

    function beginConfirm(action, index, startInstall) {
        const picked = parseInt(index, 10)
        if (picked < 0 || picked >= disks.count)
            return
        if (action === "gamesKeep" && !canKeep(picked))
            return
        confirmAction = action
        confirmIndex = picked
        confirmStartsInstall = !!startInstall
        confirmStep = 1
    }

    function confirmNo() {
        confirmStep = 0
        confirmAction = ""
        confirmStartsInstall = false
    }

    function showPage(next) {
        const index = parseInt(next, 10)
        if (index < 0 || index > 4 || erasing || installStage === "done")
            return
        if (installStage === "failed")
            installStage = ""
        if (index !== page)
            confirmNo()
        page = index
    }

    function stageRank(stage) {
        const order = ["prepare", "copy", "account", "boot", "done"]
        for (let i = 0; i < order.length; i++) {
            if (order[i] === stage)
                return i
        }
        return -1
    }

    function stageForLine(line) {
        if (line === "Preparing the disk.")
            return "prepare"
        if (line === "Copying WASD.")
            return "copy"
        if (line === "Setting up your account.")
            return "account"
        if (line === "Installing the bootloader.")
            return "boot"
        if (line === "You can remove the USB stick. Press Enter to restart.")
            return "done"
        return ""
    }

    function installLine() {
        if (installStage === "prepare")
            return "Preparing the disk."
        if (installStage === "copy")
            return "Copying WASD."
        if (installStage === "account")
            return "Setting up your account."
        if (installStage === "boot")
            return "Installing the bootloader."
        if (installStage === "done")
            return "You can remove the USB stick. Press Enter to restart."
        if (installStage === "failed")
            return savedLine
        return ""
    }

    function applyInstallLine(text) {
        const line = String(text || "").replace(/\s+/g, " ").trim()
        const next = stageForLine(line)
        if (!next || installStage === "failed" || installStage === "done")
            return false
        if (installStage !== "" && stageRank(next) < stageRank(installStage))
            return false
        installStage = next
        if ((" " + stagesSeen + " ").indexOf(" " + next + " ") < 0)
            stagesSeen = stagesSeen ? stagesSeen + " " + next : next
        erasing = true
        savedLine = installLine()
        return true
    }

    function noteInstall(text) {
        const lines = String(text || "").split("\n")
        let moved = false
        for (let i = 0; i < lines.length; i++) {
            if (applyInstallLine(lines[i]))
                moved = true
        }
        return moved
    }

    function stageSeen(stage) {
        return (" " + stagesSeen + " ").indexOf(" " + stage + " ") >= 0
    }

    function beginInstallStatus() {
        installStage = "prepare"
        stagesSeen = "prepare"
        erasing = true
        restartSent = false
        savedLine = installLine()
        confirmNo()
    }

    function failInstall(text) {
        if (installStage === "done")
            return
        const line = String(text || "").replace(/\s+/g, " ").trim()
        if (!line || line.indexOf("Traceback") >= 0 || line.indexOf("File \"") >= 0)
            savedLine = "Nothing was erased."
        else
            savedLine = line.length > 160 ? line.slice(0, 160) : line
        installStage = "failed"
        erasing = false
    }

    function restartNow() {
        if (!restartReady || restartSent)
            return
        restartSent = true
        restartAsked = true
        if (!liveSession || !liveLoader.item)
            return
        liveLoader.item.restart()
    }

    function confirmYes() {
        if (confirmStep < 1)
            return
        const start = confirmStartsInstall && confirmAction === "system"
        applyConfirm()
        confirmStep = 0
        confirmAction = ""
        confirmStartsInstall = false
        if (start)
            saveChoices()
    }

    function applyConfirm() {
        const index = confirmIndex
        if (index < 0 || index >= disks.count)
            return
        const row = disks.get(index)
        if (confirmAction === "system") {
            removeWipe(row)
            if (gamesDiskIndex === index)
                clearGames()
            diskIndex = index
            systemConfirmed = true
            return
        }
        if (confirmAction === "gamesWipe" || confirmAction === "gamesKeep") {
            if (confirmAction === "gamesKeep" && !canKeep(index))
                return
            removeWipe(row)
            if (diskIndex === index)
                diskIndex = -1
            gamesMode = confirmAction === "gamesKeep" ? "keep" : "format"
            gamesDiskIndex = index
            gamesConfirmed = true
            return
        }
        if (confirmAction === "leave") {
            if (diskIndex === index)
                diskIndex = -1
            if (gamesDiskIndex === index)
                clearGames()
            addWipe(row)
        }
    }

    function confirmTitle() {
        if (confirmIndex < 0 || confirmIndex >= disks.count)
            return ""
        const row = disks.get(confirmIndex)
        if (row.windows && confirmAction === "system")
            return "This erases Windows."
        if (row.windows)
            return "Windows is on this drive."
        if (confirmAction === "gamesKeep")
            return "Use this drive for games?"
        if (confirmAction === "gamesWipe")
            return "Wipe this drive and use it for games?"
        if (confirmAction === "leave")
            return "Wipe this drive and leave it empty?"
        return "This drive will be wiped."
    }

    function confirmBody() {
        if (confirmIndex < 0 || confirmIndex >= disks.count)
            return ""
        if (confirmAction === "gamesKeep")
            return "WASD will use this drive and will not erase it. Are you sure?"
        if (confirmAction === "leave")
            return "The files will be deleted. WASD will not install here and will not use it for games. Are you sure?"
        if (confirmAction === "gamesWipe")
            return "Everything on it will be deleted. The drive is named games and mounted at /games. Are you sure?"
        return "Everything on it will be deleted. Are you sure?"
    }

    function installOrConfirm() {
        if (installBlocked || diskIndex < 0 || erasing)
            return
        if (!systemConfirmed) {
            beginConfirm("system", diskIndex, true)
            return
        }
        saveChoices()
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
            if (gamesConfirmed)
                games.confirmed = true
            payload.games = games
        }
        const wipe = []
        for (let w = 0; w < wipeDrives.length; w++) {
            const item = wipeDrives[w]
            if (/^(nvme[0-9]+n[0-9]+|sd[a-z]+|vd[a-z]+|mmcblk[0-9]+|hd[a-z]+)$/.test(item.device || ""))
                wipe.push({ device: item.device, disk: item.disk, confirmed: true })
        }
        if (wipe.length)
            payload.wipe = wipe
        const savedWifi = wifiChoice()
        if (savedWifi)
            payload.wifi = savedWifi
        const savedTcp = tcpChoice()
        if (savedTcp)
            payload.tcp = savedTcp
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
        beginInstallStatus()
        liveLoader.item.erase(utf8Base64(choicesJson()))
    }

    function applyLive(payload) {
        const data = JSON.parse(payload)
        warnings = data.warnings || []
        installBlocked = !!data.blocked
        clearGames()
        gamesOpen = false
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
        actionIndex = pick
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
        interval: 3000
        repeat: true
        running: win.liveSession && win.installStage === ""
        onTriggered: win.refreshNetwork(false)
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
    onDiskIndexChanged: {
        systemConfirmed = false
        reconcileGames()
    }

    Component.onCompleted: boot()

    Rectangle {
        id: shell
        objectName: "shell"
        anchors.fill: parent
        color: win.bg
        border.color: Qt.rgba(1, 1, 1, 0.08)
        border.width: 1

        Rectangle {
            id: titlebar
            height: 38
            anchors.left: parent.left
            anchors.right: parent.right
            color: win.titlebar

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
                border.color: Qt.rgba(1, 1, 1, 0.28)
                border.width: 1

                MouseArea {
                    anchors.fill: parent
                    enabled: win.installStage === "" || win.installStage === "failed" || win.installStage === "done"
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
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
                        id: step
                        required property string modelData
                        required property int index
                        width: parent.width
                        height: 40
                        radius: 10
                        color: win.page === index ? win.navOn : (stepArea.containsMouse ? Qt.rgba(1, 1, 1, 0.06) : "transparent")
                        antialiasing: true

                        Text {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            verticalAlignment: Text.AlignVCenter
                            text: modelData
                            color: win.page === index ? win.ink : win.muted
                            font.family: win.bodyFont
                            font.pixelSize: 16
                            font.bold: win.page === index
                        }

                        MouseArea {
                            id: stepArea
                            anchors.fill: parent
                            enabled: !win.erasing
                            hoverEnabled: true
                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: win.showPage(index)
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
                sourceComponent: win.installStage !== "" ? statusComp : win.page === 0 ? userComp : win.page === 1 ? lookComp : win.page === 2 ? appsComp : win.page === 3 ? systemComp : diskComp
            }
        }
    }

    Shortcut {
        sequence: "Return"
        enabled: win.restartReady
        onActivated: win.restartNow()
    }

    Shortcut {
        sequence: "Enter"
        enabled: win.restartReady
        onActivated: win.restartNow()
    }

    Component {
        id: statusComp
        InstallStatus { host: win }
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
        function onStatusLine(line) {
            if (win.installStage === "done" || win.installStage === "failed")
                return
            const text = (line || "").replace(/\s+/g, " ").trim()
            if (!text)
                return
            if (
                text.indexOf("Nothing was erased.") >= 0
                || text === "The disk was erased. The install did not finish."
                || text.indexOf("The games partition was not created.") >= 0
                || text.indexOf("The account was not set up.") >= 0
                || text.indexOf("The installed apps were not copied.") >= 0
                || text.indexOf("Later updates were not pointed at WASD.") >= 0
                || text.indexOf("The security labels were not restored.") >= 0
            ) {
                win.failInstall(text)
                return
            }
            win.noteInstall(text)
        }
        function onEraseFinished(code, line) {
            if (win.installStage === "done")
                return
            win.noteInstall(line || "")
            if (code === 0 && win.installStage === "done")
                return
            if (win.installStage === "failed")
                return
            const text = (line || "").replace(/\s+/g, " ").trim()
            if (code === 0)
                win.failInstall(text || "The installer finished.")
            else
                win.failInstall(text)
        }
    }
}
