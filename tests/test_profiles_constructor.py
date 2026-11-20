"""Every profile calls HPlayer2() with keywords the constructor still takes (hplayer2#t-104).

8d6ea47 (2025-10-22) renamed the constructor's arguments to mediaPath/config/datadir/extraMediaPath
and kept a shim for the old POSITIONAL call only. profiles/default.py kept the old keywords
(basepath=, settingspath=) and raised TypeError at import: every RastaOS-7.5 card with no role file
runs hplayer2@auto -> 'default', and crash-looped (bench-03, 2026-11-20). Read statically: no
profile is imported, so no player, mpv or zyre is needed.
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _init_params():
    tree = ast.parse((ROOT / 'core/engine/hplayer.py').read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == 'HPlayer2':
            for f in node.body:
                if isinstance(f, ast.FunctionDef) and f.name == '__init__':
                    a = f.args
                    return [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs][1:]
    raise AssertionError('HPlayer2.__init__ not found')


def _calls(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'HPlayer2':
            yield node


def test_every_profile_uses_the_constructors_keywords():
    params = set(_init_params())
    assert {'mediaPath', 'config'} <= params
    bad = []
    profiles = sorted(p for p in (ROOT / 'profiles').glob('*.py'))
    assert any(p.name == 'default.py' for p in profiles)
    for p in profiles:
        for call in _calls(p):
            unknown = [k.arg for k in call.keywords if k.arg and k.arg not in params]
            if unknown or len(call.args) > len(params):
                bad.append('%s:%d %s' % (p.name, call.lineno, unknown or 'too many positional args'))
    assert not bad, 'HPlayer2() calls the constructor no longer takes: ' + ', '.join(bad)
