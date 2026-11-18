"""Test-wide defaults for the legacy core suites.

The club product registers accounts as pending approval: /v1/auth/register
honours DUSNX_DEFAULT_USER_STATUS and defaults to "pending". The legacy core
tests exercise flows that register and immediately log in, so they opt into
instant approval here. Club tests override this back to "pending" per test.
"""
import os

os.environ["DUSNX_DEFAULT_USER_STATUS"] = "approved"
