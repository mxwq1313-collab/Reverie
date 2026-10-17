"""Reproducible visible-window resize probe using only generated test data."""
import argparse
import cProfile
import io
import json
from pathlib import Path
import pstats
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--code-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--scenario', choices=('memory', 'plain', 'forward', 'codex'), default='memory')
    parser.add_argument('--hold', action='store_true', help='Keep the generated-data window open for manual resizing.')
    args = parser.parse_args()
    sys.path[:0] = [str(args.code_root), str(args.code_root / 'tests')]
    from test_workbench import WorkbenchTests
    from test_release_211 import forward_xml
    case = WorkbenchTests()
    case.setUp()
    app, root = case.app, case.root
    try:
        case.show(1260, 820)
        app.background_browsing = True
        if args.scenario == 'memory':
            app.show_page('随机回忆')
            editor = app.toolbox_panel.random.memory
        elif args.scenario in ('plain', 'forward'):
            base = app.message_rows[0]
            rows = [{**base, 'id': 70000 + i, 'content': forward_xml(10, True) if args.scenario == 'forward' else ('长消息缩放验收，保留原文[微笑]。' * 30 + '\n' + str(i)), 'msg_type': 'system' if args.scenario == 'forward' else 'text', 'attachments': []} for i in range(3 if args.scenario == 'forward' else 100)]
            app.message_rows = rows
            app.chat_text.set_rows_incremental(rows, app.owner_id)
            editor = None
        else:
            panel = app.agent_panel
            panel._clear()
            for i in range(14):
                panel._add('你' if i % 2 else 'Codex · 回答', ('## 合成回答\n\n- **归档依据**：自建测试内容。\n\n' * 16) + str(i))
            app.open_copilot(False)
            editor = panel.transcript
        def settle(seconds):
            root.after(round(seconds * 1000), root.quit)
            root.mainloop()
        settle(2)
        if args.scenario == 'forward':
            for value in app.chat_text.bubbles.values():
                value['forward'].toggle()
            settle(2)
        if editor is not None:
            editor.tag_add('sel', '1.0', '1.2')
            raw = editor.get('1.0', 'end-1c')
            identity = str(editor)
        root.title('思绪 · 合成缩放验收 · ' + args.scenario)
        if args.hold:
            root.mainloop()
            return
        gaps, samples, unmaps = [], [], []
        previous = [time.perf_counter()]
        ticking = [True]
        def tick():
            now = time.perf_counter()
            gaps.append((now - previous[0]) * 1000)
            previous[0] = now
            if ticking[0]:
                root.after(8, tick)
        def unmapped(event):
            if event.widget is app.workspace_panes:
                unmaps.append(time.perf_counter())
        app.workspace_panes.bind('<Unmap>', unmapped, add='+')
        def sample():
            pane, viewport = app.workspace_panes, app.resize_viewport
            samples.append({'mapped': bool(pane.winfo_viewable()), 'pane': [pane.winfo_width(), pane.winfo_height()], 'viewport': [viewport.winfo_width(), viewport.winfo_height()]})
        # Configure is delivered by the native window system after geometry().
        # Observe the actual pane rather than the first idle callback after a request.
        app.workspace_panes.bind('<Configure>', lambda e: root.after_idle(sample) if e.widget is app.workspace_panes else None, add='+')
        sizes = [(w, 700 + round((w - 980) * .30)) for w in range(980, 1481, 20)]
        sizes += list(reversed(sizes))
        def step(index=0):
            if index == len(sizes):
                root.after(800, root.quit)
                return
            w, h = sizes[index]
            root.geometry(f'{w}x{h}+20+35')
            root.after(35, lambda: step(index + 1))
        profile = cProfile.Profile()
        tick()
        profile.enable()
        root.after(1, step)
        root.mainloop()
        profile.disable()
        ticking[0] = False
        root.update()
        sample()
        preview = getattr(getattr(app, 'native_resize', None), 'preview', None)
        ordered = sorted(gaps)
        result = {'scenario': args.scenario, 'sizes': len(sizes), 'samples': len(samples), 'heartbeat_p95_ms': round(ordered[int(.95 * len(ordered))], 3), 'heartbeat_max_ms': round(max(gaps), 3), 'gaps_over_50ms': sum(x > 50 for x in gaps), 'workspace_unmaps': len(unmaps), 'mapped_samples': sum(x['mapped'] for x in samples), 'matching_geometry_samples': sum(x['pane'] == x['viewport'] for x in samples), 'backing_frames': preview.frames if preview else 0, 'final_geometry': samples[-1], 'errors': [str(e) for e in case.errors], 'synthetic_only': True}
        if editor is not None:
            result['text_and_widget_retained'] = editor.get('1.0', 'end-1c') == raw and str(editor) == identity
            result['selection_retained'] = tuple(map(str, editor.tag_ranges('sel'))) == ('1.0', '1.2')
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        stream = io.StringIO()
        pstats.Stats(profile, stream=stream).sort_stats('cumulative').print_stats(50)
        args.out.with_suffix('.profile.txt').write_text(stream.getvalue(), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False), flush=True)
        assert not case.errors, case.errors
    finally:
        case.doCleanups()


if __name__ == '__main__':
    main()
