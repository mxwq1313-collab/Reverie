"""Exact nine-slice equivalence, including patterned edges and alpha."""
import unittest
from PIL import Image
from wechat_archive.ui.control_textures import expand_texture


def tiled(source,border,width,height):
    if isinstance(border,int):left=top=right=bottom=border
    else:left,top,right,bottom=border
    sw,sh=source.size;out=Image.new(source.mode,(width,height))
    sx=(0,left,sw-right,sw);sy=(0,top,sh-bottom,sh)
    dx=(0,left,width-right,width);dy=(0,top,height-bottom,height)
    for r in range(3):
        for c in range(3):
            part=source.crop((sx[c],sy[r],sx[c+1],sy[r+1]))
            if not part.width or not part.height:continue
            for x in range(dx[c],dx[c+1],part.width):
                for y in range(dy[r],dy[r+1],part.height):
                    out.paste(part.crop((0,0,min(part.width,dx[c+1]-x),min(part.height,dy[r+1]-y))),(x,y))
    return out


class ControlTextureTests(unittest.TestCase):
    def test_patterned_pixels_are_equivalent_across_sizes_and_states(self):
        source=Image.new('RGBA',(14,14))
        source.putdata([((x*17)%256,(y*19)%256,((x+y)*23)%256,(x*31+y*7)%256) for y in range(14) for x in range(14)])
        for border in (0,3,(3,3,3,2),(2,3,3,3),(0,0,0,2)):
            expanded=expand_texture(source,border)
            for width,height in ((14,14),(80,39),(263,51),(1024,135),(1537,197)):
                with self.subTest(border=border,size=(width,height)):
                    self.assertEqual(tiled(source,border,width,height).tobytes(),tiled(expanded,border,width,height).tobytes())

    def test_expansion_uses_complete_periods_and_bounded_storage(self):
        source=Image.new('RGBA',(38,38),'#f6f8fc');border=15
        expanded=expand_texture(source,border)
        self.assertEqual((expanded.width-30)%8,0);self.assertEqual((expanded.height-30)%8,0)
        self.assertGreaterEqual(expanded.width,512);self.assertLess(expanded.width,550)
        self.assertGreaterEqual(expanded.height,96);self.assertLess(expanded.height,134)

    def test_zero_interior_is_kept_intact(self):
        source=Image.new('RGBA',(6,6),'#262626')
        self.assertIs(expand_texture(source,3),source)
