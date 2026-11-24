from PIL import Image, ImageDraw, ImageFont

def render(data, buf):
    names = data['names']
    vals = data['weights']
    if not (len(names) == len(vals) == 8 and abs(sum(vals) - 100) < 0.5):
        raise ValueError('Répartition invalide')
    colors=['#84dfb6','#82b9f7','#edb777','#bd9bdf','#f0959c','#67c7d1','#bacc76','#8997a7']
    im=Image.new('RGB',(860,1040),'#182128');d=ImageDraw.Draw(im)
    def txt(x,y,s,size,c='#eef4f3',bold=False,anchor=None):
     f=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if bold else '')+'.ttf',size)
     d.text((x,y),s,font=f,fill=c,anchor=anchor)
    txt(42,32,'CAP INVESTISSEMENT',22,'#84dfb6',True)
    txt(42,76,'Mon portefeuille',54,bold=True)
    txt(44,156,'Compte-titres  ·  Relevé du '+data['date'],29,'#b7c6c9')
    cx,cy=430,422;rad=196; ang=-90
    for val,c in zip(vals,colors):
     end=ang+3.6*val
     d.pieslice((cx-rad,cy-rad,cx+rad,cy+rad),ang+.35,end-.35,fill=c)
     ang=end
    d.ellipse((cx-120,cy-120,cx+120,cy+120),fill='#182128')
    txt(cx,cy-13,str(data['total']),60,bold=True,anchor='mm');txt(cx,cy+38,'positions',23,'#bdcdcf',anchor='mm')
    for i,(name,pct,col) in enumerate(zip(names,vals,colors)):
     x=44+(i%2)*402;y=668+(i//2)*53
     d.ellipse((x,y+10,x+15,y+25),fill=col)
     txt(x+27,y,name,24)
     txt(x+369,y+15,f'{pct:.1f} %'.replace('.',','),24,'#eef4f3',True,'rm')
    d.line((44,900,816,900),fill='#455259',width=2)
    txt(44,923,'Les trois premières positions pèsent '+f'{data["top3"]:.1f}'.replace('.',',')+' % du total.',24)
    txt(44,975,'Répartition des titres détenus, hors liquidités.',21,'#a5b9bc')
    im.save(buf, format='PNG')
