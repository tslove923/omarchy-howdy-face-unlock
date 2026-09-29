<h1 align="center">Howdy Face Unlock</h1>

<h3 align="center">Windows Hello–style unlocking for Omarchy — just look at the camera.</h3>

<p align="center">
  <a href="https://plugins.omarchy.org/plugin.html?id=io.github.tslove923.howdy-face-unlock">Omarchy Plugins</a>
  ·
  <a href="https://github.com/tslove923/omarchy-howdy-face-unlock/issues">Issues</a>
</p>

Face unlock for laptops with an infrared camera, built on
[Howdy](https://github.com/boltgolt/howdy) and wired into the Omarchy lock
screen. Open the lid, look up, and you're in — no password, no fingerprint
pad. It mirrors the fingerprint flow as closely as Omarchy's plugin system
allows: a dedicated PAM service, a face glyph where the fingerprint icon
lives, and the same "already scanning when the lid comes up" feel.

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

Lock Screen Explorer support (see below) does not patch any file, so the
hash pin above applies only to `patch-lock-howdy.py`. It writes its own
PAM service, module symlink, and model symlinks directly (via
`bin/howdy-lock-face-adapter`), all as root-owned system paths it creates
itself rather than as a patch to someone else's package-owned file — so
there is no third-party file whose bytes root has to trust the way the
stock `lock/Service.qml` is.

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
  password-only for the rest of that lock. A retry never starts while a
  password submission is already in flight, so typing your password
  doesn't risk a fresh camera scan landing right as it succeeds.
- Before trusting Howdy as configured, the lock screen checks that
  `/etc/pam.d/omarchy-lock-howdy`, your enrolled face model, and
  `pam_howdy.so` are all root-owned and not group/world-writable — the
  same way it already trusts nothing it can't verify for fingerprint/PAM.
  Session code able to rewrite any of those could otherwise enroll a face
  everyone matches or swap in an auth module that always succeeds.
- Optional (asked during setup): a facelock-shaped compatibility surface so
  [Lock Screen Explorer](https://github.com/SirJul1337/omarchy-lock-explorer)'s
  own face UI runs Howdy — see
  [Lock-screen replacement plugins](#lock-screen-replacement-plugins-lock-screen-explorer)
  below. Nothing inside Explorer's own files is modified.

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
isn't currently enabled is dormant.

[Lock Screen Explorer](https://github.com/SirJul1337/omarchy-lock-explorer)
(`io.github.sirjul1337.lock-explorer`) is one such plugin, and it ships its
**own native face-unlock UI**. Unfortunately it can only drive a
*facelock-shaped* backend, and none of that is configurable:

- it hardcodes `PamContext { config: "omarchy-lock-face" }`, and
- its `check-face-auth.sh` only offers the face UI when it finds
  `pam_facelock.so` in `/etc/pam.d/omarchy-lock-face`, the module
  `/usr/lib/security/pam_facelock.so`, and a model under
  `/var/lib/facelock/models/*.onnx`.

Omarchy has no plugin-to-plugin auth hook, so the only way to run Howdy
behind Explorer's face UI is to **provide that facelock-shaped surface
ourselves — backed by Howdy**, entirely outside Explorer's tree:

| file | purpose |
| --- | --- |
| `/etc/pam.d/omarchy-lock-face` | the PAM service Explorer calls; runs `pam_facelock.so` |
| `/usr/lib/security/pam_facelock.so` | a symlink to `pam_howdy.so` |
| `/var/lib/facelock/models/*.onnx` | symlinks to your Howdy face models |

In other words: Explorer's "facelock" face path resolves to Howdy. The
facelock names are Explorer's vocabulary; everything they point at is
Howdy. Nothing here claims facelock is installed to anything but Explorer's
own detector, and **a real facelock install is never shadowed** — the
adapter backs off entirely if it finds one.

This is implemented in `bin/howdy-lock-face-adapter` (`install` / `remove`)
and is **opt-in**: `setup` asks before writing these files, explaining
exactly what they are. Skipping it changes nothing for the stock lock
screen, which is patched regardless.

Why provide a surface instead of patching Explorer's `Service.qml` (the
earlier approach, now removed): patching was fragile — Explorer's anchors
drift on every release — and it injected a *second* face stack next to
Explorer's own native one. Providing the surface instead is:

- **install-order independent** — it doesn't matter whether Explorer is
  installed before or after this plugin; if Explorer is added later it
  finds the surface already in place, and if it's absent the surface is
  simply inert;
- **update-proof** — `omarchy plugin update` rewrites Explorer's files, but
  none of ours live there, so there is nothing to revert;
- **non-fatal** — if the adapter can't be installed, the rest of Howdy's
  install still succeeds.

`omarchy-shell howdy status` reports whether face unlock is healthy for
whichever lock screen is actually live (the adapter surface when Explorer
is enabled, the stock patch otherwise). A broken verdict is only trusted
after it repeats across several spaced checks well after startup, so a
transient misread — a still-starting shell, a plugin mid-reload — cannot
raise a false alarm. The post-update hook refreshes the adapter after
`omarchy update` if it was previously set up.

**Backup note:** never keep a copy of a plugin directory *inside*
`~/.config/omarchy/plugins/` (e.g. a `foo.bak-.../` sibling). The shell
scans every subdirectory with a manifest, so a second copy carrying the
same `id` can be the one it loads — which will silently serve stale code.
