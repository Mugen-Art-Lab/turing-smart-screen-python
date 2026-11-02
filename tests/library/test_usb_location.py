# SPDX-License-Identifier: GPL-3.0-or-later
"""Physical Windows hub USB path must take precedence over stale COM numbers."""
import unittest

from library.usb_location import UsbLocationError, resolve_com_port

HUB_1 = "PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(10)#USB(1)"
HUB_2 = "PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(10)#USB(2)"


class UsbLocationTests(unittest.TestCase):
    def test_two_identical_turing_devices_are_distinguished_by_socket(self):
        devices = [
            {"FriendlyName": "Turing (COM3)",
             "InstanceId": "USB\\VID_1A86&PID_5722\\USB35INCHIPSV2",
             "LocationPaths": [HUB_2]},
            {"FriendlyName": "Turing (COM16)",
             "InstanceId": "USB\\VID_1A86&PID_5722\\6&2AB426AA&0&1",
             "LocationPaths": [HUB_1]},
        ]
        self.assertEqual(resolve_com_port(HUB_1, scan=lambda: devices), "COM16")
        self.assertEqual(resolve_com_port(HUB_2, scan=lambda: devices), "COM3")

    def test_port_renumbering_is_resolved_again(self):
        before = [{
            "FriendlyName": "Turing (COM3)",
            "InstanceId": "USB\\VID_1A86&PID_5722\\USB35INCHIPSV2",
            "LocationPaths": [HUB_2],
        }]
        after = [{
            "FriendlyName": "Turing (COM17)",
            "InstanceId": "USB\\VID_1A86&PID_5722\\6&2AB426AA&0&1",
            "LocationPaths": [HUB_2],
        }]
        self.assertEqual(resolve_com_port(HUB_2, scan=lambda: before), "COM3")
        self.assertEqual(resolve_com_port(HUB_2, scan=lambda: after), "COM17")

    def test_not_found_or_ambiguous_is_not_silently_rebound(self):
        with self.assertRaises(UsbLocationError):
            resolve_com_port(HUB_1, scan=lambda: [{
                "FriendlyName": "Turing (COM3)",
                "InstanceId": "USB\\VID_1A86&PID_5722\\USB35INCHIPSV2",
                "LocationPaths": [HUB_2],
            }])
        duplicate = [
            {"FriendlyName": f"Turing (COM{number})",
             "InstanceId": "USB\\VID_1A86&PID_5722\\dup",
             "LocationPaths": [HUB_2]} for number in (3, 16)
        ]
        with self.assertRaises(UsbLocationError):
            resolve_com_port(HUB_2, scan=lambda: duplicate)

    def test_invalid_location_is_refused(self):
        with self.assertRaises(UsbLocationError):
            resolve_com_port("COM3", scan=lambda: [])


if __name__ == "__main__":
    unittest.main()
