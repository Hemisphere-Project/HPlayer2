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


def markers(tmp_path, *names):
    d = tmp_path / 'wifi'
    d.mkdir()
    for n in names:
        (d / (n + '.nmconnection')).write_text('')
    return str(d)


def test_markers_reproduce_the_biennale_rule(tmp_path):
    assert bootconf.markers_sync(markers(tmp_path), lambda i: True) == (None, None)


def test_markers_eth0_beats_wlan0(tmp_path):
    d = markers(tmp_path, 'eth0-sync-STA', 'wlan0-sync-AP')
    assert bootconf.markers_sync(d, lambda i: False) == ('eth0', 'slave')


def test_markers_wlan0_falls_to_wlan1_then_none(tmp_path):
    d = markers(tmp_path, 'wlan0-sync-AP')
    assert bootconf.markers_sync(d, lambda i: i == 'wlan0') == ('wlan0', 'master')
    assert bootconf.markers_sync(d, lambda i: i == 'wlan1') == ('wlan1', 'master')
    assert bootconf.markers_sync(d, lambda i: False) == (None, 'master')


def test_conf_role_wins_over_markers(tmp_path):
    d = markers(tmp_path, 'eth0-sync-AP')
    c = bootconf.load(write(tmp_path, '[sync]\nrole = slave\niface = wlan0\n'))
    assert bootconf.resolve_sync(c, wifi_dir=d, has_interface=lambda i: True) == ('wlan0', 'slave')


def test_conf_without_role_leaves_the_markers_in_charge(tmp_path):
    d = markers(tmp_path, 'eth0-sync-AP')
    c = bootconf.load(write(tmp_path, '[player]\nprofile = biennale\n'))
    assert bootconf.resolve_sync(c, wifi_dir=d, has_interface=lambda i: True) == ('eth0', 'master')


def test_conf_role_none_turns_sync_off_despite_markers(tmp_path):
    d = markers(tmp_path, 'eth0-sync-AP')
    c = bootconf.load(write(tmp_path, '[sync]\nrole = none\n'))
    assert bootconf.resolve_sync(c, wifi_dir=d, has_interface=lambda i: True) == (None, None)


def test_role_the_profile_cannot_run_falls_back_to_markers(tmp_path):
    d = markers(tmp_path, 'eth0-sync-STA')
    c = bootconf.load(write(tmp_path, '[sync]\nrole = elected\n'))
    got = bootconf.resolve_sync(c, roles=('master', 'slave'), wifi_dir=d, has_interface=lambda i: True)
    assert got == ('eth0', 'slave')
    assert any('elected' in e for e in c.errors)


def test_auto_never_guesses_eth0(tmp_path):
    c = bootconf.load(write(tmp_path, '[sync]\niface = auto\n'))
    assert c.sync_iface(lambda i: i in ('eth0', 'wlan0')) == 'wlan0'
    assert c.sync_iface(lambda i: i == 'eth0') is None


def test_iface_alone_is_read_without_a_role(tmp_path):
    c = bootconf.load(write(tmp_path, '[sync]\niface = wlan1\n'))
    assert c.sync_role() is None
    assert c.sync_iface(lambda i: False) == 'wlan1'      # 26-anna: role is elected by design


def test_pick_profile_reads_the_conf_only_on_auto(tmp_path):
    c = bootconf.load(write(tmp_path, '[player]\nprofile = 26-anna\n'))
    assert bootconf.pick_profile('auto', c) == '26-anna'
    assert bootconf.pick_profile('biennale', c) == 'biennale'


def test_pick_profile_falls_back_to_default(tmp_path):
    assert bootconf.pick_profile('auto', bootconf.load(str(tmp_path / 'none'))) == 'default'
    c = bootconf.load(write(tmp_path, '[player]\nprofile = ../../etc/x\n'))
    assert bootconf.pick_profile('auto', c, default='looper') == 'looper'
    assert c.errors


# --- [schedule] and [interfaces] (hplayer2#t-101 ②) ---------------------------------------

def test_switches_keep_the_profile_default_when_absent(tmp_path):
    c = bootconf.load(write(tmp_path, '[player]\nprofile = biennale\n'))
    assert c.interface('nowde', True) is True
    assert c.interface('teleco2', False) is False
    assert c.schedule(True) is True
    assert c.schedule_require_rtc(True) is True
    assert c.schedule_seeds() == {}
    assert c.errors == []


def test_switches_off_and_on(tmp_path):
    c = bootconf.load(write(tmp_path, """
[schedule]
enabled = no
require_rtc = no
[interfaces]
nowde = no
teleco2 = yes
"""))
    assert c.schedule(True) is False
    assert c.schedule_require_rtc(True) is False
    assert c.interface('nowde', True) is False
    assert c.interface('teleco2', False) is True
    assert c.errors == []


def test_a_switch_the_profile_cannot_run_is_reported_and_off(tmp_path):
    c = bootconf.load(write(tmp_path, '[interfaces]\nkeypad = yes\nnowde = no\n[schedule]\nenabled = yes\n'))
    assert c.interface('keypad', False, runs=False) is False
    assert c.interface('nowde', False, runs=False) is False      # asked off: nothing to report
    assert c.interface('teleco2', False, runs=False) is False    # not asked: nothing to report
    assert c.schedule(False, runs=False) is False
    assert c.errors == ['interfaces.keypad: not run by this profile',
                        'schedule.enabled: not run by this profile']


def test_schedule_window_seeds_are_checked_and_normalised(tmp_path):
    c = bootconf.load(write(tmp_path, """
[schedule]
enabled = yes
open    = 8:30
close   = 19:00
days    = 0111111     ; closed on Mondays
reboot  = yes
"""))
    assert c.schedule_seeds() == {'schedule-enable': True, 'schedule-open': '08:30',
                                  'schedule-close': '19:00', 'schedule-days': '0111111',
                                  'schedule-reboot': True}
    assert c.errors == []


def test_bad_window_values_are_left_to_the_cfg(tmp_path):
    c = bootconf.load(write(tmp_path, '[schedule]\nopen = 25:00\nclose = 7pm\ndays = weekdays\n'))
    assert c.schedule_seeds() == {}
    assert len(c.errors) == 3


def test_enabled_no_seeds_nothing(tmp_path):
    # the profile does not load the schedule at all: no key to seed
    c = bootconf.load(write(tmp_path, '[schedule]\nenabled = no\nopen = 09:00\n'))
    assert c.schedule_seeds() == {'schedule-open': '09:00'}
    assert c.schedule(True) is False


def test_unknown_sections_and_keys_are_reported_never_fatal(tmp_path):
    c = bootconf.load(write(tmp_path, '[interfaces]\ntelco2 = no\n[players]\nprofile = x\n'))
    assert c.present is True
    assert sorted(c.errors) == ['[players]: unknown section', 'interfaces.telco2: unknown key']
    assert c.interface('teleco2', True) is True      # the typo changed nothing


def test_seeds_set_up_a_fresh_card_and_the_saved_cfg_wins(tmp_path, monkeypatch):
    import json
    from core.engine.settings import Settings

    class HP:
        def autoBind(self, m): pass
        def emit(self, *a): pass

    c = bootconf.load(write(tmp_path, '[schedule]\nenabled = yes\nopen = 08:30\n'))
    for saved, want_open, want_enable in ((None, '08:30', True),
                                          ({'schedule-open': '11:00'}, '11:00', True),
                                          ({'schedule-enable': False}, '08:30', False)):
        monkeypatch.setattr(Settings, '_settings', dict(Settings._settings))
        cfg = tmp_path / 'hplayer2-biennale.cfg'
        if saved is None:
            cfg.unlink(missing_ok=True)
        else:
            cfg.write_text(json.dumps(saved))
        s = Settings(HP(), persistent=str(cfg))
        s._settings.update(c.schedule_seeds())          # what biennale does before addInterface
        s._settings.setdefault('schedule-open', '10:00')  # the interface's own default
        s.load()
        assert (s.get('schedule-open'), s.get('schedule-enable')) == (want_open, want_enable)
