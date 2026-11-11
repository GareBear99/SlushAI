from PIL import Image, ImageDraw, ImageFilter

img = Image.new('RGBA', (256, 256), (255, 255, 255, 255))
d = ImageDraw.Draw(img)
d.ellipse((48, 48, 208, 208), fill=(180, 120, 60, 255))
d.ellipse((96, 96, 160, 160), fill=(220, 180, 120, 255))
img = img.filter(ImageFilter.GaussianBlur(1))
img.save('example.png')
print('assets/example.png created')
