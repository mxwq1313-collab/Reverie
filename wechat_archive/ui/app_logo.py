"""The user's original cat artwork, scaled only for platform icon sizes."""
import base64, hashlib, io, json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def original():
    value=json.loads((Path(__file__).parent/'assets/app_logo.json').read_text(encoding='utf-8'))
    data=base64.b64decode(value['png_base64'],validate=True)
    if hashlib.sha256(data).hexdigest()!=value['sha256']:raise ValueError('Application logo digest mismatch')
    return data


def image(size):
    from PIL import Image,ImageOps
    with Image.open(io.BytesIO(original())) as source:
        return ImageOps.contain(source.convert('RGBA'),(size,size),method=Image.Resampling.LANCZOS)


def install(app):
    from PIL import ImageTk
    app.window_logo=ImageTk.PhotoImage(image(64),master=app.root)
    app.root.iconphoto(True,app.window_logo)
    app.brand_logo=ImageTk.PhotoImage(image(app.theme.u(32)),master=app.root)
    app.brand_label.configure(image=app.brand_logo,compound='left',padding=(0,0,app.theme.u(5),0))


def windows_icon(path):
    from PIL import Image
    with Image.open(io.BytesIO(original())) as source:
        source.save(path,format='ICO',sizes=[(n,n) for n in (16,24,32,48,64,128,256)])
    return str(path)
