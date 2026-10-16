"""Presentation-only language switching. Selector values and archive text stay canonical."""
import re
import tkinter as tk
from tkinter import ttk

_TEXT='''Codex 助手|Codex assistant
外观|Appearance
存储|Storage
AI设置|AI settings
语义检索|Semantic search
归档小工具|Archive tools
时光胶囊|Time capsule
随机回忆|Random memory
从旧对话里，遇见一个片刻。|Find a moment in an old conversation.
先在聊天归档中选择一个会话|Choose a conversation in the archive first
打捞一条回忆|Find a memory
筛选条件 ▾|Filters ▾
收起筛选 ▴|Hide filters ▴
开始日期|Start date
结束日期|End date
日期格式 YYYY-MM-DD · 北京时间 · 留空不限|YYYY-MM-DD · Beijing time · Optional
回忆只从当前会话中打捞|Memories come from the current conversation
清空回看|Clear history
工具概览|Tool overview
归档工作区|Archive workspace
当前会话内容|Current conversation
检索范围|Search scope
你想找什么？|What are you looking for?
证据与原文|Evidence and originals
回忆探索|Memory explorer
时光胶囊 · 日期|Time capsule date
回到那一天|Visit that day
随机打捞一条回忆|A random memory
回到原文|Open original
复制这条回忆|Copy this memory
文字小工坊|Text workshop
取当前选中文字|Use selected text
清理行尾空格|Trim line endings
复制整理结果|Copy edited text
消息详情|Message details
查看归档消息|View archived message
消息内容|Message content
原始内容（只读）|Original payload (read-only)
时间 · 北京时间|Time in Beijing
保存文本|Save text
保存联系人|Save contact
联系人资料|Contact details
基本信息|Basic information
来源标识|Source identifier
数据文件夹|Data folder
搜索联系人…|Search contacts…
刷新联系人|Refresh contacts
选择强度|Choose power
选择模型|Choose model
归档文件|Archive file
搜索联系人或群聊…|Search contacts or groups…
搜索帮助内容…|Search help…
搜索会话…|Search conversations…
搜索历史对话…|Search past conversations…
已读取会话概况|Conversation overview loaded
会话概况读取未完成|Conversation overview could not be loaded
已读取参与者信息|Participant information loaded
参与者信息读取未完成|Participant information could not be loaded
已完成联系人查询|Contact search complete
联系人查询未完成|Contact search did not complete
已完成聊天记录查询|Chat history search complete
聊天记录查询未完成|Chat history search did not complete
已完成原始消息读取|Original message loaded
原始消息读取未完成|Original message could not be loaded
已完成资料读取|Information loaded
资料读取未完成|Information could not be loaded
练气|Qi Refining
筑基|Foundation Building
金丹|Golden Core
元婴|Nascent Soul
化神|Spirit Transformation
渡劫|Tribulation Crossing
刷新模型列表|Refresh models
私聊消息|Private messages
群聊|Group chat
统计|Statistics
聊天足迹|Conversation footprint
刷新统计|Refresh statistics
当前身份|Current identity
整个归档|Entire archive
附件详情|Attachment details
官方资料与测评|Official resources and assessment
导入已授权题库|Import licensed bank
打开官方页面|Open official page
留下的消息|Messages
相遇的会话|Conversations
活跃的日子|Active days
写下的文字|Text characters
一天中的聊天节奏|Chat rhythm by hour
一周里的聊天节奏|Chat rhythm by weekday
话题里的声音|Voices in your conversations
内容与收藏|Content and collection
聊天日历 · 最新消息所在的 13 周|Activity calendar - latest 13 weeks
搜索聊天记录…|Search messages…
MBTI 性格分析|MBTI personality analysis
从聊天片段，了解表达与沟通倾向|Explore communication patterns from your chats
分析对象|Person to analyze
由 Codex 分析|Analyze with Codex
连接与登录|Connect and sign in
结合原文引用分析四个维度，给出倾向、反向证据和待验证问题。证据不足的维度会保留为未定。|Explore four dimensions with original references, counterevidence and follow-up questions. Insufficient evidence leaves a dimension undecided.
所选范围的相关文字会发送给 OpenAI；结果保存在本机 Codex 历史中。|Relevant text from the selected scope goes to OpenAI. Results stay in local Codex history.
请先打开归档并选择会话。|Open an archive and select a conversation first.
请等待当前操作完成。|Wait for the current operation to finish.
先在设置中连接 Codex 并登录 ChatGPT。|Connect Codex and sign in to ChatGPT in Settings first.
使用当前 Codex 模型与努力程度；点击后开启一段独立分析。|Uses the current model and effort in a new analysis conversation.
归档或会话已变化，请关闭后重新打开 MBTI。|The archive or conversation changed. Reopen MBTI to choose a fresh scope.
请重新选择分析对象。|Choose the person again.
另存图片|Save image
其他附件 / 原文件|Other attachments / original files
打开图片|Open image
播放 / 暂停|Play / pause
导入副本文件|Import copy
身份未映射|Unmapped sender
本地模型与语义检索|Local models and semantic search
全部已归档内容|All archived content
本机聊天归档|Local chat archive
私聊消息 · UTC+08:00|Private messages · UTC+08:00
私聊消息 · 北京时间 UTC+08:00|Private messages · UTC+08:00
导出所选范围内全部消息及可用附件，不受当前加载页或搜索筛选影响。|Export all messages and available attachments in the scope, including unloaded pages.
搜索历史|Search history
搜索会话|Search conversations
更新时间（北京时间）|Updated (UTC+08)
历史对话|Conversation history
选择归档与会话|Choose an archive and chat
选择读取范围|Choose reading scope
正在回复…|Replying…
千丝万绪…|Weaving thoughts…
从微信官方CDN补全缺失表情（不发送聊天正文）|Fill missing emoji from official WeChat CDN (no chat text sent)
一键读取（含图片/表情）|Read with images and emoji
模型与努力程度|Model and effort
模型|Model
应用范围|Apply scope
取消|Cancel
消息数|Messages
本人占比|Your share
查看|View
继续对话|Continue conversation
打开历史保存目录|Open history folder
另存附件|Save attachment
参数用于下一次发送；当前回答保持不变。|Applies to the next question; the current answer continues.
群聊 · 北京时间 UTC+08:00|Group chat · UTC+08:00
努力程度|Effort
下一次发送起生效；服务端按账号和模型处理。|Applies to the next question; account and model rules apply.
展开 Codex|Open Codex
收起 Codex|Hide Codex
选择归档范围|Choose archive scope
读取范围|Reading scope
快速模式|Fast mode
刷新全部模型|Refresh all models
从归档开始提问|Ask about this archive
开始提问|Ask a question
自动（模型默认）|Default effort
关闭推理|None
最少|Minimal
轻量|Low
标准|Medium
深入|High
更深入|Extra high
最大|Max
最高|Ultra
完成|Done
选择账号|Select account
选择会话|Select chat
归档|Archive
选择来源|Choose source
预览并导入|Preview and import
文件 / 目录|File / folder
加载联系人后选择会话|Load contacts to choose a chat
检测已登录的电脑微信账号|Detect signed-in desktop WeChat accounts
未选择归档|No archive selected
基础归档 · 单次≤100000条 / 64 MiB|Basic archive · up to 100,000 rows / 64 MiB
扩展归档 · 全量分批读取|Extended archive · full batch reading
正在打开归档…|Opening archive…
在设置中连接 AI|Connect AI in Settings
帮助|Help
使用帮助|Help
搜索帮助|Search help
全部章节|All chapters
暖砂|Warm sand
雾蓝|Mist blue
松绿|Pine green
紫雾|Soft violet
请选择支持的界面主题。|Choose a supported theme.
聊天归档|Chat archive
聊天|Chats
添加记录|Add records
添加|Add
导出归档|Export archive
导出|Export
工具与设置|Tools
工具|Tools
设置|Settings
用户设置|Settings
外观与阅读|Appearance
文件与存储|Files & storage
AI 连接与模型|AI connection
新建归档|New archive
打开归档|Open archive
恢复最近归档|Restore recent archive
打开数据文件夹|Open storage folder
收起 AI|Hide AI
AI Copilot|AI assistant
AI 助手|AI assistant
收起|Hide
会话|Chats
查看身份|Identity
查找联系人|Find contact
刷新|Refresh
导出会话|Export chat
询问 AI|Ask AI
搜索|Search
日期|Dates
从|From
到|To
清除筛选|Clear filters
加载更多|Load more
← 返回搜索结果|← Back to results
当前会话|This chat
全部会话|All chats
当前身份的所有私聊|All private chats
全部已归档文本|All archived text
当前查看身份|Current identity
全部已归档私聊|All archived private chats
查看上下文|Open context
复制选中文字|Copy selection
复制这条原文|Copy original message
添加聊天记录|Add chat records
从电脑微信读取|Read from WeChat
导入已有文件|Import files
选择账号|Account
选择目录|Choose folder
选择文件|Choose file
选择位置|Choose location
检测账号|Detect accounts
连接并加载联系人|Load contacts
搜索联系人|Find contact
联系人|Contact
微信标识|WeChat ID
读取范围|Range
最近 50 条|Latest 50
最近 500 条|Latest 500
最近 5000 条|Latest 5,000
最近 5 万条|Latest 50,000
最近 10 万条|Latest 100,000
最近 100 万条|Latest 1,000,000
补全已归档表情|Recover archived stickers
补全归档表情|Recover archive stickers
全部电脑本地记录|All local history
读取并归档|Read and archive
创建升级副本|Create extended copy
高级设置：微信数据目录|WeChat source folder
可选数据目录|Optional source folder
查看聊天归档|View archive
来源|Source
预览检查|Preview
开始导入|Import
高级设置：格式与校验|Format and validation
数据类型|Format
自动识别|Detect automatically
标准 JSON|Standard JSON
CSV 聊天文件|Chat CSV
Android 明文快照|Plaintext Android snapshot
Windows 微信结构化导出|Structured Windows export
封存私聊历史快照（逐批提交）|Frozen history snapshot
CSV 账号标签|CSV account namespace
CSV 默认时区|CSV time zone
严格模式：出现失败记录时整批拒绝|Strict mode: reject the batch if any record fails
新增消息|Added messages
重复跳过|Duplicates skipped
失败记录|Failed records
未支持但已保留|Unsupported records retained
预览消息|Preview messages
尚未执行|Not started
操作完成|Completed
导出聊天归档|Export chat archive
导出范围|Scope
文件格式|Format
HTML 和 TXT|HTML and TXT
仅 HTML|HTML only
仅 TXT|TXT only
保存位置|Destination
显示时区|Display time zone
导出可读文件|Export files
打开阅读首页|Open reading page
打开文件夹|Open folder
复制路径|Copy path
数据管理|Archive management
归档管理|Archive management
导入与分析报告|Import reports
原文检索|Original text search
本地知识问答|Archive search
刷新报告|Refresh reports
报告文件|Report file
修改时间|Modified
新增联系人|Add contact
编辑联系人|Edit contact
删除联系人|Delete contact
刷新列表|Refresh list
新增文本消息|Add message
编辑选中消息|Edit message
删除选中消息|Delete message
加载当前会话|Load current chat
昵称|Name
来源标识|Source ID
时间|Time
发送者|Sender
接收者|Recipient
内容|Content
连接 Codex|Connect Codex
登录 ChatGPT|Sign in to ChatGPT
新对话|New chat
检查登录|Check sign-in
检查登录状态|Check sign-in
取消登录|Cancel sign-in
退出登录|Sign out
运行组件|Runtime component
选择 codex.exe|Choose codex.exe
读取范围|Read scope
模型|Model
刷新模型|Refresh models
自动（账号默认模型）|Automatic (account default)
复制回答|Copy
保存对话|Save
重试问题|Retry
取回编辑|Edit question
待办|Tasks
总结|Summary
查原文|Find text
发送|Send
停止回答|Stop
回到最新|Jump to latest
前往设置|Open settings
打开 AI 设置|AI settings
Ctrl+Enter 发送|Ctrl+Enter to send
设置未完成|Setup required
云端 AI|Cloud AI
本地模型|Local models
本机 Ollama|Local Ollama
读取已有模型|Read installed models
向量模型|Embedding model
回答模型|Chat model
离线字面检索（无需模型）|Offline text search (no model)
Ollama 语义检索（已有模型）|Ollama semantic search
更新索引|Update index
重新计算全部索引|Rebuild index
取消|Cancel
检索原文|Search original text
本地模型回答|Ask local model
复制回答与证据|Copy answer and sources
保存回答与证据|Save answer and sources
重试失败问题|Retry question
更新索引并重试|Update index and retry
消息 ID|Message ID
UTC 时间|UTC time
检索相似度|Similarity
界面主题|Theme
浅色|Light
深色|Dark
跟随系统|Follow system
界面字体|Font
系统推荐|Recommended font
正文字号|Text size
界面语言|Language
滚动速度|Scroll speed
使用紧凑导航|Compact navigation
启动时恢复上次归档|Restore the last archive at startup
减少动画|Reduce motion
启动时显示 AI 侧栏|Show the AI sidebar at startup
应用设置|Apply settings
已应用并保存设置。|Settings applied and saved.
默认存储目录|Storage folder
默认导出目录|Export folder
默认导出格式|Export format
聊天正文字号|Text size
应用阅读设置|Apply settings
保存|Save
确认删除|Confirm deletion
未保存|Not saved
未删除|Not deleted
操作未完成|Operation failed
无法打开归档|Cannot open archive
未创建归档|Archive not created
就绪|Ready
归档已就绪。|Archive ready.
未打开归档|No archive open
尚未打开归档|No archive open
尚未选择|Not selected
先选择已归档身份和会话|Select an archived identity and chat
请先在聊天归档选择身份和会话。|Select an identity and chat in the archive first.
请先打开归档|Open an archive first
打开自己的聊天归档|Open your chat archive
打开已有归档|Open archive
归档还没有聊天记录|The archive is empty
当前身份暂无会话|No chats for this identity
没有匹配的联系人|No matching contacts
没有匹配的消息|No matching messages
清除联系人搜索|Clear contact search
重试加载|Retry loading
加载未完成|Loading failed
你|You
系统|System
Codex · 回答|Codex · Answer
私聊文本 · UTC+08:00|Private text · UTC+08:00
私聊文本 · 北京时间 UTC+08:00|Private text · UTC+08:00
私聊文本归档|Private text archive
按最近消息排列|Sorted by latest message
↑↓选择 · Enter打开|↑↓ select · Enter open
Ctrl+F搜索 · Alt+←返回|Ctrl+F search · Alt+← back
提问及相关归档片段会发送给 OpenAI|Questions and relevant archive excerpts are sent to OpenAI
连接、登录和模型在设置中调整。|Configure connection, sign-in and models in Settings.
在这里提问、阅读回答和回查消息。|Ask questions, read answers and open source messages here.
新归档、报告与索引使用此目录；已有文件保留原位。|New archives, reports and indexes use this folder. Existing files stay in place.
为空时使用默认存储目录下的 exports。|Leave empty to use exports under the storage folder.
请选择已安装字体；设置立即生效。|Choose an installed font. Changes apply immediately.
只显示已能实际使用的工具。|Only available tools are shown.
只编辑当前归档副本；有关联消息的联系人不能删除。|Edit the current archive only. Contacts with messages cannot be deleted.
每次创建新的导出目录；已有文件不会被覆盖。HTML 便于阅读，TXT 便于保存。|Each export creates a new folder. HTML is for reading; TXT is for saving.
导出所选范围内全部已入库文本，不限于当前屏幕或加载页，也不受搜索筛选影响。|Export all archived text in the selected scope, including unloaded messages.
选择一个来源；点击检测、预览或导入后才开始处理。|Choose a source, then detect, preview or import it.
保持电脑微信已登录；检测不会自动导入聊天。|Keep WeChat signed in. Detection does not import messages.
逻辑像素 · 根据系统 DPI 缩放|Logical pixels · scaled with system DPI
请选择本机存储目录。|Choose a local storage folder.
存储目录必须使用本机绝对路径。|Use an absolute local folder path.
所选存储目录不可写。|The selected folder is not writable.
请选择浅色、深色或跟随系统主题。|Choose Light, Dark or Follow system.
请选择简体中文或 English。|Choose Simplified Chinese or English.
请选择有效字体。|Choose a valid font.
字号为12–24逻辑像素。|Text size must be 12–24 logical pixels.
滚动速度为24–120逻辑像素。|Scroll speed must be 24–120 logical pixels.
设置修改完成后点击“应用设置”。|Click Apply settings after making changes.
设置已保存，当前归档位置保留。|Settings saved. The current archive stays in place.
本地模型未配置时仅显示可用的离线原文检索。|Offline search is available while local models are unconfigured.
离线字面检索可直接使用；先更新索引。|Offline text search is available. Update the index first.
只读取已安装模型，不自动下载。请选择本地模型并检查服务配置；本地模型回答会把当前检索证据交给该服务。|Use installed local models only. Answers send the retrieved evidence to the local service.
只覆盖所选范围已归档私聊文本。相似度不是置信度；模型推断需要核对原文。索引和保存文件包含聊天片段。|Only archived private text in the selected scope is used. Check model inferences against sources. Indexes and saved answers contain excerpts.
YYYY-MM-DD · 包含起止日期（北京时间）|YYYY-MM-DD · inclusive dates (UTC+08)
打开已有归档，或添加聊天记录后开始浏览。|Open an archive or add records to start reading.
添加已有文件，或从电脑微信读取所选私聊。|Import files or read selected private chats from WeChat.
可以切换查看身份，或为这个归档添加聊天记录。|Switch identity or add records to this archive.
清除联系人搜索，或换一个关键词。|Clear the contact search or try another keyword.
调整关键词或日期；清除筛选可恢复当前会话。|Adjust the keyword or dates. Clear filters to restore this chat.
检查归档是否可访问，再重试。|Check that the archive is accessible, then retry.
先到设置连接 Codex 并登录 ChatGPT，再选择归档会话。|Connect Codex and sign in to ChatGPT in Settings, then select a chat.
范围已就绪。Ctrl+Enter发送；Enter换行。快捷问题只填入，不自动发送。|Scope ready. Ctrl+Enter sends; Enter adds a new line. Quick prompts only fill the input.
连接已建立，尚未登录；请完成官方授权或检查登录状态。|Connected but not signed in. Complete sign-in or check the account in Settings.
请在聊天归档选择身份和会话，再回到这里提问。|Select an identity and chat before asking a question.
先在聊天归档选择身份和会话|Select an identity and chat first
未连接 · 独立登录状态|Disconnected · separate sign-in
已有本地模型：服务地址与模型选择|Local service and installed models
1 选择范围   →   2 更新索引   →   3 检索原文或本地问答|1 Scope   →   2 Index   →   3 Search or ask
'''
EN=dict(line.split('|',1) for line in _TEXT.splitlines() if '|' in line)


class Localizer:
    def __init__(self,root,language='zh_CN'):
        self.root=root;self.language=language;self.widgets={};self.variables={};self.combos={};self.engaged=language=='en_US'

    def tr(self,text):
        if self.language=='zh_CN':return text
        if text in EN:return EN[text]
        if '\n' in text:return '\n'.join(self.tr(line) for line in text.split('\n'))
        for marker in ('▸ ','▾ '):
            if text.startswith(marker):return marker+self.tr(text[len(marker):])
        match=re.fullmatch(r'(\d+) 条已归档 · 本人 (\d+)/(\d+) · ([\d.]+)%',text)
        if match:return f'{match[1]} archived · You {match[2]}/{match[3]} · {match[4]}%'
        match=re.fullmatch(r'全部匹配 (\d+) 条 · 当前加载 (\d+) 条',text)
        if match:return f'Matched {match[1]} · Loaded {match[2]}'
        match=re.fullmatch(r'(\d+) 条已归档',text)
        if match:return f'{match[1]} archived'
        match=re.fullmatch(r'(\d+) 个',text)
        if match:return f'{match[1]}'
        for chinese,english in (('分析归档：','Archive: '),('当前会话：','Chat: '),('范围：','Scope: '),('版本 ','Version '),('当前归档：','Archive: '),('数据与报告目录：','Storage: '),('设置未保存：','Settings not saved: '),('未完成：','Failed: '),('已登录 · ','Signed in · '),('未登录 · ','Signed out · '),('查看身份：','Identity: '),('当前匹配范围：','Scope: ')):
            if text.startswith(chinese):return english+text[len(chinese):]
        return text

    def text(self,widget,value):
        translated=self.tr(value);self.widgets[widget]=(value,translated)
        if str(widget.cget('text'))!=translated:widget.configure(text=translated)

    def variable(self,widget,name):
        if widget in self.variables:return
        original=tk.StringVar(self.root,name=name);display=tk.StringVar(self.root,value=self.tr(original.get()))
        def update(*_):
            value=self.tr(original.get())
            if display.get()!=value:display.set(value)
        callback=original.trace_add('write',update)
        widget.configure(textvariable=display);self.variables[widget]=(original,display,callback)

    def combo(self,widget):
        if widget in self.combos:
            record=self.combos[widget];current=tuple(widget.cget('values'));expected=tuple(self.tr(value) for value in record['values'])
            if current!=expected:
                reverse={self.tr(value):value for value in record['values']};record['values']=tuple(reverse.get(value,value) for value in current)
                record['busy']=True
                try:widget.configure(values=tuple(self.tr(value) for value in record['values']))
                finally:record['busy']=False
            return
        values=tuple(widget.cget('values'))
        if not values or not any(value in EN for value in values):return
        # Identity/contact and model identifiers are data, not UI strings.
        if getattr(widget,'_raw_values',False):return
        name=str(widget.cget('textvariable'))
        if not name:return
        original=tk.StringVar(self.root,name=name);display=tk.StringVar(self.root);record={'original':original,'display':display,'values':values,'busy':False}
        self.combos[widget]=record
        def canonical(*_):
            if record['busy']:return
            record['busy']=True
            try:display.set(self.tr(original.get()))
            finally:record['busy']=False
        def selected(*_):
            if record['busy']:return
            mapping={self.tr(value):value for value in record['values']}
            original.set(mapping.get(display.get(),display.get()))
        original.trace_add('write',canonical);display.trace_add('write',selected)
        widget.configure(textvariable=display,values=tuple(self.tr(value) for value in values));canonical()

    def apply(self,parent,raw_nodes=()):
        if not self.engaged:return
        if parent in raw_nodes or getattr(parent,'_raw_text',False):return
        try:
            kind=parent.winfo_class()
            if kind=='TCombobox':self.combo(parent)
            if kind in ('Label','Button','TLabel','TButton','TCheckbutton'):
                variable=str(parent.cget('textvariable')) if 'textvariable' in parent.keys() else ''
                if variable:self.variable(parent,variable)
                elif 'text' in parent.keys():
                    current=str(parent.cget('text'));previous=self.widgets.get(parent)
                    canonical=previous[0] if previous and current==previous[1] else current
                    self.text(parent,canonical)
            if kind=='TNotebook':
                for tab in parent.tabs():
                    key=(parent,tab);current=parent.tab(tab,'text');previous=self.widgets.get(key)
                    canonical=previous[0] if previous and current==previous[1] else current
                    parent.tab(tab,text=self.tr(canonical));self.widgets[key]=(canonical,self.tr(canonical))
            if kind=='Treeview':
                for column in parent.cget('columns'):
                    key=(parent,column);current=parent.heading(column,'text');previous=self.widgets.get(key)
                    canonical=previous[0] if previous and current==previous[1] else current
                    parent.heading(column,text=self.tr(canonical));self.widgets[key]=(canonical,self.tr(canonical))
            if kind=='Menu' and parent.index('end') is not None:
                for index in range(parent.index('end')+1):
                    if parent.type(index)=='separator':continue
                    key=(parent,index);current=parent.entrycget(index,'label');previous=self.widgets.get(key)
                    canonical=previous[0] if previous and current==previous[1] else current
                    parent.entryconfigure(index,label=self.tr(canonical));self.widgets[key]=(canonical,self.tr(canonical))
        except tk.TclError:pass
        for child in parent.winfo_children():self.apply(child,raw_nodes)

    def switch(self,language,root,raw_nodes=()):
        self.language=language
        if language=='en_US':self.engaged=True
        for widget,(original,display,_) in list(self.variables.items()):
            if widget.winfo_exists():display.set(self.tr(original.get()))
        for widget,record in self.combos.items():
            if not widget.winfo_exists():continue
            record['busy']=True
            try:
                widget.configure(values=tuple(self.tr(value) for value in record['values']))
                record['display'].set(self.tr(record['original'].get()))
            finally:record['busy']=False
        self.apply(root,raw_nodes)
