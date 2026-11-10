"""
Boot USB media sync that an interrupted copy cannot empty (hplayer2#t-092, from anna-players#t-018).

The profiles used to run `rsync ... --delete <usb> /data/media`: --delete removes the set while the
copy runs, so a copy cut short (power pulled, stick yanked) left a player with nothing playable, or
with only a half-written `.NAME.xxxx` rsync temp (Anna bench 2026-11-06: four old cards).

Now: STAGE -> CHECK -> SWAP.
  1. stage: rsync into `<media>.sync` beside the media dir (same filesystem); files the current set
     already holds are hard-linked from it (--link-dest), so only what changed is copied and the
     current set is never written;
  2. check: rsync exit 0 AND the stage holds every file of the source, at its size - then sync to
     disk and write the stage's manifest (MANIFEST: a name no stick holds, the tree shape copies dotfiles);
  3. swap: move the staged files INTO the media dir one atomic rename each, then remove what the new
     set no longer has. The media dir itself is never renamed: FileManager's watchdog sits on its
     inode since HPlayer2() was built, before this sync runs.
Any failure before 3 leaves the media dir exactly as it was. A swap cut short (power lost during the
renames) is finished by recover() at the next boot, USB stick or not - it reads the manifest.

Two shapes, the two filters the profiles used:
  flat (default) `rsync -tdv --exclude='.*' --exclude='*/' --exclude='Thumbs.db'`: top-level regular
                 files only, no dotfiles, no Thumbs.db; sub-folders of the media dir are never touched.
  tree=True      `rsync -rtv`: every regular file at any depth, no filter - the media dir becomes a
                 mirror of the source, sub-folders included (what -r --delete did).

sync() and recover() never raise: a profile runs them before the player starts, and an exception
there would stop the player from booting at all. They log, and return False.
"""
import json, os, shutil, subprocess

EXCLUDES = ['.*', '*/', 'Thumbs.db']
MANIFEST = '.hplayer2-usbsync-complete.json'


def _wanted(name):
    return not name.startswith('.') and name != 'Thumbs.db'


def _regular(path):
    return os.path.isfile(path) and not os.path.islink(path)


def listing(path, tree=False):
    """{relative path: size} of what the sync carries, with the shape's rsync filter."""
    out = {}
    if not os.path.isdir(path):
        return out
    if not tree:
        with os.scandir(path) as it:
            for e in it:
                if _wanted(e.name) and e.is_file(follow_symlinks=False):
                    out[e.name] = e.stat(follow_symlinks=False).st_size
        return out
    for root, _, files in os.walk(path):            # rsync -r without -l: symlinks are skipped
        for n in files:
            p = os.path.join(root, n)
            if _regular(p):
                out[os.path.relpath(p, path)] = os.lstat(p).st_size
    return out


def folders(path):
    """Sub-folders at any depth, relative (tree shape; a symlinked folder is not one)."""
    out = []
    for root, dirs, _ in os.walk(path):
        for d in dirs:
            p = os.path.join(root, d)
            if not os.path.islink(p):
                out.append(os.path.relpath(p, path))
    return sorted(out)


def _fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _clear(path):
    """Remove whatever sits at path - the new set needs that name for another kind of entry."""
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.remove(path)


def _prune(media, files, dirs):
    """tree shape: remove everything the new set does not hold, at any depth, deepest first."""
    for root, subdirs, names in os.walk(media, topdown=False):
        for n in names:
            p = os.path.join(root, n)
            if os.path.relpath(p, media) not in files:
                os.remove(p)
        for d in subdirs:
            p = os.path.join(root, d)
            if os.path.islink(p) or os.path.relpath(p, media) not in dirs:
                _clear(p)


def _finish(media, stage, m, log):
    """The swap. Idempotent: recover() re-runs it after a cut."""
    files, dirs, tree = m['files'], m.get('dirs', []), m.get('tree', False)
    os.makedirs(media, exist_ok=True)
    for d in dirs:                                       # sorted: a parent comes before its children
        p = os.path.join(media, d)
        if not (os.path.isdir(p) and not os.path.islink(p)):
            _clear(p)
            os.makedirs(p)
    for n in files:
        s, t = os.path.join(stage, n), os.path.join(media, n)
        if os.path.lexists(s):
            if os.path.isdir(t) and not os.path.islink(t):
                shutil.rmtree(t)                         # a folder where the new set has a file
            os.replace(s, t)                             # atomic; a no-op on a hard link of itself
    keep = set(files)
    if tree:
        _prune(media, keep, set(dirs))                   # only once the whole new set is in
    else:
        for n in listing(media):
            if n not in keep:
                os.remove(os.path.join(media, n))
    os.sync()
    shutil.rmtree(stage, ignore_errors=True)
    log("USB sync: %d file(s) in place" % len(files))


def _recover(media, log):
    stage = media.rstrip('/') + '.sync'
    if not os.path.isdir(stage):
        return False
    try:
        with open(os.path.join(stage, MANIFEST)) as f:
            m = json.load(f)
        m['files']
    except (OSError, ValueError, TypeError, KeyError):
        log("USB sync: dropping an unfinished stage, the media folder was never touched")
        shutil.rmtree(stage, ignore_errors=True)
        return False
    log("USB sync: finishing a swap cut short")
    _finish(media, stage, m, log)
    return True


def recover(media, log=print):
    """Finish a swap cut short, or drop a stage that never passed its check. Call at every boot."""
    try:
        return _recover(media, log)
    except Exception as e:
        log("USB sync ERROR while recovering (%r) - the media folder holds complete files only" % e)
        return False


def _sync(src, media, log, rsync, tree):
    media = media.rstrip('/')
    _recover(media, log)
    want = listing(src, tree)
    if not want:
        log("USB sync: nothing to copy in", src, "- keeping the media folder as it is")
        return False
    stage = media + '.sync'
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    cmd = [rsync, '-rtv' if tree else '-tdv']
    if not tree:
        cmd += ['--exclude=' + x for x in EXCLUDES]
    if os.path.isdir(media):
        cmd.append('--link-dest=' + os.path.abspath(media))
    cmd += [src.rstrip('/') + '/', stage + '/']
    log(' '.join(cmd))
    rc = subprocess.call(cmd)
    got = listing(stage, tree)
    if rc != 0 or got != want:
        bad = sorted(n for n in want if got.get(n) != want[n])
        log("USB sync FAILED (rsync exit %d, %d file(s) incomplete) - keeping the media folder as it is"
            % (rc, len(bad)))
        shutil.rmtree(stage, ignore_errors=True)
        return False
    m = {'tree': tree, 'files': sorted(want), 'dirs': folders(src) if tree else []}
    os.sync()                                            # the staged data is on disk before the manifest says so
    tmp = os.path.join(stage, MANIFEST + '.tmp')
    with open(tmp, 'w') as f:
        json.dump(m, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, os.path.join(stage, MANIFEST))
    _fsync_dir(stage)
    _finish(media, stage, m, log)
    return True


def sync(src, media, log=print, rsync='rsync', tree=False):
    """Mirror src into media. True: media now holds src's set. False: media holds the set it had
    (or, after an error mid-swap, complete files only - the next boot's recover() finishes it)."""
    try:
        return _sync(src, media, log, rsync, tree)
    except Exception as e:
        log("USB sync ERROR (%r) - keeping the media folder as it is" % e)
        return False
