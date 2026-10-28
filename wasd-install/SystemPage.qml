import QtQuick

Item {
    id: page
    required property var host

    Flickable {
        id: scroller
        objectName: "systemScroll"
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
                text: "System"
                color: host.ink
                font.family: host.titleFont
                font.pixelSize: 28
                font.weight: Font.DemiBold
            }

            Text {
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
                radius: 8
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
                    selectedTextColor: host.buttonInk
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

            Item {
                width: 1
                height: 28
            }

            Rectangle {
                width: parent.width
                height: 1
                color: host.line
            }

            Item {
                width: parent.width
                height: 52

                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 4
                    anchors.verticalCenter: parent.verticalCenter
                    text: host.networkOpen ? "▾" : "▸"
                    color: host.muted
                    font.pixelSize: 16
                }

                Text {
                    objectName: "networkStatus"
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.leftMargin: 28
                    anchors.verticalCenter: parent.verticalCenter
                    text: host.networkStatus
                    color: host.networkConnected ? host.ink : host.muted
                    font.family: host.bodyFont
                    font.pixelSize: 16
                    elide: Text.ElideRight
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        host.networkOpen = !host.networkOpen
                        if (host.networkOpen && host.liveSession) {
                            host.refreshNetwork(true)
                            host.refreshDevices()
                        }
                    }
                }
            }

            Column {
                width: parent.width
                visible: host.networkOpen
                leftPadding: 28
                bottomPadding: 8
                spacing: 14

                Text {
                    text: "Wi-Fi"
                    color: host.ink
                    font.family: host.bodyFont
                    font.pixelSize: 18
                }

                Column {
                    width: parent.width - 28
                    spacing: 8

                    Repeater {
                        model: host.wifiNetworks
                        delegate: Rectangle {
                            required property var modelData
                            width: parent.width
                            height: 44
                            color: Qt.rgba(0, 0, 0, 0.18)
                            border.width: 1
                            border.color: host.wifiSsid === modelData.ssid ? host.brass : host.line

                            Text {
                                anchors.left: parent.left
                                anchors.right: securityText.left
                                anchors.leftMargin: 14
                                anchors.rightMargin: 12
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.ssid
                                color: host.ink
                                font.family: host.bodyFont
                                font.pixelSize: 16
                                elide: Text.ElideRight
                            }

                            Text {
                                id: securityText
                                anchors.right: parent.right
                                anchors.rightMargin: 14
                                anchors.verticalCenter: parent.verticalCenter
                                text: (modelData.security || "Open") + (modelData.signal >= 0 ? "  " + modelData.signal : "")
                                color: host.muted
                                font.family: host.bodyFont
                                font.pixelSize: 14
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: host.chooseWifi(modelData.ssid)
                            }
                        }
                    }
                }

                Text {
                    width: parent.width - 28
                    text: "Or type a network name. Choose a network again to clear it. The first boot asks for its passphrase."
                    wrapMode: Text.WordWrap
                    color: host.muted
                    font.family: host.bodyFont
                    font.pixelSize: 14
                }

                Rectangle {
                    width: Math.min(420, parent.width - 28)
                    height: 44
                    color: Qt.rgba(0, 0, 0, 0.28)
                    radius: 8
                    border.width: 1
                    border.color: host.line

                    TextInput {
                        id: ssidField
                        anchors.fill: parent
                        anchors.leftMargin: 14
                        anchors.rightMargin: 14
                        verticalAlignment: TextInput.AlignVCenter
                        color: host.ink
                        font.pixelSize: 16
                        font.family: host.bodyFont
                        selectByMouse: true
                        clip: true
                        selectionColor: host.brass
                        selectedTextColor: host.buttonInk
                        Text {
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            visible: parent.text.length === 0
                            text: "Network name"
                            color: host.muted
                            font.family: host.bodyFont
                            font.pixelSize: 16
                        }
                        onTextEdited: host.wifiSsid = text
                    }
                }

                Text {
                    width: parent.width - 28
                    visible: host.wifiNote.length > 0
                    wrapMode: Text.WordWrap
                    text: host.wifiNote
                    color: host.wifiNameOk ? host.ink : host.danger
                    font.family: host.bodyFont
                    font.pixelSize: 14
                }

                Text {
                    text: "TCP/IP"
                    color: host.ink
                    font.family: host.bodyFont
                    font.pixelSize: 18
                    topPadding: 6
                }

                Text {
                    width: parent.width - 28
                    wrapMode: Text.WordWrap
                    text: "Automatic uses the address the network offers. Manual saves an address, a netmask, a gateway, and DNS for the installed system. Choose the adapter. That includes Wi-Fi and every network adapter."
                    color: host.muted
                    font.family: host.bodyFont
                    font.pixelSize: 14
                }

                Row {
                    spacing: 22

                    Repeater {
                        model: [
                            { key: "auto", label: "Automatic" },
                            { key: "manual", label: "Manual" }
                        ]
                        delegate: Item {
                            required property var modelData
                            width: dot.width + choiceLabel.implicitWidth + 10
                            height: 24

                            Rectangle {
                                id: dot
                                width: 16
                                height: 16
                                radius: 8
                                anchors.verticalCenter: parent.verticalCenter
                                color: "transparent"
                                border.width: 2
                                border.color: host.tcpMode === modelData.key ? host.brass : host.muted

                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 8
                                    height: 8
                                    radius: 4
                                    color: host.brass
                                    visible: host.tcpMode === modelData.key
                                }
                            }

                            Text {
                                id: choiceLabel
                                anchors.left: dot.right
                                anchors.leftMargin: 8
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.label
                                color: host.ink
                                font.family: host.bodyFont
                                font.pixelSize: 16
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    host.tcpMode = modelData.key
                                    host.networkLine = ""
                                }
                            }
                        }
                    }
                }

                Column {
                    width: parent.width - 28
                    visible: host.tcpMode === "manual"
                    spacing: 8

                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: "Choose an adapter. Choose it again to clear it. Adapters that are not connected are listed too."
                        color: host.muted
                        font.family: host.bodyFont
                        font.pixelSize: 14
                    }

                    Column {
                        width: parent.width
                        spacing: 8

                        Repeater {
                            model: host.tcpDevices
                            delegate: Rectangle {
                                required property var modelData
                                width: parent.width
                                height: 44
                                color: Qt.rgba(0, 0, 0, 0.18)
                                border.width: 1
                                border.color: host.tcpInterface === modelData.device ? host.brass : host.line

                                Text {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.leftMargin: 14
                                    anchors.rightMargin: 14
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.label + "  " + modelData.device
                                    color: host.ink
                                    font.family: host.bodyFont
                                    font.pixelSize: 16
                                    elide: Text.ElideRight
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: host.chooseAdapter(modelData.device)
                                }
                            }
                        }
                    }

                    Text {
                        width: parent.width
                        visible: host.tcpDevices.length === 0
                        wrapMode: Text.WordWrap
                        text: "No network adapters were found."
                        color: host.muted
                        font.family: host.bodyFont
                        font.pixelSize: 14
                    }

                    Repeater {
                        model: [
                            { key: "address", label: "IP address" },
                            { key: "netmask", label: "Netmask" },
                            { key: "gateway", label: "Gateway" },
                            { key: "dns", label: "DNS" }
                        ]
                        delegate: Rectangle {
                            required property var modelData
                            width: Math.min(420, parent.width)
                            height: 44
                            color: Qt.rgba(0, 0, 0, 0.28)
                            radius: 8
                            border.width: 1
                            border.color: host.line

                            TextInput {
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                anchors.rightMargin: 14
                                verticalAlignment: TextInput.AlignVCenter
                                color: host.ink
                                font.pixelSize: 16
                                font.family: host.bodyFont
                                selectByMouse: true
                                clip: true
                                selectionColor: host.brass
                                selectedTextColor: host.buttonInk
                                Text {
                                    anchors.left: parent.left
                                    anchors.verticalCenter: parent.verticalCenter
                                    visible: parent.text.length === 0
                                    text: modelData.label
                                    color: host.muted
                                    font.family: host.bodyFont
                                    font.pixelSize: 16
                                }
                                onTextEdited: {
                                    if (modelData.key === "address")
                                        host.tcpAddress = text
                                    else if (modelData.key === "netmask")
                                        host.tcpNetmask = text
                                    else if (modelData.key === "gateway")
                                        host.tcpGateway = text
                                    else
                                        host.tcpDns = text
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    width: tcpLabel.implicitWidth + 28
                    height: 36
                    radius: 9
                    color: host.networkBusy ? Qt.rgba(244 / 255, 242 / 255, 238 / 255, 0.35) : host.button
                    antialiasing: true

                    Text {
                        id: tcpLabel
                        anchors.centerIn: parent
                        text: "Save these settings"
                        color: host.buttonInk
                        font.family: host.bodyFont
                        font.pixelSize: 15
                        font.bold: true
                    }

                    MouseArea {
                        anchors.fill: parent
                        enabled: !host.networkBusy
                        cursorShape: Qt.PointingHandCursor
                        onClicked: host.applyTcp()
                    }
                }

                Text {
                    width: parent.width - 28
                    visible: host.tcpNote.length > 0
                    wrapMode: Text.WordWrap
                    text: host.tcpNote
                    color: host.tcpReady ? host.ink : host.danger
                    font.family: host.bodyFont
                    font.pixelSize: 14
                }

                Text {
                    width: parent.width - 28
                    visible: host.networkLine.length > 0
                    wrapMode: Text.WordWrap
                    text: host.networkLine
                    color: host.networkLineOk ? host.muted : host.danger
                    font.family: host.bodyFont
                    font.pixelSize: 14
                }
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
        onBack: host.page = 2
        onGo: host.page = 4
    }

    Component.onCompleted: hostName.text = host.hostname

    Connections {
        target: host
        function onWifiSsidChanged() {
            if (ssidField.text !== host.wifiSsid)
                ssidField.text = host.wifiSsid
        }
    }
}
