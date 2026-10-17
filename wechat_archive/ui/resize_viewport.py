"""A continuously mapped native workspace, sized by Tk's geometry manager."""
from tkinter import ttk


class ResizeViewport(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, style='Canvas.TFrame')

    def attach(self, pane):
        pane.place(x=0, y=0, relwidth=1, relheight=1)
