import json
import os
import sys
import webbrowser

import webview

from src.translator import KNOWN_PROVIDERS

DEFAULT_CONFIG = {
    "api_key": "", "api_provider": "openrouter", "model": "",
    "target_language": "Português", "region": None, "monitor_index": 0,
    "mode": "once", "capture_interval": 1.5, "overlay_style": "transparent",
    "hotkey_region": "f9", "hotkey_translate": "f10", "hotkey_toggle": "f11",
    "hotkey_audio": "f12", "audio_capture_mode": "system", "whisper_model": "tiny",
    "audio_source_language": "auto", "interview_context": "",
}


class Api:
    def __init__(self, app_dir, version):
        self.app_dir, self.version = app_dir, version
        self.window = None
        self.config = dict(DEFAULT_CONFIG)
        self.config_file = os.path.join(app_dir, "config.json")
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, encoding="utf-8") as f:
                    self.config.update(json.load(f))
            except (OSError, ValueError):
                pass

    def attach(self, window):
        self.window = window

    def state(self):
        return {"version": self.version, "config": self.config,
                "providers": list(KNOWN_PROVIDERS.keys())}

    def get_state(self):
        return self.state()

    def patch_config(self, patch):
        self.config.update(patch)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
        return {"ok": True}

    def open_url(self, url):
        webbrowser.open(url)

    def notify(self, event, payload=None):
        if self.window:
            self.window.evaluate_js("window.nidusEvent(%s,%s)" %
                (json.dumps(event), json.dumps(payload)))


def launch(app_dir, version, debug=False):
    api = Api(app_dir, version)
    web_dir = os.path.join(getattr(sys, "_MEIPASS", app_dir), "src", "ui", "web")
    window = webview.create_window("Nidus", os.path.join(web_dir, "index.html"),
        js_api=api, width=1160, height=788, min_size=(900, 640),
        background_color="#1E1B17")
    api.attach(window)

    def boot():
        api.notify("state", api.state())

    webview.start(boot, debug=debug,
                  gui="edgechromium" if sys.platform == "win32" else None)
