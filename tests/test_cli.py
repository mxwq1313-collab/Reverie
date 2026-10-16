import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "CLI 中文" / "chat.db"

    def run_cli(self, *args, code=0, module=False, elsewhere=False):
        entry = ["-m", "wechat_archive"] if module else [str(ROOT / "main.py")]
        result = subprocess.run(
            [sys.executable, *entry, "--db", str(self.db), *args],
            cwd=self.temp.name if elsewhere else ROOT, capture_output=True, encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1"}, timeout=15,
        )
        self.assertEqual(result.returncode, code, result.stderr)
        if code == 0:
            self.assertEqual(result.stderr, "")
            return json.loads(result.stdout)
        self.assertEqual(result.stdout, "")
        return json.loads(result.stderr)

    def test_complete_cli_crud_flow(self):
        self.assertEqual(self.run_cli("init")["status"], "ready")
        me = self.run_cli("user", "add", "wxid_me", "我")
        friend = self.run_cli("user", "add", "wxid_friend", "张三", "--avatar", "a.png")
        self.assertEqual(self.run_cli("user", "get", str(friend["id"])), friend)
        changed = self.run_cli("user", "update", str(friend["id"]), "--nickname", "朋友", "--clear-avatar")
        self.assertIsNone(changed["avatar"])
        self.assertEqual(self.run_cli("user", "list", "--limit", "1", "--offset", "1"), [changed])
        message = self.run_cli("message", "add", str(me["id"]), str(friend["id"]), "中文🙂 开会", "--time", "2026-01-01T12:00:00+08:00")
        self.assertEqual(message["create_time"], "2026-01-01T04:00:00.000000Z")
        self.assertEqual(self.run_cli("message", "get", str(message["id"])), message)
        self.assertEqual(self.run_cli("conversation", str(me["id"]), str(friend["id"])), [message])
        self.assertEqual(self.run_cli("search", "开会", "--user", str(me["id"]), "--peer", str(friend["id"])), [message])
        self.assertEqual(self.run_cli("message", "list", "--start", "2026-01-01T04:00:00Z", "--end", "2026-01-01T05:00:00Z"), [message])
        message = self.run_cli("message", "update", str(message["id"]), "--content", "修改后的消息")
        self.assertEqual(message["content"], "修改后的消息")
        self.assertEqual(self.run_cli("user", "delete", str(friend["id"]), code=1)["error"]["type"], "ConflictError")
        self.run_cli("message", "delete", str(message["id"]))
        self.run_cli("user", "delete", str(friend["id"]))
        stats = self.run_cli("stats")
        self.assertEqual((stats["users"], stats["messages"]), (1, 0))

    def test_errors_are_json_and_nonzero(self):
        self.assertEqual(self.run_cli("message", "get", "999", code=1)["error"]["type"], "NotFoundError")
        self.assertEqual(self.run_cli("message", "list", "--limit", "0", code=1)["error"]["type"], "ValidationError")

    def test_module_entry_and_absolute_script_from_other_directory(self):
        self.run_cli("init", module=True)
        self.assertEqual(self.run_cli("stats", elsewhere=True)["users"], 0)

    def test_demo_command_repeated(self):
        first = self.run_cli("demo")
        second = self.run_cli("demo")
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(second["stats"], {"users": 3, "messages": 5})

    def test_python_example_utf8_and_repeatable(self):
        # 复制源码到临时目录，使演示不会写入交付项目里的任何数据库。
        import shutil

        copy = Path(self.temp.name) / "project"
        shutil.copytree(ROOT / "wechat_archive", copy / "wechat_archive", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "examples", copy / "examples", ignore=shutil.ignore_patterns("__pycache__"))
        for _ in range(2):
            result = subprocess.run(
                [sys.executable, "-m", "examples.basic_usage"], cwd=copy,
                capture_output=True, encoding="utf-8", timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("删除本次示例消息后： {'users': 2, 'messages': 0}", result.stdout)
            self.assertNotIn("\ufffd", result.stdout)


if __name__ == "__main__":
    unittest.main()
