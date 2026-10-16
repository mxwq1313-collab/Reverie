import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode

from wechat_archive import ChatService, ValidationError
from wechat_archive.services.browse_service import BrowseService
from wechat_archive.web.server import make_server


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "demo.db"
        self.server = make_server(self.path, demo=True)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, path, *, method="GET", headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            body = response.read()
            return response.status, dict(response.getheaders()), body
        finally:
            connection.close()

    def api(self, path, code=200, **params):
        status, headers, body = self.request(path + "?" + urlencode(params))
        self.assertEqual(status, code, body.decode("utf-8"))
        self.assertIn("application/json", headers["Content-Type"])
        return json.loads(body)

    def test_status_and_users_pagination(self):
        status = self.api("/api/status")
        self.assertEqual((status["users"], status["messages"], status["mode"]), (3, 5, "demo"))
        users = self.api("/api/users", limit=1, offset=1)
        self.assertEqual(users["items"][0]["nickname"], "张三（演示）")
        self.assertTrue(users["has_more"])
        self.assertEqual(users["total"], 3)

    def test_contact_summaries_and_search(self):
        contacts = self.api("/api/contacts", user_id=1)
        self.assertEqual(contacts["total"], 2)
        self.assertEqual([row["id"] for row in contacts["items"]], [3, 2])
        self.assertEqual(contacts["items"][0]["message_count"], 2)
        self.assertEqual(contacts["items"][0]["last_message"], "谢谢，我稍后查看。")
        self.assertEqual(self.api("/api/contacts", user_id=1, q="张三")["items"][0]["id"], 2)
        self.assertEqual(self.api("/api/contacts", user_id=1, q="%_")["total"], 0)

    def test_contact_summary_does_not_show_third_party_conversation(self):
        service = self.server.service
        service.create_message(2, 3, "别人的聊天", create_time="2027-01-01T00:00:00Z")
        contacts = self.api("/api/contacts", user_id=1)
        self.assertEqual(contacts["items"][0]["last_message"], "谢谢，我稍后查看。")
        self.assertEqual(sum(row["message_count"] for row in contacts["items"]), 5)

    def test_bidirectional_messages_and_filtered_totals(self):
        conversation = self.api("/api/messages", user_id=1, peer_id=2)
        self.assertEqual(conversation["total"], 3)
        self.assertEqual([row["sender_id"] for row in conversation["items"]], [1, 2, 1])
        self.assertEqual(conversation["items"][1]["sender_name"], "张三（演示）")
        found = self.api("/api/messages", user_id=1, q="开会")
        self.assertEqual(found["total"], 2)
        self.assertEqual(self.api("/api/messages", user_id=3, q="开会")["total"], 0)

    def test_messages_time_filter_and_pagination(self):
        page1 = self.api("/api/messages", user_id=1, peer_id=2, limit=2)
        page2 = self.api("/api/messages", user_id=1, peer_id=2, limit=2, offset=2)
        self.assertEqual(page1["total"], 3)
        self.assertTrue(page1["has_more"])
        self.assertFalse(page2["has_more"])
        self.assertEqual([row["id"] for row in page1["items"] + page2["items"]], [1, 2, 3])
        window = self.api("/api/messages", user_id=1, start="2026-01-01T12:01:00+08:00", end="2026-01-01T12:02:00+08:00")
        self.assertEqual([row["id"] for row in window["items"]], [2])

    def test_missing_and_invalid_parameters(self):
        cases = (
            ("/api/contacts", {}, 400), ("/api/messages", {}, 400),
            ("/api/messages", {"user_id": "oops"}, 400),
            ("/api/messages", {"user_id": 1, "peer_id": 999}, 404),
            ("/api/messages", {"user_id": 0}, 400),
            ("/api/messages", {"user_id": 1, "limit": 1001}, 400),
            ("/api/messages", {"user_id": 1, "offset": -1}, 400),
            ("/api/messages", {"user_id": 1, "start": "2026-01-01"}, 400),
            ("/api/messages", {"user_id": 1, "unexpected": 1}, 400),
            ("/api/messages", {"user_id": 1, "q": "  "}, 400),
        )
        for path, params, code in cases:
            with self.subTest(params=params):
                self.assertIn("error", self.api(path, code, **params))
        self.assertEqual(self.request("/api/messages?user_id=1&user_id=2")[0], 400)

    def test_no_cross_origin_or_remote_host_reads(self):
        self.assertEqual(self.request("/api/users", headers={"Origin": "https://example.com"})[0], 403)
        self.assertEqual(self.request("/api/users", headers={"Host": "example.com"})[0], 403)
        self.assertEqual(self.request("/api/users", headers={"Origin": self.server.url.rstrip("/")})[0], 200)
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_web_requests_do_not_modify_data(self):
        before = self.path.read_bytes()
        self.api("/api/messages", user_id=1)
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            self.assertEqual(self.request("/api/messages", method=method)[0], 405)
        self.assertEqual(self.path.read_bytes(), before)

    def test_static_assets_and_private_files(self):
        for path, mime in (("/", "text/html"), ("/app.css", "text/css"), ("/app.js", "text/javascript"), ("/favicon.svg", "image/svg+xml")):
            status, headers, body = self.request(path)
            self.assertEqual(status, 200)
            self.assertIn(mime, headers["Content-Type"])
            self.assertTrue(body)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        for path in ("/data/demo.db", "/../README.md", "/%2e%2e/README.md", "/api/unknown"):
            self.assertEqual(self.request(path)[0], 404)
        self.assertEqual(self.request("/", method="HEAD")[2], b"")


class BrowseEdgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = ChatService(Path(self.temp.name) / "empty.db")
        self.reader = BrowseService(self.service)

    def test_empty_archive(self):
        self.assertEqual(self.reader.users(), {"items": [], "total": 0, "offset": 0, "has_more": False})

    def test_self_notes_and_contacts_without_messages(self):
        me = self.service.create_user("me", "我")
        friend = self.service.create_user("friend", "朋友")
        self.assertEqual([row["id"] for row in self.reader.contacts(me.id)["items"]], [friend.id])
        self.service.create_message(me.id, me.id, "笔记")
        self.assertEqual(self.reader.contacts(me.id)["items"][0]["id"], me.id)
        self.assertEqual(self.reader.messages(me.id, peer_id=me.id)["total"], 1)

    def test_pagination_with_more_than_one_ui_page(self):
        me = self.service.create_user("me", "我")
        peer = self.service.create_user("peer", "朋友")
        for index in range(105):
            self.service.create_message(me.id, peer.id, f"消息 {index}", create_time="2026-01-01T00:00:00Z")
        ids = []
        for offset in (0, 50, 100):
            page = self.reader.messages(me.id, peer_id=peer.id, offset=offset)
            self.assertEqual(page["total"], 105)
            ids.extend(row["id"] for row in page["items"])
        self.assertEqual(ids, list(range(1, 106)))

    def test_port_validation(self):
        for port in (-1, 65536, True):
            with self.subTest(port=port), self.assertRaises(ValidationError):
                make_server(self.service.database.path, port=port)

    def test_contact_pages_do_not_truncate_large_lists(self):
        me = self.service.create_user("me", "我")
        for index in range(55):
            self.service.create_user(f"person_{index}", f"联系人 {index}")
        first = self.reader.contacts(me.id)
        second = self.reader.contacts(me.id, offset=50)
        self.assertEqual((first["total"], len(first["items"]), first["has_more"]), (55, 50, True))
        self.assertEqual((len(second["items"]), second["has_more"]), (5, False))
        self.assertEqual(len({row["id"] for row in first["items"] + second["items"]}), 55)


if __name__ == "__main__":
    unittest.main()
