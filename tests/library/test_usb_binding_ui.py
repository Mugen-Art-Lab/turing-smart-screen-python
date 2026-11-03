# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from library.usb_binding_ui import location_for_selected_com, check_binding_disable
from library.usb_location import UsbDisplayPort, UsbLocationError

A = "PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(10)#USB(1)"
B = "PCIROOT(0)#PCI(1400)#USBROOT(0)#USB(10)#USB(2)"
DEVICES = [
    UsbDisplayPort("COM3", "USB\\VID_1A86&PID_5722\\USB35INCHIPSV2", (B,)),
    UsbDisplayPort("COM16", "USB\\VID_1A86&PID_5722\\6&2AB426AA&0&1", (A,)),
]


class UsbBindingUiTests(unittest.TestCase):
    def test_selects_only_target_usb_socket(self):
        self.assertEqual(location_for_selected_com("COM16", DEVICES), A)
        self.assertEqual(location_for_selected_com("com3", DEVICES), B)

    def test_auto_or_stale_port_cannot_be_bound(self):
        for com in ("AUTO", "COM17", ""):
            with self.assertRaises(UsbLocationError):
                location_for_selected_com(com, DEVICES)

    def test_duplicate_com_fails_closed(self):
        with self.assertRaises(UsbLocationError):
            location_for_selected_com("COM16", DEVICES + [DEVICES[1]])

    def test_existing_binding_does_not_depend_on_stale_configured_com(self):
        self.assertEqual(check_binding_disable(A, True, "COM3", lambda _: "COM16"), ("", ""))

    def test_unbinding_cannot_open_wrong_display(self):
        self.assertEqual(check_binding_disable(A, False, "COM3", lambda _: "COM16"),
                         ("mismatch", "COM16"))
        self.assertEqual(check_binding_disable(A, False, "COM16", lambda _: "COM16"), ("", ""))

    def test_offline_binding_cannot_be_unbound_by_mistake(self):
        def offline(_):
            raise UsbLocationError("Not present")
        self.assertEqual(check_binding_disable(A, False, "COM3", offline),
                         ("unavailable", ""))


if __name__ == "__main__":
    unittest.main()
