import os
import sys

from django.test.runner import DiscoverRunner


class QuietDbSetupRunner(DiscoverRunner):
    """Test runner that silences test-database setup and teardown output
    (test database creation, migrations, syncing), while leaving the
    per-test output itself intact.

    Add via `--testrunner ifcbdb.test_runner.QuietDbSetupRunner`
    (or TEST_RUNNER in settings).
    """

    def _quiet(self, method, *args, **kw):
        devnull = open(os.devnull, "w")
        saved_stdout, saved_stderr = sys.stdout, sys.stderr
        try:
            sys.stdout = devnull
            sys.stderr = devnull
            return method(*args, **kw)
        finally:
            sys.stdout, sys.stderr = saved_stdout, saved_stderr
            devnull.close()

    def setup_databases(self, **kwargs):
        print("Spinning up: creating test database and applying migrations...")
        return self._quiet(super().setup_databases, **kwargs)

    def teardown_databases(self, old_config, **kwargs):
        return self._quiet(super().teardown_databases, old_config, **kwargs)

    def run_checks(self, databases):
        "Silences the `System check identified ...` message."
        return self._quiet(super().run_checks, databases)
