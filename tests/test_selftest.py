"""The packaged-build self-test passes from source, so a failure means a broken bundle."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from duddysheet.selftest import CHECKS, run_self_test


def test_self_test_covers_the_analysis_and_excel_features() -> None:
    labels = {label for label, _check in CHECKS}
    assert {"Excel parity", "Excel charts and sparklines", "Tables, PivotTables, data tables"} <= labels


def test_self_test_passes(capsys) -> None:
    assert run_self_test(verbose=False) == 0
    assert "checks passed" in capsys.readouterr().out
