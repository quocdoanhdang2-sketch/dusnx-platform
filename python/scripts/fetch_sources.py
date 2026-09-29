"""Fetch pinned public data; gated CSConDa requires explicit local authorization.

No remote Python loaders are executed. MASSIVE's pinned HF loader points to the
versioned publisher archive; only vi-VN is read, never extractall().
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile
import urllib.request
import urllib.error


def download(url, destination, token=None):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "dusnx-data-audit/1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as out:
        while chunk := response.read(1024 * 1024):
            out.write(chunk)
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def fetch(source, manifest, output, *, allow_gated=False):
    cfg = manifest[source]
    destination = Path(output) / source
    destination.mkdir(parents=True, exist_ok=True)
    report = {"source": source, "revision": cfg["revision"], "license": cfg["license"], "files": {}}
    try:
        if source == "csconda":
            # Never use alternate mirrors/viewer APIs to evade a gate.
            token = os.getenv("HF_TOKEN")
            if not allow_gated or not token:
                report["status"] = "awaiting_access_and_explicit_opt_in"
            else:
                for name in cfg["files"]:
                    url = f"https://huggingface.co/datasets/{cfg['repository']}/resolve/{cfg['revision']}/{name}"
                    report["files"][name] = download(url, destination / Path(name).name, token)
                report["status"] = "downloaded"
        elif source == "massive":
            loader = f"https://huggingface.co/datasets/{cfg['repository']}/resolve/{cfg['revision']}/massive.py"
            report["files"]["massive.py.reference"] = download(loader, destination / "massive.py.reference")
            archive = destination / "massive-1.1.tar.gz"
            digest = hashlib.sha256(archive.read_bytes()).hexdigest() if archive.exists() else download(cfg["archive_url"], archive)
            if cfg.get("archive_sha256") and digest != cfg["archive_sha256"]:
                raise ValueError("MASSIVE archive SHA-256 mismatch")
            report["archive_sha256"] = digest
            found = False
            with tarfile.open(archive, "r:gz") as handle:
                for member in handle:
                    if member.isfile() and Path(member.name).name == "vi-VN.jsonl":
                        payload = handle.extractfile(member).read()
                        (destination / "vi-VN.jsonl").write_bytes(payload)
                        report["files"]["vi-VN.jsonl"] = hashlib.sha256(payload).hexdigest()
                        found = True
                        break
            if not found:
                raise ValueError("vi-VN.jsonl not found in publisher archive")
            report["status"] = "downloaded"
        else:
            for name in cfg["files"]:
                url = f"https://raw.githubusercontent.com/google-research-datasets/dstc8-schema-guided-dialogue/{cfg['upstream_revision']}/{name}"
                report["files"][name] = download(url, destination / Path(name).name)
            report["status"] = "reference_downloaded_not_for_training"
    except urllib.error.HTTPError as exc:
        report.update(status="access_denied" if exc.code in (401,403) else "download_failed", http_status=exc.code)
    except Exception as exc:
        report.update(status="download_failed", error=type(exc).__name__)
    (destination / "fetch_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", choices=["massive","csconda","sgd","all"], default="all")
    ap.add_argument("--manifest", default="configs/data_sources.json")
    ap.add_argument("--output", default="runtime/external-data")
    ap.add_argument("--allow-gated", action="store_true")
    args=ap.parse_args()
    manifest=json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    failed=False
    for source in manifest if args.source=="all" else [args.source]:
        report=fetch(source,manifest,args.output,allow_gated=args.allow_gated)
        print(json.dumps(report,ensure_ascii=False))
        failed |= report["status"] == "download_failed"
    raise SystemExit(1 if failed else 0)


if __name__=="__main__":
    main()
