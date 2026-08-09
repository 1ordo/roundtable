"""The licence the app tells people about is the licence it ships under.

This has already been wrong once. The Terms page rendered to every user of
every instance said the software was MIT while LICENSE said something else
entirely, which is both a legal problem, since a published grant of MIT
rights is hard to walk back, and the kind of inconsistency that makes a
reader distrust everything else in the repository.

Three files have to agree, and they are maintained by hand in three
different languages, so nothing but a test keeps them together.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# The one true answer. Change it here and the test tells you every other
# place that needs to change with it.
LICENCE_NAME = "GNU Affero General Public License"
SPDX = "AGPL-3.0-only"


def test_the_licence_file_is_the_agpl():
    text = (ROOT / "LICENSE").read_text()
    assert LICENCE_NAME.upper() in text.upper()
    # Section 13 is the whole reason for choosing this licence over the GPL:
    # it is what covers software offered to people over a network.
    assert "Remote Network Interaction" in text


def test_the_terms_page_names_the_same_licence():
    page = (ROOT / "web/src/pages/Legal.tsx").read_text()
    assert LICENCE_NAME in page, "the Terms page must name the licence the repo ships"
    assert "MIT licence" not in page, "this was wrong once and shipped to every instance"


def test_the_readme_names_the_same_licence():
    readme = (ROOT / "README.md").read_text()
    assert "AGPL" in readme or LICENCE_NAME in readme


@pytest.mark.parametrize(
    "manifest",
    ["api/pyproject.toml", "web/package.json", "extension/package.json"],
)
def test_every_manifest_declares_the_licence(manifest):
    """Corporate open-source review, SPDX scanners and dependency audits read
    the manifest rather than the LICENSE file, and treat a missing field more
    harshly than a restrictive but declared one."""
    text = (ROOT / manifest).read_text()
    assert SPDX in text, f"{manifest} does not declare {SPDX}"


def test_the_name_is_reserved_separately_from_the_code():
    """The AGPL says nothing about names, so if the trademark file goes the
    protection the author actually cares about goes with it."""
    assert (ROOT / "TRADEMARK.md").exists()
    assert (ROOT / "NOTICE").exists()
