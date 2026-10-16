"""Bounded source list rendering and on-demand group members."""


class SourceTreeRenderer:
    def __init__(self, app):
        self.app = app
        self.tree = app.source_tree
        self.jobs = set()
        self.version = 0
        self.loaded = {}
        self.pending_groups = set()
        self.tree.bind('<<TreeviewOpen>>', self.open_group, add='+')
        self.tree.bind('<Destroy>', lambda _: self.cancel(), add='+')

    def later(self, callback):
        version = self.version
        def run():
            self.jobs.discard(job)
            if version == self.version:
                callback()
        job = self.tree.after(8, run)
        self.jobs.add(job)

    def cancel(self):
        self.version += 1
        for job in self.jobs:
            self.tree.after_cancel(job)
        self.jobs.clear()
        self.loaded.clear()
        self.pending_groups.clear()

    def set_rows(self, rows):
        self.cancel()
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        self.rows = rows
        def batch(start=0):
            for index in range(start, min(start + 60, len(rows))):
                row = rows[index]
                label = f"{row.get('own_count',0)}/{row.get('message_count',0)} · {row.get('own_ratio',0):.1%}" if 'own_count' in row else '读取后统计'
                if row.get('unresolved_count'):
                    label = '≥ ' + label + f" · 身份未映射 {row['unresolved_count']} 条"
                self.tree.insert('', 'end', iid=str(index), text=row['name'], values=(row.get('message_count',0), label), open=False)
                if row.get('kind') == 'group' and row.get('members'):
                    self.tree.insert(str(index), 'end', iid='pending:' + str(index), text='展开查看群成员')
            self.app.refresh_source_selection()
            if start + 60 < len(rows):
                self.later(lambda: batch(start + 60))
        batch()

    def open_group(self, event=None):
        key = self.tree.focus()
        if not key.isdigit() or int(key) >= len(self.rows) or key in self.pending_groups:
            return
        members = self.rows[int(key)].get('members', [])
        start = self.loaded.get(key, 0)
        if start >= len(members):
            return
        placeholder = 'pending:' + key
        if self.tree.exists(placeholder):
            self.tree.delete(placeholder)
        self.pending_groups.add(key)
        def batch():
            start = self.loaded.get(key, 0)
            end = min(start + 50, len(members))
            for number in range(start, end):
                member = members[number]
                self.tree.insert(key, 'end', iid=f'member:{key}:{number}', text=member['name'], values=(member['message_count'], f"{member['message_count']} 条 · {member['ratio']:.1%}"))
            self.loaded[key] = end
            if end < len(members) and self.tree.item(key, 'open'):
                self.later(batch)
            else:
                self.pending_groups.discard(key)
        # The native open event is emitted before the open flag changes.
        self.later(batch)
