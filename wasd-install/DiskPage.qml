import QtQuick

Item {
    id: page
    required property var host

    Flickable {
        id: scroller
        anchors.fill: parent
        anchors.leftMargin: 40
        anchors.rightMargin: 40
        anchors.topMargin: 36
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

            Text {
                width: parent.width
                topPadding: 18
                bottomPadding: 8
                text: "Give your computer a name."
                color: host.muted
                font.family: host.bodyFont
                font.pixelSize: 14
            }

            Rectangle {
                width: Math.min(420, parent.width)
                height: 48
                color: Qt.rgba(0, 0, 0, 0.28)
                border.width: 1
                border.color: host.hostnameOk ? host.line : host.danger

                TextInput {
                    id: hostName
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    verticalAlignment: TextInput.AlignVCenter
                    color: host.ink
                    font.pixelSize: 18
                    font.family: host.bodyFont
                    selectByMouse: true
                    clip: true
                    selectionColor: host.brass
                    selectedTextColor: "#24160e"
                    onTextEdited: host.hostname = text
                }
            }

            Text {
                width: parent.width
                visible: !host.hostnameOk
                topPadding: 6
                text: "Use letters, numbers, and hyphens."
                color: host.danger
                font.family: host.bodyFont
                font.pixelSize: 14
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
                            onClicked: host.diskIndex = index
                        }
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
                text: "Partitioning and encryption stay in the existing installer. This app does not open it yet. The recommended install is the drive selected above."
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
        nextText: "Next"
        onBack: if (host.page > 0) host.page = host.page - 1
        onGo: host.page = 1
    }

    Component.onCompleted: hostName.text = host.hostname
}
