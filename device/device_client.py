import requests

class DeviceClient:
    def __init__(self, base_url="http://127.0.0.1:5001/api"):
        self.base_url = base_url

    def get_status(self):
        try:
            r = requests.get(f"{self.base_url}/status", timeout=5)
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    def set_config(self, config):
        try:
            r = requests.post(f"{self.base_url}/config", json=config, timeout=5)
            return r.json()
        except Exception as e:
            return {"error": str(e)}
