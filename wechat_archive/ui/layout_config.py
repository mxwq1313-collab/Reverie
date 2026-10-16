"""Avoid invalidating Tk geometry when layout values already match."""
def configure_changed(widget,**options):
    changed={}
    for key,value in options.items():
        current=widget.cget(key)
        if isinstance(value,(tuple,list)):
            equal=tuple(map(str,widget.tk.splitlist(current)))==tuple(map(str,value))
        else:equal=str(current)==str(value)
        if not equal:changed[key]=value
    if changed:widget.configure(**changed)
    return bool(changed)

def row_size(widget,row,size):
    if str(widget.rowconfigure(row).get('minsize',0))!=str(size):widget.rowconfigure(row,minsize=size)
