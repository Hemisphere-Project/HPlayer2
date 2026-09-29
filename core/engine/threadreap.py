"""Join finished threads that something still references — and say what they were.

CPython 3.13+ starts OS threads joinable and keeps a finished thread's stack mapping (8 MB on
Linux by default) until the thread is joined or its Thread object is freed. Up to 3.12 the OS
thread was detached at creation, so a finished Thread kept in an attribute cost nothing — and
HPlayer2 keeps plenty (a peer's link Timer, a clock client's refresh Timer, a player's reader
thread, ...). On the 32-bit Biennale players (~2 GB of usable address space) that surfaced as
`can't start new thread` after 7–20 h on CPython 3.14: VmSize 2.05 GB with 36 live threads
(hplayer2#t-075, KOUAGOU 2026-09-25..29).

Measured on the players' own build (cpython-3.14.0, 2026-09-29): 200 finished threads that are
still referenced = +1.6 GB VmSize; join() or dropping the reference gives it all back; the same
program on 3.12 grows by nothing.

This module does not depend on the rest of HPlayer2 (importable by path from a test).
Usage: hook `track(thread)` into Thread.start (health does), call `reap()` every few seconds.
"""
import threading
import weakref
import collections

_started = weakref.WeakSet()                # every Thread that went through start(); weak: never a holder itself
_labels = weakref.WeakKeyDictionary()       # thread -> label, taken at start (Thread drops _target after run())
_reaped = collections.Counter()             # label -> threads joined since start
_lock = threading.Lock()


def label(t):
    """What the thread runs: 'Timer -> Peer.linker', 'Thread -> MpvPlayer._mpv_communicate',
    'Thread -> lambda http2.py:128', 'Thread nowde-close-out'. Enough to find the holder."""
    kind = t.__class__.__name__
    fn = getattr(t, 'function', None) or getattr(t, '_target', None)
    if fn is not None:
        name = getattr(fn, '__qualname__', None) or repr(fn)
        if name == '<lambda>' or name.endswith('.<lambda>'):
            code = getattr(fn, '__code__', None)
            name = 'lambda %s:%d' % (code.co_filename.rsplit('/', 1)[-1], code.co_firstlineno) if code else 'lambda'
        return '%s -> %s' % (kind, name)
    n = getattr(t, 'name', '') or ''
    if n.startswith('Thread-') and '(' in n:            # 'Thread-12 (worker)': the target's name, kept after run()
        return '%s -> %s' % (kind, n[n.index('(') + 1:].rstrip(')'))
    return '%s %s' % (kind, n.rstrip('0123456789-')) if n and not n.startswith('Thread-') else kind


def track(t):
    """Remember a thread about to be started (before start(): a short-lived target is gone from
    the object by the time start() returns). Cheap. A start() that then fails → untrack()."""
    try:
        lbl = label(t)
    except Exception:
        lbl = '?'
    try:
        with _lock:
            _started.add(t)
            _labels[t] = lbl
    except TypeError:
        pass


def untrack(t):
    with _lock:
        _started.discard(t)
        _labels.pop(t, None)


def reap():
    """Join every tracked thread that has finished. Returns Counter{label: n} for this round.
    A join on a finished thread returns at once and releases its stack; a thread still running
    stays tracked and untouched (timeout 0). Never raises."""
    out = collections.Counter()
    with _lock:
        cand = list(_started)
    for t in cand:
        try:
            started = t._started.is_set()
            alive = started and t.is_alive()
        except Exception:
            started, alive = True, False
        if alive:
            continue
        if not started:
            continue                        # start() still in progress (a failed start is untracked by its caller)
        try:
            t.join(0)
        except Exception:                   # current thread, dummy thread
            pass
        with _lock:
            _started.discard(t)
            lbl = _labels.pop(t, None)
        out[lbl or '?'] += 1
    if out:
        _reaped.update(out)
    return out


def totals():
    """Counter{label: n} since start (a copy)."""
    return collections.Counter(_reaped)


def tracked():
    with _lock:
        return len(_started)
