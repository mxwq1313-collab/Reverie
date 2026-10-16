"""Readable Markdown in native Text; hidden markers preserve source and stream indices."""
import re
import webbrowser


def configure(widget, theme):
    style_key=(theme.generation,theme.body)
    if getattr(widget,'_markdown_style_key',None)==style_key:return
    widget._markdown_style_key=style_key
    u=theme.u;p=theme.palette;base=tuple(theme.body);bold=base+('bold',)
    styles={
        'md_marker':dict(elide=True),
        'md_reference_marker':dict(elide=True),
        'md_blank':dict(font=(theme.family,-1),spacing1=0,spacing2=0,spacing3=u(6)),
        'md_bold':dict(font=bold),
        'md_italic':dict(font=base+('italic',)),
        'md_h1':dict(font=(theme.family,-u(theme.text_size+3),'bold'),spacing1=u(15),spacing3=u(8)),
        'md_h2':dict(font=(theme.family,-u(theme.text_size+1),'bold'),spacing1=u(12),spacing3=u(7)),
        'md_h3':dict(font=bold,spacing1=u(10),spacing3=u(6)),
        'md_list':dict(lmargin1=u(16),lmargin2=u(30),spacing1=u(3),spacing3=u(5)),
        'md_quote':dict(foreground=p['SECONDARY'],lmargin1=u(20),lmargin2=u(20),spacing1=u(7),spacing3=u(7)),
        'md_code':dict(font=('Consolas',-u(max(12,theme.text_size-1))),background=p['CANVAS']),
        'md_codeblock':dict(font=('Consolas',-u(max(12,theme.text_size-1))),background=p['CANVAS'],lmargin1=u(18),lmargin2=u(18),spacing1=u(4),spacing3=u(4)),
        'md_rule':dict(foreground=p['LINE'],spacing1=u(8),spacing3=u(8)),
    }
    for tag,options in styles.items():widget.tag_configure(tag,**options)


def decorate(widget, text, theme):
    configure(widget,theme)
    for tag in widget.tag_names():
        if tag.startswith('md_'):widget.tag_remove(tag,'1.0','end')
    def at(offset):
        # Text's +Nc modifier counts Unicode code points, including non-BMP.
        return '1.0+'+str(offset)+'c'
    def tag(name,start,end):widget.tag_add(name,at(start),at(end))
    code=[]
    for match in re.finditer(r'(?m)^\s*```[^\n]*\n[\s\S]*?(?:^\s*```\s*$|\Z)',text):
        code.append(match.span());tag('md_codeblock',*match.span())
        first=text.find('\n',match.start(),match.end())
        tag('md_marker',match.start(),first+1)
        closing=re.search(r'(?m)^\s*```\s*$',text[first+1:match.end()])
        if closing:tag('md_marker',first+1+closing.start(),first+1+closing.end())
    def outside(start):return not any(a<=start<b for a,b in code)
    for pattern,style,size in ((r'\*\*([^\n]+?)\*\*','md_bold',2),(r'__([^\n]+?)__','md_bold',2),(r'(?<!\*)\*([^*\n]+?)\*(?!\*)','md_italic',1),(r'`([^`\n]+)`','md_code',1)):
        for m in re.finditer(pattern,text):
            if not outside(m.start()):continue
            tag(style,m.start()+size,m.end()-size);tag('md_marker',m.start(),m.start()+size);tag('md_marker',m.end()-size,m.end())
    offset=0
    for line in text.splitlines(keepends=True):
        if outside(offset):
            if not line.strip():tag('md_blank',offset,offset+len(line))
            heading=re.match(r'^(#{1,6})\s+',line)
            if heading:
                tag('md_marker',offset,offset+heading.end());tag('md_h'+str(min(3,len(heading[1]))),offset,offset+len(line))
            elif re.match(r'^\s*[-*+]\s+\S',line) or re.match(r'^\s*\d+[.)]\s',line):tag('md_list',offset,offset+len(line))
            elif re.match(r'^\s*[-*]\s*$',line):tag('md_marker',offset,offset+len(line))
            elif re.match(r'^\s*>\s?',line):
                m=re.match(r'^\s*>\s?',line);tag('md_marker',offset,offset+m.end());tag('md_quote',offset,offset+len(line))
            elif re.match(r'^\s*(?:-{3,}|\*{3,}|_{3,})\s*$',line):tag('md_rule',offset,offset+len(line))
        offset+=len(line)
    for reference in re.finditer(r'\[消息 #(\d+)\]',text):
        if outside(reference.start()):
            tag('md_reference_marker',reference.start(),reference.start()+4)
            tag('md_reference_marker',reference.end()-1,reference.end())
    for number,m in enumerate(re.finditer(r'\[([^\]\n]+)\]\((https?://[^\s)]+)\)',text)):
        if not outside(m.start()):continue
        name='md_link_'+str(number)
        tag(name,m.start()+1,m.start()+1+len(m[1]));tag('md_marker',m.start(),m.start()+1);tag('md_marker',m.start()+1+len(m[1]),m.end())
        widget.tag_configure(name,foreground=theme.palette['ACCENT'],underline=True)
        widget.tag_bind(name,'<Button-1>',lambda _,url=m[2]:webbrowser.open(url))
        widget.tag_bind(name,'<Enter>',lambda _:widget.configure(cursor='hand2'))
        widget.tag_bind(name,'<Leave>',lambda _:widget.configure(cursor='xterm'))
    for name in ('md_h1','md_h2','md_h3','md_bold','md_code','md_codeblock','md_blank','md_marker','md_reference_marker','sel'):widget.tag_raise(name)
