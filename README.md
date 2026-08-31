# Howdy Face Unlock

Face unlock for IR webcams on Omarchy, via [Howdy](https://github.com/boltgolt/howdy).
Mirrors the fingerprint flow as closely as Omarchy's plugin system allows.

## Install

```
omarchy plugin add https://github.com/tslove923/omarchy-howdy-face-unlock
~/.config/omarchy/plugins/io.github.tslove923.howdy-face-unlock/setup
```

`omarchy plugin add` only clones files — run `setup` yourself afterward. It
detects your IR camera, installs `howdy-git` and `linux-enable-ir-emitter`
from the AUR (building `python-dlib` CPU-only unless it detects an Nvidia
GPU, to dodge that AUR package's broken CUDA subpackage; the CPU-only build
clones the AUR PKGBUILD pinned to a fixed commit SHA so upstream can't move
under the build), configures the emitter, enrolls your face, and wires up
the lock screen.

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

What the plugin *does* buy: `setup` installs a `post-update` hook
(`omarchy hook install post-update ...`) that runs during `omarchy update`,
right after system packages and migrations — i.e. right after the patch may
have just been overwritten. It re-patches the file there, silently, while
`omarchy update`'s own sudo session is still authenticated, so face unlock
survives an update on its own; you don't need to notice anything or rerun
`setup` yourself in the common case.

That repair can only fail if sudo isn't authenticated non-interactively at
that point (e.g. an unusual update flow). For that case, this repo's
`Service.qml` also runs as a real first-class Omarchy service and checks on
every shell start whether the patch survived. If it's still missing, you get
a critical desktop notification telling you to rerun `setup`, instead of face
unlock just silently going dead until you notice at the worst possible moment
(i.e., at the lock screen).

On a dev checkout (`OMARCHY_PATH` pointing at a source tree), the running
shell loads the lock plugin from `$OMARCHY_PATH/shell/plugins/lock/Service.qml`
rather than `/usr/share/omarchy/...`, so `setup` and this health check resolve
that path too. A `git pull` that reverts it is the dev equivalent of an
`omarchy update` overwriting the packaged copy.

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
  path, wired in alongside the existing fingerprint one. When the lock
  screen engages — e.g. when you close the lid — Howdy starts
  authenticating right away, retrying every 250 ms until it succeeds. So
  face unlock is already live when you open the lid: just look at the
  camera. It gives up after 5 failed attempts in a row and falls back to
  password-only for the rest of that lock, rather than retrying forever.
- Before trusting Howdy as configured, the lock screen checks that
  `/etc/pam.d/omarchy-lock-howdy`, your enrolled face model, and
  `pam_howdy.so` are all root-owned and not group/world-writable — the
  same way it already trusts nothing it can't verify for fingerprint/PAM.
  Session code able to rewrite any of those could otherwise enroll a face
  everyone matches or swap in an auth module that always succeeds.

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
