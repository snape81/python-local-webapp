from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import paramiko
from scp import SCPException

from app import Api
from device import settings
from device.attestation import (
    AttestationService, CheckResult, VerificationCheck, VerificationService,
    run_command, validate_ip,
)


class AttestationTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch("device.attestation.settings.load_credentials", return_value=("test-user", "test-only")),
            patch("device.attestation.settings.EXPECTED_VERSION", "1.0"),
            patch("device.attestation.settings.VERSION_COMMAND", "read-version"),
            patch("device.attestation.settings.LOCAL_SCRIPT", Path(__file__)),
            patch("device.attestation.paramiko.SSHClient"),
            patch("device.attestation.SCPClient"),
            patch("device.attestation.run_command", side_effect=[(0, "1.0", ""), (0, "", "")]),
        ]
        mocks = []
        for patcher in self.patches:
            mocks.append(patcher.start())
            self.addCleanup(patcher.stop)
        self.credentials, _, _, _, self.ssh, self.scp, self.command = mocks
        self.client = self.ssh.return_value

    def test_success(self):
        report = AttestationService().attest("192.0.2.1")
        self.assertEqual(report.status, "OK")
        self.assertTrue(all(test.status == "OK" for test in report.tests))
        self.client.load_system_host_keys.assert_called_once()
        self.assertIsInstance(self.client.set_missing_host_key_policy.call_args.args[0], paramiko.RejectPolicy)
        self.scp.return_value.__enter__.return_value.put.assert_called_once()
        self.assertEqual(self.command.call_args.args[1], "sh /tmp/areti-attestazione.sh")
        self.client.close.assert_called_once()
        self.assertEqual(report.to_dict()["tests"][2]["status"], "OK")

    def test_missing_credentials_prevents_connection(self):
        self.credentials.side_effect = settings.ConfigurationError("Credenziali mancanti.")
        report = AttestationService().attest("192.0.2.1")
        self.assertEqual(report.status, "NON_CONFIGURATO")
        self.client.connect.assert_not_called()
        self.assertEqual(report.tests[1].status, "NON_ESEGUITO")

    def test_missing_version_configuration_prevents_connection(self):
        with patch("device.attestation.settings.EXPECTED_VERSION", ""):
            report = AttestationService().attest("192.0.2.1")
        self.assertEqual(report.status, "NON_CONFIGURATO")
        self.client.connect.assert_not_called()

    def test_missing_script_prevents_connection(self):
        with patch.object(Path, "is_file", return_value=False):
            report = AttestationService().attest("192.0.2.1")
        self.assertEqual(report.status, "NON_CONFIGURATO")
        self.client.connect.assert_not_called()

    def test_authentication_failure(self):
        self.client.connect.side_effect = paramiko.AuthenticationException("test-only")
        report = AttestationService().attest("192.0.2.1")
        self.assertEqual(report.tests[1].status, "KO")
        self.command.assert_not_called()
        self.client.close.assert_called_once()
        self.assertNotIn("test-only", report.message)

    def test_version_mismatch_stops_before_scp(self):
        self.command.side_effect = [(0, "2.0", "")]
        report = AttestationService().attest("192.0.2.1")
        self.assertEqual(report.tests[2].status, "KO")
        self.assertEqual(report.tests[3].status, "NON_ESEGUITO")
        self.scp.assert_not_called()

    def test_version_command_failure(self):
        self.command.side_effect = [(1, "1.0", "")]
        report = AttestationService().attest("192.0.2.1")
        self.assertEqual(report.tests[2].status, "KO")
        self.scp.assert_not_called()

    def test_transfer_failure_stops_execution(self):
        self.scp.return_value.__enter__.return_value.put.side_effect = SCPException("transfer error")
        report = AttestationService().attest("192.0.2.1")
        self.assertEqual(report.tests[3].status, "KO")
        self.assertEqual(report.tests[4].status, "NON_ESEGUITO")
        self.assertEqual(self.command.call_count, 1)

    def test_script_failure(self):
        self.command.side_effect = [(0, "1.0", ""), (78, "", "remote sensitive output")]
        report = AttestationService().attest("192.0.2.1")
        self.assertEqual(report.status, "KO")
        self.assertEqual(report.tests[4].status, "KO")
        self.assertNotIn("remote sensitive output", report.message)

    def test_script_timeout(self):
        self.command.side_effect = [(0, "1.0", ""), TimeoutError("timeout")]
        report = AttestationService().attest("192.0.2.1")
        self.assertEqual(report.tests[4].status, "KO")
        self.client.close.assert_called_once()


class VerificationTests(unittest.TestCase):
    def test_defaults_do_not_fake_success(self):
        report = VerificationService().verify("192.0.2.1")
        self.assertEqual(report.status, "NON_CONFIGURATO")
        self.assertEqual(len(report.tests), 2)
        self.assertTrue(all(test.status == "NON_CONFIGURATO" for test in report.tests))

    def test_all_ok(self):
        check = VerificationCheck("REST", lambda ip: CheckResult("REST", "OK", ip))
        self.assertEqual(VerificationService((check,)).verify("192.0.2.1").status, "OK")

    def test_failure_does_not_stop_remaining_checks(self):
        later = MagicMock(return_value=CheckResult("Secondo", "OK", "Disponibile."))
        report = VerificationService((
            VerificationCheck("Primo", MagicMock(side_effect=TimeoutError())),
            VerificationCheck("Secondo", later),
            VerificationCheck("Terzo"),
        )).verify("192.0.2.1")
        self.assertEqual(report.status, "KO")
        later.assert_called_once_with("192.0.2.1")
        self.assertEqual([test.status for test in report.tests], ["KO", "OK", "NON_CONFIGURATO"])

    def test_invalid_status_becomes_ko(self):
        check = VerificationCheck("REST", lambda ip: CheckResult("REST", "IGNOTO", ""))
        self.assertEqual(VerificationService((check,)).verify("192.0.2.1").status, "KO")

    def test_no_checks_is_not_success(self):
        self.assertEqual(VerificationService(()).verify("192.0.2.1").status, "NON_CONFIGURATO")

    def test_partial_configuration_is_not_success(self):
        checks = (
            VerificationCheck("REST", lambda ip: CheckResult("REST", "OK", "")),
            VerificationCheck("Altro"),
        )
        self.assertEqual(VerificationService(checks).verify("192.0.2.1").status, "NON_CONFIGURATO")


class BridgeTests(unittest.TestCase):
    def test_ip_validation(self):
        self.assertEqual(validate_ip(" 192.0.2.1 "), "192.0.2.1")
        self.assertEqual(validate_ip("2001:db8::1"), "2001:db8::1")
        for value in ("", "rtu.example", "127.0.0.1; reboot", "999.1.1.1", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_ip(value)

    def test_invalid_ip_never_reaches_services(self):
        api = Api()
        api.attestation = MagicMock()
        api.verification = MagicMock()
        self.assertEqual(api.attest_rtu("invalid")["status"], "KO")
        self.assertEqual(api.verify_attestation(None)["status"], "KO")
        api.attestation.attest.assert_not_called()
        api.verification.verify.assert_not_called()

    def test_valid_verification_bridge(self):
        self.assertEqual(Api().verify_attestation(" 192.0.2.1 ")["ip"], "192.0.2.1")

    def test_busy_backend_refuses_operation(self):
        api = Api()
        api.operation_lock.acquire()
        try:
            self.assertEqual(api.verify_attestation("192.0.2.1")["status"], "KO")
        finally:
            api.operation_lock.release()


class CommandTests(unittest.TestCase):
    def test_drains_both_streams_and_closes_channel(self):
        client = MagicMock()
        stdout = MagicMock()
        client.exec_command.return_value = (MagicMock(), stdout, MagicMock())
        channel = stdout.channel
        channel.recv_ready.side_effect = [True, False]
        channel.recv_stderr_ready.side_effect = [True, False]
        channel.recv.return_value = b"1.0\n"
        channel.recv_stderr.return_value = b"warning\n"
        channel.recv_exit_status.return_value = 0
        self.assertEqual(run_command(client, "version"), (0, "1.0", "warning"))
        channel.close.assert_called_once()

    def test_deadline_closes_channel(self):
        client = MagicMock()
        stdout = MagicMock()
        client.exec_command.return_value = (MagicMock(), stdout, MagicMock())
        channel = stdout.channel
        channel.recv_ready.return_value = False
        channel.recv_stderr_ready.return_value = False
        channel.exit_status_ready.return_value = False
        with patch("device.attestation.time.monotonic", side_effect=[0, 121]):
            with self.assertRaises(TimeoutError):
                run_command(client, "script")
        channel.close.assert_called_once()


class CredentialTests(unittest.TestCase):
    def test_absent_local_file(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("device.settings.CONFIG_ROOT", Path(folder)):
                with self.assertRaises(settings.ConfigurationError):
                    settings.load_credentials()

    def test_local_credentials_and_missing_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "local_settings.py"
            with patch("device.settings.CONFIG_ROOT", Path(folder)):
                file.write_text("SSH_USERNAME = 'test-user'\nSSH_PASSWORD = 'test-only'\n")
                self.assertEqual(settings.load_credentials(), ("test-user", "test-only"))
                file.write_text("SSH_USERNAME = 'test-user'\n")
                with self.assertRaises(settings.ConfigurationError):
                    settings.load_credentials()


if __name__ == "__main__":
    unittest.main()
