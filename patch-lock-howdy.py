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


class _MatchAny:
    """Wrap a tuple of acceptable anchor strings.

    Some upstream blocks drift incrementally (a line added here, a line
    removed there) without changing what the surrounding patch needs to do.
    An entry whose `old` is a _MatchAny will be applied against whichever of
    its alternatives is present, so the patch survives that drift instead of
    hard-failing. Exactly one alternative must match; zero is still a loud
    failure (the file moved further than we know about), and more than one is
    treated as a collision.
    """

    def __init__(self, alternatives):
        self.alternatives = tuple(alternatives)


def Match_ANY(alternatives):
    return _MatchAny(alternatives)


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
        Match_ANY((
            '    authenticatingPassword = false\n'
            '    fingerprintAuthenticating = false\n'
            '    fingerprintRetryTimer.stop()\n'
            '    if (passwordPam.active) passwordPam.abort()\n'
            '    if (fingerprintPam.active) fingerprintPam.abort()\n'
            '  }\n',
            '    authenticatingPassword = false\n'
            '    fingerprintAuthenticating = false\n'
            '    fingerprintUnreachedStreak = 0\n'
            '    fingerprintAttemptFastError = false\n'
            '    fingerprintAttemptPromptedAtMs = 0\n'
            '    fingerprintLastNudgeMs = 0\n'
            '    fingerprintLastSettleMs = 0\n'
            '    fingerprintResumedAtMs = 0\n'
            '    fingerprintProbeStreak = 0\n'
            '    fingerprintPaused = false\n'
            '    fingerprintSleptWhilePaused = false\n'
            '    fingerprintRecheckTimer.stop()\n'
            '    fingerprintRetryTimer.stop()\n'
            '    fingerprintReachTimer.stop()\n'
            '    fingerprintResumeTimer.stop()\n'
            '    if (passwordPam.active) passwordPam.abort()\n'
            '    if (fingerprintPam.active) fingerprintPam.abort()\n'
            '  }\n',
        )),
        lambda old: old.replace(
            '    fingerprintAuthenticating = false\n',
            '    fingerprintAuthenticating = false\n'
            '    howdyAuthenticating = false\n'
            '    howdyAttempts = 0\n'
            '    howdyFaceLockedOut = false\n'
            '    howdyRetryPaused = false\n',
            1,
        ).replace(
            '    if (passwordPam.active) passwordPam.abort()\n',
            '    howdyRetryTimer.stop()\n'
            '    if (passwordPam.active) passwordPam.abort()\n',
            1,
        ).replace(
            '    if (fingerprintPam.active) fingerprintPam.abort()\n',
            '    if (fingerprintPam.active) fingerprintPam.abort()\n'
            '    if (howdyPam.active) howdyPam.abort()\n',
            1,
        ),
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
        # Preserve the upstream wake behavior, which includes fingerprint
        # resume/nudge on newer Omarchy versions.
        Match_ANY((
            '  function runWake() {\n'
            '    root.displaysBlank = false\n'
            '    root.monitorDpmsKnown = false\n'
            '    if (!wakeProcess.running) wakeProcess.running = true\n'
            '    if (lockRequested) armBlankTimer()\n'
            '  }\n',
            '  function runWake() {\n'
            '    if (!wakeProcess.running) wakeProcess.running = true\n'
            '    if (lockRequested) armBlankTimer()\n'
            '  }\n',
            '  function runWake() {\n'
            '    if (!wakeProcess.running) wakeProcess.running = true\n'
            '    if (lockRequested) armBlankTimer()\n'
            '    resumeFingerprint()\n'
            '    nudgeFingerprint()\n'
            '  }\n',
        )),
        lambda old: old[:-4] + '\n'
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
        Match_ANY((
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
            '    if (result === PamResult.Success && lockRequested) {\n'
            '      // A match after a run of misses is the recovery too; the unlock resets\n'
            '      // the streak without settling, so log it here or it leaves no trace.\n'
            '      if (fingerprintUnreachedStreak > 0) logEvent("fingerprint-recovered: streak=" + fingerprintUnreachedStreak)\n'
            '      finishUnlock()\n'
            '    } else {\n'
            '      settleFingerprintAttempt(result === PamResult.Error)\n'
            '    }\n'
            '  }\n',
        )),
        lambda old: old + '\n'
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
        Match_ANY((
            '    onError: function(error) {\n'
            '      root.fingerprintAuthenticating = false\n'
            '      if (root.lockRequested && root.fingerprintConfigured) fingerprintRetryTimer.restart()\n'
            '    }\n'
            '  }\n',
            '    onError: function(error) {\n'
            '      root.settleFingerprintAttempt(true)\n'
            '    }\n'
            '  }\n',
        )),
        lambda old: old + '\n'
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
        Match_ANY((
            '  Timer {\n'
            '    id: fingerprintRetryTimer\n'
            '    interval: 250\n'
            '    repeat: false\n'
            '    onTriggered: root.startFingerprint()\n'
            '  }\n',
            '  Timer {\n'
            '    id: fingerprintRetryTimer\n'
            '    interval: FingerprintModel.MATCH_RETRY_MS\n'
            '    repeat: false\n'
            '    onTriggered: root.startFingerprint()\n'
            '  }\n',
        )),
        lambda old: old + '\n'
        '  Timer {\n'
        '    id: howdyRetryTimer\n'
        '    interval: 250\n'
        '    repeat: false\n'
        '    onTriggered: root.startHowdy()\n'
        '  }\n'
    ),
    (
        Match_ANY((
            '      root.fingerprintConfigured = String(fingerprintCheckStdout.text || "").trim() === "yes"\n'
            '      if (root.lockRequested && root.fingerprintConfigured) root.startFingerprint()\n'
            '      else if (!root.fingerprintConfigured && fingerprintPam.active) fingerprintPam.abort()\n'
            '    }\n'
            '  }\n',
            '    id: fingerprintCheckProc\n'
            '    command: ["bash", "-c", "if [[ -f /etc/pam.d/omarchy-lock-fingerprint ]] && command -v fprintd-list >/dev/null 2>&1; then LC_ALL=C fprintd-list \\"$USER\\" 2>&1; else echo no; fi"]\n'
            '    stdout: StdioCollector { id: fingerprintCheckStdout; waitForEnd: true }\n'
            '    onExited: root.applyFingerprintProbe(fingerprintCheckStdout.text)\n'
            '  }\n',
        )),
        lambda old: old + '\n'
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
        Match_ANY((
            '  Component.onCompleted: {\n'
            '    refreshBackground()\n'
            '    refreshFingerprintStatus()\n'
            '    checkStrandedLock()\n'
            '  }\n',
            '  Component.onCompleted: {\n'
            '    knownScreenCount = realScreenCount()\n'
            '    refreshBackground()\n'
            '    refreshFingerprintStatus()\n'
            '    checkStrandedLock()\n'
            '  }\n',
        )),
        lambda old: old.replace('    refreshFingerprintStatus()\n',
                                '    refreshFingerprintStatus()\n    refreshHowdyStatus()\n', 1),
    ),
    (
        Match_ANY((
            '        fingerprint: root.fingerprintConfigured,\n'
            '        authenticating: root.authenticating,\n',
            '        fingerprint: root.fingerprintConfigured,\n'
            '        fingerprintUnavailable: root.fingerprintUnavailable,\n'
            '        authenticating: root.authenticating,\n',
        )),
        lambda old: old.replace('        authenticating: root.authenticating,\n',
                                '        howdy: root.howdyConfigured,\n'
                                '        howdyPaused: root.howdyRetryPaused,\n'
                                '        authenticating: root.authenticating,\n', 1),
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
        if isinstance(old, _MatchAny):
            matches = [alt for alt in old.alternatives if text.count(alt) == 1]
            if not matches:
                print(
                    "Patch target not found (upstream file changed?); "
                    "none of the accepted anchors matched exactly once:\n"
                    + "\n---\n".join(repr(a) for a in old.alternatives),
                    file=sys.stderr,
                )
                return 1
            # Apply against the alternative that anchors the real text.
            old = matches[0]
        else:
            count = text.count(old)
            if count == 0:
                print(f"Patch target not found (upstream file changed?):\n{old!r}", file=sys.stderr)
                return 1
            if count > 1:
                print(f"Patch target not unique ({count}x):\n{old!r}", file=sys.stderr)
                return 1
        text = text.replace(old, new(old) if callable(new) else new, 1)

    with open(path, "w") as f:
        f.write(text)

    print("Patched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
