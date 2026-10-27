import QtQuick
import org.kde.plasma.plasma5support as P5Support

Item {
    id: host
    signal finished(string line)

    property string wallpaperCommand: ""
    property string applyCommand: ""
    property bool wallpaperDone: false

    function start(wallpaper, login, loading, avatar) {
        wallpaperDone = false
        wallpaperCommand = "/usr/bin/plasma-apply-wallpaperimage /usr/share/wallpapers/wasd/" + wallpaper
        let picture = ""
        if (avatar === null || avatar === undefined)
            picture = ""
        else if (avatar)
            picture = " --avatar " + avatar
        else
            picture = " --clear-avatar"
        applyCommand = "pkexec /usr/libexec/wasd-apply-look --login " + login + " --loading " + loading + picture
        exec.connectSource(wallpaperCommand)
    }

    function codeOf(data) {
        if (data["exit code"] !== undefined)
            return data["exit code"]
        if (data.exitCode !== undefined)
            return data.exitCode
        return 1
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
            if (sourceName === host.wallpaperCommand && !host.wallpaperDone) {
                host.wallpaperDone = true
                if (code !== 0) {
                    host.finished(stderr || "The wallpaper did not change.")
                    return
                }
                exec.connectSource(host.applyCommand)
                return
            }
            if (code !== 0) {
                const detail = stderr || stdout || "The login screen and the loading screen were not changed."
                host.finished("The wallpaper is changed. " + detail)
                return
            }
            const rest = stdout || "The login screen changes at the next login. The lock screen uses that same picture the next time the screen locks. The loading screen changes on the next boot."
            host.finished("The wallpaper is changed. " + rest)
        }
    }
}
