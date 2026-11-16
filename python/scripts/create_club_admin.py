#!/usr/bin/env python3
"""Bootstrap the first CLB owner account.

Only works while no owner exists; afterwards role changes go through the web
admin UI (owner token required). The password can come from --password or the
CLUB_ADMIN_PASSWORD env var so it never lands in shell history.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
PYTHON_DIR = HERE.parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(PYTHON_DIR))
sys.path.insert(0, str(PYTHON_DIR / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from apps.ai_api import auth  # noqa: E402

DEFAULT_DATA_DIR = ROOT / "runtime" / "club-data"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", default=os.getenv("CLUB_ADMIN_PASSWORD", ""))
    parser.add_argument("--display-name", default="")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR),
                        help="auth.db location for the club app (kept separate "
                             "from the DUSN-X runtime data dir)")
    args = parser.parse_args()

    if not args.password:
        print(json.dumps({"status": "refused",
                          "reason": "password required: --password or CLUB_ADMIN_PASSWORD"},
                         ensure_ascii=False))
        return 2

    os.environ["DUSNX_DATA_DIR"] = str(Path(args.data_dir).resolve())
    # Force the singleton to bind to the club data dir.
    auth._auth_db = None
    db = auth.get_auth_db()
    try:
        info = db.create_owner_account(args.username, args.password, args.display_name)
    except ValueError as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "created", "data_dir": os.environ["DUSNX_DATA_DIR"],
                      "user_id": info["user_id"], "username": info["username"],
                      "role": info["role"], "status": info["status"]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
