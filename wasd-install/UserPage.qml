import QtQuick

Item {
    id: page
    required property var host

    Flickable {
        id: scroller
        anchors.fill: parent
        anchors.leftMargin: 40
        anchors.rightMargin: 40
        anchors.topMargin: 32
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
                text: "User"
                color: host.ink
                font.family: host.titleFont
                font.pixelSize: 44
                font.weight: Font.Medium
            }

            Text {
                topPadding: 18
                bottomPadding: 6
                text: "Username"
                color: host.muted
                font.family: host.bodyFont
                font.pixelSize: 14
            }

            Rectangle {
                width: Math.min(420, parent.width)
                height: 48
                color: Qt.rgba(0, 0, 0, 0.28)
                border.width: 1
                border.color: host.userOk ? host.line : host.danger

                TextInput {
                    id: nameField
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
                    onTextEdited: host.userName = text
                }
            }

            Text {
                width: parent.width
                visible: !host.userOk
                topPadding: 6
                text: "Use a lowercase name, with no spaces."
                color: host.danger
                font.family: host.bodyFont
                font.pixelSize: 14
            }

            Grid {
                width: parent.width
                topPadding: 22
                columns: 5
                columnSpacing: 12
                rowSpacing: 12

                Repeater {
                    model: host.iconFiles
                    delegate: Rectangle {
                        required property string modelData
                        width: 84
                        height: 84
                        color: "#120c09"
                        border.width: 2
                        border.color: host.avatar === modelData ? host.brass : "transparent"

                        Image {
                            anchors.fill: parent
                            anchors.margins: 2
                            source: host.art("wasd-icons", modelData)
                            fillMode: Image.PreserveAspectCrop
                            sourceSize: Qt.size(168, 168)
                            cache: true
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: host.avatar = host.avatar === modelData ? "" : modelData
                        }
                    }
                }
            }

            Item {
                width: 1
                height: 22
            }

            Item {
                width: checkRow.width
                height: 28

                Row {
                    id: checkRow
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 12

                    Rectangle {
                        width: 18
                        height: 18
                        anchors.verticalCenter: parent.verticalCenter
                        color: host.setPassword ? host.brass : "transparent"
                        border.width: 2
                        border.color: host.setPassword ? host.brass : host.muted
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Set a password"
                        color: host.ink
                        font.family: host.bodyFont
                        font.pixelSize: 18
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: host.setPassword = !host.setPassword
                }
            }

            Text {
                width: parent.width
                visible: !host.setPassword
                topPadding: 10
                wrapMode: Text.WordWrap
                text: "Without a password, anyone who can turn on the computer is you."
                color: host.danger
                font.family: host.bodyFont
                font.pixelSize: 16
            }

            Text {
                width: parent.width
                topPadding: 8
                wrapMode: Text.WordWrap
                text: "Setting a password will secure the login screen, and an administrative command will ask for it. Not setting a password will not prompt for one."
                color: host.ink
                font.family: host.bodyFont
                font.pixelSize: 16
            }

            Text {
                width: parent.width
                visible: host.setPassword
                topPadding: 8
                wrapMode: Text.WordWrap
                text: "You will choose it the first time this computer starts."
                color: host.ink
                font.family: host.bodyFont
                font.pixelSize: 16
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
        onBack: host.page = 0
        onGo: host.page = 1
    }

    Component.onCompleted: nameField.text = host.userName
}
