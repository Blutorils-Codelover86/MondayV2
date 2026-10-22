import QtQuick

Item {
    id: face
    property string mood: "idle"
    property bool blinking: false
    property real lookX: 0
    property real lookY: 0
    property real scan: 0
    property real breath: 0
    readonly property bool happy: mood === "success"
    readonly property bool thinking: mood === "thinking"
    readonly property color eyeColor: mood === "error" ? "#ff9cae" :
        mood === "approval" || mood === "warning" ? "#ffd193" :
        happy ? "#a7efca" : mood === "offline" ? "#6e8294" : "#c8efff"
    readonly property real eyeHeight: mood === "listening" ? 17 :
        mood === "approval" ? 19 : mood === "offline" ? 5 : thinking ? 9 : 12
    SequentialAnimation on breath {
        running: face.visible && face.mood !== "offline"; loops: Animation.Infinite
        NumberAnimation { to: 1; duration: 1800; easing.type: Easing.InOutSine }
        NumberAnimation { to: 0; duration: 1800; easing.type: Easing.InOutSine }
    }
    SequentialAnimation on scan {
        running: face.visible && face.thinking; loops: Animation.Infinite
        NumberAnimation { to: 3; duration: 650; easing.type: Easing.InOutSine }
        NumberAnimation { to: -3; duration: 950; easing.type: Easing.InOutSine }
        NumberAnimation { to: 0; duration: 450 }
    }
    Rectangle {
        anchors.centerIn: parent; width: 89; height: 89; radius: 45
        color: "transparent"; border.color: face.eyeColor
        border.width: face.mood === "listening" || face.thinking ? 2 : 1
        opacity: face.mood === "offline" ? 0.15 : 0.15 + face.breath * 0.17
        scale: 1 + face.breath * 0.025
    }
    Rectangle {
        id: body
        anchors.centerIn: parent; width: 78; height: 78; radius: 39
        scale: 1 + face.breath * 0.012
        rotation: face.mood === "curious" ? -7 : face.mood === "error" ? 5 : 0
        Behavior on rotation { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
        gradient: Gradient {
            GradientStop { position: 0; color: "#2c4050" }
            GradientStop { position: 0.55; color: "#14202b" }
            GradientStop { position: 1; color: "#09121b" }
        }
        border.color: face.eyeColor; border.width: 1
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter; y: 7
            width: 30; height: 1; color: "#b8d8ea"; opacity: 0.12
        }
        Row {
            anchors.centerIn: parent
            anchors.horizontalCenterOffset: face.lookX + (face.thinking ? face.scan : 0)
            anchors.verticalCenterOffset: face.lookY - 1
            spacing: 9
            Repeater {
                model: 2
                Item {
                    required property int index
                    width: 19; height: 23
                    Rectangle {
                        anchors.centerIn: parent; width: face.mood === "approval" ? 15 : 19
                        height: face.blinking ? 2 : face.eyeHeight - (face.thinking && index === 1 ? 3 : 0)
                        radius: face.mood === "approval" ? 8 : 5
                        visible: !face.happy || face.blinking
                        rotation: face.mood === "error" ? (index === 0 ? -15 : 15) : face.mood === "warning" ? (index === 0 ? 10 : -10) : 0
                        color: face.eyeColor
                        Behavior on height { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                        Behavior on rotation { NumberAnimation { duration: 220 } }
                        Behavior on color { ColorAnimation { duration: 240 } }
                    }
                    Canvas {
                        anchors.fill: parent; visible: face.happy && !face.blinking
                        onVisibleChanged: if (visible) requestPaint()
                        onPaint: {
                            let ctx = getContext("2d")
                            ctx.clearRect(0, 0, width, height)
                            ctx.strokeStyle = "#a7efca"; ctx.lineWidth = 4; ctx.lineCap = "round"
                            ctx.beginPath(); ctx.moveTo(2, 15); ctx.quadraticCurveTo(9.5, 2, 17, 15); ctx.stroke()
                        }
                    }
                }
            }
        }
        Rectangle {
            visible: face.mood === "approval" || face.mood === "warning"
            width: 4; height: 4; radius: 2; color: face.eyeColor
            anchors.horizontalCenter: parent.horizontalCenter; y: 60
        }
    }
}
