import webview
from device.attestation import AttestationService, Report, VerificationService, validate_ip
from device.settings import RESOURCE_ROOT
import logging
import platform
from threading import Lock


class Api:
    def __init__(self):
        self.attestation = AttestationService()
        self.verification = VerificationService()
        self.operation_lock = Lock()

    def attest_rtu(self, ip):
        return self._execute("attestazione", ip, self.attestation.attest)

    def verify_attestation(self, ip):
        return self._execute("verifica", ip, self.verification.verify)

    def _execute(self, operation, ip, service):
        try:
            ip = validate_ip(ip)
        except ValueError as exc:
            logging.getLogger(__name__).warning("Richiesta con IP non valido.")
            return Report(operation, "", message=str(exc)).to_dict()
        if not self.operation_lock.acquire(blocking=False):
            return Report(operation, ip, message="Un'altra operazione e' in corso. Attendere.").to_dict()
        try:
            return service(ip).to_dict()
        finally:
            self.operation_lock.release()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    webview.create_window(
        "Areti RTU - Dante Smart HUB",
        str(RESOURCE_ROOT / "ui" / "index.html"),
        js_api=Api(),
        width=1000,
        height=800
    )

    if platform.system() == "Linux":
        webview.start(gui='qt')
    else:
        webview.start()
