"""
preflight.py
WHO DAK Intelligence Platform — retrieval/preflight.py
Environment check before any retrieval. Stop and report on failure.
Never installs packages silently.
"""
from __future__ import annotations
import argparse, importlib.util, socket, sys, tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.request import Request, urlopen

SKILL_DIR = Path(__file__).resolve().parent.parent
MIN_PYTHON = (3, 10)
NETWORK_PROBES = [
    ("WHO GHO API",    "https://ghoapi.azureedge.net/api/WHS4_100?$top=1"),
    ("World Bank API", "https://api.worldbank.org/v2/country/ZMB/indicator/SP.POP.TOTL?format=json&per_page=1"),
]
DEFAULT_OUTPUT = SKILL_DIR / "run_output"


@dataclass
class Check:
    name: str; ok: bool; level: str; message: str   # level: ok|warn|error

@dataclass
class PreflightResult:
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self): return all(c.ok for c in self.checks)

    @property
    def errors(self): return [c for c in self.checks if c.level == "error"]

    def print(self):
        for c in self.checks:
            icon = "✓" if c.ok else ("⚠" if c.level == "warn" else "✗")
            print(f"  {icon} [{c.level.upper():<5}] {c.name}: {c.message}")
        print()
        print("  Preflight passed." if self.passed
              else "  Preflight FAILED — resolve errors before retrieval.")


def _check_python() -> Check:
    v = sys.version_info[:2]
    ok = v >= MIN_PYTHON
    return Check("Python version", ok, "ok" if ok else "error",
        f"{v[0]}.{v[1]}" + ("" if ok else f" < {MIN_PYTHON[0]}.{MIN_PYTHON[1]} required"))

def _check_yaml() -> Check:
    ok = importlib.util.find_spec("yaml") is not None
    return Check("PyYAML", ok, "ok" if ok else "error",
        "available" if ok else "not installed — run: pip install pyyaml")

def _check_pypdf(require: bool) -> Check:
    ok = importlib.util.find_spec("pypdf") is not None
    level = "ok" if ok else ("error" if require else "warn")
    msg = "available" if ok else "not installed — PDFs won't be parsed (pip install pypdf>=6.0)"
    return Check("pypdf", ok or not require, level, msg)

def _check_config() -> Check:
    required = ["country_taxonomy.yml","source_hierarchy.yml","domain_indicators.yml",
                "donor_signals.yml","risk_definitions.yml","evidence_rules.yml"]
    missing = [f for f in required if not (SKILL_DIR/"config"/f).exists()]
    ok = not missing
    return Check("Config files", ok, "ok" if ok else "error",
        "6/6 present" if ok else f"missing: {missing}")

def _check_intelligence() -> Check:
    modules = ["classifier","domain_router","evidence_classifier","priming_engine","risk_assessor"]
    missing = [m for m in modules if not (SKILL_DIR/"intelligence"/f"{m}.py").exists()]
    ok = not missing
    return Check("Intelligence modules", ok, "ok" if ok else "error",
        "5/5 present" if ok else f"missing: {missing}")

def _check_output(path: Path) -> Check:
    probe = next((p for p in [path]+list(path.parents) if p.exists()), Path.cwd())
    try:
        with tempfile.NamedTemporaryFile(dir=probe, prefix=".dak_probe_", delete=True):
            pass
        return Check("Output directory", True, "ok", f"writable ({probe})")
    except OSError as e:
        return Check("Output directory", False, "error", f"not writable: {e}")

def _check_network(require: bool, timeout: int) -> list[Check]:
    results = []
    for name, url in NETWORK_PROBES:
        try:
            req = Request(url, headers={"User-Agent":"who-dak-intelligence/1.0"})
            with urlopen(req, timeout=timeout) as r:
                results.append(Check(f"Network: {name}", True, "ok", f"HTTP {r.status}"))
        except socket.timeout:
            lvl = "error" if require else "warn"
            results.append(Check(f"Network: {name}", not require, lvl, f"timeout ({timeout}s)"))
        except socket.gaierror as e:
            lvl = "error" if require else "warn"
            results.append(Check(f"Network: {name}", not require, lvl, f"DNS error: {e}"))
        except Exception as e:
            lvl = "error" if require else "warn"
            results.append(Check(f"Network: {name}", not require, lvl, str(e)[:80]))
    return results


def run(output_dir=DEFAULT_OUTPUT, require_network=False,
        require_pdf=False, skip_network=False, timeout=8) -> PreflightResult:
    r = PreflightResult()
    r.checks += [_check_python(), _check_yaml(), _check_config(),
                 _check_intelligence(), _check_output(output_dir), _check_pypdf(require_pdf)]
    if skip_network:
        r.checks.append(Check("Network", True, "warn", "skipped"))
    else:
        r.checks += _check_network(require_network, timeout)
    return r


def main(argv):
    p = argparse.ArgumentParser(description="WHO DAK Intelligence — preflight check")
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    p.add_argument("--require-network", action="store_true")
    p.add_argument("--require-pdf",     action="store_true")
    p.add_argument("--skip-network",    action="store_true")
    p.add_argument("--timeout", type=int, default=8)
    args = p.parse_args(argv[1:])
    print("\n=== WHO DAK INTELLIGENCE — PREFLIGHT ===\n")
    result = run(Path(args.output_dir), args.require_network,
                 args.require_pdf, args.skip_network, args.timeout)
    result.print()
    return 0 if result.passed else 1

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
