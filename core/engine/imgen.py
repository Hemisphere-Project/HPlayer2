from pilmoji import Pilmoji
from PIL import Image, ImageDraw, ImageFont
from ..module import Module

class ImGen(Module):
    def __init__(self, hplayer):
      super().__init__(hplayer, 'ImGen', 'yellow')  
    
    def txt2img(self, text, encoding = None):
      
      if encoding == 'UCS2':
        text = bytes.fromhex(text).decode('utf-16-be')
      
      width, height = 1920, 1080
      
      # Find appropriate Font size
      #
      img_fraction = 0.80 # portion of image width you want text width to be
      fontsize = 1
      while True:  # iterate until the text size is just larger than the criteria
        # font = ImageFont.truetype('/usr/share/fonts/TTF/Roboto-Black.ttf', fontsize)
        # font = ImageFont.truetype('./extra/Symbola.ttf', fontsize)
        font = ImageFont.truetype('./extra/OpenSansEmoji.ttf', fontsize)
        if font.getsize(text)[0] >= img_fraction*width or font.getsize(text)[1] > img_fraction*height: break
        fontsize += 1
      
      # font = ImageFont.truetype('/usr/share/fonts/noto/NotoColorEmoji.ttf', 109)
      
      img = Image.new('RGB', (width, height), color = (0, 0, 0), fill=(255,255,255))
      d = ImageDraw.Draw(img)
      
      w, h = d.textsize(text, font=font)
      pos = (int((width-w)/2), int((height-h)/2))
      # w, h = 10, 10
      d.text(pos, text, font=font)
      img.save('/tmp/hplayer_txt2img.png')
      return '/tmp/hplayer_txt2img.png'
    
    
    def txt2img2(self, text, encoding = None):
      
      if encoding == 'UCS2':
        text = bytes.fromhex(text).decode('utf-16-be')
      
      width, height = 1920, 1080
      
      img = Image.new('RGB', (width, height), color = (0, 0, 0))
      # d = ImageDraw.Draw(img)
      d = Pilmoji(img);
      
      # Find appropriate Font size
      #
      img_fraction = 0.80 # portion of image width you want text width to be
      fontsize = 1
      while True:  # iterate until the text size is just larger than the criteria
        font = ImageFont.truetype('/usr/share/fonts/TTF/Roboto-Black.ttf', fontsize)
        # font = ImageFont.truetype('./extra/Symbola.ttf', fontsize)
        if d.getsize(text, font=font)[0] >= img_fraction*width or d.getsize(text, font=font)[1] > img_fraction*height: break
        fontsize += 1
      
      # font = ImageFont.truetype('/usr/share/fonts/noto/NotoColorEmoji.ttf', 109)
      
      
      
      w, h = d.getsize(text, font=font)
      pos = (int((width-w)/2), int((height-h)/2))
      d.text(pos, text, font=font, fill=(255,255,255), emoji_scale_factor=0.8, emoji_position_offset=(0,int(fontsize*0.3)))
      # d.text((int((width-w)/2), int((height-h)/2)), text, font=font, fill=(255,255,255))
      img.save('/tmp/hplayer_txt2img.png')
      return '/tmp/hplayer_txt2img.png'