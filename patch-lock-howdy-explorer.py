#!/usr/bin/env python3
"""Idempotently patch Lock Screen Explorer's Service.qml
(io.github.sirjul1337.lock-explorer) to add a Howdy auth path that mirrors
the existing fingerprint one -- the same feature patch-lock-howdy.py applies
to the stock Omarchy lock plugin.

Why this is a separate file instead of a second PATCHES list appended to
patch-lock-howdy.py: Lock Screen Explorer is a `clonedFrom: omarchy.lock`
replacement (see issue #1) with real feature code Omarchy's stock file
doesn't have -- a design/skin picker, avatar detection, clip-design
wallpaper prep, boot-screen (Plymouth) integration, and more -- interleaved
at several of the exact points patch-lock-howdy.py anchors to. Some of
those anchors still match this file's stock-derived core verbatim
(properties, `authenticating`, `refreshFingerprintStatus`,
`resetAuthenticationState`'s tail, `handleFingerprintFinished`, the
WlSessionLock `onSecureStateChanged` tail, and the fingerprint-check
Process' `onExited` body all do -- see the patches below that reuse the
same old/new text as patch-lock-howdy.py verbatim). But several don't:
`beginLock()`'s `Qt.callLater(...)` block, `runWake()`, the fingerprint
`PamContext`/`Timer` pair (no longer contiguous -- Explorer interposes an
`unlockTimer` and a `clipFailsafe` Timer between them), `Component.onCompleted`,
the IPC `status()` object literal, and `preview()` all have Explorer-specific
lines in between that make the stock anchors not match. A single shared
PATCHES list keyed by target would need every entry to carry two variants
anyway; keeping the whole set here, tuned to this file's actual structure,
is more legible and safer to review than interleaving both inside one file.

Each (old, new) pair is applied only if `old` is present verbatim and `new`
is not already there, so a rerun after the plugin's own git checkout gets
updated (wiping any local patch, same as an `omarchy update` does to the
stock file) re-applies cleanly, and a rerun after our own patch already
landed is a safe no-op. Each `old` is asserted unique before replacement so
an upstream change to this file fails loudly here instead of silently
applying to the wrong spot or corrupting it.

Verified against Lock Screen Explorer's actual installed source at
manifest version 1.5.5, commit 08c454f ("Show the applied theme on the
shutdown splash too"). This plugin ships fast, independent updates, so
these anchors *will* eventually drift -- that's expected, not a bug in
this file. When one goes stale, `setup` and the post-update repair hook
both treat a failure here as non-fatal (they warn and move on rather than
aborting the rest of Howdy's install/repair), specifically because this
target is out of this project's control in a way the stock file isn't.
"""
import sys

PATCHES = [
    # ---- Anchors that still match the stock file's patch verbatim -------
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
        '  property bool howdyRetryPaused: false\n'
        '  property double howdyLastActivityAt: 0\n'
        '  readonly property int maxFaceAttempts: 5\n'
        '  readonly property int howdyActiveWindowMs: 10000\n'
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
        '    howdyRetryPaused = false\n'
        '    fingerprintRetryTimer.stop()\n'
        '    howdyRetryTimer.stop()\n'
        '    if (passwordPam.active) passwordPam.abort()\n'
        '    if (fingerprintPam.active) fingerprintPam.abort()\n'
        '    if (howdyPam.active) howdyPam.abort()\n'
        '  }\n'
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
        '    // Don\'t kick off a fresh camera scan while a password submission is\n'
        '    // in flight -- starting one right before the password succeeds just\n'
        '    // means aborting it again a moment later, with a visible flash of\n'
        '    // camera activity right as you\'re already logging in.\n'
        '    if (authenticatingPassword) return\n'
        '\n'
        '    howdyRetryPaused = false\n'
        '    howdyAuthenticating = true\n'
        '    if (!howdyPam.start()) {\n'
        '      howdyAuthenticating = false\n'
        '    }\n'
        '  }\n'
        '\n'
        '  // Whether a Howdy retry is still worth spending against the attempt\n'
        '  // budget: true while the lock just engaged, or something has recently\n'
        '  // shown a person is actually there (see runWake()). This is what keeps\n'
        '  // "look at the camera and it just works" (the whole point of this\n'
        '  // plugin) intact for a genuinely present user, while a scan that fails\n'
        '  // because nobody\'s there yet stops burning attempts against an empty\n'
        '  // room instead of exhausting the budget in ~30s before the user is back.\n'
        '  function howdyRecentlyActive() {\n'
        '    return Date.now() - howdyLastActivityAt <= howdyActiveWindowMs\n'
        '  }\n'
        '\n'
        '  function scheduleHowdyRetry() {\n'
        '    if (howdyRecentlyActive()) {\n'
        '      howdyRetryTimer.restart()\n'
        '    } else {\n'
        '      howdyRetryPaused = true\n'
        '      logEvent("howdy-paused: no-recent-activity")\n'
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
        '    scheduleHowdyRetry()\n'
        '  }\n'
    ),
    (
        '        pendingSessionLockTimer.stop()\n'
        '        root.startFingerprint()\n'
        '      }\n'
        '    }\n',
        '        pendingSessionLockTimer.stop()\n'
        '        root.startFingerprint()\n'
        '        root.howdyLastActivityAt = Date.now()\n'
        '        root.howdyRetryPaused = false\n'
        '        root.startHowdy()\n'
        '      }\n'
        '    }\n'
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

    # ---- Explorer-specific anchors (stock anchor does not match here) ---
    (
        '    Qt.callLater(function() {\n'
        '      root.refreshBackground()\n'
        '      root.refreshFingerprintStatus()\n'
        '      root.refreshSessionLockXray()\n'
        '      root.rescanUserDesigns()\n'
        '      // The frame is ready before the unlock needs it.\n'
        '      if (root.designHasClip) root.prepareClipWallpaper(root.designClipPath)\n'
        '      else if (root.stingPath.length > 0) root.prepareClipWallpaper(root.stingPath)\n'
        '    })\n',
        '    Qt.callLater(function() {\n'
        '      root.refreshBackground()\n'
        '      root.refreshFingerprintStatus()\n'
        '      root.refreshHowdyStatus()\n'
        '      root.refreshSessionLockXray()\n'
        '      root.rescanUserDesigns()\n'
        '      // The frame is ready before the unlock needs it.\n'
        '      if (root.designHasClip) root.prepareClipWallpaper(root.designClipPath)\n'
        '      else if (root.stingPath.length > 0) root.prepareClipWallpaper(root.stingPath)\n'
        '    })\n'
    ),
    (
        '  function runWake() {\n'
        '    screenBlanked = false\n'
        '    if (!wakeProcess.running) wakeProcess.running = true\n'
        '    if (lockRequested) armBlankTimer()\n'
        '  }\n',
        '  function runWake() {\n'
        '    screenBlanked = false\n'
        '    if (!wakeProcess.running) wakeProcess.running = true\n'
        '    if (lockRequested) armBlankTimer()\n'
        '\n'
        '    // Real wake activity (mouse/keyboard/click on the lock view, a\n'
        '    // password attempt, etc.) is evidence someone is actually back at\n'
        '    // the machine. Refresh the presence window on every such signal so\n'
        '    // an in-flight retry cycle keeps going, and -- if Howdy had paused\n'
        '    // retries or fully locked out while nobody was around -- give it a\n'
        '    // clean restart. This only fires PAM again on the transition out of\n'
        '    // paused/locked-out, not on every wake tick, so mouse-move spam\n'
        '    // can\'t repeatedly kick off scans.\n'
        '    if (lockRequested && howdyConfigured) {\n'
        '      howdyLastActivityAt = Date.now()\n'
        '      if (howdyFaceLockedOut || howdyRetryPaused) {\n'
        '        howdyAttempts = 0\n'
        '        howdyFaceLockedOut = false\n'
        '        howdyRetryPaused = false\n'
        '        howdyRetryTimer.stop()\n'
        '        logEvent("howdy-resumed: wake")\n'
        '        startHowdy()\n'
        '      }\n'
        '    }\n'
        '  }\n'
    ),
    (
        '    onError: function(error) {\n'
        '      root.fingerprintAuthenticating = false\n'
        '      if (root.lockRequested && root.fingerprintConfigured) fingerprintRetryTimer.restart()\n'
        '    }\n'
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
        '      if (root.lockRequested && root.howdyConfigured && !root.howdyFaceLockedOut) root.scheduleHowdyRetry()\n'
        '    }\n'
        '  }\n'
    ),
    (
        # Explorer interposes unlockTimer and clipFailsafe Timer blocks
        # between the fingerprintPam PamContext and this Timer, so the
        # howdyPam insertion above (right after fingerprintPam) and the
        # howdyRetryTimer insertion here (right after this Timer, the
        # nearest anchor to it) are two separate, non-adjacent patches.
        '  Timer {\n'
        '    id: fingerprintRetryTimer\n'
        '    interval: 250\n'
        '    repeat: false\n'
        '    onTriggered: root.startFingerprint()\n'
        '  }\n',
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
        '  Component.onCompleted: {\n'
        '    refreshBackground()\n'
        '    refreshFingerprintStatus()\n'
        '    refreshSessionLockXray()\n'
        '    rescanUserDesigns()\n'
        '    detectAvatar()\n'
        '    checkStrandedLock()\n'
        '  }\n',
        '  Component.onCompleted: {\n'
        '    refreshBackground()\n'
        '    refreshFingerprintStatus()\n'
        '    refreshHowdyStatus()\n'
        '    refreshSessionLockXray()\n'
        '    rescanUserDesigns()\n'
        '    detectAvatar()\n'
        '    checkStrandedLock()\n'
        '  }\n'
    ),
    (
        '        passwordPam: root.passwordPamConfigured,\n'
        '        multimedia: root.multimediaAvailable,\n'
        '        fingerprint: root.fingerprintConfigured,\n'
        '        authenticating: root.authenticating,\n',
        '        passwordPam: root.passwordPamConfigured,\n'
        '        multimedia: root.multimediaAvailable,\n'
        '        fingerprint: root.fingerprintConfigured,\n'
        '        howdy: root.howdyConfigured,\n'
        '        howdyPaused: root.howdyRetryPaused,\n'
        '        authenticating: root.authenticating,\n'
    ),
    (
        '    function preview(): string {\n'
        '      root.previewUnlocking = false\n'
        '      root.previewClipPlaying = false\n'
        '      root.refreshBackground()\n'
        '      root.refreshFingerprintStatus()\n'
        '      root.previewVisible = true\n'
        '      return "ok"\n'
        '    }\n',
        '    function preview(): string {\n'
        '      root.previewUnlocking = false\n'
        '      root.previewClipPlaying = false\n'
        '      root.refreshBackground()\n'
        '      root.refreshFingerprintStatus()\n'
        '      root.refreshHowdyStatus()\n'
        '      root.previewVisible = true\n'
        '      return "ok"\n'
        '    }\n'
    ),
    (
        # No stock equivalent (the stock plugin has no per-design preview
        # IPC call) -- included for parity, since this site refreshes
        # fingerprint status exactly the way preview() and beginLock() do.
        '    function previewDesign(id: string): string {\n'
        '      root.rescanUserDesigns()\n'
        '      if (!Designs.byId(String(id || ""))) return "unknown-design"\n'
        '      root.previewDesignId = String(id)\n'
        '      root.previewUnlocking = false\n'
        '      root.refreshBackground()\n'
        '      root.refreshFingerprintStatus()\n'
        '      root.previewVisible = true\n'
        '      return "ok"\n'
        '    }\n',
        '    function previewDesign(id: string): string {\n'
        '      root.rescanUserDesigns()\n'
        '      if (!Designs.byId(String(id || ""))) return "unknown-design"\n'
        '      root.previewDesignId = String(id)\n'
        '      root.previewUnlocking = false\n'
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
        print("Usage: patch-lock-howdy-explorer.py <Service.qml path>", file=sys.stderr)
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
            print(f"Patch target not found (Lock Screen Explorer's Service.qml changed?):\n{old!r}", file=sys.stderr)
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
