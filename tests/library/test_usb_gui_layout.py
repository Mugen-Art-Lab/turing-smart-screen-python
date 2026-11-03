# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-level guardrails for the compact Turing USB settings redesign.

Actual rendering/DPI and font sizes still require manual Windows UI review.
"""
import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "configure.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def ui_class_method(name):
    gui = next(n for n in TREE.body if isinstance(n, ast.ClassDef)
               and n.name == "TuringConfigWindow")
    return next(n for n in gui.body if isinstance(n, ast.FunctionDef)
                and n.name == name)


def control_placement(method_name, widget_name):
    """Read literal Tk place() coordinates without importing GUI dependencies."""
    method = ui_class_method(method_name)
    for node in ast.walk(method):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "place":
            continue
        widget = node.func.value
        if not (isinstance(widget, ast.Attribute) and widget.attr == widget_name):
            continue
        return {k.arg: k.value.value for k in node.keywords
                if isinstance(k.value, ast.Constant)}
    raise AssertionError(f"Missing place for {widget_name}")


class UsbDialogLayoutContractTests(unittest.TestCase):
    def test_compact_main_controls_have_vertical_separation(self):
        com = control_placement("__init__", "com_cb")
        toggle = control_placement("__init__", "usb_checkbox")
        summary = control_placement("__init__", "usb_status_label")
        orient = control_placement("__init__", "orient_cb")
        self.assertGreaterEqual(toggle["y"] - com["y"], 34)
        self.assertGreaterEqual(summary["y"] - toggle["y"], 29)
        self.assertGreaterEqual(orient["y"] - summary["y"], 35)
        self.assertEqual(summary["width"], 425)

    def test_usb_dialog_is_roomy_and_uses_grid_not_main_window(self):
        self.assertIn('popup.geometry("770x345")', SOURCE)
        self.assertIn('container.columnconfigure(1, weight=1)', SOURCE)
        self.assertIn('textvariable=self.usb_path, state="readonly"', SOURCE)
        self.assertNotIn("self.usb_path_entry.place(", SOURCE)
        self.assertNotIn("self.usb_refresh_btn.place(", SOURCE)
        self.assertIn("self.usb_dialog_ports = ttk.Combobox(", SOURCE)

    def test_old_com_is_explicitly_a_fallback(self):
        self.assertIn("COM port (saved fallback)", SOURCE)
        self.assertIn("Preselect the actual bound Windows COM", SOURCE)
        self.assertIn("bound_com = resolve_com_port(self.usb_path.get())", SOURCE)
        self.assertIn('selected = self.usb_bind_com.get()', SOURCE)
        self.assertIn('if not self._validate_usb_save():', SOURCE)


if __name__ == "__main__":
    unittest.main()
