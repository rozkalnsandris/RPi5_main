#!/usr/bin/env python3
"""Offline-only fake IO regressions for the future private TTY provisioner."""
from __future__ import annotations
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import unittest
from types import SimpleNamespace
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / "scripts/ausmalwiese_worker_settings_provisioner.py"
spec = importlib.util.spec_from_file_location("aw_provision", SOURCE)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
FAKE_ACCOUNT = "0" * 32  # synthetic, never a real account ID
FAKE_TOKEN = "synthetic-example-token-not-real-value"


def fake_stat(mode=0o600, uid=0, gid=0, links=1, size=20, ino=7, dev=8):
    kind = stat.S_IFDIR if mode == 0o700 else stat.S_IFREG
    return SimpleNamespace(st_mode=kind | mode, st_uid=uid, st_gid=gid,
                           st_nlink=links, st_size=size, st_ino=ino, st_dev=dev)


def valid_release():
    ex, san = b"offline-exe", b"offline-sanitizer"
    m = {"schema_version": 1, "repository": "rozkalnsandris/RPi5_main",
         "source_sha": mod.INSTALLED_RELEASE_SHA, "worker": mod.WORKER,
         "executor_sha256": hashlib.sha256(ex).hexdigest(),
         "sanitizer_sha256": hashlib.sha256(san).hexdigest(),
         "account_sha256": mod.ACCOUNT_SHA256}
    return {mod.EXECUTOR: ex, mod.SANITIZER: san, mod.RELEASE: json.dumps(m).encode()}, m


class ProvisionerOfflineTests(unittest.TestCase):
    def test_fixed_source_only_contract(self):
        s = SOURCE.read_text()
        self.assertIn('os.O_CREAT | os.O_EXCL', s)
        self.assertIn('os.O_NOFOLLOW', s)
        self.assertIn('os.open("/dev/tty"', s)
        self.assertIn("OWNER-AUTHORIZED-ONE-CREDENTIAL-PROVISION", s)
        self.assertIn("installed_root_entry_required", s)
        self.assertEqual(str(mod.TARGET), "/etc/rpi5-secrets/cloudflare/ausmalwiese-worker-settings-read.json")
        self.assertEqual(mod.WORKER, "coloring-pages-stats-v1")
        self.assertNotIn("subprocess", s)
        self.assertNotIn("http.client", s)
        self.assertNotIn("requests.", s)
        self.assertNotIn("os.environ", s)
        self.assertNotIn("getpass", s)

    def test_strict_release_json_rejects_duplicates_and_nonfinite(self):
        for x in (b"not json", b'{"a":1,"a":2}', b'{"a": NaN}'):
            with self.subTest(x=x):
                with self.assertRaises(mod.Stop):
                    mod.strict_json(x)

    def test_release_exact_digest_and_worker(self):
        files, base = valid_release()
        with mock.patch.object(mod, "read_root_file", side_effect=lambda path, *_: files[path]):
            mod.validated_release(mod.INSTALLED_RELEASE_SHA)
        for key, wrong in (("worker","wrong-worker"),("source_sha","f"*40),
                           ("account_sha256","0"*64),("executor_sha256","f"*64),
                           ("sanitizer_sha256","f"*64),("repository","other")):
            with self.subTest(key=key):
                changed = dict(base, **{key: wrong})
                source = dict(files, **{mod.RELEASE: json.dumps(changed).encode()})
                with mock.patch.object(mod, "read_root_file", side_effect=lambda path,*_: source[path]):
                    with self.assertRaisesRegex(mod.Stop, "release_invalid"):
                        mod.validated_release(mod.INSTALLED_RELEASE_SHA)
        with mock.patch.object(mod, "read_root_file") as reader:
            with self.assertRaisesRegex(mod.Stop, "stale_release_sha"):
                mod.validated_release("a"*40)
            reader.assert_not_called()

    def test_release_duplicate_field_and_missing_release_field_rejected(self):
        files, fields = valid_release()
        for bad in (b'{"worker":"bad","worker":"good"}',
                    json.dumps({k:v for k,v in fields.items() if k!="account_sha256"}).encode()):
            changed = {**files, mod.RELEASE: bad}
            with mock.patch.object(mod,"read_root_file",side_effect=lambda path,*_:changed[path]):
                with self.assertRaises(mod.Stop):
                    mod.validated_release(mod.INSTALLED_RELEASE_SHA)

    def test_account_binding_wrong_digest_and_bad_formats(self):
        for account in (FAKE_ACCOUNT, "G"*32, "f"*31, "A"*32, ""):
            with self.subTest(account=account):
                with self.assertRaisesRegex(mod.Stop, "account_binding_mismatch"):
                    mod.credential_bytes(account, FAKE_TOKEN)

    def test_owner_token_format_strict(self):
        with mock.patch.object(mod.hashlib, "sha256") as fake_digest:
            fake_digest.return_value.hexdigest.return_value = mod.ACCOUNT_SHA256
            payload = mod.credential_bytes(FAKE_ACCOUNT, FAKE_TOKEN)
            self.assertEqual(set(json.loads(payload)), {"worker", "account_id", "api_token"})
            self.assertLessEqual(len(payload), mod.MAX_CREDENTIAL_BYTES)
            for token in ("", "short", "a"*4097, "bad token", "abc\n" + "a"*20,
                          "ctrl\x00" + "x"*20, "\u00e9"*20):
                with self.subTest(token=repr(token)):
                    with self.assertRaisesRegex(mod.Stop, "token_format_invalid"):
                        mod.credential_bytes(FAKE_ACCOUNT, token)

    def test_trusted_entry_blocks_uninstalled_source_before_reads(self):
        with mock.patch.object(mod.os, "geteuid", return_value=0), \
             mock.patch.object(mod, "safe_parents") as parent:
            with self.assertRaisesRegex(mod.Stop,"installed_root_entry_required"):
                mod.trusted_entry()
            parent.assert_not_called()

    def test_metadata_blocks_symlink_bad_mode_owner_or_hardlink(self):
        for st in (SimpleNamespace(st_mode=stat.S_IFLNK|0o500,st_uid=0,st_gid=0,st_nlink=1),
                   fake_stat(0o400),fake_stat(0o500,uid=1000),
                   fake_stat(0o500,links=2)):
            with mock.patch("pathlib.Path.lstat", return_value=st):
                with self.assertRaisesRegex(mod.Stop, "protected_path_invalid"):
                    mod.safe_metadata(mod.ENTRY,0o500)

    def test_parent_untrusted_fails_closed(self):
        unsafe = SimpleNamespace(st_mode=stat.S_IFDIR|0o777,st_uid=0,st_gid=0)
        with mock.patch("pathlib.Path.lstat",return_value=unsafe):
            with self.assertRaisesRegex(mod.Stop,"parent_untrusted"):
                mod.safe_parents(mod.TARGET)

    def test_existing_destination_and_symlink_refused(self):
        with mock.patch.object(mod.os,"stat",return_value=fake_stat()):
            with self.assertRaisesRegex(mod.Stop,"credential_already_exists"):
                mod.absent(77)
        with mock.patch.object(mod.os,"stat",side_effect=FileNotFoundError):
            mod.absent(77)
        with mock.patch.object(mod.os,"stat",side_effect=PermissionError):
            with self.assertRaisesRegex(mod.Stop,"target_state_unknown"):
                mod.absent(77)

    def test_controlling_tty_missing_does_not_fallback_to_stdin(self):
        with mock.patch.object(mod.os,"open",side_effect=OSError), \
             mock.patch.object(mod,"read_private") as reader:
            with self.assertRaisesRegex(mod.Stop,"controlling_tty_required"):
                mod.owner_tty_values()
            reader.assert_not_called()

    def test_not_foreground_tty_refused(self):
        with mock.patch.object(mod.os,"open",return_value=51), \
             mock.patch.object(mod.os,"isatty",return_value=True), \
             mock.patch.object(mod.os,"tcgetpgrp",return_value=2), \
             mock.patch.object(mod.os,"getpgrp",return_value=3), \
             mock.patch.object(mod.os,"close") as close:
            with self.assertRaisesRegex(mod.Stop,"controlling_tty_required"):
                mod.owner_tty_values()
            close.assert_called_once_with(51)

    def test_terminal_echo_restored_on_invalid_input(self):
        original=[0,0,0,mod.termios.ECHO | mod.termios.ECHONL | mod.termios.ECHOE,0,0,[]]
        with mock.patch.object(mod.termios,"tcgetattr",return_value=original), \
             mock.patch.object(mod.termios,"tcsetattr") as setter, \
             mock.patch.object(mod.os,"write",return_value=4), \
             mock.patch.object(mod.os,"read",side_effect=[b"\xff",b"\n"]):
            with self.assertRaisesRegex(mod.Stop,"private_input_invalid"):
                mod.read_private(22,b"test",32)
            self.assertEqual(setter.call_count,2)
            self.assertEqual(setter.call_args.args[2],original)

    def test_write_once_has_exclusive_mode_and_no_retry(self):
        with mock.patch.object(mod.os,"umask",return_value=0o022), \
             mock.patch.object(mod.os,"open",return_value=83) as opener, \
             mock.patch.object(mod.os,"write",return_value=3) as writer, \
             mock.patch.object(mod.os,"close") as closer:
            with self.assertRaisesRegex(mod.Stop,"post_dispatch_unknown_state"):
                mod.exclusive_create(77,b"synthetic")
            self.assertEqual(opener.call_count,1)
            args,kwargs=opener.call_args
            self.assertEqual(args[0],mod.TARGET.name)
            self.assertTrue(args[1] & mod.os.O_EXCL)
            self.assertTrue(args[1] & mod.os.O_NOFOLLOW)
            self.assertEqual(args[2],0o600)
            self.assertEqual(kwargs["dir_fd"],77)
            self.assertEqual(writer.call_count,1)
            closer.assert_called_once_with(83)

    def test_preflight_failure_blocks_prompt_and_creation(self):
        with mock.patch.object(mod,"trusted_entry"), \
             mock.patch.object(mod,"validated_release",side_effect=mod.Stop("stale_release_sha")), \
             mock.patch.object(mod,"owner_tty_values") as tty, \
             mock.patch.object(mod,"exclusive_create") as creator:
            with self.assertRaisesRegex(mod.Stop,"stale_release_sha"):
                mod.run(mod.INSTALLED_RELEASE_SHA)
            tty.assert_not_called()
            creator.assert_not_called()

    def test_directory_drift_blocks_write(self):
        with mock.patch.object(mod,"trusted_entry"), \
             mock.patch.object(mod,"validated_release"), \
             mock.patch.object(mod,"guarded_directory",return_value=(79,(3,4))), \
             mock.patch.object(mod,"owner_tty_values",return_value=(FAKE_ACCOUNT,FAKE_TOKEN)), \
             mock.patch.object(mod,"credential_bytes",return_value=b"fake"), \
             mock.patch.object(mod,"safe_parents"), \
             mock.patch.object(mod,"safe_metadata",return_value=fake_stat(0o700,dev=3,ino=5)), \
             mock.patch.object(mod,"exclusive_create") as creator, \
             mock.patch.object(mod.os,"close"):
            with self.assertRaisesRegex(mod.Stop,"parent_drift"):
                mod.run(mod.INSTALLED_RELEASE_SHA)
            creator.assert_not_called()

    def test_unapproved_confirmation_never_calls_run(self):
        with mock.patch.object(mod,"run") as run, mock.patch("sys.stderr",new_callable=io.StringIO):
            code=mod.main(["--expected-release-main",mod.INSTALLED_RELEASE_SHA,
                           "--confirm","bad"])
            self.assertEqual(code,3)
            run.assert_not_called()

    def test_static_stop_never_emits_secret_or_exception_details(self):
        with mock.patch.object(mod,"run",side_effect=OSError("test-secret-should-not-print")), \
             mock.patch("sys.stderr",new_callable=io.StringIO) as err:
            code=mod.main(["--expected-release-main",mod.INSTALLED_RELEASE_SHA,
                           "--confirm",mod.CONFIRM])
            self.assertEqual(code,4)
            self.assertNotIn("test-secret",err.getvalue())
            self.assertIn("STOP:",err.getvalue())

if __name__=="__main__":
    unittest.main()
