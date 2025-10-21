from core.engine import network


def test_get_ethmac_prefers_mac(monkeypatch):
    def fake_interfaces():
        return ["eth0", "lo"]

    def fake_ifaddresses(iface):
        if iface == "eth0":
            mapping = {
                network.AF_LINK: [{"addr": "aa:bb:cc:dd:ee:ff"}],
            }
            if network.AF_PACKET != network.AF_LINK:
                mapping[network.AF_PACKET] = [{"addr": "11:22:33:44:55:66"}]
            return mapping
        return {}

    monkeypatch.setattr(network.ni, "interfaces", fake_interfaces)
    monkeypatch.setattr(network.ni, "ifaddresses", fake_ifaddresses)

    assert network.get_ethmac() == "aa:bb:cc:dd:ee:ff"


def test_get_rssi_without_iw(monkeypatch):
    monkeypatch.setattr(network.shutil, "which", lambda _: None)
    assert network.get_rssi("wlan0") is None


def test_get_essid_without_iw(monkeypatch):
    monkeypatch.setattr(network.shutil, "which", lambda _: None)
    assert network.get_essid("wlan0") == ""
