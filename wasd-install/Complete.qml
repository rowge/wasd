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
    property string wifiDraft: ""
    property string wifiError: ""
    property string wifiName: ""
    property string wifiSecurity: ""
    property bool wantWifi: false
    property bool wantEthernet: false
    property bool connectingWifi: false
    property bool wifiWarn: false
    property bool applyingEthernet: false
    property bool ethernetStarted: false
    property bool wantApps: false
    property bool wantAgents: false
    property bool lookHold: false
    property bool lookBusy: false
    property bool lookDone: false
    property bool agentsHold: false
    property bool agentsBusy: false
    property bool agentsStarted: false
    property bool appsStarted: false
    property string failKind: ""
    property string netResume: "apps"
    property bool appsHold: false
    property bool appsBusy: false
    property string failedApp: ""
    property string netSsid: ""
    property string netSecurity: ""
    property bool netHidden: false
    property string netPass: ""
    property string netError: ""
    property bool netBusy: false
    property string netMode: "auto"
    property string netDevice: ""
    property string netKind: ""
    property string netAddress: ""
    property string netNetmask: ""
    property string netGateway: ""
    property string netDns: ""
    property var netNetworks: []
    property var netDevices: []
    property string workNote: ""
    readonly property string appsFailTitle: failKind === "look"
            ? (failedApp.length > 0 ? failedApp : "The desktop was not set.")
            : (failedApp === "That app was refused." ? failedApp : failedApp + " did not install.")
    readonly property string appsFailBody: failKind === "look"
            ? "Retry tries again."
            : "Retry tries again. Continue leaves this one out and goes on."
    readonly property string wifiLead: "Connect to " + (wifiName || "the network you chose") + "."
    readonly property string wifiWarnTitle: "Continue without connecting?"
    readonly property string wifiWarnBody: "If you are not connected, you will not be able to install the applications you selected during installation."

    readonly property color bg: "#14161a"
    readonly property color titlebar: "#101114"
    readonly property color card: "#22252b"
    readonly property color ink: "#f4f2ee"
    readonly property color muted: "#a9a59e"
    readonly property color brass: "#7aa2ff"
    readonly property color button: "#f4f2ee"
    readonly property color buttonInk: "#16181c"
    readonly property color danger: "#ff5c5c"
    readonly property color line: Qt.rgba(1, 1, 1, 0.12)
    property var lines: [
        "Setting the desktop.",
        "Installing what you checked.",
        "Finishing up."
    ]

    function refreshLines() {
        const rows = ["Setting the desktop."]
        if (wantAgents)
            rows.push("Installing the agents.")
        rows.push("Installing what you checked.")
        rows.push("Finishing up.")
        lines = rows
    }
    readonly property string status: lines[Math.min(stepIndex, lines.length - 1)]
    readonly property bool showAppTerm: phase === "work" && status === "Installing what you checked."
    property string appOutput: ""
    property string monoFont: "monospace"

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
        let wifi = argValue("--want-wifi") === "1"
        let ethernet = argValue("--want-ethernet") === "1"
        let apps = argValue("--want-apps") === "1"
        let agents = argValue("--want-agents") === "1"
        let ssid = argValue("--wifi-ssid")
        let security = argValue("--wifi-security")
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
        try {
            if (typeof WasdWantWifi !== "undefined" && WasdWantWifi)
                wifi = true
        } catch (e) {
        }
        try {
            if (typeof WasdWantEthernet !== "undefined" && WasdWantEthernet)
                ethernet = true
        } catch (e) {
        }
        try {
            if (typeof WasdWantApps !== "undefined" && WasdWantApps)
                apps = true
        } catch (e) {
        }
        try {
            if (typeof WasdWantAgents !== "undefined" && WasdWantAgents)
                agents = true
        } catch (e) {
        }
        try {
            if (typeof WasdWifiSet !== "undefined" && WasdWifiSet)
                wifi = false
        } catch (e) {
        }
        try {
            if (typeof WasdWifiSsid !== "undefined" && WasdWifiSsid)
                ssid = WasdWifiSsid
        } catch (e) {
        }
        try {
            if (typeof WasdWifiSecurity !== "undefined" && WasdWifiSecurity)
                security = WasdWifiSecurity
        } catch (e) {
        }
        wantWifi = wifi
        wantEthernet = ethernet
        wantApps = apps
        wantAgents = agents
        refreshLines()
        wifiName = ssid
        wifiSecurity = security
        bodyFont = pickFont(["Segoe UI", "Liberation Sans", "Noto Sans", "DejaVu Sans"], bodyFont)
        monoFont = pickFont(["Liberation Mono", "DejaVu Sans Mono", "Noto Sans Mono"], monoFont)
        if (want)
            phase = "password"
        else if (wifi)
            phase = "wifi"
        else
            enterWork()
    }

    function enterWork() {
        phase = "work"
        stepIndex = 0
        if (ethernetStarted || !wantEthernet || preview || helperPort <= 0)
            return
        ethernetStarted = true
        applyingEthernet = true
        const xhr = new XMLHttpRequest()
        xhr.timeout = 30000
        xhr.open("POST", "http://127.0.0.1:" + helperPort + "/tcp")
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE)
                return
            win.applyingEthernet = false
            if (xhr.status === 200) {
                const detail = (xhr.responseText || "").trim()
                win.workNote = detail && detail !== "ok" ? detail : ""
                return
            }
            const detail = (xhr.responseText || "").trim()
            win.workNote = detail || "Those settings were not used."
        }
        xhr.onerror = function() {
            win.applyingEthernet = false
            win.workNote = "Those settings were not used."
        }
        xhr.ontimeout = function() {
            win.applyingEthernet = false
            win.workNote = "Those settings were not used."
        }
        xhr.send("")
    }

    function advance() {
        if (wantWifi) {
            phase = "wifi"
            return
        }
        enterWork()
    }

    function passphraseProblem(value) {
        if (value.indexOf("\n") >= 0)
            return "That passphrase cannot be used."
        const security = (wifiSecurity || "").trim().toLowerCase()
        const open = security === "" || security === "--" || security === "open" || security === "none"
        if (!open && !value)
            return "Type the passphrase."
        if (value && (value.length < 8 || value.length > 63))
            return "A passphrase is 8 to 63 characters, or empty for an open network."
        return ""
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
            advance()
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
                win.advance()
                return
            }
            const detail = (xhr.responseText || "").trim()
            win.passwordError = detail || "The password was not set."
        }
        xhr.send(first)
    }

    function confirmWifi() {
        const value = wifiDraft
        const problem = passphraseProblem(value)
        if (problem) {
            wifiError = problem
            return
        }
        wifiDraft = ""
        wifiField.text = ""
        wifiError = ""
        if (preview || helperPort <= 0) {
            enterWork()
            return
        }
        connectingWifi = true
        const xhr = new XMLHttpRequest()
        xhr.open("POST", "http://127.0.0.1:" + helperPort + "/wifi")
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE)
                return
            win.connectingWifi = false
            if (xhr.status === 200) {
                win.enterWork()
                return
            }
            const detail = (xhr.responseText || "").trim()
            win.wifiError = detail || "Could not connect."
        }
        xhr.send(value)
    }

    function cancelWifi() {
        if (connectingWifi)
            return
        wifiWarn = true
    }

    function dismissWifiWarn() {
        wifiWarn = false
    }

    function continueWithoutWifi() {
        wifiWarn = false
        wifiDraft = ""
        wifiField.text = ""
        wifiError = ""
        wantWifi = false
        if (preview || helperPort <= 0) {
            enterWork()
            return
        }
        connectingWifi = true
        const xhr = new XMLHttpRequest()
        xhr.open("POST", "http://127.0.0.1:" + helperPort + "/wifi/skip")
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE)
                return
            win.connectingWifi = false
            if (xhr.status === 200) {
                win.enterWork()
                return
            }
            win.wantWifi = true
            win.phase = "wifi"
            const detail = (xhr.responseText || "").trim()
            win.wifiError = detail || "Could not continue."
        }
        xhr.send("")
    }

    function postApps(path, body, done) {
        const xhr = new XMLHttpRequest()
        xhr.timeout = path === "/apps/install" || path === "/apps/retry" || path === "/agents/install" || path === "/agents/retry" || path === "/look/apply" ? 0 : 30000
        xhr.open("POST", "http://127.0.0.1:" + helperPort + path)
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE)
                return
            done(xhr)
        }
        xhr.onerror = function() {
            done(xhr)
        }
        xhr.ontimeout = function() {
            done(xhr)
        }
        xhr.send(body)
    }

    function beginApps() {
        if (preview || helperPort <= 0) {
            appsHold = false
            return
        }
        appsStarted = true
        netResume = "apps"
        failKind = "apps"
        appsHold = true
        appsBusy = true
        failedApp = ""
        postApps("/apps/check", "", function(xhr) {
            win.appsBusy = false
            if (xhr.status !== 200) {
                win.failedApp = (xhr.responseText || "Could not install that app.").trim()
                return
            }
            const text = (xhr.responseText || "").trim()
            if (text === "none") {
                win.appsHold = false
                win.wantApps = false
                return
            }
            if (text === "offline") {
                win.phase = "net"
                win.loadNet()
                return
            }
            if (text === "online") {
                win.installNext()
                return
            }
            const split = text.indexOf("\n")
            if (text.indexOf("bad\n") === 0 && split > 0) {
                win.failedApp = text.slice(split + 1)
                return
            }
            win.failedApp = text || "Could not install that app."
        })
    }

    function installNext() {
        if (preview || helperPort <= 0)
            return
        appsBusy = true
        failedApp = ""
        phase = "work"
        postApps("/apps/install", "", function(xhr) {
            win.handleInstall(xhr)
        })
    }

    function handleInstall(xhr) {
        appsBusy = false
        if (xhr.status !== 200) {
            failedApp = (xhr.responseText || "Could not install that app.").trim()
            return
        }
        const text = (xhr.responseText || "").trim()
        if (text === "done") {
            appsHold = false
            failedApp = ""
            return
        }
        if (text === "next") {
            installNext()
            return
        }
        if (text === "offline") {
            phase = "net"
            netResume = "apps"
            loadNet()
            return
        }
        const split = text.indexOf("\n")
        if (split > 0 && (text.indexOf("fail\n") === 0 || text.indexOf("bad\n") === 0)) {
            failedApp = text.slice(split + 1)
            return
        }
        failedApp = text || "Could not install that app."
    }

    function retryApp() {
        if (appsBusy || preview || helperPort <= 0)
            return
        appsBusy = true
        postApps("/apps/retry", "", function(xhr) {
            win.handleInstall(xhr)
        })
    }

    function continueApp() {
        if (appsBusy || preview || helperPort <= 0)
            return
        appsBusy = true
        failedApp = ""
        postApps("/apps/continue", "", function(xhr) {
            win.appsBusy = false
            if (xhr.status !== 200) {
                win.failedApp = (xhr.responseText || "Could not continue.").trim()
                return
            }
            const text = (xhr.responseText || "").trim()
            if (text === "next") {
                win.installNext()
                return
            }
            win.handleInstall(xhr)
        })
    }

    function loadNet() {
        netError = ""
        if (wifiName && !netSsid) {
            netSsid = wifiName
            netField.text = wifiName
        }
        if (preview || helperPort <= 0)
            return
        postApps("/apps/list", "", function(xhr) {
            if (xhr.status !== 200)
                return
            try {
                const data = JSON.parse(xhr.responseText || "{}")
                win.netNetworks = data.networks || []
                win.netDevices = data.devices || []
            } catch (e) {
            }
        })
    }

    function chooseNet(name, security) {
        if (netSsid === name) {
            netSsid = ""
            netSecurity = ""
            netHidden = false
            netField.text = ""
            return
        }
        netSsid = name
        netSecurity = security || ""
        netHidden = false
        netField.text = name
    }

    function chooseNetAdapter(device, kind) {
        if (netDevice === device) {
            netDevice = ""
            netKind = ""
            return
        }
        netDevice = device
        netKind = kind || ""
    }

    function ipv4Ok(value) {
        const parts = value.split(".")
        if (parts.length !== 4)
            return false
        for (let i = 0; i < 4; i++) {
            const part = parts[i]
            if (!/^\d+$/.test(part) || (part.length > 1 && part.charAt(0) === "0") || parseInt(part, 10) > 255)
                return false
        }
        return true
    }

    function netPassProblem(value, security) {
        if (value.indexOf("\n") >= 0)
            return "That passphrase cannot be used."
        const text = (security || "").trim().toLowerCase()
        const open = text === "" || text === "--" || text === "open" || text === "none"
        if (!open && !value)
            return "Type the passphrase."
        if (value && (value.length < 8 || value.length > 63))
            return "A passphrase is 8 to 63 characters, or empty for an open network."
        return ""
    }

    function connectNet() {
        if (netBusy)
            return
        const ssid = netSsid.trim()
        const manual = netMode === "manual"
        let tcp = null
        if (manual) {
            if (!netAddress.trim() || !netNetmask.trim() || !netGateway.trim() || !netDns.trim() || !netDevice)
                netError = "Fill in the address, netmask, gateway, DNS, and choose an adapter."
            else if (!ipv4Ok(netAddress.trim()))
                netError = "Use an IP address like 192.168.1.20."
            else if (!ipv4Ok(netNetmask.trim()) || !ipv4Ok(netGateway.trim()))
                netError = "Use an address, a netmask, and a gateway."
            else if (netKind !== "wifi" && netKind !== "ethernet")
                netError = "Choose an adapter."
            else if (netKind === "wifi" && !ssid)
                netError = "Type the network name."
            else {
                netError = ""
                tcp = {
                    mode: "manual",
                    interface: netDevice,
                    kind: netKind,
                    address: netAddress.trim(),
                    netmask: netNetmask.trim(),
                    gateway: netGateway.trim(),
                    dns: netDns.trim()
                }
            }
            if (netError)
                return
        }
        if (!ssid && !(tcp && tcp.kind === "ethernet")) {
            netError = "Choose a Wi-Fi network or set an address."
            return
        }
        let security = netSecurity
        let hidden = netHidden
        if (ssid) {
            let found = false
            for (let i = 0; i < netNetworks.length; i++) {
                if (netNetworks[i].ssid === ssid) {
                    security = netNetworks[i].security || ""
                    hidden = false
                    found = true
                    break
                }
            }
            if (!found) {
                security = ""
                hidden = true
            }
        }
        const problem = ssid ? netPassProblem(netPass, security) : ""
        if (problem) {
            netError = problem
            return
        }
        const pick = { ssid: ssid, security: security, hidden: hidden }
        if (tcp && (!ssid || tcp.kind === "wifi" || tcp.kind === "ethernet"))
            pick.tcp = tcp
        const secret = netPass
        netPass = ""
        netPassField.text = ""
        netError = ""
        if (preview || helperPort <= 0) {
            phase = "work"
            appsHold = false
            return
        }
        netBusy = true
        postApps("/apps/pick", JSON.stringify(pick), function(xhr) {
            if (xhr.status !== 200) {
                win.netBusy = false
                win.netError = (xhr.responseText || "Could not connect.").trim()
                return
            }
            const path = ssid ? "/apps/connect" : "/apps/address"
            const body = ssid ? secret : ""
            win.postApps(path, body, function(next) {
                win.netBusy = false
                if (next.status !== 200) {
                    win.netError = (next.responseText || "Could not connect.").trim()
                    return
                }
                win.phase = "work"
                if (win.netResume === "agents")
                    win.installNextAgent()
                else
                    win.installNext()
            })
        })
    }

    function skipApps() {
        if (netBusy)
            return
        netPass = ""
        netPassField.text = ""
        netError = ""
        if (preview || helperPort <= 0) {
            phase = "work"
            appsHold = false
            agentsHold = false
            wantApps = false
            return
        }
        netBusy = true
        const skippingAgents = netResume === "agents"
        postApps(skippingAgents ? "/agents/skip" : "/apps/skip", "", function(xhr) {
            win.netBusy = false
            if (xhr.status !== 200) {
                win.netError = (xhr.responseText || "Could not continue.").trim()
                return
            }
            win.phase = "work"
            win.failedApp = ""
            if (skippingAgents) {
                win.agentsHold = false
                win.agentsBusy = false
                return
            }
            win.appsHold = false
            win.wantApps = false
        })
    }

    function afterLook() {
        lookDone = true
        lookHold = false
        lookBusy = false
        failedApp = ""
        failKind = ""
        if (wantAgents) {
            stepIndex = 1
            beginAgents()
            return
        }
        if (wantApps) {
            stepIndex = 1
            beginApps()
        }
    }

    function applyLook() {
        if (lookBusy || lookDone || preview || helperPort <= 0)
            return
        lookBusy = true
        lookHold = true
        failedApp = ""
        failKind = ""
        postApps("/look/apply", "", function(xhr) {
            win.lookBusy = false
            if (xhr.status === 200) {
                win.afterLook()
                return
            }
            win.lookHold = true
            win.failKind = "look"
            win.failedApp = (xhr.responseText || "The desktop was not set.").trim()
        })
    }

    function beginAgents() {
        if (preview || helperPort <= 0) {
            agentsHold = false
            return
        }
        agentsStarted = true
        agentsHold = true
        agentsBusy = true
        failedApp = ""
        failKind = "agents"
        netResume = "agents"
        postApps("/agents/check", "", function(xhr) {
            win.agentsBusy = false
            if (xhr.status !== 200) {
                win.failKind = "agents"
                win.failedApp = (xhr.responseText || "Could not install that agent.").trim()
                return
            }
            const text = (xhr.responseText || "").trim()
            if (text === "none") {
                win.agentsHold = false
                return
            }
            if (text === "offline") {
                win.phase = "net"
                win.loadNet()
                return
            }
            if (text === "online") {
                win.installNextAgent()
                return
            }
            win.failKind = "agents"
            win.failedApp = text || "Could not install that agent."
        })
    }

    function installNextAgent() {
        if (preview || helperPort <= 0)
            return
        agentsBusy = true
        failedApp = ""
        phase = "work"
        postApps("/agents/install", "", function(xhr) {
            win.handleAgent(xhr)
        })
    }

    function handleAgent(xhr) {
        agentsBusy = false
        if (xhr.status !== 200) {
            failKind = "agents"
            failedApp = (xhr.responseText || "Could not install that agent.").trim()
            return
        }
        const text = (xhr.responseText || "").trim()
        if (text === "done") {
            agentsHold = false
            failedApp = ""
            return
        }
        if (text === "next") {
            installNextAgent()
            return
        }
        if (text === "offline") {
            phase = "net"
            netResume = "agents"
            loadNet()
            return
        }
        const split = text.indexOf("\n")
        if (split > 0 && text.indexOf("fail\n") === 0) {
            failKind = "agents"
            failedApp = text.slice(split + 1)
            return
        }
        failKind = "agents"
        failedApp = text || "Could not install that agent."
    }

    function retryAgent() {
        if (agentsBusy || preview || helperPort <= 0)
            return
        agentsBusy = true
        postApps("/agents/retry", "", function(xhr) {
            win.handleAgent(xhr)
        })
    }

    function continueAgent() {
        if (agentsBusy || preview || helperPort <= 0)
            return
        agentsBusy = true
        failedApp = ""
        postApps("/agents/continue", "", function(xhr) {
            win.agentsBusy = false
            if (xhr.status !== 200) {
                win.failKind = "agents"
                win.failedApp = (xhr.responseText || "Could not continue.").trim()
                return
            }
            win.handleAgent(xhr)
        })
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

    function pollAppOutput() {
        if (!showAppTerm || preview || helperPort <= 0)
            return
        const xhr = new XMLHttpRequest()
        xhr.open("GET", "http://127.0.0.1:" + helperPort + "/output")
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE)
                return
            if (xhr.status === 200)
                win.appOutput = xhr.responseText || ""
        }
        xhr.send()
    }

    Timer {
        interval: 2400
        running: win.phase === "work" && !win.hold && !win.applyingEthernet && !win.appsHold && !win.appsBusy && !win.lookHold && !win.lookBusy && !win.agentsHold && !win.agentsBusy && win.failedApp.length === 0
        repeat: true
        onTriggered: {
            if (win.stepIndex === 0 && !win.lookDone && !win.preview && win.helperPort > 0) {
                win.applyLook()
                return
            }
            if (win.wantAgents && win.stepIndex === 1 && !win.agentsStarted && !win.preview && win.helperPort > 0) {
                win.beginAgents()
                return
            }
            const appsAt = win.wantAgents ? 2 : 1
            if (win.wantApps && win.stepIndex === appsAt && !win.appsStarted && !win.preview && win.helperPort > 0) {
                win.beginApps()
                return
            }
            if (win.stepIndex >= win.lines.length - 1) {
                win.finish()
                return
            }
            win.stepIndex = win.stepIndex + 1
        }
    }

    Timer {
        interval: 400
        repeat: true
        running: win.showAppTerm && !win.preview && win.helperPort > 0
        triggeredOnStart: true
        onTriggered: win.pollAppOutput()
    }

    Component.onCompleted: boot()

    Rectangle {
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
                radius: 8
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
                    selectedTextColor: win.buttonInk
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
                radius: 8
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
                    selectedTextColor: win.buttonInk
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
                radius: 9
                enabled: !win.settingPassword
                color: enabled ? win.button : Qt.rgba(244 / 255, 242 / 255, 238 / 255, 0.35)
                antialiasing: true

                Text {
                    id: setLabel
                    anchors.centerIn: parent
                    text: win.settingPassword ? "Setting the password." : "Set password"
                    color: win.buttonInk
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
            visible: win.phase === "wifi"
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
                wrapMode: Text.WordWrap
                text: win.wifiLead
                color: win.ink
                font.family: win.bodyFont
                font.pixelSize: 28
            }

            Text {
                width: parent.width
                topPadding: 8
                bottomPadding: 16
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: "Leave this empty for an open network."
                color: win.muted
                font.family: win.bodyFont
                font.pixelSize: 14
            }

            Rectangle {
                width: parent.width
                height: 48
                color: Qt.rgba(0, 0, 0, 0.28)
                radius: 8
                border.width: 1
                border.color: win.line

                TextInput {
                    id: wifiField
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
                    selectedTextColor: win.buttonInk
                    onTextEdited: win.wifiDraft = text
                }
            }

            Text {
                width: parent.width
                visible: win.wifiError.length > 0
                topPadding: 8
                wrapMode: Text.WordWrap
                text: win.wifiError
                color: win.danger
                font.family: win.bodyFont
                font.pixelSize: 16
            }

            Item {
                width: 1
                height: 18
            }

            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 14

                Rectangle {
                    width: connectLabel.implicitWidth + 36
                    height: 44
                    radius: 9
                    enabled: !win.connectingWifi
                    color: enabled ? win.button : Qt.rgba(244 / 255, 242 / 255, 238 / 255, 0.35)
                    antialiasing: true

                    Text {
                        id: connectLabel
                        anchors.centerIn: parent
                        text: win.connectingWifi ? "Connecting." : "Connect"
                        color: win.buttonInk
                        font.family: win.bodyFont
                        font.pixelSize: 16
                        font.bold: true
                    }

                    MouseArea {
                        anchors.fill: parent
                        enabled: !win.connectingWifi
                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: win.confirmWifi()
                    }
                }

                Rectangle {
                    width: cancelLabel.implicitWidth + 36
                    height: 44
                    radius: 9
                    enabled: !win.connectingWifi
                    color: "transparent"
                    border.width: 1
                    border.color: win.line
                    antialiasing: true

                    Text {
                        id: cancelLabel
                        anchors.centerIn: parent
                        text: "Cancel"
                        color: win.ink
                        font.family: win.bodyFont
                        font.pixelSize: 16
                    }

                    MouseArea {
                        anchors.fill: parent
                        enabled: !win.connectingWifi
                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: win.cancelWifi()
                    }
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
                objectName: "workSpinner"
                anchors.horizontalCenter: parent.horizontalCenter
                visible: !win.showAppTerm
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
                    running: win.phase === "work" && !win.showAppTerm
                }
            }

            Rectangle {
                id: appTerm
                objectName: "appTerm"
                visible: win.showAppTerm
                anchors.horizontalCenter: parent.horizontalCenter
                width: parent.width
                height: 176
                radius: 9
                color: win.titlebar
                clip: true

                Flickable {
                    id: appTermFlick
                    anchors.fill: parent
                    anchors.margins: 14
                    contentWidth: width
                    contentHeight: appTermText.implicitHeight
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    onContentHeightChanged: contentY = Math.max(0, contentHeight - height)

                    Text {
                        id: appTermText
                        objectName: "appTermText"
                        width: appTermFlick.width
                        text: win.appOutput.length > 0 ? win.appOutput : "Waiting for the install."
                        color: win.ink
                        font.family: win.monoFont
                        font.pixelSize: 13
                        wrapMode: Text.Wrap
                    }
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

            Text {
                width: parent.width
                visible: win.workNote.length > 0
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: win.workNote
                color: win.workNote === "Saved for this adapter. It is not connected yet." ? win.muted : win.danger
                font.family: win.bodyFont
                font.pixelSize: 16
            }
        }

        Flickable {
            visible: win.phase === "net"
            anchors.top: titlebar.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.margins: 28
            clip: true
            contentWidth: width
            contentHeight: netColumn.implicitHeight
            boundsBehavior: Flickable.StopAtBounds

            Column {
                id: netColumn
                width: parent.width
                spacing: 12

                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: "There is no connection."
                    color: win.ink
                    font.family: win.bodyFont
                    font.pixelSize: 26
                }

                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: "The apps you checked are downloaded now. Choose a Wi-Fi network, or set an address, a netmask, a gateway, and DNS. You can skip this and add the apps later."
                    color: win.muted
                    font.family: win.bodyFont
                    font.pixelSize: 15
                }

                Text {
                    width: parent.width
                    visible: win.netNetworks.length === 0
                    wrapMode: Text.WordWrap
                    text: "No networks were found. Type a network name."
                    color: win.muted
                    font.family: win.bodyFont
                    font.pixelSize: 14
                }

                Repeater {
                    model: win.netNetworks
                    delegate: Rectangle {
                        required property var modelData
                        width: netColumn.width
                        height: 44
                        color: Qt.rgba(0, 0, 0, 0.18)
                        border.width: 1
                        border.color: win.netSsid === modelData.ssid ? win.brass : win.line

                        Text {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.margins: 14
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.ssid
                            color: win.ink
                            font.family: win.bodyFont
                            font.pixelSize: 16
                            elide: Text.ElideRight
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: win.chooseNet(modelData.ssid, modelData.security)
                        }
                    }
                }

                Rectangle {
                    width: Math.min(420, parent.width)
                    height: 44
                    color: Qt.rgba(0, 0, 0, 0.28)
                    radius: 8
                    border.width: 1
                    border.color: win.line

                    TextInput {
                        id: netField
                        anchors.fill: parent
                        anchors.leftMargin: 14
                        anchors.rightMargin: 14
                        verticalAlignment: TextInput.AlignVCenter
                        color: win.ink
                        font.pixelSize: 16
                        font.family: win.bodyFont
                        selectByMouse: true
                        clip: true
                        selectionColor: win.brass
                        selectedTextColor: win.buttonInk
                        Text {
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            visible: parent.text.length === 0
                            text: "Network name"
                            color: win.muted
                            font.family: win.bodyFont
                            font.pixelSize: 16
                        }
                        onTextEdited: {
                            win.netSsid = text
                            win.netSecurity = ""
                            win.netHidden = false
                        }
                    }
                }

                Rectangle {
                    width: Math.min(420, parent.width)
                    height: 44
                    color: Qt.rgba(0, 0, 0, 0.28)
                    radius: 8
                    border.width: 1
                    border.color: win.line

                    TextInput {
                        id: netPassField
                        anchors.fill: parent
                        anchors.leftMargin: 14
                        anchors.rightMargin: 14
                        verticalAlignment: TextInput.AlignVCenter
                        echoMode: TextInput.Password
                        color: win.ink
                        font.pixelSize: 16
                        font.family: win.bodyFont
                        selectByMouse: true
                        clip: true
                        selectionColor: win.brass
                        selectedTextColor: win.buttonInk
                        Text {
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            visible: parent.text.length === 0 && parent.echoMode === TextInput.Password
                            text: "Passphrase"
                            color: win.muted
                            font.family: win.bodyFont
                            font.pixelSize: 16
                        }
                        onTextEdited: win.netPass = text
                    }
                }

                Text {
                    text: "TCP/IP"
                    color: win.ink
                    font.family: win.bodyFont
                    font.pixelSize: 18
                }

                Row {
                    spacing: 22

                    Repeater {
                        model: [
                            { key: "auto", label: "Automatic" },
                            { key: "manual", label: "Manual" }
                        ]
                        delegate: Item {
                            required property var modelData
                            width: modeDot.width + modeLabel.implicitWidth + 10
                            height: 24

                            Rectangle {
                                id: modeDot
                                width: 16
                                height: 16
                                radius: 8
                                anchors.verticalCenter: parent.verticalCenter
                                color: "transparent"
                                border.width: 2
                                border.color: win.netMode === modelData.key ? win.brass : win.muted

                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 8
                                    height: 8
                                    radius: 4
                                    color: win.brass
                                    visible: win.netMode === modelData.key
                                }
                            }

                            Text {
                                id: modeLabel
                                anchors.left: modeDot.right
                                anchors.leftMargin: 8
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.label
                                color: win.ink
                                font.family: win.bodyFont
                                font.pixelSize: 16
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: win.netMode = modelData.key
                            }
                        }
                    }
                }

                Column {
                    width: parent.width
                    visible: win.netMode === "manual"
                    spacing: 8

                    Text {
                        width: parent.width
                        visible: win.netDevices.length === 0
                        wrapMode: Text.WordWrap
                        text: "No network adapters were found."
                        color: win.muted
                        font.family: win.bodyFont
                        font.pixelSize: 14
                    }

                    Repeater {
                        model: win.netDevices
                        delegate: Rectangle {
                            required property var modelData
                            width: netColumn.width
                            height: 44
                            color: Qt.rgba(0, 0, 0, 0.18)
                            border.width: 1
                            border.color: win.netDevice === modelData.device ? win.brass : win.line

                            Text {
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                anchors.rightMargin: 14
                                verticalAlignment: Text.AlignVCenter
                                text: modelData.label + "  " + modelData.device
                                color: win.ink
                                font.family: win.bodyFont
                                font.pixelSize: 16
                                elide: Text.ElideRight
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: win.chooseNetAdapter(modelData.device, modelData.kind)
                            }
                        }
                    }

                    Repeater {
                        model: [
                            { key: "address", label: "IP address" },
                            { key: "netmask", label: "Netmask" },
                            { key: "gateway", label: "Gateway" },
                            { key: "dns", label: "DNS" }
                        ]
                        delegate: Rectangle {
                            required property var modelData
                            width: Math.min(420, netColumn.width)
                            height: 44
                            color: Qt.rgba(0, 0, 0, 0.28)
                            radius: 8
                            border.width: 1
                            border.color: win.line

                            TextInput {
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                anchors.rightMargin: 14
                                verticalAlignment: TextInput.AlignVCenter
                                color: win.ink
                                font.pixelSize: 16
                                font.family: win.bodyFont
                                selectByMouse: true
                                clip: true
                                selectionColor: win.brass
                                selectedTextColor: win.buttonInk
                                Text {
                                    anchors.left: parent.left
                                    anchors.verticalCenter: parent.verticalCenter
                                    visible: parent.text.length === 0
                                    text: modelData.label
                                    color: win.muted
                                    font.family: win.bodyFont
                                    font.pixelSize: 16
                                }
                                onTextEdited: {
                                    if (modelData.key === "address")
                                        win.netAddress = text
                                    else if (modelData.key === "netmask")
                                        win.netNetmask = text
                                    else if (modelData.key === "gateway")
                                        win.netGateway = text
                                    else
                                        win.netDns = text
                                }
                            }
                        }
                    }
                }

                Text {
                    width: parent.width
                    visible: win.netError.length > 0
                    wrapMode: Text.WordWrap
                    text: win.netError
                    color: win.danger
                    font.family: win.bodyFont
                    font.pixelSize: 15
                }

                Row {
                    spacing: 12

                    Rectangle {
                        width: netConnectLabel.implicitWidth + 28
                        height: 40
                        radius: 9
                        color: win.netBusy ? Qt.rgba(244 / 255, 242 / 255, 238 / 255, 0.35) : win.button
                        antialiasing: true

                        Text {
                            id: netConnectLabel
                            anchors.centerIn: parent
                            text: "Connect"
                            color: win.buttonInk
                            font.family: win.bodyFont
                            font.pixelSize: 16
                            font.bold: true
                        }

                        MouseArea {
                            anchors.fill: parent
                            enabled: !win.netBusy
                            cursorShape: Qt.PointingHandCursor
                            onClicked: win.connectNet()
                        }
                    }

                    Rectangle {
                        objectName: "skipAppsButton"
                        width: netSkipLabel.implicitWidth + 28
                        height: 40
                        radius: 9
                        color: "transparent"
                        border.width: 1
                        border.color: Qt.rgba(244 / 255, 242 / 255, 238 / 255, 0.55)
                        antialiasing: true

                        Text {
                            id: netSkipLabel
                            anchors.centerIn: parent
                            text: "Skip for now"
                            color: win.ink
                            font.family: win.bodyFont
                            font.pixelSize: 16
                        }

                        MouseArea {
                            anchors.fill: parent
                            enabled: !win.netBusy
                            cursorShape: Qt.PointingHandCursor
                            onClicked: win.skipApps()
                        }
                    }
                }
            }
        }

        Rectangle {
            anchors.fill: parent
            visible: win.phase === "work" && win.failedApp.length > 0
            color: Qt.rgba(0, 0, 0, 0.62)

            Rectangle {
                z: 1
                anchors.centerIn: parent
                width: Math.min(520, parent.width - 80)
                height: appsFailColumn.height + 36
                radius: 14
                color: win.card
                border.width: 1
                border.color: win.line
                antialiasing: true

                Column {
                    id: appsFailColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 18
                    spacing: 12

                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: win.appsFailTitle
                        color: win.ink
                        font.family: win.bodyFont
                        font.pixelSize: 26
                    }

                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: win.appsFailBody
                        color: win.muted
                        font.family: win.bodyFont
                        font.pixelSize: 16
                    }

                    Row {
                        spacing: 18

                        Rectangle {
                            objectName: "retryAppButton"
                            width: retryAppLabel.implicitWidth + 28
                            height: 36
                            radius: 9
                            color: win.button
                            antialiasing: true

                            Text {
                                id: retryAppLabel
                                anchors.centerIn: parent
                                text: "Retry"
                                color: win.buttonInk
                                font.family: win.bodyFont
                                font.pixelSize: 16
                                font.bold: true
                            }

                            MouseArea {
                                anchors.fill: parent
                                enabled: !win.appsBusy && !win.agentsBusy && !win.lookBusy
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (win.failKind === "look")
                                        win.applyLook()
                                    else if (win.failKind === "agents")
                                        win.retryAgent()
                                    else
                                        win.retryApp()
                                }
                            }
                        }

                        Rectangle {
                            objectName: "continueAppButton"
                            visible: win.failKind !== "look"
                            width: appsContinueLabel.implicitWidth + 28
                            height: 36
                            radius: 9
                            color: win.button
                            antialiasing: true

                            Text {
                                id: appsContinueLabel
                                anchors.centerIn: parent
                                text: "Continue"
                                color: win.buttonInk
                                font.family: win.bodyFont
                                font.pixelSize: 16
                                font.bold: true
                            }

                            MouseArea {
                                anchors.fill: parent
                                enabled: !win.appsBusy && !win.agentsBusy
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (win.failKind === "agents")
                                        win.continueAgent()
                                    else
                                        win.continueApp()
                                }
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            anchors.fill: parent
            visible: win.phase === "wifi" && win.wifiWarn
            color: Qt.rgba(0, 0, 0, 0.62)

            MouseArea {
                anchors.fill: parent
                onClicked: win.dismissWifiWarn()
            }

            Rectangle {
                z: 1
                anchors.centerIn: parent
                width: Math.min(520, parent.width - 80)
                height: warnColumn.height + 36
                radius: 14
                color: win.card
                border.width: 1
                border.color: win.line
                antialiasing: true

                MouseArea {
                    anchors.fill: parent
                }

                Column {
                    id: warnColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 18
                    spacing: 12

                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: win.wifiWarnTitle
                        color: win.ink
                        font.family: win.bodyFont
                        font.pixelSize: 26
                    }

                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: win.wifiWarnBody
                        color: win.muted
                        font.family: win.bodyFont
                        font.pixelSize: 16
                    }

                    Row {
                        spacing: 18

                        Text {
                            text: "Go back"
                            color: win.muted
                            font.family: win.bodyFont
                            font.pixelSize: 16

                            MouseArea {
                                anchors.fill: parent
                                anchors.margins: -8
                                cursorShape: Qt.PointingHandCursor
                                onClicked: win.dismissWifiWarn()
                            }
                        }

                        Rectangle {
                            width: continueLabel.implicitWidth + 28
                            height: 36
                            radius: 9
                            color: win.button
                            antialiasing: true

                            Text {
                                id: continueLabel
                                anchors.centerIn: parent
                                text: "Continue"
                                color: win.buttonInk
                                font.family: win.bodyFont
                                font.pixelSize: 16
                                font.bold: true
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: win.continueWithoutWifi()
                            }
                        }
                    }
                }
            }
        }
    }
}
