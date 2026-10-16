"""Native date labels must work on English Windows and the ASCII C locale."""
from datetime import datetime
import locale,unittest
import test_workbench as fixture
from wechat_archive.ui.message_widgets import date_heading

class DateHeadingTests(unittest.TestCase):
    def test_year_month_day_and_language_have_stable_digits(self):
        stamp=datetime(1,2,3)
        self.assertEqual(date_heading(stamp),'0001年02月03日')
        self.assertEqual(date_heading(stamp,'en_US'),'0001-02-03')

class LocaleUITests(unittest.TestCase):
    setUp=fixture.WorkbenchTests.setUp
    def test_ascii_c_locale_can_render_and_relocalize_chinese_date_labels(self):
        original=locale.setlocale(locale.LC_ALL)
        try:
            locale.setlocale(locale.LC_ALL,'C')
            app=self.app;app.chat_text.set_rows(app.message_rows,app.owner_id)
            labels=[w for w in app.chat_text.body.winfo_children() if hasattr(w,'_date_value')]
            self.assertTrue(labels);self.assertEqual(labels[0].cget('text'),'2026年10月10日')
            app.localizer.language='en_US';app.localize_ui();self.assertEqual(labels[0].cget('text'),'2026-10-10')
            app.localizer.language='zh_CN';app.localize_ui();self.assertEqual(labels[0].cget('text'),'2026年10月10日')
            self.assertEqual(self.errors,[])
        finally:locale.setlocale(locale.LC_ALL,original)

if __name__=='__main__':unittest.main(verbosity=2)
