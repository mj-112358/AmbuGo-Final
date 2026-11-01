#!/usr/bin/env python3
"""Verify an AmbuGo replication ZIP or its extracted manifest.

This verifier uses only the Python standard library. The optional microscopic
smoke test additionally requires dependencies installed in work/v9/vendor.
"""
from __future__ import annotations
import argparse,hashlib,json,stat,subprocess,sys,tempfile,zipfile
from pathlib import Path,PurePosixPath


def safe_parts(name):
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name:
        raise ValueError(f'Unsafe archive path: {name}')
    return p.parts


def digest_stream(f):
    h=hashlib.sha256();n=0
    for chunk in iter(lambda:f.read(1024*1024),b''):
        n+=len(chunk);h.update(chunk)
    return h.hexdigest(),n


def validate_manifest(m):
    seen=set()
    for entry in m['files']:
        parts=safe_parts(entry['path'])
        if not parts or entry['path'] in seen:raise ValueError('Duplicate or empty manifest path')
        seen.add(entry['path'])
        if len(entry['sha256'])!=64 or entry['bytes']<0:raise ValueError('Invalid manifest entry')
    return seen


def verify_archive(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)):raise ValueError('Duplicate ZIP member')
        for info in z.infolist():
            safe_parts(info.filename)
            if stat.S_IFMT(info.external_attr>>16)==stat.S_IFLNK:raise ValueError('Archive symlinks are not permitted')
        matches=[n for n in names if n.endswith('/MANIFEST.json') or n=='MANIFEST.json']
        if len(matches)!=1:raise ValueError('Expected exactly one MANIFEST.json')
        mp=matches[0];prefix=mp[:-len('MANIFEST.json')]
        m=json.loads(z.read(mp));wanted=validate_manifest(m)
        if any(not n.startswith(prefix) for n in names):raise ValueError('ZIP contains a member outside the manifested root')
        actual={n[len(prefix):] for n in names if not n.endswith('/') and n.startswith(prefix)}
        if actual!=wanted|{'MANIFEST.json'}:raise ValueError('Manifest membership differs from ZIP membership')
        total=0
        for e in m['files']:
            with z.open(prefix+e['path']) as f:h,n=digest_stream(f)
            if h!=e['sha256'] or n!=e['bytes']:raise ValueError('Hash or size mismatch: '+e['path'])
            total+=n
    return m,prefix,dict(verified=True,files=len(m['files']),uncompressed_bytes=total,archive_bytes=Path(path).stat().st_size,model_sha256=m.get('frozen_model_sha256'))


def verify_directory(root):
    root=Path(root).resolve();m=json.loads((root/'MANIFEST.json').read_text());validate_manifest(m);total=0
    for e in m['files']:
        p=root.joinpath(*safe_parts(e['path']))
        if not p.is_file() or p.is_symlink():raise ValueError('Missing or unsafe extracted file: '+e['path'])
        with p.open('rb') as f:h,n=digest_stream(f)
        if h!=e['sha256'] or n!=e['bytes']:raise ValueError('Hash or size mismatch: '+e['path'])
        total+=n
    return m,dict(verified=True,files=len(m['files']),uncompressed_bytes=total,model_sha256=m.get('frozen_model_sha256'))


def smoke(root):
    """Run a short numerical smoke check of the software and local paths."""
    root=Path(root).resolve();source=root/'work/v9'
    fixture=root/'outputs/AmbuGo_v7_Synthetic_Data'
    required=['nodes.csv','edges.csv','vehicle_classes.csv','od_probabilities.csv']
    for n in required:
        if not (fixture/n).is_file():raise ValueError('Missing fixture '+n)
    for executable in ['sumo','netconvert']:
        if not (source/'vendor/sumo/bin'/executable).is_file():
            raise RuntimeError('Install requirements into work/v9/vendor before the optional smoke test')
    with tempfile.TemporaryDirectory(prefix='ambugo_smoke_') as out:
        code=("import sys,json;from pathlib import Path;"
              "sys.path.insert(0,str(Path('work/v9').resolve()));import sumo_study as s;"
              "r=s.run_case(987654,.6,1,'P0',warmup=30,horizon=180,mission_end=60,"
              "save_trace=False,output=sys.argv[1]);"
              "assert r['partition_identity_max_error']==0;"
              "assert r['residence_identity_error']==0;"
              "assert r['colliding_vehicle_events']==0;"
              "assert r['starting_teleport_events']==0;"
              "assert r['signal_timing_violations']==0;"
              "print(json.dumps({k:r[k] for k in ['partition_identity_max_error',"
              "'residence_identity_error','colliding_vehicle_events','starting_teleport_events',"
              "'signal_timing_violations','missions_completed']}))")
        p=subprocess.run([sys.executable,'-c',code,out],cwd=root,text=True,capture_output=True,timeout=180)
        if p.returncode:raise RuntimeError('Microscopic smoke failed:\n'+p.stdout+p.stderr)
        return dict(passed=True,scope='180 s numerical/path portability smoke only',output=p.stdout.strip())


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('archive',nargs='?');ap.add_argument('--directory');ap.add_argument('--extract');ap.add_argument('--smoke',action='store_true');args=ap.parse_args()
    if bool(args.archive)==bool(args.directory):ap.error('Specify an archive OR --directory')
    if args.directory:
        if args.extract:ap.error('--extract applies only to an archive')
        m,result=verify_directory(args.directory);root=Path(args.directory)
    else:
        m,prefix,result=verify_archive(args.archive);root=None
        if args.extract:
            dest=Path(args.extract)
            if dest.exists() and any(dest.iterdir()):raise ValueError('Extraction destination must be new or empty')
            dest.mkdir(parents=True,exist_ok=True)
            with zipfile.ZipFile(args.archive) as z:z.extractall(dest)
            root=dest/Path(prefix);_,result['extracted_manifest']=verify_directory(root);result['extracted_root']=str(root.resolve())
    if args.smoke:
        if root is None:ap.error('--smoke requires --directory or --extract')
        result['smoke']=smoke(root)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
