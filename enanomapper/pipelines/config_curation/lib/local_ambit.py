"""Pre-flight-check a local AMBIT instance, then drive the Maven import test
for one project.

AMBIT's process lifecycle stays manual (Eclipse or a manual Tomcat run, per
nanodata/guide/README.md) -- this module never starts or stops it, only
checks reachability and shells out to Maven against whatever is already
running.

Each project's import is a JUnit test class `Import_<PREFIX>_test` extending
`net.idea.nanodata.NanodataImportTest`, living at
`projectdata-<project>/src/test/java/.../Import_<PREFIX>_test.java`
(confirmed real example: projectdata-gracious's Import_GRACIOUS_test.java).
Most classes have a `test_all` method that imports everything for that
project (confirmed in 9 of the projectdata-* modules, e.g.
Import_HARMLESS_test.test_all); a few (e.g. Import_GRACIOUS_test) don't and
instead split the import across several narrower `@Test` methods. The
default here is: use `test_all` if the class defines it, else run the whole
class (every `@Test` in it). An explicit `test_method` overrides both
(`ClassName#methodName`, standard Maven surefire syntax) for targeting one
method while iterating on a fix.
"""

from __future__ import annotations

import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_TEST_CLASS_RE = re.compile(r"public class (Import_\w+_test)\b")
_TEST_ALL_RE = re.compile(r"\bpublic void test_all\s*\(")


@dataclass
class ReachabilityResult:
    reachable: bool
    detail: str


def check_ambit_reachable(
    base_url: str, timeout: float = 5.0
) -> ReachabilityResult:
    """Probe the local AMBIT base URL.

    A bare GET against `<base_url>` (e.g. http://localhost:9090/ambit2)
    returning HTTP 405 is the confirmed-correct signal that AMBIT is up --
    that path doesn't accept GET, but a 405 only comes from a live servlet
    container, not a dead port. Any other 4xx/2xx/3xx also counts as
    reachable; connection errors/timeouts do not.
    """
    try:
        urllib.request.urlopen(base_url, timeout=timeout)
        return ReachabilityResult(True, "AMBIT responded")
    except urllib.error.HTTPError as e:
        return ReachabilityResult(True, f"AMBIT responded with HTTP {e.code}")
    except (urllib.error.URLError, OSError) as e:
        return ReachabilityResult(
            False,
            f"AMBIT not reachable at {base_url}: {e}. Start it manually "
            "(Eclipse or Tomcat, see nanodata/guide/README.md) before "
            "running an import.",
        )


def find_test_class(nanodata_root: Path, project: str) -> Path | None:
    """Locate `Import_<PREFIX>_test.java` under `projectdata-<project>/`.

    `project` is the module suffix as used in the folder name (e.g.
    "gracious" for projectdata-gracious), not the PREFIX (e.g. "GRCS")
    used inside the file.
    """
    module_dir = nanodata_root / f"projectdata-{project}"
    if not module_dir.exists():
        return None
    candidates = sorted(
        module_dir.glob("src/test/java/**/Import_*_test.java")
    )
    return candidates[0] if candidates else None


def _extract_class_name(java_file: Path) -> str | None:
    m = _TEST_CLASS_RE.search(java_file.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def _has_test_all(java_file: Path) -> bool:
    """Whether the class defines `test_all` (confirmed present in 9 of the
    projectdata-* modules, e.g. Import_HARMLESS_test; absent in others,
    e.g. Import_GRACIOUS_test, which splits the import across several
    narrower @Test methods instead).
    """
    text = java_file.read_text(encoding="utf-8")
    return _TEST_ALL_RE.search(text) is not None


@dataclass
class ImportRunResult:
    ran: bool
    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    detail: str


def run_local_import(
    nanodata_root: Path,
    project: str,
    *,
    ambit_base_url: str = "http://localhost:9090/ambit2",
    test_method: str | None = None,
    timeout: float = 1800.0,
) -> ImportRunResult:
    """Pre-flight-check AMBIT, then `mvn -pl projectdata-<project> test
    -Dtest=Import_<PREFIX>_test[#method]` from `nanodata_root`.

    Does not parse or diff the resulting `<PREFIX>-undefined_*.properties`
    reports itself -- call undefined_reports's load_backlog() /
    rank_backlog_current() again after this returns to see the effect
    (before/after is the caller's job, since "before" has to be captured
    prior to calling this).
    """
    reach = check_ambit_reachable(ambit_base_url)
    if not reach.reachable:
        return ImportRunResult(
            ran=False, command=[], returncode=None, stdout="", stderr="",
            detail=reach.detail,
        )

    java_file = find_test_class(nanodata_root, project)
    if java_file is None:
        return ImportRunResult(
            ran=False, command=[], returncode=None, stdout="", stderr="",
            detail=f"No Import_*_test.java found under "
                   f"{nanodata_root / f'projectdata-{project}'}"
                   f"/src/test/java/",
        )
    class_name = _extract_class_name(java_file)
    if class_name is None:
        return ImportRunResult(
            ran=False, command=[], returncode=None, stdout="", stderr="",
            detail="Could not find a 'public class Import_*_test' "
                   f"declaration in {java_file}",
        )

    if test_method is not None:
        effective_method = test_method
    elif _has_test_all(java_file):
        effective_method = "test_all"
    else:
        effective_method = None
    test_selector = (
        class_name
        if effective_method is None
        else f"{class_name}#{effective_method}"
    )
    command = [
        "mvn", "-pl", f"projectdata-{project}", "test",
        f"-Dtest={test_selector}",
    ]
    try:
        proc = subprocess.run(
            command,
            cwd=nanodata_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return ImportRunResult(
            ran=False, command=command, returncode=None,
            stdout=e.stdout or "", stderr=e.stderr or "",
            detail=f"mvn timed out after {timeout}s",
        )
    except FileNotFoundError:
        return ImportRunResult(
            ran=False, command=command, returncode=None, stdout="", stderr="",
            detail="mvn not found on PATH",
        )

    detail = (
        "BUILD SUCCESS"
        if proc.returncode == 0
        else f"mvn exited {proc.returncode}"
    )
    return ImportRunResult(
        ran=True, command=command, returncode=proc.returncode,
        stdout=proc.stdout, stderr=proc.stderr, detail=detail,
    )
