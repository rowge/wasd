import QtQuick

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
            return "Desktop wallpaper"
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

    function pictureLabel(fileName) {
        if (!fileName)
            return "None"
        let stem = fileName
        const dot = stem.lastIndexOf(".")
        if (dot > 0)
            stem = stem.slice(0, dot)
        stem = stem.replace(/[-_]+/g, " ")
        if (stem.length === 0)
            return "None"
        return stem.charAt(0).toUpperCase() + stem.slice(1)
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

    Flickable {
        id: scroller
        anchors.fill: parent
        anchors.leftMargin: 32
        anchors.rightMargin: 32
        anchors.topMargin: 28
        anchors.bottomMargin: 88
        contentWidth: width
        contentHeight: column.height
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height

        Column {
            id: column
            width: scroller.width
            spacing: 0

            Text {
                text: "Look"
                color: host.ink
                font.family: host.titleFont
                font.pixelSize: 28
                font.weight: Font.DemiBold
                bottomPadding: 18
            }

            Repeater {
                model: host.tool ? 4 : 3

                delegate: Column {
                    id: section
                    required property int index
                    readonly property string key: page.sectionKey(index)
                    readonly property string choice: page.sectionChoice(index)
                    readonly property bool open: host.lookOpen === key
                    readonly property bool portrait: index === 3
                    width: column.width

                    Rectangle {
                        width: parent.width
                        height: 1
                        color: host.line
                    }

                    Item {
                        width: parent.width
                        height: 48

                        Text {
                            id: tri
                            anchors.left: parent.left
                            anchors.leftMargin: 4
                            anchors.verticalCenter: parent.verticalCenter
                            text: section.open ? "▾" : "▸"
                            color: host.muted
                            font.pixelSize: 16
                        }

                        Text {
                            id: label
                            anchors.left: tri.right
                            anchors.leftMargin: 14
                            anchors.verticalCenter: parent.verticalCenter
                            text: page.sectionTitle(section.index)
                            color: host.ink
                            font.family: host.bodyFont
                            font.pixelSize: 18
                        }

                        Text {
                            anchors.left: label.right
                            anchors.right: parent.right
                            anchors.leftMargin: 16
                            anchors.verticalCenter: parent.verticalCenter
                            visible: !section.open
                            text: page.pictureLabel(section.choice)
                            color: host.muted
                            font.family: host.bodyFont
                            font.pixelSize: 14
                            elide: Text.ElideRight
                            horizontalAlignment: Text.AlignRight
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: host.openLook(section.key)
                        }
                    }

                    Column {
                        width: parent.width
                        visible: section.open
                        leftPadding: 26
                        bottomPadding: 16
                        spacing: 12

                        Rectangle {
                            visible: !section.portrait
                            width: parent.width - 26
                            height: visible ? 220 : 0
                            radius: 10
                            color: "#101114"
                            border.width: 2
                            border.color: host.brass
                            clip: true
                            antialiasing: true

                            Image {
                                anchors.fill: parent
                                anchors.margins: 2
                                source: section.choice.length > 0 ? host.art(page.sectionFolder(section.index), section.choice) : ""
                                fillMode: Image.PreserveAspectCrop
                                sourceSize: Qt.size(960, 540)
                                cache: true
                            }
                        }

                        Item {
                            visible: section.portrait
                            width: parent.width - 26
                            height: visible ? 128 : 0

                            Rectangle {
                                anchors.centerIn: parent
                                width: 112
                                height: 112
                                radius: 12
                                color: "#101114"
                                border.width: 3
                                border.color: section.choice.length > 0 ? host.brass : "transparent"
                                antialiasing: true

                                Image {
                                    anchors.fill: parent
                                    anchors.margins: 3
                                    visible: section.choice.length > 0
                                    source: section.choice.length > 0 ? host.art(page.sectionFolder(section.index), section.choice) : ""
                                    fillMode: Image.PreserveAspectCrop
                                    sourceSize: Qt.size(224, 224)
                                    cache: true
                                }

                                Text {
                                    anchors.centerIn: parent
                                    visible: section.choice.length === 0
                                    text: "None"
                                    color: host.muted
                                    font.family: host.bodyFont
                                    font.pixelSize: 14
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    enabled: section.choice.length > 0
                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onClicked: page.choose(section.index, section.choice)
                                }
                            }
                        }

                        Item {
                            id: stripBox
                            width: parent.width - 26
                            height: section.portrait ? 44 : 52

                            function maxX() {
                                return Math.max(0, film.contentWidth - film.width)
                            }

                            function scrollBy(direction) {
                                var step = Math.max(72, film.width - 36)
                                film.contentX = Math.max(0, Math.min(stripBox.maxX(), film.contentX + direction * step))
                            }

                            Flickable {
                                id: film
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
                                        film.contentX = Math.max(0, Math.min(stripBox.maxX(), film.contentX - delta))
                                        event.accepted = true
                                    }
                                }

                                Row {
                                    id: stripRow
                                    spacing: 8
                                    height: parent.height

                                    Repeater {
                                        model: page.sectionFiles(section.index)

                                        delegate: Rectangle {
                                            id: thumb
                                            required property string modelData
                                            readonly property bool on: section.choice === modelData
                                            width: section.portrait ? 40 : 76
                                            height: section.portrait ? 40 : 44
                                            radius: 6
                                            color: "#101114"
                                            border.width: 2
                                            border.color: thumb.on ? host.brass : "transparent"
                                            clip: true
                                            antialiasing: true

                                            Image {
                                                anchors.fill: parent
                                                anchors.margins: thumb.on ? 2 : 0
                                                source: host.art(page.sectionFolder(section.index), thumb.modelData)
                                                fillMode: Image.PreserveAspectCrop
                                                sourceSize: Qt.size(section.portrait ? 96 : 152, section.portrait ? 96 : 88)
                                                cache: true
                                            }

                                            MouseArea {
                                                anchors.fill: parent
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: page.choose(section.index, thumb.modelData)
                                            }
                                        }
                                    }
                                }
                            }

                            Rectangle {
                                visible: stripBox.maxX() > 4 && film.contentX > 1
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
                                visible: stripBox.maxX() > 4 && film.contentX < stripBox.maxX() - 1
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
