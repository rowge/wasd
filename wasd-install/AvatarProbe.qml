import QtQuick
import org.kde.plasma.plasma5support as P5Support

Item {
    id: probe
    signal current(string name)

    Component.onCompleted: exec.connectSource("/usr/libexec/wasd-apply-look --current")

    P5Support.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []
        onNewData: function(sourceName, data) {
            disconnectSource(sourceName)
            const line = (data.stdout || "").trim().split("\n")[0]
            probe.current(line || "")
        }
    }
}
