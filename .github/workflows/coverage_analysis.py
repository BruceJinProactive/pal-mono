import sys


def parse_pytest_cov(coverage_data: str) -> dict[str, int]:
    """Parse coverage data and return a dictionary of file coverage percentages."""
    coverage = {}
    for line in coverage_data.split("\\n"):
        if line.endswith("%"):
            row = line.split()
            file = row[0]
            coverage_pct = int(row[3].strip("%"))
            coverage[file] = coverage_pct
    return coverage


def main():
    THRESHOLD = 30

    if len(sys.argv) < 4:
        sys.exit(
            "Usage: python coverage-analysis.py <main_coverage> <new_coverage> <target-filepaths>"
        )

    main_coverage = parse_pytest_cov(sys.argv[1])
    new_coverage = parse_pytest_cov(sys.argv[2])

    # coverage scanning
    below_main = []  # lower coverage than main
    below_threshold = []  # lower coverage than threshold
    for file in sys.argv[3:]:
        if file not in new_coverage:
            # deleted file
            continue
        if new_coverage[file] < THRESHOLD:
            below_threshold.append(file)
        if file in main_coverage and new_coverage[file] < main_coverage[file]:
            below_main.append(file)

    # Build output
    newline = "\n"
    if below_main:
        below_main_output = f"<details><summary>:o: These files have lower coverage than main</summary>\n\n```\n{newline.join(below_main)}\n```\n</details>\n"
    else:
        below_main_output = (
            ":white_check_mark: All files have at least the coverage in main\n"
        )
    if below_threshold:
        below_threshold_output = f"<details><summary>:o: These files have lower coverage than the threshold</summary>\n\n```\n{newline.join(below_threshold)}\n```\n</details>\n"
    else:
        below_threshold_output = (
            ":white_check_mark: All files have coverage above the threshold\n"
        )
    full_output = below_main_output + below_threshold_output
    if (
        "TOTAL" in main_coverage
        and "TOTAL" in new_coverage
        and new_coverage["TOTAL"] < main_coverage["TOTAL"]
    ):
        full_output += ":o: Total coverage has dropped\n"
    print(full_output)


if __name__ == "__main__":
    main()
