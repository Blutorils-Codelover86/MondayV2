import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts

Window {
    id: root
    title: "MONDAY companion"
    width: 372
    height: expanded ? panel.height + 88 : 90
    color: "transparent"
    visible: true
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    x: Screen.width - width - 28
    y: Screen.height - height - 64
    property bool expanded: true
    property var state: ({phase: "idle", response: "Ready when you are.", progress: "", approval: null, alert: null, monitoring: true})
    property string localError: ""
    property string endpoint: ""
    property string secret: ""
    property bool preview: Qt.application.arguments.indexOf("--preview") >= 0
    property bool smoke: Qt.application.arguments.indexOf("--smoke") >= 0
    property bool smokeSent: false
    property bool smokeCaptured: false
    property bool polling: false
    property int failures: 0
    property bool blink: false
    readonly property bool busy: state.phase === "busy" || state.phase === "approval"
    readonly property string accent: state.phase === "approval" ? "#ffc785" : state.phase === "error" ? "#ff929d" : "#98d4ff"

    function request(method, path, payload, callback) {
        if (preview || !endpoint) return
        let xhr = new XMLHttpRequest()
        xhr.open(method, endpoint + path)
        xhr.setRequestHeader("Authorization", "Bearer " + secret)
        if (method === "POST") xhr.setRequestHeader("Content-Type", "application/json")
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE) return
            if (path === "/state") polling = false
            if (xhr.status === 200) {
                failures = 0
                try {
                    let previousAlert = root.state.alert ? root.state.alert.key : ""
                    root.state = JSON.parse(xhr.responseText)
                    if (root.state.alert && root.state.alert.key !== previousAlert) root.expanded = true
                } catch (e) { root.localError = "Could not read MONDAY's response." }
                if (root.smoke && path === "/state" && !root.smokeSent && root.state.ready) {
                    root.smokeSent = true
                    input.text = "system ram usage"
                    input.accepted()
                } else if (root.smoke && root.smokeSent && !root.smokeCaptured && root.state.phase === "done" && root.state.response.indexOf("RAM is") === 0) {
                    root.smokeCaptured = true
                    console.log("MONDAY_UI_SMOKE_OK: " + root.state.response)
                    smokeCapture.start()
                }
                if (callback) callback()
            } else if (xhr.status > 0) {
                try { root.localError = JSON.parse(xhr.responseText).error } catch (e) { root.localError = "MONDAY could not handle that request." }
            } else {
                failures += 1
                if (failures > 4) { root.localError = "Connection lost. Restart with monday pet on."; poll.stop() }
            }
        }
        xhr.send(method === "POST" ? JSON.stringify(payload || {}) : "")
    }
    function submit(command) {
        if (!command.trim() || busy) return
        localError = ""
        input.text = ""
        expanded = true
        root.state = {phase: "busy", response: "", progress: "Understanding your request", monitoring: state.monitoring}
        request("POST", "/command", {objective: command})
    }
    Component.onCompleted: {
        for (let i = 0; i < Qt.application.arguments.length; ++i) {
            if (Qt.application.arguments[i].indexOf("http://127.0.0.1:") === 0) {
                endpoint = Qt.application.arguments[i]; secret = Qt.application.arguments[i + 1]; break
            }
        }
        if (preview) {
            state = {phase: "done", response: "RAM is 51% used; 3.67 GiB is available.", progress: "", monitoring: true, approval: null, alert: null}
            previewTimer.start()
        } else {
            request("POST", "/ready", {})
            poll.start()
        }
    }
    onClosing: request("POST", "/shutdown", {})
    Timer {
        id: smokeCapture; interval: 200
        onTriggered: root.contentItem.grabToImage(function(result) {
            let args = Qt.application.arguments
            result.saveToFile(args[args.indexOf("--smoke") + 1])
            Qt.quit()
        })
    }
    Timer { id: poll; interval: 800; repeat: true; onTriggered: { if (!root.polling) { root.polling = true; root.request("GET", "/state", null) } } }
    Timer {
        id: previewTimer; interval: 600
        onTriggered: root.contentItem.grabToImage(function(result) {
            let args = Qt.application.arguments
            let index = args.indexOf("--preview")
            result.saveToFile(args[index + 1])
            Qt.quit()
        })
    }
    Timer { interval: 3500; repeat: true; running: true; onTriggered: { root.blink = true; reopen.start() } }
    Timer { id: reopen; interval: 120; onTriggered: root.blink = false }

    Rectangle {
        id: panel
        visible: root.expanded
        width: parent.width - 12
        x: 6; y: 4
        height: contents.implicitHeight + 26
        radius: 20
        color: "#11151d"
        border.color: "#343e50"; border.width: 1
        ColumnLayout {
            id: contents
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 14 }
            spacing: 10
            RowLayout {
                Layout.fillWidth: true; spacing: 7
                Rectangle { implicitWidth: 6; implicitHeight: 6; radius: 3; color: root.busy ? root.accent : "#9be6b3" }
                Text { text: "MONDAY"; color: "#e9edf5"; font.pixelSize: 12; font.weight: Font.DemiBold; font.letterSpacing: 2 }
                Item {
                    Layout.fillWidth: true; implicitHeight: 22
                    MouseArea { anchors.fill: parent; cursorShape: Qt.SizeAllCursor; onPressed: root.startSystemMove() }
                }
                ToolButton {
                    text: root.state.monitoring ? "◉" : "○"
                    implicitWidth: 28; implicitHeight: 26
                    palette.buttonText: root.state.monitoring ? "#9be6b3" : "#8892a4"
                    ToolTip.visible: hovered; ToolTip.text: root.state.monitoring ? "Pause proactive health hints" : "Resume proactive health hints"
                    onClicked: root.request("POST", "/watch", {enabled: !root.state.monitoring})
                }
                ToolButton { text: "−"; implicitWidth: 24; implicitHeight: 26; palette.buttonText: "#9da9bd"; onClicked: root.expanded = false }
                ToolButton { text: "×"; implicitWidth: 24; implicitHeight: 26; palette.buttonText: "#9da9bd"; onClicked: { root.request("POST", "/shutdown", {}, function() { Qt.quit() }) } }
            }
            Text {
                Layout.fillWidth: true
                text: root.localError || (root.state.approval ? "This needs your approval." : root.busy ? root.state.progress : root.state.response || "Ready when you are.")
                color: root.localError || root.state.phase === "error" ? "#ffadb5" : "#e4e9f3"
                textFormat: Text.PlainText; wrapMode: Text.Wrap
                font.pixelSize: 13; lineHeight: 1.25
                maximumLineCount: 5; elide: Text.ElideRight
            }
            ScrollView {
                visible: !!root.state.approval
                Layout.fillWidth: true; Layout.preferredHeight: visible ? 92 : 0
                TextArea {
                    text: root.state.approval ? root.state.approval.prompt : ""
                    readOnly: true; textFormat: TextEdit.PlainText; wrapMode: TextEdit.Wrap
                    color: "#ffd9a8"; font.pixelSize: 12
                    background: Rectangle { radius: 8; color: "#262017" }
                }
            }
            RowLayout {
                visible: !!root.state.approval; spacing: 8
                Button { text: "Approve"; onClicked: root.request("POST", "/approve", {id: root.state.approval.id, accepted: true}) }
                Button { text: "Deny"; onClicked: root.request("POST", "/approve", {id: root.state.approval.id, accepted: false}) }
            }
            Rectangle {
                visible: !!root.state.alert
                Layout.fillWidth: true
                implicitHeight: alertContents.implicitHeight + 20
                radius: 10; color: "#1d2730"
                ColumnLayout {
                    id: alertContents; anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10 }
                    Text { text: root.state.alert ? root.state.alert.message : ""; textFormat: Text.PlainText; color: "#cbe7ff"; wrapMode: Text.Wrap; Layout.fillWidth: true; font.pixelSize: 12 }
                    RowLayout {
                        Button { text: "Check it"; onClicked: { if (root.state.alert) root.submit(root.state.alert.command) } }
                        Button { text: "Dismiss"; onClicked: root.request("POST", "/dismiss", {}) }
                    }
                }
            }
            Rectangle {
                Layout.fillWidth: true; implicitHeight: 43; radius: 12
                color: "#080c13"; border.color: input.activeFocus ? "#6c93b7" : "#2c3444"
                TextField {
                    id: input
                    anchors { left: parent.left; right: send.left; top: parent.top; bottom: parent.bottom; leftMargin: 8 }
                    placeholderText: "Tell me what you need…"
                    color: "#edf3ff"; placeholderTextColor: "#758299"
                    font.pixelSize: 13; background: Item {}
                    enabled: !root.busy
                    maximumLength: 4000
                    onAccepted: root.submit(text)
                }
                ToolButton {
                    id: send
                    anchors { right: parent.right; verticalCenter: parent.verticalCenter; rightMargin: 4 }
                    text: root.busy ? "■" : "↑"
                    implicitWidth: 34; implicitHeight: 34
                    palette.buttonText: root.accent
                    onClicked: root.busy ? root.request("POST", "/cancel", {}) : root.submit(input.text)
                    ToolTip.visible: hovered; ToolTip.text: root.busy ? "Stop this task" : "Send command"
                }
            }
            RowLayout {
                spacing: 7
                Repeater {
                    model: ["RAM", "CPU", "Storage", "GPU"]
                    delegate: Rectangle {
                        required property string modelData
                        width: quickText.implicitWidth + 20; height: 26; radius: 8
                        color: chipMouse.containsMouse ? "#28364a" : "#1b2432"
                        Text { id: quickText; anchors.centerIn: parent; text: modelData; color: "#b8c7db"; font.pixelSize: 11 }
                        MouseArea { id: chipMouse; anchors.fill: parent; hoverEnabled: true; enabled: !root.busy; cursorShape: Qt.PointingHandCursor; onClicked: root.submit("system " + modelData.toLowerCase() + " usage") }
                    }
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: "explain"; color: "#8296b3"; font.pixelSize: 11
                    MouseArea { anchors.fill: parent; enabled: !root.busy; cursorShape: Qt.PointingHandCursor; onClicked: root.submit("explain") }
                }
            }
        }
    }
    Rectangle { visible: root.expanded; width: 14; height: 14; radius: 2; rotation: 45; color: "#11151d"; x: root.width - 72; y: panel.y + panel.height - 7 }
    Item {
        id: bot
        width: 88; height: 80
        anchors.right: parent.right; anchors.rightMargin: 17
        anchors.bottom: parent.bottom; anchors.bottomMargin: 3
        Rectangle {
            id: body
            anchors.horizontalCenter: parent.horizontalCenter
            y: 3; width: 72; height: 72; radius: 36
            gradient: Gradient {
                GradientStop { position: 0; color: "#263442" }
                GradientStop { position: 0.55; color: "#111922" }
                GradientStop { position: 1; color: "#090e15" }
            }
            border.color: "#718698"; border.width: 1
            property color eyeColor: root.state.phase === "approval" ? "#ffd6a0" : root.state.phase === "error" ? "#ffb6bb" : "#d0efff"
            Row {
                anchors.centerIn: parent
                anchors.verticalCenterOffset: -1
                spacing: 9
                Repeater {
                    model: 2
                    Rectangle {
                        width: 17; height: root.blink ? 2 : 11; radius: root.blink ? 1 : 4
                        color: body.eyeColor
                        Behavior on height { NumberAnimation { duration: 65 } }
                        Behavior on color { ColorAnimation { duration: 180 } }
                    }
                }
            }
        }
        MouseArea {
            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
            onClicked: { root.expanded = !root.expanded; if (root.expanded) input.forceActiveFocus() }
            onPressAndHold: root.startSystemMove()
        }
    }
}
