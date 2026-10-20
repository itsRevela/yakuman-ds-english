import subprocess
import zlib

import pytest

from make_patch import encode_bps
from patch_manifest import ManifestError, check, inputs_digest, publish

SOURCE = bytes(range(256)) * 4
TARGET = SOURCE[:500] + b"English" + SOURCE[507:]
SOURCE_CRC = zlib.crc32(SOURCE)


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "core.autocrlf", "false")
    (tmp_path / "text").mkdir()
    (tmp_path / "text" / "menus.json").write_text('{"en": "Rules"}\n', encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.md").write_text("notes\n", encoding="utf-8")
    (tmp_path / "tools" / "emu").mkdir(parents=True)
    (tmp_path / "tools" / "emu" / "harness.py").write_text("x = 1\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    return tmp_path


def test_digest_changes_when_a_build_input_changes(repo):
    before = inputs_digest(repo)
    (repo / "text" / "menus.json").write_text('{"en": "Rule List"}\n', encoding="utf-8")
    assert inputs_digest(repo) != before


def test_digest_ignores_docs_and_test_harness(repo):
    before = inputs_digest(repo)
    (repo / "docs" / "notes.md").write_text("changed\n", encoding="utf-8")
    (repo / "tools" / "emu" / "harness.py").write_text("x = 2\n", encoding="utf-8")
    assert inputs_digest(repo) == before


def test_digest_is_the_same_for_crlf_and_lf_checkouts(repo):
    git(repo, "config", "core.autocrlf", "true")
    lf = inputs_digest(repo)
    (repo / "text" / "menus.json").write_bytes(b'{"en": "Rules"}\r\n')
    assert inputs_digest(repo) == lf


def test_published_patch_passes_the_check(repo):
    publish(repo, encode_bps(SOURCE, TARGET), expected_source_crc=SOURCE_CRC)
    check(repo, expected_source_crc=SOURCE_CRC)


def test_check_fails_when_sources_change_after_publishing(repo):
    publish(repo, encode_bps(SOURCE, TARGET), expected_source_crc=SOURCE_CRC)
    (repo / "text" / "menus.json").write_text('{"en": "Rule List"}\n', encoding="utf-8")
    with pytest.raises(ManifestError, match="stale"):
        check(repo, expected_source_crc=SOURCE_CRC)


def test_publish_rejects_a_patch_for_another_rom(repo):
    with pytest.raises(ManifestError, match="source"):
        publish(repo, encode_bps(SOURCE, TARGET), expected_source_crc=SOURCE_CRC ^ 1)
