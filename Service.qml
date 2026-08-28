import QtQuick
import Quickshell
import Quickshell.Io

// This plugin's only real shell-side job: notice if the lock screen's
// Howdy patch got reverted (an `omarchy update` overwrites
// lock/Service.qml, which is package-owned -- this plugin's `setup`
// script re-patches it, but nothing runs that automatically after an
// update) and tell the user, rather than let face unlock silently go
// dead until they notice at the worst possible moment.
Item {
  id: root

  property var shell: null

  // Packaged default; on a dev checkout the running shell reads the lock
  // plugin from $OMARCHY_PATH/shell instead, so the check below resolves it.
  readonly property string lockQml: "/usr/share/omarchy/shell/plugins/lock/Service.qml"
  readonly property string pamFile: "/etc/pam.d/omarchy-lock-howdy"

  property bool healthy: true
  property bool warnedOnce: false

  function checkHealth() {
    if (!healthCheckProc.running) healthCheckProc.running = true
  }

  Process {
    id: healthCheckProc
    command: ["bash", "-c",
      "qml=${OMARCHY_PATH:-/usr/share/omarchy}/shell/plugins/lock/Service.qml; " +
      "[[ -f $qml ]] || qml=" + root.lockQml + "; " +
      "[[ -f " + root.pamFile + " ]] && grep -q omarchy-lock-howdy \"$qml\" && echo ok || echo broken"]
    stdout: StdioCollector {
      id: healthStdout
      waitForEnd: true
      onStreamFinished: {
        root.healthy = String(text || "").trim() === "ok"
        if (!root.healthy && !root.warnedOnce) {
          root.warnedOnce = true
          notifyProc.running = true
        }
      }
    }
  }

  Process {
    id: notifyProc
    command: [
      "omarchy-notification-send", "-u", "critical", "-g", "󰄀",
      "Face Unlock Needs Repair",
      "An Omarchy update likely reverted the lock screen patch Howdy Face Unlock depends on. Re-run this plugin's setup script to fix it."
    ]
  }

  IpcHandler {
    target: "howdy"

    function status(): string {
      return root.healthy ? "ok" : "broken"
    }

    function check(): string {
      root.checkHealth()
      return "checking"
    }
  }

  Component.onCompleted: checkHealth()
}
