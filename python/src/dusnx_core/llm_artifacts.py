"""Checksummed, path-safe SFT transfer packages. No implicit model promotion."""
import json
from pathlib import Path
import zipfile
from .llm_data import digest, verify_file_manifest, write_json


def pack(root, destination):
    root=Path(root).resolve();destination=Path(destination).resolve()
    if destination.is_relative_to(root):raise ValueError('ZIP must be outside artifact root')
    manifest={'files':{p.relative_to(root).as_posix():digest(p) for p in sorted(root.rglob('*'))
                      if p.is_file() and p.name!='artifact_manifest.json'}}
    if not manifest['files']:raise ValueError('Empty artifact')
    verify_file_manifest(root,manifest)
    write_json(root/'artifact_manifest.json',manifest)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as z:
        for name in [*manifest['files'],'artifact_manifest.json']:z.write(root/name,name)
    destination.with_suffix('.zip.sha256').write_text(digest(destination)+'\n',encoding='ascii')
    return manifest


def unpack(archive,destination,expected_sha):
    archive=Path(archive);root=Path(destination).resolve()
    if digest(archive)!=expected_sha.strip():raise ValueError('ZIP checksum mismatch')
    if root.exists() and any(root.iterdir()):raise ValueError('Extract only into empty directory')
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        if len(set(names))!=len(names):raise ValueError('Duplicate ZIP member')
        for i in z.infolist():
            if '\\' in i.filename or ':' in i.filename or not (root/i.filename).resolve().is_relative_to(root):
                raise ValueError('Unsafe ZIP path')
            if (i.external_attr>>16)&0o170000==0o120000:raise ValueError('ZIP symlink')
        manifest=json.loads(z.read('artifact_manifest.json'))
        if set(names)!=set(manifest['files'])|{'artifact_manifest.json'}:raise ValueError('Unlisted ZIP file')
        z.extractall(root)
    verify_file_manifest(root,manifest)
    return root
