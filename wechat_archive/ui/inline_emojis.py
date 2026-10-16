"""Offline WeChat text emoticons. Original text remains selectable/searchable."""
import base64
from collections import OrderedDict
from functools import lru_cache
from importlib.resources import files
import io
import json
import re

TOKEN = re.compile(r'\[[^\[\]\r\n]{1,16}\]')


@lru_cache(maxsize=1)
def catalog():
    data = json.loads(files('wechat_archive.ui').joinpath('assets/wechat_emoticons.json').read_text(encoding='utf-8'))
    return data


@lru_cache(maxsize=1)
def atlas():
    from PIL import Image
    return Image.open(io.BytesIO(base64.b64decode(catalog()['png_base64']))).convert('RGBA')


def tokens(value):
    names = catalog()['positions']
    return [match.group() for match in TOKEN.finditer(value) if match.group() in names]


def natural_width(value, theme):
    size = max(18, theme.font.metrics('linespace'))
    names = catalog()['positions']
    widths = []
    for line in value.split('\n'):
        width = 0
        start = 0
        for match in TOKEN.finditer(line):
            if match.group() in names:
                width += theme.font.measure(line[start:match.start()]) + size + 2
                start = match.end()
        widths.append(width + theme.font.measure(line[start:]))
    return max(widths, default=0)


def photo_for(widget, theme, code, size):
    from PIL import Image, ImageTk
    cache = getattr(theme, '_wechat_emoji_photos', None)
    if cache is None:
        cache = theme._wechat_emoji_photos = OrderedDict()
    key = (code, size)
    photo = cache.get(key)
    if photo is None:
        picture = atlas().crop(tuple(catalog()['positions'][code])).resize((size, size), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(picture, master=widget)
        cache[key] = photo
        while len(cache) > 256:
            cache.popitem(last=False)
    else:
        cache.move_to_end(key)
    return photo


def render_inline(widget, theme):
    """Elide token glyphs and insert images; Text.get still returns the raw token."""
    value = widget.get('1.0', 'end-1c')
    codes = tokens(value)
    if not codes:
        return
    size = max(18, theme.font.metrics('linespace'))
    state = str(widget.cget('state'))
    widget.configure(state='normal')
    widget._wechat_emoji_photos = []
    widget._wechat_emoji_items = []
    widget._wechat_emoji_size = size
    widget.tag_configure('wechat_emoji_token', elide=True)
    start = '1.0'
    for code in codes:
        index = widget.search(code, start, stopindex='end', exact=True)
        if not index:
            break
        photo = photo_for(widget, theme, code, size)
        name = widget.image_create(index, image=photo, align='center', padx=1)
        widget._wechat_emoji_photos.append(photo)
        widget._wechat_emoji_items.append((code, name))
        end = f'{index}+{len(code)+1}c'
        widget.tag_add('wechat_emoji_token', f'{index}+1c', end)
        start = end
    widget.configure(state=state)


def resize_inline(widget, theme):
    size = max(18, theme.font.metrics('linespace'))
    if size == getattr(widget, '_wechat_emoji_size', size):
        return
    refs = []
    for code, name in widget._wechat_emoji_items:
        photo = photo_for(widget, theme, code, size)
        widget.image_configure(name, image=photo)
        refs.append(photo)
    widget._wechat_emoji_photos = refs
    widget._wechat_emoji_size = size
