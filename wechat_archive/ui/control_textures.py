"""Pre-tile ttk backgrounds without changing their nine-slice pixels."""
from PIL import Image


def expand_texture(source,border):
    if isinstance(border,int):left=top=right=bottom=border
    else:left,top,right,bottom=border
    sw,sh=source.size
    inner_w=sw-left-right;inner_h=sh-top-bottom
    if min(inner_w,inner_h)<=0:return source
    width=left+right+inner_w*max(1,(512-left-right+inner_w-1)//inner_w)
    height=top+bottom+inner_h*max(1,(96-top-bottom+inner_h-1)//inner_h)
    result=Image.new(source.mode,(width,height))
    sx=(0,left,sw-right,sw);sy=(0,top,sh-bottom,sh)
    dx=(0,left,width-right,width);dy=(0,top,height-bottom,height)
    for row in range(3):
        for col in range(3):
            size=(dx[col+1]-dx[col],dy[row+1]-dy[row]);part=source.crop((sx[col],sy[row],sx[col+1],sy[row+1]))
            if min(size)<=0 or not part.width or not part.height:continue
            tile=Image.new(source.mode,size);tile.paste(part,(0,0));fw=min(part.width,size[0]);fh=min(part.height,size[1])
            while fw<size[0]:
                amount=min(fw,size[0]-fw);tile.paste(tile.crop((0,0,amount,fh)),(fw,0));fw+=amount
            while fh<size[1]:
                amount=min(fh,size[1]-fh);tile.paste(tile.crop((0,0,size[0],amount)),(0,fh));fh+=amount
            result.paste(tile,(dx[col],dy[row]))
    return result


def prepare_texture(photo,border,root):
    from PIL import ImageTk
    return ImageTk.PhotoImage(expand_texture(ImageTk.getimage(photo),border),master=root)
