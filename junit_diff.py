"""Compare test outcomes in two JUnit XML reports."""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path


TestKey = tuple[str, str]
Report = dict[TestKey, str]
FAILING = {"failed", "error"}
SECTIONS = {
    "new_failures": "New failures",
    "recovered": "Recovered",
    "still_failing": "Still failing",
    "added": "Added",
    "removed": "Removed",
    "status_changes": "Other status changes",
}


class ReportError(ValueError):
    """The input cannot be interpreted as one test run."""


@dataclass(frozen=True)
class Change:
    classname: str
    name: str
    before: str | None
    after: str | None


@dataclass
class Comparison:
    before_count: int
    after_count: int
    unchanged: int
    groups: dict[str, list[Change]]


def read_report(path: Path) -> Report:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError, LookupError, ValueError) as exc:
        raise ReportError(f"{path}: {exc}") from exc

    if root.tag.rsplit("}", 1)[-1] not in {"testsuite", "testsuites"}:
        raise ReportError(f"{path}: expected a testsuite or testsuites root element")

    results: Report = {}
    for case in root.iterfind(".//{*}testcase"):
        name = case.get("name")
        if not name or not name.strip():
            raise ReportError(f"{path}: found a testcase without a name")
        classname = case.get("classname", "")
        key = (classname, name)
        if key in results:
            raise ReportError(
                f"{path}: duplicate testcase (classname={classname!r}, name={name!r})"
            )

        outcome = "passed"
        for tag, status in (("error", "error"), ("failure", "failed"), ("skipped", "skipped")):
            if case.find(f"{{*}}{tag}") is not None:
                outcome = status
                break
        results[key] = outcome
    return results


def classify(before: str | None, after: str | None) -> str | None:
    if after in FAILING:
        return "still_failing" if before in FAILING else "new_failures"
    if after is None:
        return "removed"
    if before is None:
        return "added"
    if before in FAILING and after == "passed":
        return "recovered"
    if before != after:
        return "status_changes"
    return None


def compare(before: Report, after: Report) -> Comparison:
    groups: dict[str, list[Change]] = {key: [] for key in SECTIONS}
    unchanged = 0
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key), after.get(key)
        category = classify(old, new)
        if category is None:
            unchanged += 1
        else:
            classname, name = key
            groups[category].append(Change(classname, name, old, new))
    return Comparison(len(before), len(after), unchanged, groups)


def render_text(result: Comparison) -> str:
    lines = [f"{result.before_count} tests before, {result.after_count} after"]
    for category, label in SECTIONS.items():
        changes = result.groups[category]
        if changes:
            lines.extend(("", f"{label} ({len(changes)})"))
            for change in changes:
                identifier = "::".join(filter(None, (change.classname, change.name)))
                transition = f"{change.before or 'absent'} -> {change.after or 'absent'}"
                lines.append(f"  {identifier}  {transition}")
    lines.extend(("", f"{result.unchanged} unchanged (passed or skipped)"))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path, help="JUnit XML from the reference run")
    parser.add_argument("after", type=Path, help="JUnit XML from the current run")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--fail-on-new", action="store_true", help="exit 1 for new failures")
    args = parser.parse_args(argv)
    try:
        result = compare(read_report(args.before), read_report(args.after))
    except ReportError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(asdict(result), indent=2))
    else:
        print(render_text(result))
    return int(args.fail_on_new and bool(result.groups["new_failures"]))


if __name__ == "__main__":
    sys.exit(main())
