#!/usr/bin/env python3
"""Idempotently patch Omarchy's lock/Service.qml to add a Howdy auth path
that mirrors the existing fingerprint one. Each (old, new) pair below is
applied only if `old` is present verbatim and `new` is not already there,
so a rerun after the package overwrites the file re-applies cleanly, and a
rerun after our own patch already landed is a safe no-op. Each `old` is
asserted unique before replacement so an upstream change to this file fails
loudly here instead of silently corrupting it.
"""
import sys

PATCHES = [
    (
        '  property bool fingerprintAuthenticating: false\n'
        '  property bool passwordPamConfigured: false\n'
        '  property bool fingerprintConfigured: false\n',
        '  property bool fingerprintAuthenticating: false\n'
        '  property bool howdyAuthenticating: false\n'
        '  property bool passwordPamConfigured: false\n'
        '  property bool fingerprintConfigured: false\n'
        '  property bool howdyConfigured: false\n'
        '  property int howdyAttempts: 0\n'
        '  property bool howdyFaceLockedOut: false\n'
        '  readonly property int maxFaceAttempts: 5\n'
    ),
    (
        '  readonly property bool authenticating: authenticatingPassword || fingerprintAuthenticating\n',
        '  readonly property bool authenticating: authenticatingPassword || fingerprintAuthenticating || howdyAuthenticating\n'
    ),
    (
        '  function refreshFingerprintStatus() {\n'
        '    if (!fingerprintCheckProc.running) fingerprintCheckProc.running = true\n'
        '  }\n',
        '  function refreshFingerprintStatus() {\n'
        '    if (!fingerprintCheckProc.running) fingerprintCheckProc.running = true\n'
        '  }\n'
        '\n'
        '  function refreshHowdyStatus() {\n'
        '    if (!howdyCheckProc.running) howdyCheckProc.running = true\n'
        '  }\n'
    ),
    (
        '    authenticatingPassword = false\n'
        '    fingerprintAuthenticating = false\n'
        '    fingerprintRetryTimer.stop()\n'
        '    if (passwordPam.active) passwordPam.abort()\n'
        '    if (fingerprintPam.active) fingerprintPam.abort()\n'
        '  }\n',
        '    authenticatingPassword = false\n'
        '    fingerprintAuthenticating = false\n'
        '    howdyAuthenticating = false\n'
        '    howdyAttempts = 0\n'
        '    howdyFaceLockedOut = false\n'
        '    fingerprintRetryTimer.stop()\n'
        '    howdyRetryTimer.stop()\n'
        '    if (passwordPam.active) passwordPam.abort()\n'
        '    if (fingerprintPam.active) fingerprintPam.abort()\n'
        '    if (howdyPam.active) howdyPam.abort()\n'
        '  }\n'
    ),
    (
        '    Qt.callLater(function() {\n'
        '      root.refreshBackground()\n'
        '      root.refreshFingerprintStatus()\n'
        '    })\n',
        '    Qt.callLater(function() {\n'
        '      root.refreshBackground()\n'
        '      root.refreshFingerprintStatus()\n'
        '      root.refreshHowdyStatus()\n'
        '    })\n'
    ),
    (
        '  function handleFingerprintFinished(result) {\n'
        '    fingerprintAuthenticating = false\n'
        '\n'
        '    if (!lockRequested) return\n'
        '    if (result === PamResult.Success) {\n'
        '      finishUnlock()\n'
        '    } else if (fingerprintConfigured) {\n'
        '      fingerprintRetryTimer.restart()\n'
        '    }\n'
        '  }\n',
        '  function handleFingerprintFinished(result) {\n'
        '    fingerprintAuthenticating = false\n'
        '\n'
        '    if (!lockRequested) return\n'
        '    if (result === PamResult.Success) {\n'
        '      finishUnlock()\n'
        '    } else if (fingerprintConfigured) {\n'
        '      fingerprintRetryTimer.restart()\n'
        '    }\n'
        '  }\n'
        '\n'
        '  function startHowdy() {\n'
        '    if (!lockRequested || !sessionLock.secure || !howdyConfigured) return\n'
        '    if (howdyPam.active || howdyAuthenticating) return\n'
        '    if (howdyFaceLockedOut) return\n'
        '\n'
        '    howdyAuthenticating = true\n'
        '    if (!howdyPam.start()) {\n'
        '      howdyAuthenticating = false\n'
        '    }\n'
        '  }\n'
        '\n'
        '  function handleHowdyFinished(result) {\n'
        '    howdyAuthenticating = false\n'
        '\n'
        '    if (!lockRequested) return\n'
        '    if (result === PamResult.Success) {\n'
        '      finishUnlock()\n'
        '      return\n'
        '    }\n'
        '    if (!howdyConfigured) return\n'
        '\n'
        '    howdyAttempts += 1\n'
        '    if (howdyAttempts >= maxFaceAttempts) {\n'
        '      howdyFaceLockedOut = true\n'
        '      logEvent("howdy-locked-out")\n'
        '      failureMessage = "Too many face attempts \\u2014 use your password"\n'
        '      return\n'
        '    }\n'
        '    howdyRetryTimer.restart()\n'
        '  }\n'
    ),
    (
        '        pendingSessionLockTimer.stop()\n'
        '        root.startFingerprint()\n'
        '      }\n'
        '    }\n',
        '        pendingSessionLockTimer.stop()\n'
        '        root.startFingerprint()\n'
        '        root.startHowdy()\n'
        '      }\n'
        '    }\n'
    ),
    (
        '    onError: function(error) {\n'
        '      root.fingerprintAuthenticating = false\n'
        '      if (root.lockRequested && root.fingerprintConfigured) fingerprintRetryTimer.restart()\n'
        '    }\n'
        '  }\n'
        '\n'
        '  Timer {\n'
        '    id: fingerprintRetryTimer\n'
        '    interval: 250\n'
        '    repeat: false\n'
        '    onTriggered: root.startFingerprint()\n'
        '  }\n',
        '    onError: function(error) {\n'
        '      root.fingerprintAuthenticating = false\n'
        '      if (root.lockRequested && root.fingerprintConfigured) fingerprintRetryTimer.restart()\n'
        '    }\n'
        '  }\n'
        '\n'
        '  PamContext {\n'
        '    id: howdyPam\n'
        '    config: "omarchy-lock-howdy"\n'
        '    user: root.userName\n'
        '\n'
        '    onCompleted: function(result) {\n'
        '      root.handleHowdyFinished(result)\n'
        '    }\n'
        '\n'
        '    onError: function(error) {\n'
        '      root.howdyAuthenticating = false\n'
        '      if (root.lockRequested && root.howdyConfigured && !root.howdyFaceLockedOut) howdyRetryTimer.restart()\n'
        '    }\n'
        '  }\n'
        '\n'
        '  Timer {\n'
        '    id: fingerprintRetryTimer\n'
        '    interval: 250\n'
        '    repeat: false\n'
        '    onTriggered: root.startFingerprint()\n'
        '  }\n'
        '\n'
        '  Timer {\n'
        '    id: howdyRetryTimer\n'
        '    interval: 250\n'
        '    repeat: false\n'
        '    onTriggered: root.startHowdy()\n'
        '  }\n'
    ),
    (
        '      root.fingerprintConfigured = String(fingerprintCheckStdout.text || "").trim() === "yes"\n'
        '      if (root.lockRequested && root.fingerprintConfigured) root.startFingerprint()\n'
        '      else if (!root.fingerprintConfigured && fingerprintPam.active) fingerprintPam.abort()\n'
        '    }\n'
        '  }\n',
        '      root.fingerprintConfigured = String(fingerprintCheckStdout.text || "").trim() === "yes"\n'
        '      if (root.lockRequested && root.fingerprintConfigured) root.startFingerprint()\n'
        '      else if (!root.fingerprintConfigured && fingerprintPam.active) fingerprintPam.abort()\n'
        '    }\n'
        '  }\n'
        '\n'
        '  Process {\n'
        '    id: howdyCheckProc\n'
        '    // Only trust Howdy auth assets the session cannot rewrite: the PAM\n'
        '    // service, the face model, and the PAM module itself must all be\n'
        '    // root-owned and not group/world-writable. Session code able to\n'
        '    // rewrite any of them could otherwise enroll a face everyone matches\n'
        '    // or swap in an auth module that always succeeds.\n'
        '    command: ["bash", "-c", [\n'
        '      "p=/etc/pam.d/omarchy-lock-howdy",\n'
        '      "m=/etc/howdy/models/${USER}.dat",\n'
        '      "mod=/usr/lib/security/pam_howdy.so; [[ -f $mod ]] || mod=/lib/security/pam_howdy.so",\n'
        '      "[[ -f $p && -f $m && -f $mod ]] || { echo no; exit 0; }",\n'
        '      "[[ $(stat -c %u $p) == 0 && $(stat -c %u $m) == 0 && $(stat -c %u $mod) == 0 ]] || { echo no; exit 0; }",\n'
        '      "[[ -z $(find $p $m $mod -perm /go+w -print -quit) ]] || { echo no; exit 0; }",\n'
        '      "echo yes"\n'
        '    ].join("; ")]\n'
        '    stdout: StdioCollector { id: howdyCheckStdout; waitForEnd: true }\n'
        '    onExited: {\n'
        '      root.howdyConfigured = String(howdyCheckStdout.text || "").trim() === "yes"\n'
        '      if (root.lockRequested && root.howdyConfigured) root.startHowdy()\n'
        '      else if (!root.howdyConfigured) { if (howdyPam.active) howdyPam.abort(); howdyRetryTimer.stop() }\n'
        '    }\n'
        '  }\n'
    ),
    (
        '  Component.onCompleted: {\n'
        '    refreshBackground()\n'
        '    refreshFingerprintStatus()\n'
        '    checkStrandedLock()\n'
        '  }\n',
        '  Component.onCompleted: {\n'
        '    refreshBackground()\n'
        '    refreshFingerprintStatus()\n'
        '    refreshHowdyStatus()\n'
        '    checkStrandedLock()\n'
        '  }\n'
    ),
    (
        '        passwordPam: root.passwordPamConfigured,\n'
        '        fingerprint: root.fingerprintConfigured,\n'
        '        authenticating: root.authenticating,\n',
        '        passwordPam: root.passwordPamConfigured,\n'
        '        fingerprint: root.fingerprintConfigured,\n'
        '        howdy: root.howdyConfigured,\n'
        '        authenticating: root.authenticating,\n'
    ),
    (
        '    function preview(): string {\n'
        '      root.refreshBackground()\n'
        '      root.refreshFingerprintStatus()\n'
        '      root.previewVisible = true\n'
        '      return "ok"\n'
        '    }\n',
        '    function preview(): string {\n'
        '      root.refreshBackground()\n'
        '      root.refreshFingerprintStatus()\n'
        '      root.refreshHowdyStatus()\n'
        '      root.previewVisible = true\n'
        '      return "ok"\n'
        '    }\n'
    ),
]


def main():
    if len(sys.argv) != 2:
        print("Usage: patch_lock_qml.py <Service.qml path>", file=sys.stderr)
        return 1

    path = sys.argv[1]
    with open(path, "r") as f:
        text = f.read()

    if "omarchy-lock-howdy" in text:
        print("Already patched, nothing to do.")
        return 0

    for old, new in PATCHES:
        count = text.count(old)
        if count == 0:
            print(f"Patch target not found (upstream file changed?):\n{old!r}", file=sys.stderr)
            return 1
        if count > 1:
            print(f"Patch target not unique ({count}x):\n{old!r}", file=sys.stderr)
            return 1
        text = text.replace(old, new, 1)

    with open(path, "w") as f:
        f.write(text)

    print("Patched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
