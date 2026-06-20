from dataclasses import dataclass
from typing import Optional

from junitparser import JUnitXml, TestCase, Error, Failure


@dataclass
class ParsedTestResult:
    name: str
    classname: str
    feature_area: str
    suite_name: str
    status: str            # passed | failed | error | skipped
    duration_seconds: float
    error_message: Optional[str]
    error_type: Optional[str]
    stack_trace: Optional[str]


def _derive_feature_area(classname: str) -> str:
    """
    Derive feature area from classname.
    e.g. 'com.example.auth.LoginTest' -> 'auth'
         'tests.payment.checkout_test' -> 'payment'
    """
    if not classname:
        return "unknown"
    parts = classname.split(".")
    # Skip common prefixes like 'com', 'org', 'tests', 'test'
    skip = {"com", "org", "net", "io", "tests", "test", "src"}
    meaningful = [p for p in parts if p.lower() not in skip]
    if len(meaningful) >= 2:
        return meaningful[-2]   # second-to-last segment is usually the module
    if meaningful:
        return meaningful[0]
    return parts[0] if parts else "unknown"


def parse_junit_xml(xml_content: str, suite_name: str = "") -> list[ParsedTestResult]:
    results: list[ParsedTestResult] = []

    try:
        xml = JUnitXml.fromstring(xml_content.encode())
    except Exception:
        return results

    # JUnitXml can be a single TestSuite or a collection
    suites = list(xml) if hasattr(xml, "__iter__") else [xml]

    for suite in suites:
        s_name = getattr(suite, "name", None) or suite_name or "default"
        for case in suite:
            if not isinstance(case, TestCase):
                continue

            classname = getattr(case, "classname", "") or ""
            name = getattr(case, "name", "") or ""
            duration = float(getattr(case, "time", 0) or 0)
            feature_area = _derive_feature_area(classname)

            # Determine status
            result_elements = list(case.iterchildren())
            error_message = None
            error_type = None
            stack_trace = None
            status = "passed"

            for elem in result_elements:
                if isinstance(elem, Failure):
                    status = "failed"
                    error_message = getattr(elem, "message", "") or ""
                    error_type = getattr(elem, "type", "") or "AssertionError"
                    stack_trace = elem.text or ""
                    break
                elif isinstance(elem, Error):
                    status = "error"
                    error_message = getattr(elem, "message", "") or ""
                    error_type = getattr(elem, "type", "") or "Exception"
                    stack_trace = elem.text or ""
                    break

            if case.is_skipped:
                status = "skipped"

            results.append(
                ParsedTestResult(
                    name=name,
                    classname=classname,
                    feature_area=feature_area,
                    suite_name=s_name,
                    status=status,
                    duration_seconds=duration,
                    error_message=error_message,
                    error_type=error_type,
                    stack_trace=stack_trace,
                )
            )

    return results
