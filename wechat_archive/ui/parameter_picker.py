"""Small composer chip opens a frameless model and supported-power card."""
import tkinter as tk
from tkinter import ttk
from .model_controls import AUTO_MODEL
from .power_popover import PowerPopover
from .icon_button import icon_image


def build_parameters(panel,page):
    app=panel.app;u=app.theme.u
    bar=ttk.Frame(page);bar.grid(row=5,column=0,sticky='ew',pady=(u(4),0));bar.columnconfigure(0,weight=1)
    popup=tk.Toplevel(panel.root);popup.withdraw();popup.title('模型与努力程度');popup.transient(panel.root);panel.parameters_popup=popup
    popup.protocol('WM_DELETE_WINDOW',popup.withdraw)
    # Canonical selectors remain available to the existing model and settings code.
    form=ttk.Frame(popup)
    panel.model_box=ttk.Combobox(form,textvariable=panel.model,values=(AUTO_MODEL,*panel.model_ids),state='readonly')
    panel.init_inference()
    panel.effort_box=ttk.Combobox(form,textvariable=panel.effort,values=tuple(panel.effort_ids),state='readonly')
    panel.models_button=app.icon(form,'refresh','刷新模型列表',panel.refresh_models,'Copilot.TButton')
    panel.parameter_caption=tk.StringVar(panel.root,value=app.tr('选择模型'))
    panel.parameters_button=ttk.Button(bar,textvariable=panel.parameter_caption,style='PowerChip.TButton',width=-1,compound='right')
    panel.parameters_button.grid(row=0,column=0,sticky='w');panel.parameters_button._raw_text=True
    panel.power_popover=PowerPopover(panel,popup);panel.parameters_button.configure(command=panel.power_popover.show)
    def caption(*_):
        t=app.theme;name=panel.selected_model_name()
        value=t.elide(name,max(t.u(72),bar.winfo_width()-t.u(48)),True) if name else app.tr('选择模型')
        if value!=panel.parameter_caption.get():panel.parameter_caption.set(value)
        key=(t.generation,t.u(14),t.palette['SECONDARY'])
        if getattr(panel.parameters_button,'arrow_key',None)!=key:
            panel.parameters_button.arrow_key=key
            panel.parameters_button.arrow_image=icon_image(panel.root,'chevron',key[2],key[1])
            panel.parameters_button.configure(image=panel.parameters_button.arrow_image)
    panel.refresh_parameter_caption=caption
    panel.model.trace_add('write',caption);panel.effort.trace_add('write',caption);bar.bind('<Configure>',caption,add='+');caption()
