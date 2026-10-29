import QtQuick
import org.kde.plasma.plasma5support as P5Support

Item {
    id: probe
    signal chosen(string payload)

    Component.onCompleted: exec.connectSource("/usr/libexec/lookapply.py --current")

    P5Support.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []
        onNewData: function(sourceName, data) {
            disconnectSource(sourceName)
            const line = (data.stdout || "").trim().split("\n")[0]
            probe.chosen(line || "")
        }
    }
}
