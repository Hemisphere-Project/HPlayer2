"""A Regie project over 1 MB still saves (sacvp-kernel4-2025 39c82e3, « fix sio limit »).

The page saves the whole project as ONE socket.io message. python-engineio refuses any
message over `max_http_buffer_size` — 1 MB by default — so a show with a big grid lost its
save without a word on the page. The real Regie server runs here on a free port, and a raw
Engine.IO long-polling client (stdlib only) sends a 2 MB save to it.
"""
import json, os, time, urllib.error, urllib.request

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core.interfaces.regie as regie                          # noqa: E402
from test_socketio_drain import RegieStub, freePort                 # noqa: E402


def poll(base, sid=None, body=None, timeout=5.0):
    url = base + '/socket.io/?EIO=4&transport=polling' + ('&sid=' + sid if sid else '')
    req = urllib.request.Request(url, data=body.encode() if body is not None else None,
                                 headers={'Content-Type': 'text/plain;charset=UTF-8'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode()


def wait_up(base, timeout=5.0):
    deadline = time.time() + timeout
    while True:
        try:
            return poll(base, timeout=1.0)
        except OSError:
            if time.time() > deadline:
                raise
            time.sleep(0.05)


def save_project(base, project):
    _, opened = wait_up(base)
    sid = json.loads(opened[1:])['sid']                  # '0{"sid": …}'
    poll(base, sid, '40')                                # socket.io CONNECT
    poll(base, sid)                                      # its ack
    try:
        status, _ = poll(base, sid, '42' + json.dumps(['save', project]))
    except urllib.error.HTTPError as e:
        status = e.code
    except TimeoutError:            # an over-size POST may be left unanswered rather than refused
        status = None
    return status


def test_a_project_over_one_megabyte_saves(tmp_path):
    iface = RegieStub(str(tmp_path))
    port = freePort()
    server = regie.ThreadedHTTPServer(iface, port)
    server.start()
    try:
        project = json.dumps({'pool': [{'name': 'x' * 100}] * 20000, 'project': [[]]})
        assert len(project) > 2_000_000
        status = save_project('http://127.0.0.1:%d' % port, project)
        assert status == 200
        path = os.path.join(str(tmp_path), 'project.json')
        deadline = time.time() + 5.0
        while time.time() < deadline and not (os.path.exists(path) and os.path.getsize(path) == len(project)):
            time.sleep(0.05)
        with open(path) as f:
            assert f.read() == project
    finally:
        server.stop()
