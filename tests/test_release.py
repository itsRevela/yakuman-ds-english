import pytest

from release import ReleaseError, bump_for, next_version, roll_changelog


def test_feat_bumps_minor_and_fix_bumps_patch():
    assert bump_for(["fix: typo in the options screen"]) == "patch"
    assert bump_for(["fix: typo", "feat: translate the title"]) == "minor"


def test_non_release_commit_types_do_not_release():
    assert bump_for(["docs: readme", "chore(release): v0.1.0", "test: more", "ci: workflow"]) is None


def test_breaking_change_marker_or_footer_bumps_major():
    assert bump_for(["feat!: new text engine"]) == "major"
    assert bump_for(["fix: x\n\nBREAKING CHANGE: saves from older patches no longer load"]) == "major"


def test_next_version_from_no_tag_and_from_a_tag():
    assert next_version(None, "minor") == "0.1.0"
    assert next_version("v1.2.3", "patch") == "1.2.4"
    assert next_version("v1.2.3", "minor") == "1.3.0"
    assert next_version("v1.2.3", "major") == "2.0.0"


def test_breaking_change_before_1_0_bumps_minor():
    assert next_version("v0.4.2", "major") == "0.5.0"


def test_next_version_rejects_a_malformed_tag():
    with pytest.raises(ReleaseError):
        next_version("release-3", "patch")


CHANGELOG = """# Changelog

## [Unreleased]

### Fixed

- Something.

## [0.1.0] - 2026-01-01

### Added

- First.
"""


def test_roll_changelog_moves_unreleased_notes_under_the_version():
    text, notes = roll_changelog(CHANGELOG, "0.2.0", "2026-10-20")
    assert notes == "### Fixed\n\n- Something."
    assert "## [Unreleased]\n\n## [0.2.0] - 2026-10-20\n\n### Fixed\n\n- Something.\n\n## [0.1.0]" in text


def test_roll_changelog_refuses_an_empty_unreleased_section():
    empty = CHANGELOG.replace("### Fixed\n\n- Something.\n\n", "")
    with pytest.raises(ReleaseError):
        roll_changelog(empty, "0.2.0", "2026-10-20")
