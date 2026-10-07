"""Shared test assertions."""
from conftest import call, ffprobe, sha


def run_ok(name, media_file, out_dir, **kw):
    """Call a tool on a fixture, assert ok + input untouched, return (result, ffprobe(output))."""
    before = sha(media_file)
    r = call(name, input=str(media_file), output_dir=str(out_dir), **kw)
    assert r["ok"], r
    assert sha(media_file) == before, "input file was modified"
    return r, ffprobe(r["output"])
