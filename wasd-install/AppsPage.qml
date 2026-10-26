import QtQuick

Item {
    id: page
    required property var host

    function appChecked(name, id, extra) {
        if (extra)
            return host.extraPicked(id)
        return !!host.appOn[name]
    }

    component ChoiceButton: Rectangle {
        id: choice
        required property string label
        required property var host
        signal clicked()
        width: choiceLabel.implicitWidth + 28
        height: 32
        color: "transparent"
        border.width: 1
        border.color: host.line

        Text {
            id: choiceLabel
            anchors.centerIn: parent
            text: choice.label
            color: host.ink
            font.family: host.bodyFont
            font.pixelSize: 14
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: choice.clicked()
        }
    }

    Flickable {
        id: scroller
        objectName: "pageScroll"
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
                text: "Apps & Agents"
                color: host.ink
                font.family: host.titleFont
                font.pixelSize: 40
                font.weight: Font.Medium
                bottomPadding: 18
            }

            Rectangle {
                width: parent.width
                height: 1
                color: host.line
            }

            Item {
                width: parent.width
                height: 48

                Text {
                    id: appTri
                    anchors.left: parent.left
                    anchors.leftMargin: 4
                    anchors.verticalCenter: parent.verticalCenter
                    text: host.appsOpen === "apps" ? "▾" : "▸"
                    color: host.muted
                    font.pixelSize: 16
                }

                Text {
                    anchors.left: appTri.right
                    anchors.leftMargin: 14
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Apps"
                    color: host.ink
                    font.family: host.bodyFont
                    font.pixelSize: 18
                }

                Text {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    visible: host.appsOpen !== "apps"
                    text: host.appSummary
                    color: host.muted
                    font.family: host.bodyFont
                    font.pixelSize: 14
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: host.openApps("apps")
                }
            }

            Column {
                width: parent.width
                visible: host.appsOpen === "apps"
                leftPadding: 26
                bottomPadding: 12
                spacing: 12

                Row {
                    spacing: 8

                    ChoiceButton {
                        objectName: "selectAllApps"
                        label: "Select All"
                        host: page.host
                        onClicked: host.selectAllApps()
                    }

                    ChoiceButton {
                        objectName: "selectNoneApps"
                        label: "Select None"
                        host: page.host
                        onClicked: host.selectNoneApps()
                    }
                }

                Rectangle {
                    width: parent.width - 26
                    height: 42
                    color: Qt.rgba(0, 0, 0, 0.28)
                    border.width: 1
                    border.color: host.line

                    TextInput {
                        id: query
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        verticalAlignment: TextInput.AlignVCenter
                        color: host.ink
                        font.pixelSize: 16
                        font.family: host.bodyFont
                        selectByMouse: true
                        clip: true
                        selectionColor: host.brass
                        selectedTextColor: "#24160e"
                        onTextEdited: host.queryEdited(text)
                    }

                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        verticalAlignment: Text.AlignVCenter
                        visible: query.text.length === 0
                        text: "Search for any other app"
                        color: host.muted
                        font.family: host.bodyFont
                        font.pixelSize: 16
                    }
                }

                Grid {
                    width: parent.width - 26
                    columns: 2
                    columnSpacing: 24
                    rowSpacing: 4

                    Repeater {
                        model: host.shownAppModel
                        delegate: Item {
                            required property string name
                            required property string id
                            required property bool extra
                            width: (parent.width - 24) / 2
                            height: 24

                            Rectangle {
                                id: mark
                                width: 16
                                height: 16
                                anchors.verticalCenter: parent.verticalCenter
                                color: page.appChecked(name, id, extra) ? host.brass : "transparent"
                                border.width: 2
                                border.color: page.appChecked(name, id, extra) ? host.brass : host.muted
                            }

                            Text {
                                anchors.left: mark.right
                                anchors.leftMargin: 10
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                text: name
                                color: host.ink
                                font.family: host.bodyFont
                                font.pixelSize: 15
                                elide: Text.ElideRight
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: host.toggleApp(name, id, extra)
                            }
                        }
                    }
                }
            }

            Rectangle {
                width: parent.width
                height: 1
                color: host.line
            }

            Item {
                width: parent.width
                height: 48

                Text {
                    id: agentTri
                    anchors.left: parent.left
                    anchors.leftMargin: 4
                    anchors.verticalCenter: parent.verticalCenter
                    text: host.appsOpen === "agents" ? "▾" : "▸"
                    color: host.muted
                    font.pixelSize: 16
                }

                Text {
                    id: agentLabel
                    anchors.left: agentTri.right
                    anchors.leftMargin: 14
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Agents"
                    color: host.ink
                    font.family: host.bodyFont
                    font.pixelSize: 18
                }

                Text {
                    anchors.left: agentLabel.right
                    anchors.right: parent.right
                    anchors.leftMargin: 16
                    anchors.verticalCenter: parent.verticalCenter
                    visible: host.appsOpen !== "agents"
                    text: host.agentSummary
                    color: host.muted
                    font.family: host.bodyFont
                    font.pixelSize: 14
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignRight
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: host.openApps("agents")
                }
            }

            Column {
                width: parent.width
                visible: host.appsOpen === "agents"
                leftPadding: 26
                bottomPadding: 8
                spacing: 12

                Row {
                    spacing: 8

                    ChoiceButton {
                        objectName: "selectAllAgents"
                        label: "Select All"
                        host: page.host
                        onClicked: host.selectAllAgents()
                    }

                    ChoiceButton {
                        objectName: "selectNoneAgents"
                        label: "Select None"
                        host: page.host
                        onClicked: host.selectNoneAgents()
                    }
                }

                Grid {
                    width: parent.width - 26
                    columns: 2
                    columnSpacing: 24
                    rowSpacing: 8

                    Repeater {
                    model: host.agentNames
                    delegate: Item {
                        required property string modelData
                        width: (parent.width - 24) / 2
                        height: 26

                        Rectangle {
                            id: mark
                            width: 16
                            height: 16
                            anchors.verticalCenter: parent.verticalCenter
                            color: host.agentOn[modelData] ? host.brass : "transparent"
                            border.width: 2
                            border.color: host.agentOn[modelData] ? host.brass : host.muted
                        }

                        Text {
                            anchors.left: mark.right
                            anchors.leftMargin: 10
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData
                            color: host.ink
                            font.family: host.bodyFont
                            font.pixelSize: 15
                            elide: Text.ElideRight
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: host.toggleAgent(modelData)
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
        anchors.leftMargin: 32
        anchors.rightMargin: 32
        anchors.bottomMargin: 12
        host: page.host
        nextText: "Next"
        onBack: host.page = 1
        onGo: host.page = 3
    }
}
