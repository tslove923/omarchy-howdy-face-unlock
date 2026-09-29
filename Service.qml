import QtQuick
import Quickshell
import Quickshell.Io

// This plugin's only real shell-side job: notice if face unlock has gone
// dead and tell the user, rather than let it fail silently until they hit
// it at the worst possible moment (the lock screen).
//
// There are two supported lock screens, and only one is loaded for the
// `lock` IPC target at a time:
//   - the stock lock/Service.qml, package-owned -- an `omarchy update`
//     overwrites it, which this plugin's `setup` and its post-update hook
//     both repair. Health = the howdy patch is present in that file.
//   - Lock Screen Explorer (io.github.sirjul1337.lock-explorer), a
//     `clonedFrom: omarchy.lock` replacement with its own native face UI.
//     Howdy backs it through a facelock-shaped surface written OUTSIDE
//     Explorer's tree (see bin/howdy-lock-face-adapter) -- never by
//     patching Explorer's files, so an Explorer update cannot revert it.
//     Health = that surface is present, not a QML patch.
// Whichever is live is the one whose health matters; checking the dormant
// one would report a false result. A broken verdict is only trusted after
// it repeats across several spaced checks well after startup, so a
// transient misread (a still-starting shell, a plugin mid-reload) can
// never raise an alarm.
Item {
  id: root

  property var shell: null

  // Packaged default; on a dev checkout the running shell reads the lock
  // plugin from $OMARCHY_PATH/shell instead, so the check below resolves it.
  readonly property string lockQml: "/usr/share/omarchy/shell/plugins/lock/Service.qml"
  readonly property string explorerQml: Quickshell.env("HOME") + "/.config/omarchy/plugins/io.github.sirjul1337.lock-explorer/Service.qml"
  readonly property string pamFile: "/etc/pam.d/omarchy-lock-howdy"
  // The facelock-shaped surface Explorer calls, when it is the live lock screen.
  readonly property string pamFace: "/etc/pam.d/omarchy-lock-face"

  property bool healthy: true
  property bool warnedOnce: false
  // A "broken" verdict is only believed after it has been seen this many
  // times in a row, spaced out, well after startup. This is deliberately
  // conservative: the failure modes that produced false alarms before were
  // all *transient* -- a shell that is still starting up answers
  // `omarchy plugin list` with "not responding" for about a second, and a
  // freshly reloaded plugin can transiently read the wrong lock target.
  // A single bad reading must never notify. A genuine breakage (an update
  // reverted the patch and the hook could not repair it) persists across
  // every later check, so it still gets caught -- just after confirmation
  // instead of on the first sample.
  property int brokenStreak: 0
  readonly property int brokenThreshold: 3
  // Let the shell finish coming up (and finish loading/reloading plugins)
  // before the first check. Checking during startup was the single biggest
  // source of false "broken" readings.
  readonly property int startupGraceMs: 20000
  readonly property int recheckMs: 15000

  function checkHealth() {
    if (!healthCheckProc.running) healthCheckProc.running = true
  }

  Process {
    id: healthCheckProc
    command: ["bash", "-c", [
      "pam_howdy=" + root.pamFile,
      "qml=${OMARCHY_PATH:-/usr/share/omarchy}/shell/plugins/lock/Service.qml",
      "[[ -f $qml ]] || qml=" + root.lockQml,
      // Explorer replaces the stock lock plugin only while it is actually
      // enabled -- `omarchy plugin list --json` is the source of truth for
      // that, not just whether it is installed on disk.
      "explorer_qml=" + root.explorerQml,
      "explorer_enabled=no",
      "if [[ -f $explorer_qml ]] && command -v omarchy >/dev/null 2>&1; then " +
        "if omarchy plugin list --json 2>/dev/null | grep -q '\"id\": *\"io.github.sirjul1337.lock-explorer\"[^}]*\"enabled\": *true'; then explorer_enabled=yes; fi; " +
      "fi",
      // Explorer live: health is the facelock-shaped surface backed by Howdy.
      "if [[ $explorer_enabled == yes ]]; then " +
        "if [[ -f " + root.pamFace + " ]] && grep -q 'pam_facelock.so' " + root.pamFace + " && " +
           "[[ -e /usr/lib/security/pam_facelock.so ]] && " +
           "compgen -G '/var/lib/facelock/models/*.onnx' >/dev/null 2>&1; then echo ok; else echo broken; fi; " +
        "exit 0; " +
      "fi",
      // Stock lock live: health is the howdy patch present in the QML.
      "[[ -f " + root.pamFile + " ]] && grep -q omarchy-lock-howdy \"$qml\" && echo ok || echo broken"
    ].join("; ")]
    stdout: StdioCollector {
      id: healthStdout
      waitForEnd: true
      onStreamFinished: {
        const ok = String(text || "").trim() === "ok"
        if (ok) {
          root.healthy = true
          root.brokenStreak = 0
          return
        }
        // Not ok. Require the same verdict several times in a row before
        // believing it, and re-check on an interval in between.
        root.brokenStreak += 1
        if (root.brokenStreak < root.brokenThreshold) {
          recheckTimer.start()
          return
        }
        root.healthy = false
        if (!root.warnedOnce) {
          root.warnedOnce = true
          notifyProc.running = true
        }
      }
    }
  }

  // First check only after the shell has settled.
  Timer {
    id: startupTimer
    interval: root.startupGraceMs
    repeat: false
    onTriggered: root.checkHealth()
  }

  // Spacing between consecutive "broken" samples while confirming a verdict.
  Timer {
    id: recheckTimer
    interval: root.recheckMs
    repeat: false
    onTriggered: root.checkHealth()
  }

  Process {
    id: notifyProc
    command: [
      "omarchy-notification-send", "-u", "normal", "-g", "󰄀",
      "Face Unlock Needs Repair",
      "The lock screen patch Howdy Face Unlock uses is missing and the automatic repair after an update did not restore it. Run this plugin's setup script to fix it."
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

  Component.onCompleted: startupTimer.start()
}
