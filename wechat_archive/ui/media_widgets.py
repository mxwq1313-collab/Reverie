"""Bounded local previews and explicit save actions for verified attachments."""
from pathlib import Path
import shutil
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from ..importer.rich_importer import ready_media,resource_path,media_root


def present_content(row):
    original=row.get('content') or '['+row.get('msg_type','消息')+']'
    unmapped=original.startswith('[发送者未映射]\n')
    if unmapped and original.split('\n',1)[1].lstrip().startswith('<'):
        return '[发送者未映射]\n'+present_content({**row,'content':original.split('\n',1)[1]})
    if row.get('chat_kind')=='group' and row.get('sender_wxid'):
        from urllib.parse import unquote
        sender=unquote(row['sender_wxid'].split(':',2)[-1])
        if original.startswith(sender+':\n'):original=original[len(sender)+2:]
        elif original.startswith(sender+':\r\n'):original=original[len(sender)+3:]
    from ..message_content import forwarded_text
    forwarded=forwarded_text(original) if row.get('msg_type')=='system' else None
    if forwarded:return forwarded
    if row.get('msg_type','text')=='text' or not original.lstrip().startswith('<'):return original
    labels={'image':'图片 / 表情','audio':'语音','video':'视频','file':'文件','location':'位置','system':'分享或系统消息'}
    label='['+labels.get(row['msg_type'],'消息')+']'
    try:
        from xml.etree import ElementTree
        if len(original)>2*1024*1024:return label
        root=ElementTree.fromstring(original);title=root.findtext('.//title') or '';description=root.findtext('.//descrip') or ''
        return label+(' '+title[:300] if title else '')+('\n'+description[:1000] if description else '')
    except Exception:return label


def save_attachment(app,item,parent=None):
    try:
        source=ready_media(app.controller.require_archive(),item)
        target=filedialog.asksaveasfilename(parent=parent or app.root,title='另存附件',initialfile=source.name,confirmoverwrite=True)
        if target:
            target=Path(target).resolve()
            if target==source.resolve():raise ValueError('请选择归档附件目录之外的位置')
            shutil.copyfile(source,target)
            app.status.set('附件已另存：'+str(target))
    except Exception as error:messagebox.showerror('附件未保存',str(error),parent=parent or app.root)


def preview_image(app,item,related=None):
    from PIL import Image,ImageTk,ImageOps
    path=ready_media(app.controller.require_archive(),item)
    source=Image.open(path)
    if source.width*source.height>40_000_000:source.close();raise ValueError('图片超过预览预算')
    window=tk.Toplevel(app.root);window.title('图片 · '+path.name);window.geometry('800x680');window.transient(app.root)
    controls=ttk.Frame(window,padding=16);controls.pack(side='bottom',fill='x')
    status=tk.StringVar(window)
    ttk.Label(controls,textvariable=status,style='Hint.TLabel',wraplength=620).pack(anchor='w',pady=(0,8))
    row=ttk.Frame(controls);row.pack(fill='x')
    ttk.Button(row,text='另存图片',command=lambda:save_attachment(app,item,window),style='Quiet.TButton').pack(side='left')
    alternatives=[x for x in related or [] if x.get('availability')=='ready' and x.get('id')!=item.get('id')]
    if alternatives:
        menu=tk.Menu(row,tearoff=False)
        for value in alternatives:
            name=Path(value.get('relative_uri') or '').name
            menu.add_command(label='另存 '+name,command=lambda x=value:save_attachment(app,x,window))
        more=ttk.Button(row,text='其他附件 / 原文件',style='Quiet.TButton')
        more.configure(command=lambda:menu.tk_popup(more.winfo_rootx(),more.winfo_rooty()+more.winfo_height()));more.pack(side='left',padx=8)
    label=ttk.Label(window,anchor='center');label.pack(fill='both',expand=True,padx=16,pady=16)
    state={'frame':0,'playing':False,'job':None,'closed':False}
    window.preview_state=state
    total=getattr(source,'n_frames',1)
    def draw():
        if state['closed']:return
        try:
            source.seek(state['frame']);picture=ImageOps.exif_transpose(source).convert('RGBA');picture.thumbnail((max(120,window.winfo_width()-32),max(120,label.winfo_height())))
            photo=ImageTk.PhotoImage(picture,master=window);label.configure(image=photo);label.image=photo
            variant=' · 缩略图' if item.get('variant')=='thumbnail' else ' · 压缩图' if item.get('variant')=='compressed' else ''
            status.set(f'{path.name} · {source.width} × {source.height} · {item["size_bytes"]/1024:.1f} KiB'+variant+(f' · {state["frame"]+1}/{total} 帧' if total>1 else ''))
            if state['playing'] and total>1:
                state['frame']=(state['frame']+1)%total;state['job']=window.after(max(30,min(5000,source.info.get('duration',100))),draw)
        except Exception as error:status.set('预览未完成：'+str(error));state['playing']=False
    def toggle():
        if state['job']:window.after_cancel(state['job']);state['job']=None
        state['playing']=not state['playing'];draw()
    if total>1:ttk.Button(row,text='播放 / 暂停',command=toggle,style='Quiet.TButton').pack(side='right')
    def close(event=None):
        if event is not None and event.widget is not window:return
        if state['closed']:return
        state['closed']=True
        if state['job']:window.after_cancel(state['job'])
        source.close()
        if event is None:window.destroy()
    window.protocol('WM_DELETE_WINDOW',close);window.bind('<Escape>',lambda _:close());window.bind('<Destroy>',close,add='+');state['job']=window.after(100,draw);app.theme.apply_tree(window)
    return window


def attachment_details(app,item,related=None,message=None):
    if item['kind']=='image' and item['availability']=='ready':
        try:return preview_image(app,item,related)
        except Exception as error:detail='当前编码暂不可预览：'+str(error)
    else:detail='原文件未取得' if item['availability']!='ready' else ''
    u=app.theme.u;window=tk.Toplevel(app.root);window.title(app.tr('附件详情'));window.transient(app.root)
    body=ttk.Frame(window,padding=u(24));body.pack(fill='both',expand=True)
    name=Path(item.get('relative_uri') or '').name or {'image':'图片 / 表情','audio':'语音','video':'视频','file':'文件'}.get(item['kind'],'附件')
    title=ttk.Label(body,text=name,font=app.theme.name,wraplength=u(460));title._raw_text=True;title.pack(anchor='w')
    size=item.get('size_bytes');size_text='未知大小' if size is None else f'{size/1024/1024:.1f} MiB' if size>=1024*1024 else f'{size/1024:.1f} KiB'
    variant={'original':'原文件','thumbnail':'缩略图','compressed':'压缩副本'}.get(item.get('variant'),'附件')
    ttk.Label(body,text=size_text+' · '+variant,style='Hint.TLabel').pack(anchor='w',pady=u(12))
    if message:
        description=present_content(message)
        if description:ttk.Label(body,text=description[:1000],wraplength=u(460)).pack(anchor='w',pady=(0,u(12)))
    if detail:ttk.Label(body,text=detail,style='Hint.TLabel',wraplength=u(460)).pack(anchor='w',pady=(0,u(12)))
    if message and '<emoji' in (message.get('content') or '') and item['availability']!='ready' and hasattr(app,'repair_archived_emojis'):
        def repair():window.destroy();app.repair_archived_emojis()
        ttk.Button(body,text='补全归档表情',command=repair,style='Quiet.TButton').pack(anchor='w',pady=(0,u(12)))
    save=ttk.Button(body,text='另存附件',command=lambda:save_attachment(app,item,window));save.pack(anchor='w')
    if item['availability']!='ready':save.configure(state='disabled')
    window.bind('<Escape>',lambda _:window.destroy());app.theme.apply_tree(window);app.localizer.apply(window,());return window


def attachment_widgets(timeline,container,row):
    from ..message_content import forwarded_document
    document=forwarded_document(row.get('content')) if row.get('msg_type')=='system' else None
    if document and document['items']:
        from .forward_message import ForwardMessage
        control=ForwardMessage(timeline,container,row,document)
        timeline.bubbles[row['id']]['forward']=control
        others=[item for item in row.get('attachments',[]) if item.get('kind')!='image']
        if others:attachment_content(timeline,container,{**row,'attachments':others})
        return
    return attachment_content(timeline,container,row)


def attachment_content(timeline,container,row,thumbnail_owner=None):
    if not row.get('attachments'):return
    app=getattr(timeline,'app',None)
    if app is None:return
    u=timeline.theme.u;own=row['sender_id']==getattr(app,'owner_id',None)
    items=row['attachments'];images=[x for x in items if x['kind']=='image' and x['availability']=='ready']
    # Decoded image and source container belong to one image interaction.
    visible=[x for x in items if x['kind']=='image'] if images and row.get('msg_type') in ('image','emoji') else items
    for item in visible:
        frame=tk.Frame(container,background=timeline.theme.palette['CANVAS'],borderwidth=0,highlightthickness=0)
        frame.pack(anchor='e' if own else 'w',pady=(u(6),u(4)))
        name=Path(item.get('relative_uri') or '').name or {'image':'图片 / 表情','audio':'语音','video':'视频','file':'文件'}.get(item['kind'],'附件')
        def preview(value=dict(item)):
            return attachment_details(app,value,items,row)
        if item['kind']=='image' and item['availability']=='ready':
            if item['size_bytes']<=16*1024*1024:
                from .thumbnail_service import ThumbnailService
                if not hasattr(app,'thumbnail_service'):app.thumbnail_service=ThumbnailService(app)
                width=min(u(320),max(u(150),timeline.canvas.winfo_width()-u(48)));height=u(280)
                canvas=tk.Canvas(frame,width=width,height=u(48),background=timeline.theme.palette['CANVAS'],highlightthickness=0,borderwidth=0,cursor='hand2',takefocus=1)
                canvas.create_text(width/2,u(24),text='图片加载中…',fill=timeline.theme.palette['SECONDARY'],font=timeline.theme.small);canvas.pack(anchor='w')
                canvas.bind('<Button-1>',lambda _,action=preview:action());canvas.bind('<Return>',lambda _,action=preview:action())
                canvas.bind('<Map>',lambda _:timeline.refresh_visible(),add='+')
                canvas.on_thumbnail_ready=timeline.thumbnail_ready
                canvas._thumbnail_request=(dict(item),width,height);canvas._thumbnail_requested=False
                timeline.thumbnails.append((thumbnail_owner or container,canvas))
            else:ttk.Button(frame,text='打开图片',command=preview,style='Quiet.TButton').pack(anchor='w')
        else:
            label={'image':'图片 / 表情','audio':'语音','video':'视频','file':'文件'}.get(item['kind'],'附件')
            from .icon_button import icon_image
            icon='file' if item['kind']=='file' else 'play' if item['kind'] in ('audio','video') else 'preview'
            button=ttk.Button(frame,text=label,compound='left',command=preview,style='Quiet.TButton');button._keep_caption=True;button.attachment_item=dict(item);button.pack(anchor='w')
            def refresh(button=button,icon=icon):
                cache=getattr(timeline.theme,'icon_cache',None)
                if cache is None:timeline.theme.icon_cache=cache={}
                key=(icon,timeline.theme.palette['SECONDARY'],u(22))
                if key not in cache:cache[key]=icon_image(app.root,*key)
                button.configure(image=cache[key]);button.image=cache[key]
            button.refresh_icon=refresh;refresh()
        timeline.theme.apply_tree(frame);timeline.theme.wheel_router.attach(frame)
