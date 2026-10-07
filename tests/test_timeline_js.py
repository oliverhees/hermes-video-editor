"""Unit tests for the pure timeline logic (editor/web/timeline.js) run in Node."""
import shutil
import subprocess
import textwrap

import pytest

from conftest import ROOT

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="node is not installed")


def run(script, tmp_path):
    f = tmp_path / "t.cjs"
    f.write_text("const T = require(%r)\nconst assert = require('assert')\nlet n = 0; const id = () => 'n' + (++n)\n" % str(ROOT / "editor" / "web" / "timeline.js")
                 + textwrap.dedent(script) + "\nconsole.log('OK')\n")
    r = subprocess.run([NODE, str(f)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr + r.stdout


def test_layout_at_and_total(tmp_path):
    run("""
    const clips = [{id:'a',asset:'x',in:0,out:4},{id:'b',asset:'y',in:2,out:5}]
    const L = T.layout(clips)
    assert.deepStrictEqual(L.items.map(i => [i.start, i.end]), [[0,4],[4,7]]); assert.strictEqual(L.total, 7)
    assert.deepStrictEqual([T.at(clips, 1).index, T.at(clips, 1).src], [0, 1])
    assert.deepStrictEqual([T.at(clips, 4).index, T.at(clips, 4).src], [1, 2])         // boundary belongs to the next clip
    assert.deepStrictEqual([T.at(clips, 5.5).index, T.at(clips, 5.5).src], [1, 3.5])
    assert.strictEqual(T.at(clips, 99).index, 1); assert.strictEqual(T.at(clips, -3).index, 0)
    assert.strictEqual(T.at([], 1), null); assert.strictEqual(T.total([]), 0)
    """, tmp_path)


def test_split_keeps_total_and_source_continuity(tmp_path):
    run("""
    const clips = [{id:'a',asset:'x',in:1,out:5}]
    const r = T.split(clips, 1.5, 'new')
    assert.ok(r.changed); assert.strictEqual(r.index, 1)
    assert.deepStrictEqual(r.clips.map(c => [c.id, c.in, c.out]), [['a',1,2.5],['new',2.5,5]])
    assert.strictEqual(T.total(r.clips), 4)
    assert.ok(!T.split(clips, 0.01, 'z').changed && !T.split(clips, 3.99, 'z').changed)  // too close to an edge
    assert.ok(!T.split([], 1).changed)
    assert.strictEqual(clips[0].out, 5)                                                   // input untouched
    """, tmp_path)


def test_delete_range_ripples_across_clips(tmp_path):
    run("""
    const clips = [{id:'a',asset:'x',in:0,out:4},{id:'b',asset:'y',in:0,out:4}]
    let r = T.deleteRange(clips, 3, 5, id)
    assert.deepStrictEqual(r.map(c => [c.asset, c.in, c.out]), [['x',0,3],['y',1,4]]); assert.strictEqual(T.total(r), 6)
    r = T.deleteRange(clips, 1, 2, id)                                                     // inside one clip -> two pieces
    assert.deepStrictEqual(r.map(c => [c.asset, c.in, c.out]), [['x',0,1],['x',2,4],['y',0,4]])
    assert.notStrictEqual(r[0].id, r[1].id)
    r = T.deleteRange(clips, 0, 4, id)                                                     // exactly one clip
    assert.deepStrictEqual(r.map(c => c.id), ['b'])
    r = T.deleteRange(clips, 5, 3, id)                                                     // reversed arguments
    assert.strictEqual(T.total(r), 6)
    assert.strictEqual(T.total(T.deleteRange(clips, 0, 99, id)), 0)
    assert.ok(Math.abs(T.total(T.deleteRange(clips, 1, 1.01, id)) - 7.99) < 1e-9)           // a tiny range still ripples exactly
    """, tmp_path)


def test_silence_removal_per_clip(tmp_path):
    run("""
    const clips = [{id:'a',asset:'x',in:0,out:10},{id:'b',asset:'y',in:0,out:3},{id:'c',asset:'x',in:20,out:30}]
    const ranges = [[2,4],[8,12],[25,26]]
    let r = T.applySilence(clips, 'x', ranges, null, id)
    assert.deepStrictEqual(r.map(c => [c.asset, c.in, c.out]), [['x',0,2],['x',4,8],['y',0,3],['x',20,25],['x',26,30]])
    r = T.applySilence(clips, 'x', ranges, 'a', id)                                         // only the selected clip
    assert.deepStrictEqual(r.map(c => [c.id.startsWith('n') ? 'new' : c.id, c.in, c.out]), [['a',0,2],['new',4,8],['b',0,3],['c',20,30]])
    assert.deepStrictEqual(T.subtractRanges(clips[0], [[0,10]], id), [])
    assert.deepStrictEqual(T.subtractRanges(clips[0], [], id), [clips[0]])
    """, tmp_path)


def test_trim_move_and_drop_index(tmp_path):
    run("""
    const clips = [{id:'a',asset:'x',in:2,out:6},{id:'b',asset:'y',in:0,out:3}]
    assert.deepStrictEqual([T.trim(clips,0,'left',1.5,10)[0].in, T.trim(clips,0,'left',1.5,10)[0].out], [3.5, 6])
    assert.strictEqual(T.trim(clips,0,'left',-5,10)[0].in, 0)                               // cannot go before the file start
    assert.strictEqual(T.trim(clips,0,'left',99,10)[0].in, 5.9)                             // keeps the minimum length
    assert.strictEqual(T.trim(clips,0,'right',99,10)[0].out, 10)                            // cannot exceed the file length
    assert.strictEqual(T.trim(clips,0,'right',-99,10)[0].out, 2.1)
    assert.strictEqual(T.total(T.trim(clips,0,'left',1,10)), 6)                             // ripple
    assert.deepStrictEqual(T.move(clips, 0, 1).map(c => c.id), ['b','a'])
    assert.deepStrictEqual(T.move(clips, 1, 0).map(c => c.id), ['b','a'])
    assert.deepStrictEqual(T.move(clips, 0, 0).map(c => c.id), ['a','b'])
    assert.strictEqual(T.dropIndex(clips, 0, 0.5), 0); assert.strictEqual(T.dropIndex(clips, 0, 2.9), 1)
    assert.deepStrictEqual(T.insertAt(clips, 1, {id:'z'}).map(c => c.id), ['a','z','b'])
    assert.deepStrictEqual(T.forExport(clips, {x:{path:'/p/x.mp4'}, y:{path:'/p/y.mp4'}}), [{path:'/p/x.mp4',in:2,out:6},{path:'/p/y.mp4',in:0,out:3}])
    """, tmp_path)


def test_history_undo_redo(tmp_path):
    run("""
    const h = T.createHistory(3)
    let state = {v: 1}; h.push(state); state = {v: 2}; h.push(state); state = {v: 3}
    assert.ok(h.canUndo() && !h.canRedo())
    let prev = h.undo(state); assert.deepStrictEqual(prev, {v: 2}); state = prev
    prev = h.undo(state); assert.deepStrictEqual(prev, {v: 1}); state = prev
    assert.strictEqual(h.undo(state), null)
    let next = h.redo(state); assert.deepStrictEqual(next, {v: 2}); state = next
    h.push(state); assert.ok(!h.canRedo())                                                 // new edit clears redo
    for (let i = 0; i < 10; i++) h.push({v: i}); let c = 0; while (h.undo({}) ) c++; assert.strictEqual(c, 3)   // history limit
    """, tmp_path)


def test_transform_geometry_and_tf_survives_edits(tmp_path):
    run("""
    assert.deepStrictEqual(T.canvasSize('9:16', 1080), [1080, 1920]); assert.deepStrictEqual(T.canvasSize('16:9', 720), [1280, 720])
    assert.deepStrictEqual(T.canvasSize('1:1', 1080), [1080, 1080]); assert.deepStrictEqual(T.canvasSize('4:5', 1080), [1080, 1350])
    assert.deepStrictEqual(T.canvasSize('auto', 0, 641, 361), [642, 362]); assert.deepStrictEqual(T.canvasSize('9:16', 123), [1080, 1920])
    // a 16:9 picture "fit" into a 9:16 canvas: full width, centred, bars above and below
    assert.deepStrictEqual(T.fgRect(1920, 1080, 1080, 1920, null), [0, 656, 1080, 608])
    assert.deepStrictEqual(T.fgRect(1920, 1080, 1080, 1920, {s: 2, x: 0, y: 0}), [-540, 352, 2160, 1216])
    assert.deepStrictEqual(T.fgRect(1920, 1080, 1080, 1920, {s: 1, x: 0.25, y: -0.1}), [270, 464, 1080, 608])
    assert.ok(Math.abs(T.fillScale(1920, 1080, 1080, 1920) - 3.1604938) < 1e-6)
    assert.deepStrictEqual(T.cleanTf({s: 99, x: 'a', y: -9}), {s: 10, x: 0, y: -3}); assert.deepStrictEqual(T.cleanTf(null), {s: 1, x: 0, y: 0})
    assert.ok(T.isDefaultTf(undefined) && T.isDefaultTf({s:1,x:0,y:0}) && !T.isDefaultTf({s:1.1,x:0,y:0}))
    // split / delete / trim keep the transform on every piece, and the input is not mutated
    const clips = [{id:'a',asset:'x',in:0,out:8,tf:{s:2,x:0.1,y:0}}]
    const r = T.split(clips, 3, 'n'); assert.deepStrictEqual(r.clips.map(c => c.tf), [{s:2,x:0.1,y:0},{s:2,x:0.1,y:0}])
    assert.notStrictEqual(r.clips[0].tf, r.clips[1].tf)
    assert.deepStrictEqual(T.deleteRange(clips, 2, 3, id).map(c => c.tf.s), [2, 2])
    assert.strictEqual(T.trim(clips, 0, 'right', -1, 8)[0].tf.s, 2)
    assert.deepStrictEqual(T.forExport(clips, {x:{path:'/p.mp4'}}), [{path:'/p.mp4', in:0, out:8, tf:{s:2,x:0.1,y:0}}])
    assert.strictEqual(T.forExport([{id:'b',asset:'x',in:0,out:1}], {x:{path:'/p.mp4'}})[0].tf, undefined)
    """, tmp_path)
