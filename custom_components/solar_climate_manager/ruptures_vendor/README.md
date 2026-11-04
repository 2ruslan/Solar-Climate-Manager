# ruptures 1.1.9 — Python subset

Upstream: https://github.com/deepcharles/ruptures (BSD-2-Clause; see LICENSE).
Source: https://files.pythonhosted.org/packages/source/r/ruptures/ruptures-1.1.9.tar.gz
Source archive SHA256: aa940f3c02235dab94753ff15689f8ebaca10c83da71cb29cbb7f981dfa362dc

Copied base.py, detection/binseg.py, costs/costl1.py, exceptions.py and
utils/utils.py. Only import paths were changed to relative imports. The local
cost factory supports CostL1 only; __init__.py exports Binseg only.
The upstream numerical algorithms are unchanged. Upstream sources are excluded
from project-specific lint/type rules, but compiled and exercised by tests.

This subset needs NumPy, already pinned by our target Home Assistant release.
It avoids unused SciPy and compiled kernel extensions: the upstream PyPI 1.1.9
package has no CPython 3.14 wheel and failed installation without a compiler.
No network download or compilation takes place when analysis runs.
