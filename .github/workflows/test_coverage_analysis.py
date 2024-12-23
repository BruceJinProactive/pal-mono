import sys
from unittest.mock import patch

import coverage_analysis
import pytest


def test_coverage_usage(capsys):
    test_args = ["coverage_analysis.py"]
    with patch.object(sys, "argv", test_args):
        with pytest.raises(SystemExit):
            coverage_analysis.main()
            captured = capsys.readouterr()
            assert (
                "Usage: python coverage_analysis.py <main_coverage> <new_coverage> <target-filepaths>"
                in captured.err
            )


def test_coverage_below_both(capsys):
    test_args = [
        "coverage_analysis.py",
        "file1.py 100 100 1%",
        "file1.py 100 100 0%",
        "file1.py",
    ]
    with patch.object(sys, "argv", test_args):
        coverage_analysis.main()
        captured = capsys.readouterr()
        assert ":o: These files have lower coverage than the threshold" in captured.out
        assert ":o: These files have lower coverage than main" in captured.out
        assert "file1.py" in captured.out


def test_coverage_below_main(capsys):
    test_args = [
        "coverage_analysis.py",
        "file1.py 100 100 100%",
        "file1.py 100 100 99%",
        "file1.py",
    ]
    with patch.object(sys, "argv", test_args):
        coverage_analysis.main()
        captured = capsys.readouterr()
        assert ":o: These files have lower coverage than main" in captured.out
        assert (
            ":o: These files have lower coverage than the threshold" not in captured.out
        )
        assert "file1.py" in captured.out


def test_coverage_below_threshold(capsys):
    test_args = [
        "coverage_analysis.py",
        "file1.py 100 100 1%",
        "file1.py 100 100 2%",
        "file1.py",
    ]
    with patch.object(sys, "argv", test_args):
        coverage_analysis.main()
        captured = capsys.readouterr()
        assert ":o: These files have lower coverage than the threshold" in captured.out
        assert ":o: These files have lower coverage than main" not in captured.out
        assert "file1.py" in captured.out


def test_coverage_above_both(capsys):
    test_args = [
        "coverage_analysis.py",
        "file1.py 100 100 99%",
        "file1.py 100 100 100%",
        "file1.py",
    ]
    with patch.object(sys, "argv", test_args):
        coverage_analysis.main()
        captured = capsys.readouterr()
        assert (
            ":white_check_mark: All files have at least the coverage in main"
            in captured.out
        )
        assert (
            ":white_check_mark: All files have coverage above the threshold"
            in captured.out
        )


def test_no_new_coverage(capsys):
    test_args = [
        "coverage_analysis.py",
        "file1.py 100 100 99%",
        "",
        "file1.py",
    ]
    with patch.object(sys, "argv", test_args):
        coverage_analysis.main()
        captured = capsys.readouterr()
        assert (
            ":white_check_mark: All files have at least the coverage in main"
            in captured.out
        )
        assert (
            ":white_check_mark: All files have coverage above the threshold"
            in captured.out
        )
        assert "file1.py" not in captured.out


def test_dropped_total(capsys):
    test_args = [
        "coverage_analysis.py",
        "file1.py 100 100 100%\\nTOTAL 100 100 100%",
        "file1.py 100 100 100%\\nTOTAL 100 100 99%",
        "file1.py",
    ]
    with patch.object(sys, "argv", test_args):
        coverage_analysis.main()
        captured = capsys.readouterr()
        print(captured.out)
        assert ":o: Total coverage has dropped" in captured.out
