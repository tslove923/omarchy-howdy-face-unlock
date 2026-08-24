# Howdy Face Unlock

Face unlock for IR webcams on Omarchy, via [Howdy](https://github.com/boltgolt/howdy).
Mirrors the fingerprint flow as closely as Omarchy's plugin system allows.

## Install

```
omarchy plugin add <this repo's URL>
~/.config/omarchy/plugins/io.github.tslove923.howdy-face-unlock/setup
```

`omarchy plugin add` only clones files — run `setup` yourself afterward. It
detects your IR camera, installs `howdy-git` and `linux-enable-ir-emitter`
from the AUR (building `python-dlib` CPU-only unless it detects an Nvidia
GPU, to dodge that AUR package's broken CUDA subpackage), configures the
emitter, enrolls your face, and wires up the lock screen.

Setup and removal are also reachable from the Omarchy menu: **Setup → Security
→ Face Unlock** and **Remove → Security → Face Unlock** (both only appear
once an IR camera is detected / Howdy is installed, respectively).

## Remove

```
~/.config/omarchy/plugins/io.github.tslove923.howdy-face-unlock/remove
omarchy plugin remove io.github.tslove923.howdy-face-unlock
```

## Why this is a plugin and not just a script

It isn't, entirely. Omarchy's lock screen (`omarchy.lock`) is a single
first-party `service`-kind plugin with no hook for a third party to add a new
PAM auth backend to it — plugins mount independently, they don't extend each
other. So `setup` still has to hand-patch
`/usr/share/omarchy/shell/plugins/lock/Service.qml` directly, the same as it
would if this were a loose script. That file is package-owned, so an
`omarchy update` can silently revert the patch.

What the plugin *does* buy: this repo's `Service.qml` runs as a real
first-class Omarchy service and checks on every shell start whether that
patch survived. If an update wiped it, you get a critical desktop
notification telling you to rerun `setup`, instead of face unlock just
silently going dead until you notice at the worst possible moment (i.e., at
the lock screen).

Query its health directly: `omarchy-shell howdy status` → `ok` or `broken`.

## What setup actually changes

- Installs `howdy-git`, `linux-enable-ir-emitter`, `v4l-utils`, `python-dlib`
- `/etc/howdy/config.ini` — tuned for IR (`dark_threshold`, `certainty`,
  `max_height`), `workaround = off` (Howdy's default `input` workaround tries
  to fake an Enter keypress via `/dev/uinput` to unblock a legacy
  simultaneous-password-prompt flow this lock screen doesn't have — with a
  dedicated `PamContext` per auth method, it just hangs), and made
  world-readable (the lock screen's PAM module runs unprivileged, in-process,
  with no root daemon to broker access the way fprintd has, so it has to be
  able to read its own config as that user)
- `/etc/pam.d/omarchy-lock-howdy` — a PAM service dedicated to Howdy,
  independent of `omarchy-lock-fingerprint`
- `lock/Service.qml` — a parallel `startHowdy()`/`howdyPam`/`howdyCheckProc`
  path, wired in alongside the existing fingerprint one

## Known rough edges

- `linux-enable-ir-emitter configure` doesn't manage to save anything on
  every camera — some just work under plain capture, and the tool's own
  "already working" pre-check exits non-zero for that. `setup` treats this as
  informational, not fatal.
- Omarchy is actively deciding between Howdy and other face-auth backends
  (see [basecamp/omarchy#5212](https://github.com/basecamp/omarchy/pull/5212)
  and [discussion #4982](https://github.com/basecamp/omarchy/discussions/4982)).
  This plugin exists so face unlock works today, independent of how that
  settles upstream.
