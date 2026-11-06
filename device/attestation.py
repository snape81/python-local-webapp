from dataclasses import asdict, dataclass, field
from ipaddress import ip_address
import logging
import shlex
import time
from typing import Callable

import paramiko
from scp import SCPClient, SCPException

from device import settings


logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


@dataclass
class Report:
    operation: str
    ip: str
    status: str = "KO"
    message: str = ""
    tests: list[CheckResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def validate_ip(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Inserire un indirizzo IP valido della RTU.")
    try:
        return str(ip_address(value.strip()))
    except ValueError as exc:
        raise ValueError("Inserire un indirizzo IPv4 o IPv6 valido, non un hostname.") from exc


def run_command(client: paramiko.SSHClient, command: str) -> tuple[int, str, str]:
    _, stdout, _ = client.exec_command(command, timeout=settings.SSH_TIMEOUT)
    channel = stdout.channel
    output = bytearray()
    errors = bytearray()
    deadline = time.monotonic() + settings.COMMAND_TIMEOUT
    try:
        while True:
            # Drain both streams to avoid blocking commands with substantial stderr.
            for ready, receive, target in (
                (channel.recv_ready, channel.recv, output),
                (channel.recv_stderr_ready, channel.recv_stderr, errors),
            ):
                if ready():
                    chunk = receive(32768)
                    target.extend(chunk[:max(0, 65536 - len(target))])
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                return (
                    channel.recv_exit_status(),
                    output.decode("utf-8", errors="replace").strip(),
                    errors.decode("utf-8", errors="replace").strip(),
                )
            if time.monotonic() >= deadline:
                raise TimeoutError("Timeout del comando remoto; verificare lo stato della RTU prima di riprovare.")
            time.sleep(0.01)
    finally:
        channel.close()


class AttestationService:
    def attest(self, ip: str) -> Report:
        report = Report("attestazione", ip)
        steps = [
            "Configurazione locale", "Connessione SSH", "Versione RTU",
            "Trasferimento SCP", "Esecuzione script",
        ]
        report.tests = [CheckResult(name, "NON_ESEGUITO", "In attesa.") for name in steps]
        current = 0
        client = paramiko.SSHClient()
        try:
            username, password = settings.load_credentials()
            if not settings.EXPECTED_VERSION or not settings.VERSION_COMMAND:
                raise settings.ConfigurationError("Definire EXPECTED_VERSION e VERSION_COMMAND in device/settings.py.")
            if not settings.LOCAL_SCRIPT.is_file():
                raise settings.ConfigurationError("Script di attestazione mancante: fornire scripts/attest_rtu.sh.")
            report.tests[current] = CheckResult(steps[current], "OK", "Prerequisiti locali disponibili.")

            current = 1
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
            client.connect(
                ip, port=settings.SSH_PORT, username=username, password=password,
                timeout=settings.SSH_TIMEOUT, banner_timeout=settings.SSH_TIMEOUT,
                auth_timeout=settings.SSH_TIMEOUT, look_for_keys=False, allow_agent=False,
            )
            report.tests[current] = CheckResult(steps[current], "OK", "Connessione SSH autenticata.")

            current = 2
            code, version, _ = run_command(client, settings.VERSION_COMMAND)
            if code != 0:
                raise RuntimeError(f"Lettura versione fallita (exit code {code}).")
            if version != settings.EXPECTED_VERSION:
                raise RuntimeError(
                    f"Versione non compatibile: rilevata {version!r}, attesa {settings.EXPECTED_VERSION!r}."
                )
            report.tests[current] = CheckResult(steps[current], "OK", f"Versione compatibile: {version}.")

            current = 3
            transport = client.get_transport()
            if transport is None or not transport.is_active():
                raise RuntimeError("Connessione SSH non attiva prima del trasferimento.")
            with SCPClient(transport, socket_timeout=settings.SSH_TIMEOUT) as scp:
                scp.put(str(settings.LOCAL_SCRIPT), remote_path=settings.REMOTE_SCRIPT)
            report.tests[current] = CheckResult(steps[current], "OK", "Script trasferito sulla RTU.")

            current = 4
            code, _, _ = run_command(client, f"sh {shlex.quote(settings.REMOTE_SCRIPT)}")
            if code != 0:
                raise RuntimeError(f"Script di attestazione fallito (exit code {code}).")
            report.tests[current] = CheckResult(steps[current], "OK", "Script terminato con exit code 0.")
            report.status = "OK"
            report.message = "Procedura completata. Eseguire la verifica per confermare l'attestazione a Dante Smart HUB."
        except settings.ConfigurationError as exc:
            report.status = "NON_CONFIGURATO"
            report.message = str(exc)
            report.tests[current] = CheckResult(steps[current], "NON_CONFIGURATO", str(exc))
            logger.warning("Attestazione non configurata: %s", exc)
        except (paramiko.SSHException, SCPException, OSError, EOFError, RuntimeError) as exc:
            # Never expose authentication data or arbitrary remote output to the UI.
            if isinstance(exc, TimeoutError):
                detail = "Timeout: lo stato remoto puo' essere incerto. Verificare la RTU prima di riprovare."
            elif isinstance(exc, RuntimeError):
                detail = str(exc)
            else:
                detail = (
                    f"Operazione fallita ({type(exc).__name__}). "
                    "Controllare rete, credenziali, chiave host e log locali."
                )
            report.message = detail
            report.tests[current] = CheckResult(steps[current], "KO", detail)
            logger.warning("Attestazione fallita nello step %s (%s)", steps[current], type(exc).__name__)
        finally:
            client.close()
        return report


@dataclass(frozen=True)
class VerificationCheck:
    name: str
    run: Callable[[str], CheckResult] | None = None


class VerificationService:
    def __init__(self, checks: tuple[VerificationCheck, ...] | None = None):
        self.checks = checks if checks is not None else (
            VerificationCheck("Comunicazione REST"),
            VerificationCheck("Controllo attestazione Dante Smart HUB (da definire)"),
        )

    def verify(self, ip: str) -> Report:
        report = Report("verifica", ip)
        for check in self.checks:
            if check.run is None:
                result = CheckResult(check.name, "NON_CONFIGURATO", "Controllo non ancora implementato.")
            else:
                try:
                    result = check.run(ip)
                    if result.status not in ("OK", "KO", "NON_CONFIGURATO"):
                        raise ValueError("Stato del controllo non valido.")
                except (OSError, RuntimeError, ValueError) as exc:
                    logger.warning("Verifica fallita: %s (%s)", check.name, type(exc).__name__)
                    result = CheckResult(check.name, "KO", f"Errore del controllo ({type(exc).__name__}).")
            report.tests.append(result)
        statuses = [test.status for test in report.tests]
        if not statuses:
            report.status = "NON_CONFIGURATO"
        elif "KO" in statuses:
            report.status = "KO"
        elif all(status == "OK" for status in statuses):
            report.status = "OK"
        else:
            report.status = "NON_CONFIGURATO"
        report.message = {
            "OK": "Attestazione a Dante Smart HUB verificata.",
            "KO": "Verifica fallita: almeno un controllo ha esito KO.",
            "NON_CONFIGURATO": "Verifica incompleta: definire e implementare tutti i controlli.",
        }[report.status]
        return report
