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
            return "Login screen"
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
        anchors.leftMargin: 36
        anchors.rightMargin: 36
        anchors.topMargin: 28
        anchors.bottomMargin: 76
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
                font.pixelSize: 44
                font.weight: Font.Medium
                bottomPadding: 22
            }

            Repeater {
                model: host.tool ? 4 : 3
                delegate: Column {
                    id: section
                    required property int index
                    width: column.width
                    property bool open: host.lookOpen === page.sectionKey(index)

                    Rectangle {
                        width: parent.width
                        height: 1
                        color: host.line
                    }

                    Item {
                        width: parent.width
                        height: 52

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
                            anchors.left: tri.right
                            anchors.leftMargin: 14
                            anchors.verticalCenter: parent.verticalCenter
                            text: page.sectionTitle(index)
                            color: host.ink
                            font.family: host.bodyFont
                            font.pixelSize: 18
                        }

                        Row {
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 12
                            visible: !section.open

                            Text {
                                visible: index === 2 && !host.tool
                                anchors.verticalCenter: parent.verticalCenter
                                text: host.themeChoice
                                color: host.muted
                                font.family: host.bodyFont
                                font.pixelSize: 14
                            }

                            Text {
                                visible: index === 3 && page.sectionChoice(index).length === 0
                                anchors.verticalCenter: parent.verticalCenter
                                text: "None"
                                color: host.muted
                                font.family: host.bodyFont
                                font.pixelSize: 14
                            }

                            Rectangle {
                                visible: page.sectionChoice(index).length > 0
                                width: index === 3 ? 40 : 112
                                height: index === 3 ? 40 : 63
                                color: "#120c09"
                                border.width: 2
                                border.color: host.brass

                                Image {
                                    anchors.fill: parent
                                    anchors.margins: 2
                                    source: host.shareRoot.length >= 0 ? host.art(page.sectionFolder(index), page.sectionChoice(index)) : ""
                                    fillMode: Image.PreserveAspectCrop
                                    sourceSize: index === 3 ? Qt.size(80, 80) : Qt.size(224, 126)
                                    cache: true
                                }
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: host.openLook(page.sectionKey(index))
                        }
                    }

                    Column {
                        width: parent.width
                        visible: section.open
                        leftPadding: 26
                        bottomPadding: 14
                        spacing: 12

                        Text {
                            visible: index === 2 && !host.tool
                            text: "Theme"
                            color: host.muted
                            font.family: host.bodyFont
                            font.pixelSize: 14
                        }

                        Flow {
                            visible: index === 2 && !host.tool
                            width: parent.width - 26
                            spacing: 8

                            Repeater {
                                model: host.themes
                                delegate: Rectangle {
                                    required property string modelData
                                    property bool on: host.themeChoice === modelData
                                    width: themeText.implicitWidth + 22
                                    height: 32
                                    color: on ? host.brass : "transparent"
                                    border.width: 1
                                    border.color: on ? host.brass : host.line

                                    Text {
                                        id: themeText
                                        anchors.centerIn: parent
                                        text: modelData
                                        color: on ? "#24160e" : host.ink
                                        font.family: host.bodyFont
                                        font.pixelSize: 14
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: host.themeChoice = modelData
                                    }
                                }
                            }
                        }

                        Text {
                            visible: index === 2 && !host.tool
                            text: "Wallpaper"
                            color: host.muted
                            font.family: host.bodyFont
                            font.pixelSize: 14
                        }

                        Flow {
                            width: parent.width - 26
                            spacing: 8

                            Repeater {
                                model: page.sectionFiles(index)
                                delegate: Rectangle {
                                    required property string modelData
                                    width: index === 3 ? 84 : 112
                                    height: index === 3 ? 84 : 63
                                    color: "#120c09"
                                    border.width: 2
                                    border.color: page.sectionChoice(index) === modelData ? host.brass : "transparent"

                                    Image {
                                        anchors.fill: parent
                                        anchors.margins: 2
                                        source: host.shareRoot.length >= 0 ? host.art(page.sectionFolder(index), modelData) : ""
                                        fillMode: Image.PreserveAspectCrop
                                        sourceSize: Qt.size(224, 126)
                                        cache: true
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: page.choose(index, modelData)
                                    }
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
