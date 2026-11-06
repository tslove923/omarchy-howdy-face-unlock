import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io

FloatingWindow {
  id: wizard
  title: "Howdy · Face unlock"
  visible: false
  width: 860
  height: 610
  color: "transparent"

  property string backend: Qt.resolvedUrl("backend.py").toString().replace("file://", "")
  property string terminal: Qt.resolvedUrl("terminal").toString().replace("file://", "")
  property string userName: Quickshell.env("USER")
  property var cameras: []
  property var install: ({})
  property var scan: ({result: "starting"})
  property int step: 0
  property string selectedCamera: ""
  property string errorText: ""
  property int frameNumber: 0
  property color bg: "#17191f"
  property color panel: "#222630"
  property color fg: "#f1f2f5"
  property color muted: "#a1a8b5"
  property color accent: "#a8c7fa"
  property color line: "#38404c"
  property color good: "#93d7ab"
  property color warn: "#f0c785"

  function open() {
    visible = true
    step = 0
    refresh()
    if (!themeProc.running) themeProc.running = true
  }
  function refresh() {
    if (!cameraProc.running) cameraProc.running = true
    if (!statusProc.running) statusProc.running = true
  }
  function startPreview() {
    stopPreview()
    if (!selectedCamera || !install.installed || commandProc.running) return
    previewProc.command = ["python3", backend, "stream", selectedCamera, userName, step === 2 ? "verify" : "preview"]
    previewRestart.start()
  }
  function stopPreview() {
    previewRestart.stop()
    if (previewProc.running) previewProc.running = false
    scan = ({result: "starting"})
    cameraImage.source = ""
  }
  function launch(action) {
    stopPreview()
    commandProc.command = action === "setup" ? [terminal, "setup", selectedCamera] : [terminal, "enroll"]
    commandProc.running = true
  }
  function resultTitle() {
    switch (scan.result) {
    case "match": return "Face matched"
    case "no-match": return "Face found · no match"
    case "no-face": return "No face detected"
    case "no-model": return "No enrolled face yet"
    case "dark": return "Image is too dark"
    default: return "Starting camera…"
    }
  }
  function resultHint() {
    switch (scan.result) {
    case "match": return "Howdy recognizes you at its configured threshold."
    case "no-match": return "Try facing the camera or add another scan in different lighting."
    case "no-face": return "Move into view and face the IR camera."
    case "no-model": return "Add a face scan to enable recognition."
    case "dark": return "Check the IR emitter or move to better lighting."
    default: return "The preview is local to this window."
    }
  }
  onVisibleChanged: {
    if (!visible) stopPreview()
    else refresh()
  }
  onStepChanged: {
    if (visible) startPreview()
    else stopPreview()
  }
  onSelectedCameraChanged: if (visible) startPreview()
  Component.onDestruction: stopPreview()

  Process {
    id: cameraProc
    command: ["python3", wizard.backend, "cameras"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          const parsed = JSON.parse(String(text))
          if (Array.isArray(parsed)) {
            wizard.cameras = parsed
            if (!wizard.selectedCamera || !parsed.some(c => c.path === wizard.selectedCamera)) {
              const recommended = parsed.find(c => c.recommended)
              wizard.selectedCamera = recommended ? recommended.path : (parsed.length ? parsed[0].path : "")
            }
          } else wizard.errorText = parsed.error || "Camera discovery failed"
          if (wizard.visible && wizard.selectedCamera && !previewProc.running) wizard.startPreview()
        } catch (e) { wizard.errorText = "Could not read camera list" }
      }
    }
  }
  Process {
    id: statusProc
    command: ["python3", wizard.backend, "status"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          wizard.install = JSON.parse(String(text))
          if (!previewProc.running && !commandProc.running && wizard.selectedCamera && wizard.install.installed && !wizard.errorText) wizard.startPreview()
        } catch (e) { wizard.errorText = "Could not read Howdy status" }
      }
    }
  }
  Process {
    id: stateProc
    command: ["python3", wizard.backend, "state"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          wizard.scan = JSON.parse(String(text))
          if (wizard.install.preview && wizard.scan.at) {
            cameraImage.source = ""
            cameraImage.source = "file://" + wizard.install.preview
          }
        } catch (e) {}
      }
    }
  }
  Process {
    id: themeProc
    command: ["python3", wizard.backend, "theme"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          const colors = JSON.parse(String(text))
          wizard.bg = colors.background || wizard.bg
          wizard.panel = colors.lighter_background || wizard.panel
          wizard.fg = colors.foreground || wizard.fg
          wizard.muted = colors.dark_foreground || wizard.muted
          wizard.accent = colors.accent || wizard.accent
          wizard.line = colors.muted || wizard.line
          wizard.good = colors.green || wizard.good
          wizard.warn = colors.yellow || wizard.warn
        } catch (e) {}
      }
    }
  }
  Process {
    id: previewProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        const output = String(text).trim()
        if (output) {
          try { wizard.errorText = JSON.parse(output).error || output }
          catch (e) { wizard.errorText = output }
        }
      }
    }
  }
  Timer {
    id: previewRestart
    interval: 300
    onTriggered: if (wizard.visible && !commandProc.running) previewProc.running = true
  }
  Process {
    id: commandProc
    onRunningChanged: {
      if (!running && wizard.visible) {
        wizard.refresh()
        wizard.startPreview()
      }
    }
  }
  Timer {
    interval: 850
    running: wizard.visible
    repeat: true
    onTriggered: {
      if (!stateProc.running) stateProc.running = true
    }
  }
  Timer {
    interval: 2500
    running: wizard.visible
    repeat: true
    onTriggered: {
      if (!statusProc.running) statusProc.running = true
    }
  }

  Rectangle {
    anchors.fill: parent
    color: wizard.bg
    radius: 18
    border.color: wizard.line
    border.width: 1

    ColumnLayout {
      anchors.fill: parent
      anchors.margins: 30
      spacing: 0
      RowLayout {
        Layout.fillWidth: true
        Text { text: "◉"; color: wizard.accent; font.pixelSize: 26 }
        ColumnLayout {
          Layout.leftMargin: 9
          spacing: 1
          Text { text: "Face unlock"; color: wizard.fg; font.pixelSize: 23; font.weight: Font.DemiBold }
          Text { text: "Set up Howdy for Omarchy"; color: wizard.muted; font.pixelSize: 12 }
        }
        Item { Layout.fillWidth: true }
        Text { text: "×"; color: wizard.muted; font.pixelSize: 26
          MouseArea { anchors.fill: parent; onClicked: wizard.visible = false }
        }
      }
      RowLayout {
        Layout.fillWidth: true
        Layout.topMargin: 27
        Layout.bottomMargin: 22
        spacing: 10
        Repeater {
          model: ["01  Camera", "02  Enroll", "03  Verify"]
          delegate: Rectangle {
            required property int index
            required property string modelData
            Layout.fillWidth: true
            height: 35
            radius: 8
            color: wizard.step === index ? wizard.accent : wizard.panel
            Text { anchors.centerIn: parent; text: modelData; color: wizard.step === index ? wizard.bg : wizard.muted; font.pixelSize: 13; font.weight: Font.DemiBold }
            MouseArea { anchors.fill: parent; onClicked: { if (index <= 1 || wizard.install.enrolled) wizard.step = index } }
          }
        }
      }
      Rectangle { Layout.fillWidth: true; height: 1; color: wizard.line }

      RowLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.topMargin: 23
        spacing: 24
        ColumnLayout {
          Layout.preferredWidth: 305
          Layout.fillHeight: true
          spacing: 12
          Text {
            text: wizard.step === 0 ? "Choose your camera" : wizard.step === 1 ? "Add your face" : "Test recognition"
            color: wizard.fg; font.pixelSize: 20; font.weight: Font.DemiBold
          }
          Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            color: wizard.muted; font.pixelSize: 13
            text: wizard.step === 0 ? "The greyscale-only sensor is usually your IR camera. Configure it, then check its preview before enrolling." :
                  wizard.step === 1 ? "Look straight at the camera and hold still. Howdy stores a face encoding, not the preview image." :
                                      "This uses Howdy’s detector, your saved model, and its configured match threshold."
          }
          Repeater {
            model: wizard.step === 0 ? wizard.cameras : []
            delegate: Rectangle {
              required property var modelData
              Layout.fillWidth: true
              height: 65
              radius: 9
              color: wizard.selectedCamera === modelData.path ? Qt.alpha(wizard.accent, .13) : wizard.panel
              border.color: wizard.selectedCamera === modelData.path ? wizard.accent : wizard.line
              Column {
                anchors.fill: parent; anchors.margins: 10; spacing: 3
                Text { text: modelData.name + (modelData.recommended ? "  ·  RECOMMENDED IR" : ""); color: wizard.fg; font.pixelSize: 12; font.weight: Font.DemiBold; elide: Text.ElideRight; width: parent.width }
                Text { text: modelData.path; color: wizard.muted; font.pixelSize: 10; elide: Text.ElideMiddle; width: parent.width }
                Text { text: modelData.formats.join(" · "); color: wizard.muted; font.pixelSize: 10 }
              }
              MouseArea { anchors.fill: parent; onClicked: { wizard.errorText = ""; wizard.selectedCamera = modelData.path } }
            }
          }
          Text {
            visible: wizard.step === 0 && wizard.cameras.length === 0
            text: "No video cameras found. Install v4l-utils, connect a camera, then rescan."
            color: wizard.warn; wrapMode: Text.WordWrap; Layout.fillWidth: true; font.pixelSize: 12
          }
          Text {
            visible: wizard.step === 1
            text: wizard.install.enrolled ? "✓ Face model saved" : "No face model saved yet"
            color: wizard.install.enrolled ? wizard.good : wizard.muted; font.pixelSize: 13
          }
          Text {
            visible: wizard.step === 2
            text: wizard.resultTitle()
            color: wizard.scan.result === "match" ? wizard.good : wizard.scan.result === "no-match" || wizard.scan.result === "dark" ? wizard.warn : wizard.fg
            font.pixelSize: 17; font.weight: Font.DemiBold
          }
          Text {
            visible: wizard.step === 2
            Layout.fillWidth: true
            text: wizard.resultHint() + (wizard.scan.distance !== null && wizard.scan.distance !== undefined ? "\nDistance " + wizard.scan.distance + " · threshold " + wizard.scan.threshold : "")
            color: wizard.muted; font.pixelSize: 12; wrapMode: Text.WordWrap
          }
          Item { Layout.fillHeight: true }
          Text {
            visible: wizard.errorText.length > 0
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: wizard.errorText
            color: wizard.warn; font.pixelSize: 12
          }
          Rectangle {
            Layout.fillWidth: true; height: 39; radius: 8
            color: wizard.accent
            opacity: wizard.selectedCamera ? 1 : .45
            Text { anchors.centerIn: parent; text: wizard.step === 0 ? (wizard.install.installed && wizard.install.camera === wizard.selectedCamera ? "Continue" : "Configure this camera") : wizard.step === 1 ? "Add my face" : "Test again"; color: wizard.bg; font.pixelSize: 13; font.weight: Font.DemiBold }
            MouseArea {
              anchors.fill: parent
              enabled: wizard.selectedCamera.length > 0
              onClicked: {
                wizard.errorText = ""
                if (wizard.step === 0) {
                  if (wizard.install.installed && wizard.install.camera === wizard.selectedCamera) wizard.step = 1
                  else wizard.launch("setup")
                } else if (wizard.step === 1) wizard.launch("enroll")
                else wizard.startPreview()
              }
            }
          }
          Text {
            visible: wizard.step === 0
            text: "Rescan cameras"
            color: wizard.accent; font.pixelSize: 12
            MouseArea { anchors.fill: parent; onClicked: wizard.refresh() }
          }
          Text {
            visible: wizard.step === 1 && wizard.install.enrolled
            text: "Continue to verification →"
            color: wizard.accent; font.pixelSize: 12
            MouseArea { anchors.fill: parent; onClicked: wizard.step = 2 }
          }
        }
        Rectangle {
          Layout.fillWidth: true
          Layout.fillHeight: true
          radius: 12
          color: wizard.panel
          border.color: wizard.line
          clip: true
          Image {
            id: cameraImage
            anchors.fill: parent
            fillMode: Image.PreserveAspectFit
            cache: false
          }
          Text {
            anchors.centerIn: parent
            visible: cameraImage.status !== Image.Ready
            text: !wizard.install.installed ? "Preview starts after camera setup" : "Waiting for camera…"
            color: wizard.muted; font.pixelSize: 13
          }
          Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom; anchors.bottomMargin: 15
            width: liveLabel.implicitWidth + 24; height: 29; radius: 15
            color: Qt.alpha(wizard.bg, .86)
            Text { id: liveLabel; anchors.centerIn: parent; text: wizard.step === 2 ? wizard.resultTitle() : "LOCAL CAMERA PREVIEW"; color: wizard.fg; font.pixelSize: 11; font.weight: Font.DemiBold }
          }
        }
      }
      Rectangle { Layout.fillWidth: true; height: 1; color: wizard.line }
      Text {
        Layout.topMargin: 12
        text: "Camera runs only while this window is open · Preview frames are kept in temporary runtime storage"
        color: wizard.muted; font.pixelSize: 11
      }
    }
  }
}
