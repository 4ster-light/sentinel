"""Value tests for the process user resolution and permission checks"""

import pwd
from types import SimpleNamespace

import pytest

import sentinel_core.process as process


def entry(name: str = "alice", uid: int = 1000, gid: int = 1000) -> SimpleNamespace:
	return SimpleNamespace(pw_name=name, pw_uid=uid, pw_gid=gid)


def use_groups(monkeypatch: pytest.MonkeyPatch, groups: list[int]) -> None:
	monkeypatch.setattr(process.os, "getgrouplist", lambda name, gid: list(groups))


def use_ids(monkeypatch: pytest.MonkeyPatch, uid: int, gid: int) -> None:
	monkeypatch.setattr(process.os, "geteuid", lambda: uid)
	monkeypatch.setattr(process.os, "getegid", lambda: gid)


class TestResolveProcessUser:
	def test_rejects_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(process.os, "name", "nt")

		with pytest.raises(ValueError, match="not supported on Windows"):
			process._resolve_process_user("alice")

	def test_rejects_an_empty_user(self) -> None:
		with pytest.raises(ValueError, match="Process user cannot be empty"):
			process._resolve_process_user("   ")

	def test_resolves_a_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(pwd, "getpwnam", lambda name: entry(name))
		use_groups(monkeypatch, [1000, 27])

		assert process._resolve_process_user(" alice ") == ("alice", 1000, 1000, [1000, 27])

	def test_resolves_a_numeric_uid(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(pwd, "getpwuid", lambda uid: entry("alice", uid, 1000))
		use_groups(monkeypatch, [1000])

		assert process._resolve_process_user("1000") == ("alice", 1000, 1000, [1000])

	def test_reports_an_unknown_uid(self, monkeypatch: pytest.MonkeyPatch) -> None:
		def missing(uid: int) -> SimpleNamespace:
			raise KeyError(uid)

		monkeypatch.setattr(pwd, "getpwuid", missing)

		with pytest.raises(ValueError, match="User with UID 1234 was not found"):
			process._resolve_process_user("1234")

	def test_reports_an_unknown_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
		def missing(name: str) -> SimpleNamespace:
			raise KeyError(name)

		monkeypatch.setattr(pwd, "getpwnam", missing)

		with pytest.raises(ValueError, match="User 'ghost' was not found"):
			process._resolve_process_user("ghost")


class TestValidateUserPermissions:
	def test_rejects_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(process.os, "name", "nt")

		with pytest.raises(ValueError, match="not supported on Windows"):
			process._validate_user_permissions("alice", 1000, 1000)

	def test_root_may_switch_to_any_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
		use_ids(monkeypatch, 0, 0)

		process._validate_user_permissions("alice", 2000, 2000)

	def test_rejects_another_uid(self, monkeypatch: pytest.MonkeyPatch) -> None:
		use_ids(monkeypatch, 1000, 1000)

		with pytest.raises(ValueError, match="without root privileges") as excinfo:
			process._validate_user_permissions("alice", 2000, 1000)

		assert str(excinfo.value) == (
			"Cannot run as user 'alice' (uid: 2000) without root privileges; current uid is 1000"
		)

	def test_rejects_another_gid(self, monkeypatch: pytest.MonkeyPatch) -> None:
		use_ids(monkeypatch, 1000, 1000)

		with pytest.raises(ValueError, match="without root privileges") as excinfo:
			process._validate_user_permissions("alice", 1000, 2000)

		assert str(excinfo.value) == (
			"Cannot switch to primary gid 2000 for user 'alice' without root privileges; current gid is 1000"
		)

	def test_accepts_the_current_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
		use_ids(monkeypatch, 1000, 1000)

		process._validate_user_permissions("alice", 1000, 1000)
