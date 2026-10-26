import QtQuick
import Qt.labs.folderlistmodel

Item {
    id: lister
    signal provide(var loading, var login, var wallpapers)

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

    function publish() {
        if (loadingModel.status !== FolderListModel.Ready)
            return
        if (loginModel.status !== FolderListModel.Ready)
            return
        if (wallModel.status !== FolderListModel.Ready)
            return
        lister.provide(
            prefer(names(loadingModel), ["keysketch.jpg"]),
            prefer(names(loginModel), ["camp.png"]),
            prefer(names(wallModel), ["wasdsketch.png"])
        )
    }

    FolderListModel {
        id: loadingModel
        folder: "file:///usr/share/wasd/loading"
        nameFilters: ["*.jpg", "*.jpeg", "*.png", "*.webp"]
        showDirs: false
        showOnlyReadable: true
        onStatusChanged: lister.publish()
    }

    FolderListModel {
        id: loginModel
        folder: "file:///usr/share/wasd/login"
        nameFilters: ["*.jpg", "*.jpeg", "*.png", "*.webp"]
        showDirs: false
        showOnlyReadable: true
        onStatusChanged: lister.publish()
    }

    FolderListModel {
        id: wallModel
        folder: "file:///usr/share/wallpapers/wasd"
        nameFilters: ["*.jpg", "*.jpeg", "*.png", "*.webp"]
        showDirs: false
        showOnlyReadable: true
        onStatusChanged: lister.publish()
    }
}
