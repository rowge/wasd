import QtQuick
import Qt.labs.folderlistmodel
import org.kde.plasma.plasma5support as P5Support

Item {
    id: host
    signal disks(string payload)
    signal filesReady(string payload)
    signal eraseFinished(int code, string line)
    signal statusLine(string line)

    property bool installRunning: false
    property string statusId: ""

    function codeOf(data) {
        if (data["exit code"] !== undefined)
            return data["exit code"]
        if (data.exitCode !== undefined)
            return data.exitCode
        return 1
    }

    function prefer(names, first) {
        const rank = {}
        for (let i = 0; i < first.length; i++)
            rank[first[i]] = i
        const copy = names.slice()
        copy.sort(function(a, b) {
            const ra = rank[a] === undefined ? 1000 : rank[a]
            const rb = rank[b] === undefined ? 1000 : rank[b]
            if (ra !== rb)
                return ra - rb
            const al = a.toLowerCase()
            const bl = b.toLowerCase()
            if (al < bl)
                return -1
            if (al > bl)
                return 1
            return 0
        })
        return copy
    }

    function names(model) {
        const found = []
        for (let i = 0; i < model.count; i++)
            found.push(model.get(i, "fileName"))
        return found
    }

    function publishFiles() {
        const models = [iconModel, loadingModel, loginModel, wallModel]
        for (let i = 0; i < models.length; i++) {
            if (models[i].status !== FolderListModel.Ready)
                return
        }
        const icons = prefer(names(iconModel), [
            "knight.jpg", "superhero-female.jpg", "pilot.jpg", "fox.jpg", "wizard.jpg",
            "soldier.jpg", "gunslinger.jpg", "archer.jpg", "wolf-brawler.jpg", "superhero.jpg"
        ]).filter(function(name) { return name !== "wasd-logo.png" })
        host.filesReady(JSON.stringify({
            icons: icons,
            loading: prefer(names(loadingModel), ["stained-glass.jpg"]),
            login: prefer(names(loginModel), ["throne.jpg", "camp.png"]),
            wallpapers: prefer(names(wallModel), ["stained-glass.jpg"])
        }))
    }

    function probe() {
        exec.connectSource("/usr/libexec/wasd-live-info")
    }

    function erase(payload) {
        const alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
        let id = ""
        for (let i = 0; i < 16; i++)
            id += alphabet.charAt(Math.floor(Math.random() * alphabet.length))
        statusId = id
        installRunning = true
        statusTimer.start()
        exec.connectSource("/usr/libexec/wasd-erase --install --status-id " + id + " " + payload)
    }

    function restart() {
        exec.connectSource("/usr/bin/systemctl reboot")
    }

    P5Support.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []
        onNewData: function(sourceName, data) {
            const code = host.codeOf(data)
            const stdout = (data.stdout || "").trim()
            const stderr = (data.stderr || "").trim()
            disconnectSource(sourceName)
            if (sourceName.indexOf("wasd-install.status") >= 0) {
                const parts = (data.stdout || "").split("\n")
                if (parts.length >= 2 && parts[0].trim() === host.statusId && parts[1].trim())
                    host.statusLine(parts[1].trim())
                return
            }
            if (sourceName.indexOf("wasd-live-info") >= 0) {
                if (code !== 0 || !stdout)
                    host.disks("{\"warnings\":[\"The disks could not be read.\"],\"blocked\":true,\"disks\":[]}")
                else
                    host.disks(stdout)
                return
            }
            host.installRunning = false
            statusTimer.stop()
            host.eraseFinished(code, stderr || stdout)
        }
    }

    Timer {
        id: statusTimer
        interval: 1000
        repeat: true
        running: false
        onTriggered: {
            if (!host.installRunning || !host.statusId)
                return
            const source = "/usr/bin/cat /tmp/wasd-install.status"
            const sources = exec.connectedSources
            for (let i = 0; i < sources.length; i++) {
                if (sources[i] === source)
                    return
            }
            exec.connectSource(source)
        }
    }

    FolderListModel {
        id: iconModel
        folder: "file:///usr/share/wasd/icons"
        nameFilters: ["*.jpg", "*.jpeg", "*.png", "*.webp"]
        showDirs: false
        showOnlyReadable: true
        onStatusChanged: host.publishFiles()
    }

    FolderListModel {
        id: loadingModel
        folder: "file:///usr/share/wasd/loading"
        nameFilters: ["*.jpg", "*.jpeg", "*.png", "*.webp"]
        showDirs: false
        showOnlyReadable: true
        onStatusChanged: host.publishFiles()
    }

    FolderListModel {
        id: loginModel
        folder: "file:///usr/share/wasd/login"
        nameFilters: ["*.jpg", "*.jpeg", "*.png", "*.webp"]
        showDirs: false
        showOnlyReadable: true
        onStatusChanged: host.publishFiles()
    }

    FolderListModel {
        id: wallModel
        folder: "file:///usr/share/wallpapers/wasd"
        nameFilters: ["*.jpg", "*.jpeg", "*.png", "*.webp"]
        showDirs: false
        showOnlyReadable: true
        onStatusChanged: host.publishFiles()
    }
}
