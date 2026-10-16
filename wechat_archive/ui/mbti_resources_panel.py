"""Official reference links and an explicit licensed-bank import in the product UI."""
import tkinter as tk
from tkinter import ttk,filedialog
import webbrowser
from ..ai.mbti_resources import SOURCES,GUIDE,VERIFIED_ON,import_licensed_bank,load_bank
from .common_widgets import ScrollPanel


def open_resources(app):
    window=tk.Toplevel(app.root);window.title('MBTI · 官方资料');window.geometry('650x600');window.transient(app.root)
    scroll=ScrollPanel(window,app.theme);scroll.pack(fill='both',expand=True);body=scroll.body;u=app.theme.u
    ttk.Label(body,text='官方资料与测评',font=app.theme.title).pack(anchor='w')
    ttk.Label(body,text='资料核验：'+VERIFIED_ON+' · 当前未内置官方完整题库',style='Hint.TLabel').pack(anchor='w',pady=(u(8),u(16)))
    ttk.Label(body,text=GUIDE,wraplength=u(560)).pack(anchor='w',pady=(0,u(20)))
    for source in SOURCES:
        ttk.Label(body,text=source['title'],font=app.theme.name,wraplength=u(560)).pack(anchor='w',pady=(u(12),u(5)))
        ttk.Label(body,text=source['note'],style='Hint.TLabel',wraplength=u(560)).pack(anchor='w')
        ttk.Button(body,text='打开官方页面',command=lambda value=source['url']:webbrowser.open(value),style='Quiet.TButton').pack(anchor='w',pady=u(5))
    hint=tk.StringVar(window,value='可导入具有出版方授权、且允许模型处理的题库；内容仅保存在本机，分析时按预算使用。')
    ttk.Label(body,textvariable=hint,style='Hint.TLabel',wraplength=u(560)).pack(anchor='w',pady=u(16))
    def choose():
        filename=filedialog.askopenfilename(parent=window,title='导入已授权 MBTI 题库',filetypes=[('授权题库','*.json')])
        if not filename:return
        try:
            key,count=import_licensed_bank(app.controller.profile_dir,filename)
            settings=app.controller.settings();settings['ai']={**settings.get('ai',{}),'mbti_bank_id':key};app.controller.save_settings(settings)
            hint.set(f'已登记 {count} 题；题库将作为下次分析的参照。')
        except Exception as error:hint.set('题库未导入：'+str(error))
    ttk.Button(body,text='导入已授权题库',command=choose).pack(anchor='w')
    current=app.controller.settings().get('ai',{}).get('mbti_bank_id')
    try:
        bank=load_bank(app.controller.profile_dir,current)
        if bank:hint.set(f"已登记用户授权题库 {len(bank['items'])} 题。")
    except Exception as error:hint.set(str(error))
    window.bind('<Escape>',lambda _:window.destroy());app.theme.apply_tree(window);app.localizer.apply(window,());return window
