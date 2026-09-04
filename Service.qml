import QtQuick
import Quickshell
import Quickshell.Io

// This plugin's only real shell-side job: notice if the lock screen's
// Howdy patch got reverted and tell the user, rather than let face unlock
// silently go dead until they notice at the worst possible moment.
//
// Two different files can carry that patch, and only one is ever actually
// loaded for the `lock` IPC target at a time (see README's "Lock-screen
// replacement plugins" section and issue #1):
//   - the stock lock/Service.qml, package-owned -- an `omarchy update`
//     overwrites it, which this plugin's `setup` and its post-update hook
//     both repair.
//   - Lock Screen Explorer's own Service.qml, when that `clonedFrom:
//     omarchy.lock` replacement plugin is installed and enabled -- its
//     own updates (`omarchy plugin update`, not `omarchy update`) can
//     revert it, and Omarchy has no post-plugin-update hook to repair
//     that automatically the way the stock file's hook does.
// Check whichever one is actually active, so this watchdog reflects
// reality instead of reporting the dormant file as healthy while the
// live one silently has no Howdy patch at all.
Item {
  id: root

  property var shell: null

  // Packaged default; on a dev checkout the running shell reads the lock
  // plugin from $OMARCHY_PATH/shell instead, so the check below resolves it.
  readonly property string lockQml: "/usr/share/omarchy/shell/plugins/lock/Service.qml"
  readonly property string explorerQml: Quickshell.env("HOME") + "/.config/omarchy/plugins/io.github.sirjul1337.lock-explorer/Service.qml"
  readonly property string pamFile: "/etc/pam.d/omarchy-lock-howdy"

  property bool healthy: true
  property bool warnedOnce: false

  function checkHealth() {
    if (!healthCheckProc.running) healthCheckProc.running = true
  }

  Process {
    id: healthCheckProc
    command: ["bash", "-c", [
      "qml=${OMARCHY_PATH:-/usr/share/omarchy}/shell/plugins/lock/Service.qml",
      "[[ -f $qml ]] || qml=" + root.lockQml,
      // Lock Screen Explorer replaces the stock lock plugin only while it
      // is actually enabled -- `omarchy plugin list --json` is the source
      // of truth for that, not just whether it's installed on disk.
      "explorer_qml=" + root.explorerQml,
      "if [[ -f $explorer_qml ]] && command -v omarchy >/dev/null 2>&1; then " +
        "active=$(omarchy plugin list --json 2>/dev/null | grep -o '\"id\":\"io.github.sirjul1337.lock-explorer\"[^}]*\"enabled\":true'); " +
        "[[ -n $active ]] && qml=$explorer_qml; " +
      "fi",
      "[[ -f " + root.pamFile + " ]] && grep -q omarchy-lock-howdy \"$qml\" && echo ok || echo broken"
    ].join("; ")]
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
      "An Omarchy (or plugin) update likely reverted the lock screen patch Howdy Face Unlock depends on. Re-run this plugin's setup script to fix it."
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
