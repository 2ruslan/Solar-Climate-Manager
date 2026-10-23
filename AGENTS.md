# Project verification

- After code changes, run the full verification suite before reporting completion: dependency checks (`pip check`), Ruff, mypy, unit tests, syntax compilation, Home Assistant integration tests, and the frontend browser checks.
- On Windows, run the Home Assistant and browser suites in Linux Docker using the versions pinned in `requirements/ha.txt`. Follow `docs/development.md`; start Docker Desktop if needed.
- Run unit tests and Home Assistant pytest tests in separate processes: unit tests install Home Assistant stubs that must not leak into the integration suite.
- Run mypy in the lightweight dev environment without Home Assistant, as documented. Run unit tests on Python 3.11 and the pinned HA Python version.
- Run `tests/frontend/check_panel.py` after the HA suite in the same environment so `/tmp/scm-panel-fixture.json` is available.
- Fix failures and rerun affected checks. Report exact results and any blocked or skipped checks; never describe local unit tests alone as full verification.
- Keep GitHub Actions disabled unless the user explicitly asks to enable them.
