"""
core/engine/usbsync.py (hplayer2#t-092, from anna-players#t-018): the boot USB sync never leaves the
media folder empty. Real rsync on temp folders; a copy cut short is played by a stand-in rsync, a
power cut by stopping between steps and booting again (recover()).

Two shapes, the two filters the profiles used: flat (26-anna, anna: top-level files, no dotfiles)
and tree (ecel: the whole stick, sub-folders and dotfiles included).
"""
import json, os, shutil, stat
import pytest

from core.engine import usbsync

pytestmark = pytest.mark.skipif(shutil.which('rsync') is None, reason='needs rsync')

QUIET = lambda *a: None


def put(d, files):
    os.makedirs(d, exist_ok=True)
    for name, body in files.items():
        with open(os.path.join(d, name), 'w') as f:
            f.write(body)


def tree(d):
    return {n: open(os.path.join(d, n)).read() for n in sorted(os.listdir(d))
            if os.path.isfile(os.path.join(d, n))}


def rtree(d):
    """Every file at any depth, {relative path: content}."""
    out = {}
    for root, _, files in os.walk(d):
        for n in files:
            p = os.path.join(root, n)
            out[os.path.relpath(p, d)] = open(p).read()
    return out


@pytest.fixture
def card(tmp_path):
    usb, media = str(tmp_path / 'usb' / 'sync'), str(tmp_path / 'data' / 'media')
    put(media, {'1-old.mp3': 'old one', 'keep.mp3': 'same', '.hidden': 'x'})
    os.makedirs(os.path.join(media, 'show2'))
    put(os.path.join(media, 'show2'), {'a.mp3': 'sub'})
    old = os.stat(os.path.join(media, 'keep.mp3'))
    os.utime(os.path.join(media, 'keep.mp3'), (old.st_atime, 1_700_000_000))
    put(usb, {'1-new.mp3': 'new one', 'keep.mp3': 'same', '.Trash': 'x', 'Thumbs.db': 'x'})
    os.utime(os.path.join(usb, 'keep.mp3'), (old.st_atime, 1_700_000_000))
    return usb, media


@pytest.fixture
def stick(tmp_path):
    """ecel's shape: the stick's root IS the source, mirrored whole."""
    usb, media = str(tmp_path / 'usb'), str(tmp_path / 'data' / 'media')
    put(media, {'1-old.mp4': 'old', 'keep.mp4': 'same'})
    put(os.path.join(media, 'gone'), {'x.mp4': 'gone'})
    put(os.path.join(media, 'show'), {'a.mp4': 'a, the old take', 'b.mp4': 'b'})   # sizes differ: rsync's quick check
    put(usb, {'1-new.mp4': 'new', 'keep.mp4': 'same', '.dot': 'd'})
    put(os.path.join(usb, 'show'), {'a.mp4': 'a new'})
    put(os.path.join(usb, 'show', 'deep'), {'c.mp4': 'c'})
    os.makedirs(os.path.join(usb, 'empty'))
    for d in (media, usb):
        p = os.path.join(d, 'keep.mp4')
        os.utime(p, (os.stat(p).st_atime, 1_700_000_000))
    return usb, media


def fake_rsync(tmp_path, script):
    p = tmp_path / 'rsync'
    p.write_text('#!/bin/sh\n' + script + '\n')
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


# ─── flat: 26-anna, anna ───────────────────────────────────────────────────────────────────────

def test_sync_replaces_the_set(card):
    usb, media = card
    ino = os.stat(os.path.join(media, 'keep.mp3')).st_ino
    assert usbsync.sync(usb, media, log=QUIET)
    assert tree(media) == {'.hidden': 'x', '1-new.mp3': 'new one', 'keep.mp3': 'same'}
    assert tree(os.path.join(media, 'show2')) == {'a.mp3': 'sub'}       # sub-folders untouched
    assert os.stat(os.path.join(media, 'keep.mp3')).st_ino == ino     # unchanged file: linked, not copied
    assert not os.path.exists(media + '.sync')


def test_media_dir_keeps_its_inode(card):
    usb, media = card                                                  # FileManager's watchdog sits on it
    ino = os.stat(media).st_ino
    usbsync.sync(usb, media, log=QUIET)
    assert os.stat(media).st_ino == ino


def test_rsync_error_keeps_the_set(card, tmp_path):
    usb, media = card
    before = tree(media)
    bad = fake_rsync(tmp_path, 'eval last=\\${$#}; echo partial > "$last/1-new.mp3"; '
                               'echo tmp > "$last/.1-new.mp3.Ab12Cd"; exit 23')
    assert not usbsync.sync(usb, media, log=QUIET, rsync=bad)
    assert tree(media) == before
    assert not os.path.exists(media + '.sync')


def test_short_copy_with_exit_0_keeps_the_set(card, tmp_path):
    usb, media = card
    before = tree(media)
    liar = fake_rsync(tmp_path, 'eval last=\\${$#}; echo par > "$last/1-new.mp3"; exit 0')
    assert not usbsync.sync(usb, media, log=QUIET, rsync=liar)
    assert tree(media) == before


def test_empty_sync_folder_keeps_the_set(card):
    usb, media = card
    for n in os.listdir(usb):
        os.remove(os.path.join(usb, n))
    before = tree(media)
    assert not usbsync.sync(usb, media, log=QUIET)
    assert tree(media) == before


def test_power_cut_while_staging_drops_the_stage(card):
    usb, media = card
    before = tree(media)
    put(media + '.sync', {'1-new.mp3': 'new', '.1-new.mp3.Ab12Cd': 'half'})   # no manifest
    assert not usbsync.recover(media, log=QUIET)
    assert tree(media) == before and not os.path.exists(media + '.sync')


def test_power_cut_during_the_swap_is_finished_at_next_boot(card):
    usb, media = card
    stage = media + '.sync'
    put(stage, {'1-new.mp3': 'new one'})                              # keep.mp3 already moved
    with open(os.path.join(stage, usbsync.MANIFEST), 'w') as f:
        json.dump({'tree': False, 'files': ['1-new.mp3', 'keep.mp3'], 'dirs': []}, f)
    assert usbsync.recover(media, log=QUIET)
    assert tree(media) == {'.hidden': 'x', '1-new.mp3': 'new one', 'keep.mp3': 'same'}
    assert tree(os.path.join(media, 'show2')) == {'a.mp3': 'sub'}
    assert not os.path.exists(stage)


def test_a_manifest_of_another_shape_drops_the_stage(card):
    usb, media = card
    before = tree(media)
    put(media + '.sync', {'1-new.mp3': 'new one'})
    with open(os.path.join(media + '.sync', usbsync.MANIFEST), 'w') as f:
        json.dump(['1-new.mp3'], f)                                    # t-018's draft format: never shipped
    assert not usbsync.recover(media, log=QUIET)
    assert tree(media) == before and not os.path.exists(media + '.sync')


# ─── tree: ecel ────────────────────────────────────────────────────────────────────────────────

def test_tree_mirrors_the_stick(stick):
    usb, media = stick
    ino_dir, ino_keep = os.stat(media).st_ino, os.stat(os.path.join(media, 'keep.mp4')).st_ino
    assert usbsync.sync(usb, media, log=QUIET, tree=True)
    assert rtree(media) == {'1-new.mp4': 'new', 'keep.mp4': 'same', '.dot': 'd',
                            'show/a.mp4': 'a new', 'show/deep/c.mp4': 'c'}
    assert sorted(usbsync.folders(media)) == ['empty', 'show', 'show/deep']   # `gone` went, `empty` came
    assert os.stat(media).st_ino == ino_dir
    assert os.stat(os.path.join(media, 'keep.mp4')).st_ino == ino_keep
    assert not os.path.exists(media + '.sync')


def test_tree_rsync_error_keeps_the_whole_tree(stick, tmp_path):
    usb, media = stick
    before, dirs = rtree(media), usbsync.folders(media)
    bad = fake_rsync(tmp_path, 'eval last=\\${$#}; mkdir -p "$last/show"; echo half > "$last/show/a.mp4"; exit 23')
    assert not usbsync.sync(usb, media, log=QUIET, rsync=bad, tree=True)
    assert rtree(media) == before and usbsync.folders(media) == dirs
    assert not os.path.exists(media + '.sync')


def test_tree_swap_cut_short_is_finished_at_next_boot(stick):
    usb, media = stick
    stage = media + '.sync'
    put(os.path.join(stage, 'show'), {'a.mp4': 'a new'})
    put(media, {'1-new.mp4': 'new'})                                   # moved before the cut
    with open(os.path.join(stage, usbsync.MANIFEST), 'w') as f:
        json.dump({'tree': True, 'files': ['1-new.mp4', 'keep.mp4', 'show/a.mp4'], 'dirs': ['show']}, f)
    assert usbsync.recover(media, log=QUIET)                            # no shape given: the manifest has it
    assert rtree(media) == {'1-new.mp4': 'new', 'keep.mp4': 'same', 'show/a.mp4': 'a new'}
    assert usbsync.folders(media) == ['show']
    assert not os.path.exists(stage)


def test_tree_a_folder_becomes_a_file_and_back(tmp_path):
    usb, media = str(tmp_path / 'usb'), str(tmp_path / 'media')
    put(os.path.join(media, 'x'), {'in.mp4': 'old'})
    put(media, {'y': 'old file'})
    put(usb, {'x': 'now a file'})
    put(os.path.join(usb, 'y'), {'z.mp4': 'now a folder'})
    assert usbsync.sync(usb, media, log=QUIET, tree=True)
    assert rtree(media) == {'x': 'now a file', 'y/z.mp4': 'now a folder'}


# ─── never in the profile's way ────────────────────────────────────────────────────────────────

def test_an_error_never_reaches_the_profile(card, tmp_path):
    usb, media = card
    before = tree(media)
    logged = []
    assert not usbsync.sync(usb, media, log=lambda *a: logged.append(a),
                            rsync=str(tmp_path / 'no-rsync-here'))
    assert tree(media) == before
    assert any('ERROR' in str(a) for a in logged)
    usbsync.recover(media, log=QUIET)                                  # the next boot drops the stage
    assert not os.path.exists(media + '.sync') and tree(media) == before
