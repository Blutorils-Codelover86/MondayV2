import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts

Window {
    id: root
    title: "MONDAY companion"
    // Requested geometry is content-derived, never read back from WM-assigned width/height.
    readonly property int requestedWidth: expanded ? 400 : 116
    readonly property int requestedHeight: expanded ? Math.ceil(panel.height + 104) : 104
    width: requestedWidth
    height: requestedHeight
    minimumWidth: requestedWidth
    maximumWidth: requestedWidth
    minimumHeight: requestedHeight
    maximumHeight: requestedHeight
    color: "transparent"
    visible: true
    flags: Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
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
    property bool connected: true
    property bool celebrating: false
    readonly property string expression: !connected ? "offline" : state.approval ? "approval" :
        busy ? "thinking" : state.status === "CANCELLED" || state.status === "BLOCKED" ? "warning" :
        localError || state.phase === "error" ? "error" :
        state.alert || state.status === "PARTIAL" ? "warning" : celebrating ? "success" :
        input.activeFocus ? "listening" : petMouse.containsMouse ? "curious" : "idle"
    onRequestedWidthChanged: geometryUpdate.restart()
    onRequestedHeightChanged: geometryUpdate.restart()
    Timer {
        id: geometryUpdate; interval: 120
        onTriggered: root.request("POST", "/geometry", {width: root.requestedWidth, height: root.requestedHeight})
    }
    Timer { id: celebration; interval: 2800; onTriggered: root.celebrating = false }
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
                root.connected = true
                try {
                    let previousAlert = root.state.alert ? root.state.alert.key : ""
                    let previousResponse = root.state.response
                    if (path !== "/geometry") root.state = JSON.parse(xhr.responseText)
                    if (root.state.phase === "done" && root.state.status === "SUCCESS" && root.state.response !== previousResponse) {
                        root.celebrating = true; celebration.restart()
                    }
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
                if (failures > 4) { root.connected = false; root.localError = "Connection lost; retrying locally…" }
            }
        }
        xhr.send(method === "POST" ? JSON.stringify(payload || {}) : "")
    }
    function submit(command) {
        if (!command.trim()) return
        if (/^stop(?: the current task| current task)?[!.]?$/i.test(command.trim())) { input.text = ""; request("POST", "/cancel", {}); return }
        if (busy) return
        localError = ""
        input.text = ""
        expanded = true
        root.state = {phase: "busy", response: "", progress: "Understanding your request", monitoring: state.monitoring}
        request("POST", "/command", {objective: command})
    }
    function focusInput() { root.requestActivate(); input.forceActiveFocus() }
    function togglePanel() {
        if (root.state.approval) { root.expanded = true; return }
        root.expanded = !root.expanded
        if (root.expanded) Qt.callLater(root.focusInput)
    }
    Shortcut { sequence: "Escape"; onActivated: { if (!root.busy) root.expanded = false } }
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
            geometryUpdate.restart()
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
    Timer { id: poll; objectName: "pollTimer"; interval: 800; repeat: true; onTriggered: { if (!root.polling) { root.polling = true; root.request("GET", "/state", null) } } }
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
        width: root.requestedWidth - 12
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
                ToolButton { objectName: "collapseButton"; text: "−"; enabled: !root.state.approval; implicitWidth: 24; implicitHeight: 26; palette.buttonText: "#9da9bd"; onClicked: root.togglePanel() }
                ToolButton { text: "×"; implicitWidth: 24; implicitHeight: 26; palette.buttonText: "#9da9bd"; onClicked: { root.request("POST", "/shutdown", {}, function() { Qt.quit() }) } }
            }
            ScrollView {
                id: responseScroll
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(42, Math.min(164, responseText.implicitHeight))
                contentWidth: availableWidth
                TextArea {
                    id: responseText; objectName: "responseText"
                    width: responseScroll.availableWidth
                    text: root.localError || (root.state.approval ? "This needs your approval." : root.busy ? root.state.progress : root.state.response || "Ready when you are.")
                    color: root.localError || root.state.phase === "error" ? "#ffadb5" : "#e4e9f3"
                    textFormat: TextEdit.PlainText; wrapMode: TextEdit.Wrap
                    readOnly: true; selectByMouse: true; padding: 0
                    font.pixelSize: 13
                    background: Item {}
                }
            }
            Text {
                objectName: "taskStatus"
                Layout.fillWidth: true
                visible: !!root.state.status
                text: "Task: " + (root.state.status || "IDLE")
                color: root.accent; font.pixelSize: 11; textFormat: Text.PlainText
            }
            ScrollView {
                objectName: "taskSteps"
                visible: !!root.state.steps && root.state.steps.length > 0
                Layout.fillWidth: true; Layout.preferredHeight: visible ? Math.min(84, stepsText.implicitHeight) : 0
                contentWidth: availableWidth
                TextArea {
                    id: stepsText
                    width: parent.width
                    text: (root.state.steps || []).map(function(step, i) { return (i + 1) + ". " + step.tool + " — " + step.status }).join("\n")
                    readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText
                    color: "#aebed3"; font.pixelSize: 11; padding: 0; background: Item {}
                }
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
                Button { objectName: "approveButton"; text: "Approve"; onClicked: root.request("POST", "/approve", {id: root.state.approval.id, accepted: true}) }
                Button { objectName: "denyButton"; text: "Deny"; onClicked: root.request("POST", "/approve", {id: root.state.approval.id, accepted: false}) }
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
                    objectName: "commandInput"
                    anchors { left: parent.left; right: send.left; top: parent.top; bottom: parent.bottom; leftMargin: 8 }
                    placeholderText: "Tell me what you need…"
                    color: "#edf3ff"; placeholderTextColor: "#758299"
                    font.pixelSize: 13; background: Item {}
                    enabled: true
                    maximumLength: 4000
                    onAccepted: root.submit(text)
                }
                ToolButton {
                    id: send
                    objectName: "sendButton"
                    anchors { right: parent.right; verticalCenter: parent.verticalCenter; rightMargin: 4 }
                    text: root.busy ? "STOP" : "↑"
                    implicitWidth: root.busy ? 54 : 34; implicitHeight: 34
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
    Rectangle { visible: root.expanded; width: 14; height: 14; radius: 2; rotation: 45; color: "#11151d"; x: root.requestedWidth - 72; y: panel.y + panel.height - 7 }
    Item {
        id: bot
        width: 96; height: 96
        x: root.requestedWidth - width - 10
        y: root.requestedHeight - height - 2
        PetFace { id: face; objectName: "petFace"; anchors.fill: parent; mood: root.expression; blinking: root.blink }
        MouseArea {
            id: petMouse; objectName: "petMouse"
            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
            hoverEnabled: true
            onPositionChanged: function(mouse) { face.lookX = (mouse.x / width - 0.5) * 4; face.lookY = (mouse.y / height - 0.5) * 3 }
            onExited: { face.lookX = 0; face.lookY = 0 }
            onClicked: root.togglePanel()
            onPressAndHold: root.startSystemMove()
        }
    }
}
