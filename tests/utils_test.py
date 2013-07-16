import unittest
from deployer.utils import parse_ifconfig_output

output_1 = """
eth0      Link encap:Ethernet  HWaddr 08:00:27:4c:bc:84
          inet addr:10.0.3.15  Bcast:10.0.3.255  Mask:255.255.255.0
          inet6 addr: fe80::a00:27ff:fe4c:bc83/64 Scope:Link
          UP BROADCAST RUNNING MULTICAST  MTU:1500  Metric:1
          RX packets:3008946 errors:0 dropped:0 overruns:0 frame:0
          TX packets:2245787 errors:0 dropped:0 overruns:0 carrier:0
          collisions:0 txqueuelen:1000
          RX bytes:521487561 (521.4 MB)  TX bytes:1485805583 (1.4 GB)

lo        Link encap:Local Loopback
          inet addr:127.0.0.1  Mask:255.0.0.0
          inet6 addr: ::1/128 Scope:Host
          UP LOOPBACK RUNNING  MTU:16436  Metric:1
          RX packets:448011 errors:0 dropped:0 overruns:0 frame:0
          TX packets:448011 errors:0 dropped:0 overruns:0 carrier:0
          collisions:0 txqueuelen:0
          RX bytes:213448877 (213.4 MB)  TX bytes:213448877 (213.4 MB)

tap7      Link encap:Ethernet  HWaddr 66:72:04:b6:81:d4
          inet addr:46.29.46.232  Bcast:46.28.46.255  Mask:255.255.255.0
          inet6 addr: fe80::6472:4ff:feb6:81d3/64 Scope:Link
          UP BROADCAST RUNNING MULTICAST  MTU:1500  Metric:1
          RX packets:981 errors:0 dropped:631 overruns:0 frame:0
          TX packets:60 errors:0 dropped:0 overruns:0 carrier:0
          collisions:0 txqueuelen:100
          RX bytes:85606 (85.6 KB)  TX bytes:11787 (11.7 KB)"""

output_2 = """
lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
    options=3<RXCSUM,TXCSUM>
    inet6 fe80::1%lo0 prefixlen 64 scopeid 0x1
    inet 127.0.0.1 netmask 0xff000000
    inet6 ::1 prefixlen 128
gif0: flags=8010<POINTOPOINT,MULTICAST> mtu 1280
stf0: flags=0<> mtu 1280
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
    ether 20:c9:d0:83:95:39
    inet6 fe80::22c9:d0ff:fe83:9539%en0 prefixlen 64 scopeid 0x4
    inet 10.126.120.72 netmask 0xffff0000 broadcast 10.126.255.255
    media: autoselect
    status: active
p2p0: flags=8843<UP,BROADCAST,RUNNING,SIMPLEX,MULTICAST> mtu 2304
    ether 02:c9:d0:83:95:44
    media: autoselect
    status: inactive
en2: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
    options=b<RXCSUM,TXCSUM,VLAN_HWTAGGING>
    ether a8:20:67:2b:e0:3e
    inet6 fe80::aa20:66ff:fe2b:e03f%en2 prefixlen 64 scopeid 0x6
    inet 10.126.100.28 netmask 0xffff0000 broadcast 10.126.255.255
    media: autoselect (1000baseT <full-duplex>)
    status: active
"""

class UtilsTest(unittest.TestCase):
    def test_node_initialisation(self):
        self.assertEqual(repr(parse_ifconfig_output(output_1)),
                "IfConfig(interfaces=[" +
                "NetworkInterface(name='eth0', ip='10.0.3.15'), " +
                "NetworkInterface(name='lo', ip='127.0.0.1'), " +
                "NetworkInterface(name='tap7', ip='46.29.46.232')])")

        self.assertEqual(repr(parse_ifconfig_output(output_2)),
                "IfConfig(interfaces=[" +
                "NetworkInterface(name='lo0', ip='127.0.0.1'), " +
                "NetworkInterface(name='en0', ip='10.126.120.72'), " +
                "NetworkInterface(name='en2', ip='10.126.100.28')])")

        # get_interface
        self.assertEqual(repr(parse_ifconfig_output(output_1).get_interface('eth0')),
                "NetworkInterface(name='eth0', ip='10.0.3.15')")
        self.assertRaises(AttributeError, parse_ifconfig_output(output_1).get_interface, 'eth100')

        # get_adress
        self.assertEqual(repr(parse_ifconfig_output(output_1).get_address('10.0.3.15')),
                "NetworkInterface(name='eth0', ip='10.0.3.15')")
        self.assertRaises(AttributeError, parse_ifconfig_output(output_1).get_address, '10.100.100.100')
