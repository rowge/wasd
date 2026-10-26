import QtQuick
import Qt.labs.folderlistmodel
import org.kde.plasma.plasma5support as P5Support

Item {
    id: host
    signal disks(string payload)
    signal filesReady(string payload)
    signal eraseFinished(int code, string line)

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
        exec.connectSource("/usr/libexec/wasd-erase --install " + payload)
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
            if (sourceName.indexOf("wasd-live-info") >= 0) {
                if (code !== 0 || !stdout)
                    host.disks("{\"warnings\":[\"The disks could not be read.\"],\"blocked\":true,\"disks\":[]}")
                else
                    host.disks(stdout)
                return
            }
            host.eraseFinished(code, stderr || stdout)
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
