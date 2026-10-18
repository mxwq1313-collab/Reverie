"""Lazy management and asynchronous context contacts."""
import time,threading,unittest
from unittest.mock import patch
import test_workbench as fixture

class HiddenPageLagTests(unittest.TestCase):
    setUp=fixture.WorkbenchTests.setUp
    show=fixture.WorkbenchTests.show
    def settle(self,predicate):
        stop=time.monotonic()+5
        while time.monotonic()<stop:
            self.root.update()
            if predicate():return
            time.sleep(.005)
        self.fail('background UI did not settle')
    def test_hidden_tree_is_lazy_and_tab_open_rebuilds_current_rows(self):
        app=self.app;app.background_browsing=True;self.show()
        with patch.object(app.message_tree,'insert',wraps=app.message_tree.insert) as insert:
            app.load_messages(_prepared={'items':list(app.message_rows),'total':len(app.message_rows),'has_more':False})
            self.assertEqual(insert.call_count,0)
            app.show_page('数据管理');self.settle(lambda:not getattr(app,'management_job',None))
        self.assertEqual(set(app.message_tree.get_children()),{str(row['id']) for row in app.message_rows})
        self.assertEqual(self.errors,[])
    def test_context_and_return_do_not_query_contacts_on_ui_thread(self):
        app=self.app;self.show();app.background_browsing=True
        app.search_scope.set('全部会话');app.load_messages()
        self.settle(lambda:app.browser_reads.future is None and not getattr(app.chat_text,'rendering',False))
        rows=list(app.contact_rows);ui_thread=threading.get_ident();original=type(app.controller).contacts;threads=[]
        def checked(reader,*args):
            threads.append(threading.get_ident());return original(reader,*args)
        with patch.object(type(app.controller),'contacts',checked):
            app.show_context(self.second)
            self.settle(lambda:app.browser_reads.future is None and not getattr(app.chat_text,'rendering',False))
            app.return_search_results();self.settle(lambda:not getattr(app.chat_text,'rendering',False))
        self.assertNotIn(ui_thread,threads);self.assertEqual(app.contact_rows,rows)
        self.assertEqual(self.errors,[])
