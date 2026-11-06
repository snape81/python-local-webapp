from pathlib import Path
import runpy
import sys


RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
CONFIG_ROOT = Path(sys.executable).parent if getattr(sys, "frozen", False) else RESOURCE_ROOT
EXPECTED_VERSION = ""
VERSION_COMMAND = ""
LOCAL_SCRIPT = RESOURCE_ROOT / "scripts" / "attest_rtu.sh"
REMOTE_SCRIPT = "/tmp/areti-attestazione.sh"
SSH_PORT = 22
SSH_TIMEOUT = 10
COMMAND_TIMEOUT = 120


class ConfigurationError(Exception):
    pass


def load_credentials() -> tuple[str, str]:
    credentials_file = CONFIG_ROOT / "local_settings.py"
    if not credentials_file.is_file():
        raise ConfigurationError(
            "Creare local_settings.py con SSH_USERNAME e SSH_PASSWORD."
        )

    settings = runpy.run_path(str(credentials_file))
    username = settings.get("SSH_USERNAME", "")
    password = settings.get("SSH_PASSWORD", "")
    if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
        raise ConfigurationError("Credenziali SSH locali mancanti o non valide.")
    return username, password
