from core.engine import bootconf


def write(tmp_path, text):
    p = tmp_path / 'hplayer2.conf'
    p.write_text(text)
    return str(p)


def test_absent_file_keeps_every_default(tmp_path):
    c = bootconf.load(str(tmp_path / 'nope.conf'))
    assert c.present is False
    assert c.profile('biennale') == 'biennale'
    assert c.sync_role() is None
    assert c.sync_iface(lambda i: True) is None
    assert c.wall_sync() is False
    assert c.wall_sync(True) is True
    assert c.flag('interfaces', 'keypad', True) is True


def test_env_overrides_the_default_path(tmp_path, monkeypatch):
    monkeypatch.setenv(bootconf.ENV_PATH, write(tmp_path, '[player]\nprofile = anna\n'))
    c = bootconf.load()
    assert c.present is True
    assert c.profile() == 'anna'


def test_biennale_master_role(tmp_path):
    c = bootconf.load(write(tmp_path, """
[player]
profile = biennale
[sync]
iface = eth0
role  = master   ; the AP side
wall  = yes
[schedule]
enabled = yes
"""))
    assert c.present and c.errors == []
    assert c.sync_role() == 'master'
    assert c.sync_iface(lambda i: False) == 'eth0'     # explicit iface: no probing
    assert c.wall_sync() is True
    assert c.flag('schedule', 'enabled') is True
    assert c.flag('interfaces', 'nowde') is False


def test_auto_iface_follows_the_live_profiles_order(tmp_path):
    c = bootconf.load(write(tmp_path, '[sync]\nrole = elected\n'))
    assert c.sync_iface(lambda i: i in ('wlan0', 'wint')) == 'wint'
    assert c.sync_iface(lambda i: i in ('wlan1',)) == 'wlan1'
    assert c.sync_iface(lambda i: False) is None


def test_role_none_and_iface_none_turn_sync_off(tmp_path):
    c = bootconf.load(write(tmp_path, '[sync]\nrole = none\niface = none\n'))
    assert c.sync_role() is None
    assert c.sync_iface(lambda i: True) is None


def test_typos_are_reported_never_fatal(tmp_path):
    c = bootconf.load(write(tmp_path, '[sync]\nrole = maser\nwall = perhaps\n'))
    assert c.sync_role() is None
    assert c.wall_sync(True) is True
    assert len(c.errors) == 2


def test_malformed_file_reads_as_absent(tmp_path):
    c = bootconf.load(write(tmp_path, 'role = master\n'))        # no section header
    assert c.present is False
    assert c.errors
    assert c.sync_role('slave') == 'slave'
