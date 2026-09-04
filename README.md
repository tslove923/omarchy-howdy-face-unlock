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

### How the patch step stays safe to run as root

Both `setup` and the post-update hook patch `lock/Service.qml` by staging a
copy into a root-owned scratch dir (`sudo mktemp -d`, mode `700`) and running
`patch-lock-howdy.py` from there instead of straight out of this checkout.
Staging alone isn't enough, though: by the time that patch step runs, `sudo`
is already authenticated from earlier in the same script (or, for the hook,
from `omarchy update`'s own pacman prompt) — so anything running as the
invoking user could still swap `patch-lock-howdy.py` in this user-writable
checkout right up until root's `cp` reads it, and root would stage and
execute those swapped bytes instead. Moving the read into a root-owned
directory shrinks that window; it doesn't close it.

What closes it: both call sites pin `patch-lock-howdy.py`'s sha256 as a
constant and have root verify the staged copy against it before ever
executing it, refusing on mismatch. That checks *what* is about to run
rather than *where* it was staged from, so a swapped file is caught
regardless of timing. Bump the pinned hash in both `setup` and
`hooks/post-update.d/repair-howdy-lock.hook` if you ever modify
`patch-lock-howdy.py`.

`patch-lock-howdy-explorer.py` (Lock Screen Explorer's own `Service.qml`,
see below) skips all of this and runs directly as the invoking user, with
no scratch dir, no hash pin, no `sudo`. That's deliberate, not an
oversight: its target file lives in the user's own plugin checkout, not a
package-owned path — the invoking user already owns it outright, so
patching it doesn't cross a privilege boundary the way writing to
`/usr/share/omarchy` does. The scratch-dir-plus-hash dance defends against
a warm `sudo` timestamp being used to run tampered bytes as root; with no
privilege escalation involved, anyone able to tamper with that patcher
could equally tamper with anything else the user's own shell already
trusts, so the same ceremony there wouldn't buy anything real.

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
  authenticating right away, retrying every 250 ms on failure. So face
  unlock is already live when you open the lid: just look at the camera.
  A failed attempt only keeps retrying while there's been recent activity
  (the lock just engaged, or a wake signal — mouse move, key press, a
  password attempt — within the last 10s); otherwise retries pause instead
  of burning through attempts against an empty room while nobody's there.
  Any wake signal while paused (or even after full lockout) resets the
  attempt count and re-arms a fresh attempt immediately, so face unlock is
  live again the moment you're actually back — not still shaking off a
  lockout from the last time it scanned an empty desk. Only 5 failed
  attempts in a row *with* someone actually present trips the fallback to
  password-only for the rest of that lock.
- Before trusting Howdy as configured, the lock screen checks that
  `/etc/pam.d/omarchy-lock-howdy`, your enrolled face model, and
  `pam_howdy.so` are all root-owned and not group/world-writable — the
  same way it already trusts nothing it can't verify for fingerprint/PAM.
  Session code able to rewrite any of those could otherwise enroll a face
  everyone matches or swap in an auth module that always succeeds.
- If [Lock Screen Explorer](https://github.com/SirJul1337/omarchy-lock-explorer)
  is installed, its own `Service.qml` gets the same treatment via a second
  patcher tuned to its structure — see
  [Lock-screen replacement plugins](#lock-screen-replacement-plugins-lock-screen-explorer)
  below.

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

## Lock-screen replacement plugins (Lock Screen Explorer)

Plugins that replace the lock screen entirely declare
`"omarchy": {"clonedFrom": "omarchy.lock"}` in their manifest. Enabling one
makes Omarchy disable the stock `omarchy.lock` service and load the
replacement's own `Service.qml` for the `lock` IPC target instead — Omarchy
only ever loads one `lock`-targeting service at a time, so whichever one
isn't currently enabled is dormant, patched or not.

[Lock Screen Explorer](https://github.com/SirJul1337/omarchy-lock-explorer)
(`io.github.sirjul1337.lock-explorer`) is one such plugin, and this project
now ships a second patcher, `patch-lock-howdy-explorer.py`, tuned to its
actual `Service.qml` structure (it's a large, single-file service with its
own avatar detection, clip-design wallpaper prep, boot-screen/Plymouth
integration, and a design/skin picker — the skins themselves are pure
display components with no auth logic of their own, so one patch target is
enough). `setup` runs it automatically, in addition to the stock patch,
whenever it finds Lock Screen Explorer installed at
`~/.config/omarchy/plugins/io.github.sirjul1337.lock-explorer/` —
regardless of which of the two is currently *enabled*, so Howdy is already
wired in however and whenever you switch between them. The post-update
hook and this plugin's own Service.qml watchdog both know how to check
whichever of the two files is actually active, the same way.

A few things worth knowing about this support:

- **It's non-fatal.** Lock Screen Explorer is a fast-moving third-party
  plugin outside this project's control, and its structure *will*
  eventually drift out from under `patch-lock-howdy-explorer.py`'s anchors
  (unlike the stock patch, which stays a hard failure — that's the
  primary, stable target). When that happens, `setup` prints a clear
  warning and continues with the rest of Howdy's install; it doesn't abort
  just because a bonus, independently-versioned integration went stale.
- **No automatic repair after `omarchy plugin update`.** That command (not
  `omarchy update`) is what pulls a new version of Lock Screen Explorer,
  and Omarchy has no post-plugin-update hook point today for this plugin
  to catch that with. The post-update hook (`omarchy update`) still
  opportunistically re-patches Explorer's file as a safety net, and this
  plugin's own Service.qml watchdog will notice and tell you to rerun
  `setup` by hand if a plugin update reverts it in between.
- **Tested by static patch application and code reading, not by enabling
  Lock Screen Explorer as the live lock screen.** The patch has been
  applied to Lock Screen Explorer's actual installed `Service.qml`,
  checked for idempotency (a second run no-ops) and brace/paren balance,
  and read through line by line to confirm the Howdy path doesn't collide
  with Explorer's own `authenticating` aggregate, its retry timers, or its
  IPC `status()` fields. It has not been verified against the live,
  enabled lock screen. If something doesn't work in practice, please open
  an issue.
