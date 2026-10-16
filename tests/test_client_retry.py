"""Recovery checks bind retries to the same source/scope and never use real models."""
import unittest
from unittest.mock import patch
import test_agent as agent_fixture
import test_knowledge_ui as knowledge_fixture


class AgentRetryTests(unittest.TestCase):
    setUp=agent_fixture.AgentPanelTests.setUp
    wait=agent_fixture.AgentPanelTests.wait

    def fail_send(self):
        self.panel.connect();self.wait(lambda:not self.panel.busy)
        self.panel.login();self.wait(lambda:self.panel.authenticated and not self.panel.busy)
        self.panel.fill_prompt('原失败问题')
        with patch.object(self.panel.client,'send',side_effect=OSError('synthetic failure')):
            self.panel.send();self.wait(lambda:not self.panel.busy)
        self.assertIsNotNone(self.panel.retry_request)

    def test_failed_question_can_be_retrieved_and_retried(self):
        self.fail_send();self.panel.edit_question_button.invoke()
        self.assertEqual(self.panel.input.get('1.0','end').strip(),'原失败问题')
        self.panel.retry_button.invoke();self.wait(lambda:not self.panel.busy and not self.panel.active)
        self.assertIn('已查询授权范围',self.panel.transcript.get('1.0','end'))
        self.assertIsNone(self.panel.retry_request)

    def test_source_change_and_scope_change_block_old_retry(self):
        self.fail_send();before=len(self.panel.messages)
        self.controller.manage_message('update',message_id=1,content='new synthetic version')
        self.panel.retry_question();self.assertEqual(len(self.panel.messages),before)
        self.assertIn('不能自动重试',self.panel.state.get())

    def test_partial_reply_remains_when_failed_or_interrupted(self):
        self.fail_send();self.panel._add('Codex','部分已收到回答')
        self.panel._notification('turn/completed',{'turn':{'status':'interrupted'}})
        self.assertIn('部分已收到回答',self.panel.transcript.get('1.0','end'))
        self.assertIsNotNone(self.panel.retry_request)

    def test_reconnect_keeps_failed_question_without_sending_it(self):
        self.fail_send();self.panel.connect();self.wait(lambda:not self.panel.busy)
        self.assertEqual(self.panel.retry_request['question'],'原失败问题')
        self.assertEqual(self.panel.messages,[])


class KnowledgeRetryTests(unittest.TestCase):
    setUp=knowledge_fixture.KnowledgeUITests.setUp
    wait=knowledge_fixture.KnowledgeUITests.wait
    ready=knowledge_fixture.KnowledgeUITests.ready
    knowledge=knowledge_fixture.KnowledgeUITests.knowledge

    def test_missing_index_can_update_and_repeat_original_search(self):
        panel=self.knowledge;self.wait(lambda:panel.context()==panel.last_context)
        panel.input.insert('1.0','单元记录');panel.search();self.wait(lambda:not panel.busy)
        self.assertIsNotNone(panel.failed_request)
        panel.sync_retry_button.invoke();self.wait(lambda:len(panel.hits)==1 and not panel.busy)
        self.assertEqual(panel.input.get('1.0','end').strip(),'单元记录')

    def test_local_model_failure_preserves_question_and_retries(self):
        panel=self.ready();panel.models=['fixture'];panel.chat_model.set('fixture')
        panel.input.insert('1.0','单元记录')
        class Generator:
            model='fixture';last_revision='synthetic'
            def generate(self,*_):raise OSError('本地服务连接失败')
        with patch('wechat_archive.ui.knowledge_panel.OllamaGenerator',return_value=Generator()):
            panel.ask();self.wait(lambda:not panel.busy)
        self.assertIn('检查本地模型服务',panel.state.get());self.assertIsNotNone(panel.failed_request)
        class Recovered:
            model='fixture';last_revision='synthetic'
            def generate(self,*_):return {'claims':[{'text':'来自原文的测试回答','citations':['E1']}]}
        with patch('wechat_archive.ui.knowledge_panel.OllamaGenerator',return_value=Recovered()):
            panel.retry_button.invoke();self.wait(lambda:not panel.busy)
        self.assertIsNotNone(panel.answer);self.assertIsNone(panel.failed_request)

    def test_scope_change_discards_retry_and_no_evidence_is_not_network_error(self):
        panel=self.knowledge;self.wait(lambda:panel.context()==panel.last_context)
        panel.input.insert('1.0','单元记录');panel.search();self.wait(lambda:not panel.busy)
        panel.scope.set('当前身份的所有私聊');self.assertIsNone(panel.failed_request)
        panel.sync();self.wait(lambda:not panel.busy);panel.input.delete('1.0','end');panel.input.insert('1.0','完全不相关字符')
        panel.search();self.wait(lambda:not panel.busy)
        self.assertIsNone(panel.failed_request);self.assertIn('disabled',panel.retry_button.state())
