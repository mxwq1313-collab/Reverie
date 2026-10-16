"""The user's original cat artwork, kept intact behind a rounded, alpha-preserving icon mask."""
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
    from PIL import Image,ImageOps,ImageDraw,ImageChops
    if not isinstance(size,int) or isinstance(size,bool) or not 1<=size<=1024:raise ValueError('Invalid logo size')
    with Image.open(io.BytesIO(original())) as source:
        result=ImageOps.contain(source.convert('RGBA'),(size,size),method=Image.Resampling.LANCZOS)
    scale=4;w,h=result.size;mask=Image.new('L',(w*scale,h*scale))
    ImageDraw.Draw(mask).rounded_rectangle((0,0,w*scale-1,h*scale-1),radius=min(w,h)*scale*.22,fill=255)
    mask=mask.resize((w,h),Image.Resampling.LANCZOS).point(lambda value:0 if value<8 else 255 if value>247 else value)
    result.putalpha(ImageChops.multiply(result.getchannel('A'),mask))
    return result


def install(app):
    from PIL import ImageTk
    app.window_logo=ImageTk.PhotoImage(image(64),master=app.root)
    app.root.iconphoto(True,app.window_logo)
    app.brand_logo=ImageTk.PhotoImage(image(app.theme.u(32)),master=app.root)
    app.brand_label.configure(image=app.brand_logo,compound='left',padding=(0,0,app.theme.u(5),0))


def windows_icon(path):
    sizes=(16,24,32,48,64,128,256);frames=[image(size) for size in sizes]
    frames[-1].save(path,format='ICO',sizes=[(n,n) for n in sizes],append_images=frames[:-1])
    return str(path)
