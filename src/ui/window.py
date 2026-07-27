import json
import os
import sys
import threading
import time
import webbrowser

import webview

from src.ui.controller import NidusController


class Api:
    def __init__(self, app_dir, version, debug=False):
        self.app_dir = app_dir
        self.version = version
        self.window = None
        self.controller = NidusController(app_dir, version, self.notify, debug=debug)

    def attach(self, window):
        self.window = window
        self.controller.attach_window(window)

    def notify(self, event, payload=None):
        if not self.window:
            return
        try:
            self.window.evaluate_js(
                "window.nidusEvent(%s,%s)" % (json.dumps(event), json.dumps(payload))
            )
        except Exception:
            pass

    def get_state(self):
        return self.controller.get_state()

    def patch_config(self, patch):
        return self.controller.patch_config(patch or {})

    def select_region(self):
        return self.controller.select_region()

    def translate_toggle(self):
        return self.controller.translate_toggle()

    def toggle_overlay(self):
        return self.controller.toggle_overlay()

    def open_url(self, url):
        webbrowser.open(url)


def launch(app_dir, version, debug=False):
    api = Api(app_dir, version, debug=debug)
    web_dir = os.path.join(getattr(sys, "_MEIPASS", app_dir), "src", "ui", "web")
    window = webview.create_window(
        "Nidus",
        os.path.join(web_dir, "index.html"),
        js_api=api,
        width=1160,
        height=788,
        min_size=(900, 640),
        background_color="#1E1B17",
    )
    api.attach(window)

    def boot():
        api.notify("state", api.get_state())

    def on_closing():
        api.controller.shutdown()

    window.events.closing += on_closing
    webview.start(boot, debug=debug, gui="edgechromium" if sys.platform == "win32" else None)
