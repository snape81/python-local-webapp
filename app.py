import webview
from device.device_client import DeviceClient
import platform

class Api:
    def __init__(self):
        self.client = DeviceClient()

    def get_status(self):
        return self.client.get_status()

    def set_config(self, config):
        return self.client.set_config(config)

api = Api()

if __name__ == '__main__':
    webview.create_window(
        "Device Manager",
        "ui/index.html",
        js_api=api,
        width=900,
        height=600
    )

    if platform.system() == "Linux":
        webview.start(gui='qt')
    else:
        webview.start()
