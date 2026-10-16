"""Live per-question model, reasoning and speed controls backed by the server catalog."""
import tkinter as tk
from tkinter import ttk

AUTO_MODEL='自动（账号默认模型）'
PREFERRED_MODEL='gpt-6.1-sol'
EFFORT_LABELS={'':'自动（模型默认）','none':'关闭推理','minimal':'最少','low':'练气','medium':'筑基','high':'金丹','xhigh':'元婴','max':'化神','ultra':'渡劫'}


def clean_catalog(rows):
    result=[];seen=set()
    for row in rows[:1000] if isinstance(rows,list) else ():
        if not isinstance(row,dict):continue
        name=row.get('model') or row.get('id')
        if not isinstance(name,str) or not name or len(name)>128 or name in seen:continue
        seen.add(name);efforts=[]
        raw_efforts=row.get('supportedReasoningEfforts',[])
        for item in raw_efforts[:16] if isinstance(raw_efforts,list) else ():
            value=item.get('reasoningEffort') if isinstance(item,dict) else None
            if isinstance(value,str) and value in EFFORT_LABELS and value:efforts.append({'reasoningEffort':value})
        result.append({'id':name,'model':name,'displayName':str(row.get('displayName') or name)[:128],
            'hidden':bool(row.get('hidden')),'isDefault':bool(row.get('isDefault')),
            'defaultReasoningEffort':row.get('defaultReasoningEffort') if isinstance(row.get('defaultReasoningEffort'),str) and row.get('defaultReasoningEffort') in EFFORT_LABELS else None,
            'supportedReasoningEfforts':efforts})
    return result


class ModelControls:
    def init_inference(self):
        saved=self.app.controller.settings().get('ai',{});saved=saved if isinstance(saved,dict) else {}
        self.model_catalog=clean_catalog(saved.get('model_catalog',[]));self.config_job=None;self.catalog_ready=False
        self.preferred_model_applied=saved.get('preferred_model_applied') is True
        raw=saved.get('effort') if isinstance(saved.get('effort'),str) and saved.get('effort') in EFFORT_LABELS else ''
        self.effort=tk.StringVar(self.root,value=EFFORT_LABELS[raw]);self.fast_mode=tk.BooleanVar(self.root,value=saved.get('fast_mode') is True)
        self.effort_ids={EFFORT_LABELS['']:None}
        if self.model_catalog:self.set_catalog(self.model_catalog);self.catalog_ready=False
        self.model.trace_add('write',lambda *_:self.model_changed())
        self.scope.trace_add('write',lambda *_:self.scope_changed())
        self.effort.trace_add('write',lambda *_:self.queue_configuration())
        self.fast_mode.trace_add('write',lambda *_:self.speed_changed())

    def set_catalog(self,models):
        self.model_catalog=clean_catalog(models)
        self.model_ids={f"{item['displayName']} · {item['model']}":item['model'] for item in self.model_catalog}
        current=self.model.get();self.model_box.configure(values=(AUTO_MODEL,*self.model_ids))
        if not self.preferred_model_applied and PREFERRED_MODEL in self.model_ids.values():
            self.model.set(next(label for label,value in self.model_ids.items() if value==PREFERRED_MODEL));self.preferred_model_applied=True;current=self.model.get()
        if current not in (AUTO_MODEL,*self.model_ids):self.model.set(AUTO_MODEL)
        self.catalog_ready=True
        if hasattr(self,'effort'):self.model_changed()

    def selected_model(self):
        value=self.model_ids.get(self.model.get())
        if value:return value
        return next((item['model'] for item in self.model_catalog if item['isDefault']),None)

    def selected_model_name(self):
        value=self.selected_model()
        return next((item['displayName'] for item in self.model_catalog if item['model']==value),None)

    def model_changed(self):
        row=next((item for item in self.model_catalog if item['model']==self.selected_model()),{})
        self.effort_ids={EFFORT_LABELS['']:None,**{EFFORT_LABELS[x['reasoningEffort']]:x['reasoningEffort'] for x in row.get('supportedReasoningEfforts',[])}}
        if self.effort.get() not in self.effort_ids:self.effort.set(EFFORT_LABELS[''])
        if hasattr(self,'effort_box'):self.effort_box.configure(values=tuple(self.effort_ids))
        self.queue_configuration()
        if hasattr(self,'localize_controls'):self.localize_controls()
        if hasattr(self,'power_popover'):self.power_popover.queue_refresh()
        if hasattr(self,'refresh_parameter_caption'):self.refresh_parameter_caption()

    def selected_effort(self):
        explicit=self.effort_ids.get(self.effort.get())
        if explicit:return explicit
        row=next((item for item in self.model_catalog if item['model']==self.selected_model()),{})
        return row.get('defaultReasoningEffort')

    def scope_changed(self):
        self.app.notify_copilot_binding();self.queue_configuration()

    def speed_changed(self):
        if hasattr(self,'fast_button'):
            self.fast_button.toggled=self.fast_mode.get();self.fast_button.refresh_icon()
        self.queue_configuration()

    def queue_configuration(self):
        if self.closed:return
        if self.config_job:self.root.after_cancel(self.config_job)
        self.config_job=self.root.after(250,self.flush_configuration)

    def flush_configuration(self):
        if self.config_job:self.root.after_cancel(self.config_job)
        self.config_job=None;self.save_configuration()

    def localize_controls(self):
        if hasattr(self.app,'localizer'):self.app.localizer.apply(self.model_box.master,())

    def scope_picker(self):
        from .scope_dialog import open_scope_picker
        open_scope_picker(self)
