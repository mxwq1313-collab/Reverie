"""Export-result actions use synthetic outputs and mock the operating-system launch."""
from pathlib import Path
import unittest
from unittest.mock import patch
import test_workbench as workbench_fixture


class ExportResultTests(unittest.TestCase):
    setUp=workbench_fixture.WorkbenchTests.setUp
    wait=workbench_fixture.WorkbenchTests.wait

    def export(self,kind='HTML 和 TXT',scope='当前会话'):
        self.app.export_parent.set(str(self.folder));self.app.export_scope.set(scope);self.app.export_format.set(kind)
        self.app.export_action();self.wait();self.assertIsNotNone(self.app.last_export)
        return Path(self.app.last_export['directory'])

    def test_html_only_and_combined_open_index_and_folder(self):
        for kind in ('仅 HTML','HTML 和 TXT'):
            directory=self.export(kind)
            with patch.object(self.app,'launch_export_path') as launch:
                self.app.open_export_button.invoke();launch.assert_called_with(directory/'index.html')
                self.app.open_export_folder_button.invoke();launch.assert_called_with(directory)
            self.app.copy_export_path_button.invoke();self.assertEqual(self.root.clipboard_get(),str(directory))

    def test_single_txt_opens_file_and_multiple_txt_opens_folder(self):
        directory=self.export('仅 TXT')
        with patch.object(self.app,'launch_export_path') as launch:
            self.app.open_export_button.invoke();self.assertEqual(launch.call_args.args[0].suffix,'.txt')
        directory=self.export('仅 TXT','全部已归档文本')
        self.assertEqual(self.app.open_export_button['text'],'打开 TXT 文件夹')
        with patch.object(self.app,'launch_export_path') as launch:
            self.app.open_export_button.invoke();launch.assert_called_once_with(directory)

    def test_failed_new_export_cannot_open_previous_success_as_new_result(self):
        self.export();self.app.export_parent.set('');self.app.export_action()
        self.assertIsNone(self.app.last_export)
        for button in (self.app.open_export_button,self.app.open_export_folder_button,self.app.copy_export_path_button):
            self.assertIn('disabled',button.state())

    def test_deleted_output_is_reported_and_not_launched(self):
        directory=self.export();(directory/'index.html').unlink()
        with patch.object(self.app,'launch_export_path') as launch:
            self.app.open_export_button.invoke();launch.assert_not_called()
        self.assertIn('未能打开',self.app.status.get())

    def test_launch_failure_is_visible_and_archive_stays_unchanged(self):
        before=self.path.read_bytes();self.export()
        with patch.object(self.app,'launch_export_path',side_effect=OSError('unit launch unavailable')):
            self.app.open_export_button.invoke()
        self.assertIn('unit launch unavailable',self.app.status.get());self.assertEqual(before,self.path.read_bytes())
