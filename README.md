# deadcode-sweep

[![CI](https://github.com/slopggobblercobbler81/deadcode-sweep/actions/workflows/ci.yml/badge.svg)](https://github.com/slopggobblercobbler81/deadcode-sweep/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](pyproject.toml)

> A lightning-fast, zero-dependency static analyzer for **Python** and **JavaScript / TypeScript** codebases. Detects unused functions, unreachable code, and orphaned imports with safe auto-fixing.

---

## Features

- **Multi-Language Support**: Analyzes Python (`.py`, `.pyi`, `.pyw`) and JavaScript/TypeScript (`.js`, `.jsx`, `.mjs`, `.cjs`, `.ts`, `.tsx`).
- **AST-Powered Analysis**: True syntax-tree parsing for Python; robust structural and lexical analysis for JavaScript.
- **Orphaned Import Detection**: Pinpoints unused module and symbol imports (`import`, `from ... import`, ES6 `import`, CommonJS `require`).
- **Unreachable Code Detection**:
  - Statements following `return`, `raise`, `throw`, `break`, `continue`, `sys.exit()`.
  - Dead branches like `if False:` / `if (false)` and dead loops `while False:` / `while (false)`.
- **Unused Function Detection**:
  - Finds unreferenced private helpers (`_helper`), inner functions, and unexported declarations.
  - Multi-file project-wide symbol resolution.
  - Intelligently skips test functions (`test_*`), framework hooks, and decorator patterns (`@property`, `@pytest.fixture`, `@app.route`).
- **Safe In-Place Autofix (`--fix`)**: Automatically removes orphaned import lines and cleans up partial from-imports without breaking formatting.
- **CI/CD Ready (`--check`)**: Returns exit code `1` when issues are discovered, perfect for GitHub Actions and pre-commit hooks.
- **Flexible Reporting Formats**: Output as human-readable color text, `json`, `csv`, `summary` table, or GitHub Actions annotations (`github`).
- **Zero Third-Party Dependencies**: Runs directly on pure Python standard library.

---

## Installation

Install directly via `pip` or from source:

```bash
# Clone the repository
git clone https://github.com/slopggobblercobbler81/deadcode-sweep.git
cd deadcode-sweep

# Install locally in editable mode
pip install -e .
```

---

## Quick Start

### Basic Scan
Scan the current directory:
```bash
deadcode-sweep .
```

### Scan Specific Directories or Files
```bash
deadcode-sweep src/ lib/ app.py
```

### Auto-fix Orphaned Imports
Safely clean up unused imports in-place:
```bash
deadcode-sweep . --fix
```

### CI Mode
Fail build if dead code is detected:
```bash
deadcode-sweep src/ --check
```

### JSON or CSV Output
```bash
# JSON output to file
deadcode-sweep src/ --format json -o deadcode-report.json

# CSV output for data auditing
deadcode-sweep src/ --format csv -o audit.csv
```

### Filter by Language
```bash
# Only analyze Python files
deadcode-sweep . --lang python

# Only analyze JavaScript / TypeScript files
deadcode-sweep . --lang javascript
```

---

## What It Detects

### 1. Orphaned Imports
```python
# Python
import sys       # [WARN] Imported symbol 'sys' is never used
import os        # Kept (used below)
print(os.name)
```
```javascript
// JavaScript
import { used, unused } from './math'; // [WARN] Imported symbol 'unused' is never used
console.log(used);
```

### 2. Unreachable Code
```python
def calculate(val):
    if val > 100:
        return val * 2
        print("Done!")    # [WARN] Code after 'return' (line 3) will never execute
    return val

if False:
    execute_fallback()    # [WARN] Branch condition statically False; block never executed
```

### 3. Unused Functions
```python
def _internal_calc(a, b): # [WARN] Private function '_internal_calc' is never called within 'math_utils.py'
    return a * b

def public_api():
    return 42
```

---

## CLI Options Reference

| Flag | Argument | Description |
|------|----------|-------------|
| `paths` | `[PATH ...]` | Target files or directories to scan (default: `.`) |
| `--check` | *none* | Exit with code `1` if issues are found (ideal for CI) |
| `--fix` | *none* | Automatically remove orphaned imports in-place |
| `--lang` | `all`, `python`, `javascript` | Filter scanner language (default: `all`) |
| `--format` | `text`, `json`, `csv`, `github`, `summary` | Report format (default: `text`) |
| `--min-severity` | `info`, `warning`, `error` | Minimum issue severity level (default: `warning`) |
| `--ignore-dirs` | `DIR1,DIR2` | Additional directories to exclude |
| `--ignore-names` | `NAME1,NAME2` | Function or symbol names to exclude from checks |
| `--include-public-functions` | *none* | Check public functions in single-file scans |
| `-o`, `--output` | `FILE` | Write report to file instead of stdout |
| `--no-color` | *none* | Disable ANSI color styling in console output |
| `-v`, `--version` | *none* | Show version information |

---

## GitHub Actions CI Integration

Add `deadcode-sweep` to your workflow `.github/workflows/ci.yml`:

```yaml
name: Dead Code Check

on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install deadcode-sweep
        run: pip install git+https://github.com/slopggobblercobbler81/deadcode-sweep.git
      - name: Run dead code scan
        run: deadcode-sweep src/ --check --format github
```

When run in GitHub Actions with `--format github`, issues appear directly as inline PR annotations!

---

## Running Tests

Run the full automated test suite:

```bash
python -m unittest discover -s tests -v
```

---

## License

This project is licensed under the [MIT License](LICENSE).
