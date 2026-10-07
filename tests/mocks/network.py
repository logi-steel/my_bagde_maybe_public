"""Host mock of `network` (access point only)."""

AP_IF = 1
STA_IF = 0


class WLAN:
    IF_AP = 1
    IF_STA = 0
    SEC_OPEN = 0
    SEC_WPA2 = 3
    instances = {}

    def __init__(self, iface):
        self.iface = iface
        self._active = False
        self.cfg = {}
        WLAN.instances[iface] = self

    def active(self, v=None):
        if v is None:
            return self._active
        self._active = bool(v)

    def config(self, *args, **kw):
        if args:
            return self.cfg.get(args[0])
        self.cfg.update(kw)

    def ifconfig(self, *a):
        return ("192.168.4.1", "255.255.255.0", "192.168.4.1", "192.168.4.1")
