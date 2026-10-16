"""Apply the current palette to native dropdown lists when they are actually opened."""


def prepare_combobox(widget,theme):
    if getattr(widget,'_themed_dropdown',False):return
    original=str(widget.cget('postcommand'));signature=None
    def posted():
        nonlocal signature
        if original:widget.tk.call('eval',original)
        key=(theme.generation,theme.body,theme.active_mode)
        if key==signature:return
        popup=str(widget.tk.call('ttk::combobox::PopdownWindow',str(widget)))
        p=theme.palette
        widget.tk.call(popup+'.f.l','configure','-font',theme.body,'-background',p['PAPER'],'-foreground',p['INK'],
                       '-selectbackground',p['SELECTED'],'-selectforeground',p['INK'],'-relief','flat','-borderwidth',0,
                       '-highlightthickness',0,'-activestyle','none')
        signature=key
    widget.configure(postcommand=posted);widget._themed_dropdown=True
