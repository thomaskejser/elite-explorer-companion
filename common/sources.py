import json
import pathlib
import shutil
import urllib.request

from common.db import ROOT

RAW = ROOT / "raw"
UA = {"User-Agent": "elite-explorer-companion/1.0 (+https://github.com/)"}


def _meta_path(dest):
    return dest.with_name(dest.name + ".meta.json")


def _read_meta(dest):
    try:
        return json.loads(_meta_path(dest).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_meta(dest, url, remote):
    _meta_path(dest).write_text(
        json.dumps({"url": url, "etag": remote.get("etag"),
                    "last_modified": remote.get("last_modified"),
                    "size": dest.stat().st_size}, indent=2), encoding="utf-8")


def _head(url):
    req = urllib.request.Request(url, method="HEAD", headers=UA)
    with urllib.request.urlopen(req, timeout=120) as h:
        return {"etag": h.headers.get("ETag"),
                "last_modified": h.headers.get("Last-Modified"),
                "size": int(h.headers.get("Content-Length") or 0)}


def _unchanged(dest, meta, remote):
    if remote.get("etag") and meta.get("etag"):
        return remote["etag"] == meta["etag"]
    if remote.get("last_modified") and meta.get("last_modified"):
        return remote["last_modified"] == meta["last_modified"]
    if remote.get("size"):
        return remote["size"] == dest.stat().st_size
    return False


def download(url, name, min_bytes=1000, raw=None):
    dest = (raw or RAW) / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    have = dest.exists() and dest.stat().st_size >= min_bytes

    remote = None
    try:
        remote = _head(url)
    except Exception as exc:                                           # noqa: BLE001
        if not have:
            raise
        print(f"  cannot reach {url} ({exc})")
        print(f"  *** USING THE CACHED {name}, WHICH MAY BE STALE ***")
        return dest

    if have and _unchanged(dest, _read_meta(dest), remote):
        print(f"  {name} unchanged on the server ({dest.stat().st_size/1e6:,.1f} MB)")
        _write_meta(dest, url, remote)
        return dest

    if have:
        print(f"  {name} changed on the server: {dest.stat().st_size/1e6:,.1f} MB on "
              f"disk, {remote['size']/1e6:,.1f} MB published "
              f"({remote.get('last_modified')})")

    print(f"  GET {url}", flush=True)
    part = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=3600) as r, open(part, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 22)
    if part.stat().st_size < min_bytes:
        part.unlink()
        raise SystemExit(f"{url} returned only {part.stat().st_size} bytes -- refusing "
                         f"to replace {name}")
    part.replace(dest)
    _write_meta(dest, url, remote)
    print(f"  -> {name} ({dest.stat().st_size/1e6:,.1f} MB)")
    return dest


def source_meta(name, raw=None):
    return _read_meta((raw or RAW) / name)


def validator(meta):
    return (meta.get("etag"), meta.get("last_modified"), meta.get("size"))


def _state_path(name, raw=None):
    return (raw or RAW) / (name + ".staged.json")


def read_staged_state(name, raw=None):
    try:
        return json.loads(_state_path(name, raw).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_staged_state(name, state, raw=None):
    _state_path(name, raw).write_text(json.dumps(state, indent=2), encoding="utf-8")


def is_staged(name, raw=None):
    state = read_staged_state(name, raw)
    return bool(state.get("complete")) and \
        state.get("validator") == list(validator(source_meta(name, raw)))
