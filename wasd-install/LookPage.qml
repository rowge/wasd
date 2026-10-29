import QtQuick
import QtQuick.Layouts

Item {
    id: page
    required property var host

    function sectionKey(index) {
        if (index === 0)
            return "loading"
        if (index === 1)
            return "login"
        if (index === 2)
            return "desktop"
        return "avatar"
    }

    function sectionTitle(index) {
        if (index === 0)
            return "Loading screen"
        if (index === 1)
            return "Login/lock screen"
        if (index === 2)
            return host.tool ? "Desktop wallpaper" : "Desktop"
        return "User picture"
    }

    function sectionFolder(index) {
        if (index === 0)
            return "wasd-loading-screens"
        if (index === 1)
            return "wasd-login-screens"
        if (index === 2)
            return "wasd-wallpapers"
        return "wasd-icons"
    }

    function sectionFiles(index) {
        if (index === 0)
            return host.loadingFiles
        if (index === 1)
            return host.loginFiles
        if (index === 2)
            return host.wallpaperFiles
        return host.iconFiles
    }

    function sectionChoice(index) {
        if (index === 0)
            return host.loadingChoice
        if (index === 1)
            return host.loginChoice
        if (index === 2)
            return host.wallpaperChoice
        return host.avatarChoice
    }

    function choose(index, fileName) {
        if (host.tool)
            host.choicesHeld = true
        if (index === 0)
            host.loadingChoice = fileName
        else if (index === 1)
            host.loginChoice = fileName
        else if (index === 2)
            host.wallpaperChoice = fileName
        else {
            host.avatarTouched = true
            host.avatarChoice = host.avatarChoice === fileName ? "" : fileName
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 20
        anchors.rightMargin: 20
        anchors.topMargin: 16
        anchors.bottomMargin: 88
        spacing: 10

        Text {
            text: "Look"
            color: host.ink
            font.family: host.titleFont
            font.pixelSize: 26
            font.weight: Font.DemiBold
        }

        Text {
            text: "Pictures for starting up, signing in, and the desktop."
            color: host.muted
            font.family: host.bodyFont
            font.pixelSize: 13
        }

        GridLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            columns: 2
            columnSpacing: 12
            rowSpacing: 12

            Repeater {
                model: host.tool ? 4 : 3

                delegate: Rectangle {
                    id: card
                    required property int index
                    readonly property bool themes: index === 2 && !host.tool
                    readonly property bool portrait: index === 3
                    readonly property string choice: page.sectionChoice(index)
                    Layout.fillWidth: true
                    Layout.fillHeight: host.tool || !card.themes
                    Layout.preferredHeight: card.themes ? 210 : 240
                    Layout.maximumHeight: card.themes ? 230 : 4000
                    Layout.columnSpan: card.themes ? 2 : 1
                    radius: 14
                    color: host.card
                    antialiasing: true

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 8

                        Text {
                            text: page.sectionTitle(card.index)
                            color: host.ink
                            font.family: host.bodyFont
                            font.pixelSize: 14
                            font.bold: true
                        }

                        Text {
                            visible: card.themes
                            text: "Theme"
                            color: host.muted
                            font.family: host.bodyFont
                            font.pixelSize: 13
                        }

                        Flickable {
                            visible: card.themes
                            Layout.fillWidth: true
                            Layout.preferredHeight: visible ? 34 : 0
                            contentWidth: themeRow.width
                            contentHeight: 34
                            flickableDirection: Flickable.HorizontalFlick
                            boundsBehavior: Flickable.StopAtBounds
                            clip: true

                            Row {
                                id: themeRow
                                spacing: 8
                                height: 34

                                Repeater {
                                    model: host.themes

                                    delegate: Rectangle {
                                        id: chip
                                        required property string modelData
                                        readonly property bool on: host.themeChoice === modelData
                                        width: chipText.implicitWidth + 22
                                        height: 32
                                        radius: 8
                                        color: chip.on ? host.brass : "transparent"
                                        border.width: 1
                                        border.color: chip.on ? host.brass : host.line
                                        antialiasing: true

                                        Text {
                                            id: chipText
                                            anchors.centerIn: parent
                                            text: chip.modelData
                                            color: chip.on ? host.buttonInk : host.ink
                                            font.family: host.bodyFont
                                            font.pixelSize: 13
                                            font.bold: chip.on
                                        }

                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: host.themeChoice = chip.modelData
                                        }
                                    }
                                }
                            }
                        }

                        Text {
                            visible: card.themes
                            text: "Wallpaper"
                            color: host.muted
                            font.family: host.bodyFont
                            font.pixelSize: 13
                        }

                        Rectangle {
                            visible: !card.portrait && !card.themes
                            Layout.fillWidth: true
                            Layout.fillHeight: visible
                            Layout.minimumHeight: visible ? 88 : 0
                            Layout.preferredHeight: visible ? 120 : 0
                            radius: 10
                            color: "#101114"
                            border.width: 2
                            border.color: host.brass
                            clip: true
                            antialiasing: true

                            Image {
                                anchors.fill: parent
                                anchors.margins: 2
                                source: card.choice.length > 0 ? host.art(page.sectionFolder(card.index), card.choice) : ""
                                fillMode: Image.PreserveAspectCrop
                                sourceSize: Qt.size(640, 360)
                                cache: true
                            }
                        }

                        Item {
                            visible: card.portrait
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumHeight: 72

                            Rectangle {
                                anchors.centerIn: parent
                                width: Math.min(112, parent.height)
                                height: width
                                radius: 12
                                color: "#101114"
                                border.width: 3
                                border.color: card.choice.length > 0 ? host.brass : "transparent"
                                antialiasing: true

                                Image {
                                    anchors.fill: parent
                                    anchors.margins: 3
                                    visible: card.choice.length > 0
                                    source: card.choice.length > 0 ? host.art(page.sectionFolder(card.index), card.choice) : ""
                                    fillMode: Image.PreserveAspectCrop
                                    sourceSize: Qt.size(224, 224)
                                    cache: true
                                }

                                Text {
                                    anchors.centerIn: parent
                                    visible: card.choice.length === 0
                                    text: "None"
                                    color: host.muted
                                    font.family: host.bodyFont
                                    font.pixelSize: 14
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    enabled: card.choice.length > 0
                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onClicked: page.choose(card.index, card.choice)
                                }
                            }
                        }

                        Item {
                            id: stripBox
                            Layout.fillWidth: true
                            Layout.preferredHeight: card.portrait ? 44 : (card.themes ? 76 : 52)

                            function maxX() {
                                return Math.max(0, scroller.contentWidth - scroller.width)
                            }

                            function scrollBy(direction) {
                                var step = Math.max(72, scroller.width - 36)
                                scroller.contentX = Math.max(0, Math.min(stripBox.maxX(), scroller.contentX + direction * step))
                            }

                            Flickable {
                                id: scroller
                                anchors.fill: parent
                                contentWidth: stripRow.width
                                contentHeight: height
                                flickableDirection: Flickable.HorizontalFlick
                                boundsBehavior: Flickable.StopAtBounds
                                clip: true

                                WheelHandler {
                                    onWheel: function(event) {
                                        if (stripBox.maxX() <= 0)
                                            return
                                        var delta = event.angleDelta.x !== 0 ? event.angleDelta.x : event.angleDelta.y
                                        if (delta === 0)
                                            return
                                        scroller.contentX = Math.max(0, Math.min(stripBox.maxX(), scroller.contentX - delta))
                                        event.accepted = true
                                    }
                                }

                                Row {
                                    id: stripRow
                                    spacing: 8
                                    height: parent.height

                                    Repeater {
                                        model: page.sectionFiles(card.index)

                                        delegate: Rectangle {
                                            id: thumb
                                            required property string modelData
                                            readonly property bool on: card.choice === modelData
                                            width: card.portrait ? 40 : (card.themes ? 120 : 76)
                                            height: card.portrait ? 40 : (card.themes ? 68 : 44)
                                            radius: 6
                                            color: "#101114"
                                            border.width: 2
                                            border.color: thumb.on ? host.brass : "transparent"
                                            clip: true
                                            antialiasing: true

                                            Image {
                                                anchors.fill: parent
                                                anchors.margins: thumb.on ? 2 : 0
                                                source: host.art(page.sectionFolder(card.index), thumb.modelData)
                                                fillMode: Image.PreserveAspectCrop
                                                sourceSize: Qt.size(card.portrait ? 96 : 152, card.portrait ? 96 : 88)
                                                cache: true
                                            }

                                            MouseArea {
                                                anchors.fill: parent
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: page.choose(card.index, thumb.modelData)
                                            }
                                        }
                                    }
                                }
                            }

                            Rectangle {
                                visible: stripBox.maxX() > 4 && scroller.contentX > 1
                                z: 2
                                width: 28
                                height: Math.min(parent.height - 4, 40)
                                anchors.left: parent.left
                                anchors.leftMargin: 2
                                anchors.verticalCenter: parent.verticalCenter
                                radius: height / 2
                                color: Qt.rgba(16 / 255, 17 / 255, 20 / 255, 0.62)
                                border.width: 1
                                border.color: Qt.rgba(244 / 255, 242 / 255, 238 / 255, 0.45)
                                antialiasing: true

                                Text {
                                    anchors.centerIn: parent
                                    text: "‹"
                                    color: Qt.rgba(244 / 255, 242 / 255, 238 / 255, 0.92)
                                    font.family: host.bodyFont
                                    font.pixelSize: 22
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: stripBox.scrollBy(-1)
                                }
                            }

                            Rectangle {
                                visible: stripBox.maxX() > 4 && scroller.contentX < stripBox.maxX() - 1
                                z: 2
                                width: 28
                                height: Math.min(parent.height - 4, 40)
                                anchors.right: parent.right
                                anchors.rightMargin: 2
                                anchors.verticalCenter: parent.verticalCenter
                                radius: height / 2
                                color: Qt.rgba(16 / 255, 17 / 255, 20 / 255, 0.62)
                                border.width: 1
                                border.color: Qt.rgba(244 / 255, 242 / 255, 238 / 255, 0.45)
                                antialiasing: true

                                Text {
                                    anchors.centerIn: parent
                                    text: "›"
                                    color: Qt.rgba(244 / 255, 242 / 255, 238 / 255, 0.92)
                                    font.family: host.bodyFont
                                    font.pixelSize: 22
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: stripBox.scrollBy(1)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    PageFooter {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: 36
        anchors.rightMargin: 36
        anchors.bottomMargin: 16
        host: page.host
        showBack: !host.tool
        nextText: host.tool ? "Apply" : "Next"
        nextEnabled: !host.tool || (!host.applying && host.avatarReady)
        note: host.tool ? (host.savedLine || "The loading screen changes on the next boot.") : ""
        onBack: host.page = 0
        onGo: {
            if (host.tool)
                host.applyLook()
            else
                host.page = 2
        }
    }
}
