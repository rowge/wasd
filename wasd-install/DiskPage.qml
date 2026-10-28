import QtQuick

Item {
    id: page
    required property var host

    Flickable {
        id: scroller
        objectName: "diskScroll"
        anchors.fill: parent
        anchors.leftMargin: 40
        anchors.rightMargin: 40
        anchors.topMargin: 36
        anchors.bottomMargin: 128
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
                text: "Disk"
                color: host.ink
                font.family: host.titleFont
                font.pixelSize: 44
                font.weight: Font.Medium
            }

            Text {
                width: parent.width
                topPadding: 8
                wrapMode: Text.WordWrap
                text: "The recommended install is one drive. The selected drive will be wiped."
                color: host.muted
                font.family: host.bodyFont
                font.pixelSize: 17
            }

            Column {
                width: parent.width
                topPadding: 16
                bottomPadding: 16
                spacing: 6

                Repeater {
                    model: host.warnings
                    delegate: Text {
                        required property string modelData
                        width: column.width
                        wrapMode: Text.WordWrap
                        text: modelData
                        color: host.danger
                        font.family: host.bodyFont
                        font.pixelSize: 16
                    }
                }
            }

            Column {
                width: parent.width
                spacing: 12

                Repeater {
                    model: host.diskModel
                    delegate: Rectangle {
                        required property string name
                        required property string size
                        required property int index
                        width: column.width
                        height: 72
                        color: Qt.rgba(0, 0, 0, 0.18)
                        border.color: host.diskIndex === index ? host.brass : host.line
                        border.width: 1

                        Rectangle {
                            id: mark
                            x: 18
                            anchors.verticalCenter: parent.verticalCenter
                            width: 16
                            height: 16
                            radius: 8
                            color: "transparent"
                            border.color: host.diskIndex === index ? host.brass : host.muted
                            border.width: 2

                            Rectangle {
                                anchors.centerIn: parent
                                width: 8
                                height: 8
                                radius: 4
                                color: host.brass
                                visible: host.diskIndex === index
                            }
                        }

                        Column {
                            anchors.left: mark.right
                            anchors.leftMargin: 14
                            anchors.right: sizeText.left
                            anchors.rightMargin: 12
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2

                            Text {
                                width: parent.width
                                text: name
                                color: host.ink
                                font.family: host.bodyFont
                                font.pixelSize: 18
                                elide: Text.ElideRight
                            }

                            Text {
                                width: parent.width
                                visible: text !== ""
                                text: host.diskLine(index)
                                color: host.muted
                                font.family: host.bodyFont
                                font.pixelSize: host.diskIndex === index ? 18 : 14
                                font.bold: host.diskIndex === index
                                elide: Text.ElideRight
                            }
                        }

                        Text {
                            id: sizeText
                            anchors.right: parent.right
                            anchors.rightMargin: 18
                            anchors.verticalCenter: parent.verticalCenter
                            text: size
                            color: host.muted
                            font.family: host.bodyFont
                            font.pixelSize: 15
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                host.diskIndex = index
                                host.actionIndex = index
                            }
                        }
                    }
                }
            }

            Text {
                width: parent.width
                topPadding: 18
                wrapMode: Text.WordWrap
                text: "A second drive for games can stay when you reinstall WASD."
                color: host.ink
                font.family: host.bodyFont
                font.pixelSize: 16
            }

            Text {
                id: gamesHead
                objectName: "gamesDrive"
                visible: host.diskModel.count > 1 || host.gamesOpen
                width: parent.width
                topPadding: 14
                wrapMode: Text.WordWrap
                text: host.gamesHeading()
                color: host.ink
                font.family: host.bodyFont
                font.pixelSize: 16
                font.bold: true

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: host.toggleGamesOpen()
                }
            }

            Column {
                width: parent.width
                visible: host.gamesOpen
                spacing: 10
                topPadding: 10

                Text {
                    width: parent.width
                    visible: host.diskModel.count === 1 && !host.splitFits()
                    wrapMode: Text.WordWrap
                    text: "This drive is too small to leave room for games."
                    color: host.muted
                    font.family: host.bodyFont
                    font.pixelSize: 15
                }

                Repeater {
                    model: host.diskModel
                    delegate: Rectangle {
                        required property string name
                        required property string size
                        required property int index
                        required property bool windows
                        width: column.width
                        height: host.diskModel.count > 1 ? 88 : 0
                        visible: host.diskModel.count > 1
                        color: Qt.rgba(0, 0, 0, 0.18)
                        border.color: (index === host.diskIndex && host.gamesMode === "split") || (host.gamesDiskIndex === index && (host.gamesMode === "keep" || host.gamesMode === "format")) ? host.brass : host.line
                        border.width: 1

                        Column {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.leftMargin: 16
                            anchors.rightMargin: 16
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2

                            Text {
                                width: parent.width
                                text: name + (size ? "  " + size : "")
                                color: host.ink
                                font.family: host.bodyFont
                                font.pixelSize: 16
                                elide: Text.ElideRight
                            }

                            Text {
                                width: parent.width
                                wrapMode: Text.WordWrap
                                text: host.gamesLine(index)
                                color: host.muted
                                font.family: host.bodyFont
                                font.pixelSize: 14
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: host.pickGamesDrive(index)
                        }
                    }
                }

                Column {
                    width: parent.width
                    visible: host.gamesMode === "split"
                    spacing: 8

                    Item {
                        id: slider
                        width: parent.width
                        height: 28
                        property real minV: 64
                        property real maxV: Math.max(65, host.usableGb() - 32)
                        property real span: Math.max(1, maxV - minV)

                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width
                            height: 4
                            radius: 2
                            color: host.line
                        }

                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: Math.max(8, (host.osGb - slider.minV) / slider.span * parent.width)
                            height: 4
                            radius: 2
                            color: host.brass
                        }

                        Rectangle {
                            width: 18
                            height: 18
                            radius: 9
                            color: host.brass
                            y: (parent.height - height) / 2
                            x: Math.max(0, Math.min(parent.width - width, (host.osGb - slider.minV) / slider.span * (parent.width - width)))
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onPressed: reposition(mouse.x)
                            onPositionChanged: if (pressed) reposition(mouse.x)
                            function reposition(x) {
                                const span = Math.max(1, width)
                                const t = Math.max(0, Math.min(1, x / span))
                                host.setOsGb(Math.round(slider.minV + t * slider.span))
                            }
                        }
                    }

                    Row {
                        spacing: 16

                        Column {
                            spacing: 4

                            Text {
                                text: "WASD, gigabytes"
                                color: host.muted
                                font.family: host.bodyFont
                                font.pixelSize: 13
                            }

                            Rectangle {
                                width: 140
                                height: 40
                                color: Qt.rgba(0, 0, 0, 0.28)
                                border.width: 1
                                border.color: host.line

                                TextInput {
                                    objectName: "osGbBox"
                                    anchors.fill: parent
                                    anchors.leftMargin: 12
                                    anchors.rightMargin: 12
                                    verticalAlignment: TextInput.AlignVCenter
                                    color: host.ink
                                    font.pixelSize: 18
                                    font.family: host.bodyFont
                                    selectByMouse: true
                                    clip: true
                                    text: host.osGbText
                                    inputMethodHints: Qt.ImhDigitsOnly
                                    validator: IntValidator { bottom: 1; top: 999999 }
                                    onTextEdited: host.osGbText = text
                                    onEditingFinished: host.setOsGb(text)
                                }
                            }
                        }

                        Column {
                            spacing: 4

                            Text {
                                text: "/games, gigabytes"
                                color: host.muted
                                font.family: host.bodyFont
                                font.pixelSize: 13
                            }

                            Rectangle {
                                width: 140
                                height: 40
                                color: Qt.rgba(0, 0, 0, 0.28)
                                border.width: 1
                                border.color: host.line

                                TextInput {
                                    objectName: "gamesGbBox"
                                    anchors.fill: parent
                                    anchors.leftMargin: 12
                                    anchors.rightMargin: 12
                                    verticalAlignment: TextInput.AlignVCenter
                                    color: host.ink
                                    font.pixelSize: 18
                                    font.family: host.bodyFont
                                    selectByMouse: true
                                    clip: true
                                    text: host.gamesGbText
                                    inputMethodHints: Qt.ImhDigitsOnly
                                    validator: IntValidator { bottom: 1; top: 999999 }
                                    onTextEdited: host.gamesGbText = text
                                    onEditingFinished: host.setGamesGb(text)
                                }
                            }
                        }
                    }

                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: "WASD keeps the first part. The rest is mounted at /games."
                        color: host.muted
                        font.family: host.bodyFont
                        font.pixelSize: 14
                    }
                }
            }

            Item {
                width: 1
                height: 22
            }

            Rectangle {
                width: parent.width
                height: 1
                color: host.line
            }

            Text {
                id: advanced
                width: parent.width
                topPadding: 14
                wrapMode: Text.WordWrap
                textFormat: Text.StyledText
                text: "<b><font color='#f6ead8'>Advanced.</font></b> <font color='#e7d3b6'>Partitioning and the other disk choices. This is not the recommended install.</font>"
                font.family: host.bodyFont
                font.pixelSize: 15
                color: host.muted

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: host.advancedOpen = !host.advancedOpen
                }
            }

            Text {
                width: parent.width
                visible: host.advancedOpen
                topPadding: 8
                wrapMode: Text.WordWrap
                text: "Partitioning and encryption are not part of this install. The recommended install is the drive selected above."
                color: host.muted
                font.family: host.bodyFont
                font.pixelSize: 14
            }
        }
    }

    PageFooter {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: 40
        anchors.rightMargin: 40
        anchors.bottomMargin: 16
        host: page.host
        nextText: host.eraseLabel
        nextEnabled: !host.installBlocked && host.diskIndex >= 0 && !host.erasing
        showGo: host.showEraseButton
        altText: host.gamesAltLabel
        note: host.savedLine
        onBack: host.page = 3
        onGo: host.installOrConfirm()
        onAlt: {
            if (host.gamesOpen) {
                host.useWholeDrive()
                return
            }
            host.openGamesSection()
            Qt.callLater(function() {
                scroller.contentY = Math.max(0, gamesHead.y - 12)
            })
        }
    }

    Rectangle {
        anchors.fill: parent
        visible: host.confirmStep > 0
        color: Qt.rgba(0, 0, 0, 0.62)

        MouseArea {
            anchors.fill: parent
            onClicked: host.confirmNo()
        }

        Rectangle {
            z: 1
            anchors.centerIn: parent
            width: Math.min(560, parent.width - 80)
            height: dialogColumn.height + 36
            color: "#1a0f0b"
            border.width: 1
            border.color: host.brass

            MouseArea {
                anchors.fill: parent
            }

            Column {
                id: dialogColumn
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 18
                spacing: 12

                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: host.confirmTitle()
                    color: host.ink
                    font.family: host.titleFont
                    font.pixelSize: 26
                }

                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: host.confirmBody()
                    color: host.muted
                    font.family: host.bodyFont
                    font.pixelSize: 16
                }

                Row {
                    spacing: 18

                    Text {
                        text: "No"
                        color: host.muted
                        font.family: host.bodyFont
                        font.pixelSize: 16

                        MouseArea {
                            objectName: "confirmNo"
                            anchors.fill: parent
                            anchors.margins: -8
                            cursorShape: Qt.PointingHandCursor
                            onClicked: host.confirmNo()
                        }
                    }

                    Rectangle {
                        width: yesLabel.implicitWidth + 28
                        height: 36
                        color: host.brass

                        Text {
                            id: yesLabel
                            anchors.centerIn: parent
                            text: "Yes"
                            color: "#24160e"
                            font.family: host.bodyFont
                            font.pixelSize: 16
                            font.bold: true
                        }

                        MouseArea {
                            objectName: "confirmYes"
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: host.confirmYes()
                        }
                    }
                }
            }
        }
    }
}
