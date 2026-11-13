"""Branded news cards generated from attributed headlines, without invented analysis."""
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from zoneinfo import ZoneInfo

W,H=1080,1350
BG='#102C25'; INK='#F3F0E5'; GREEN='#B9D88A'; MUTED='#ACBEB4'; GOLD='#E5BD6E'
FONT_ROOT=Path('/usr/share/fonts/truetype/dejavu')

def font(size,bold=False):
    return ImageFont.truetype(str(FONT_ROOT/('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')),size)

def lines(draw,text,f,width):
    result=[]; line=''
    for word in text.split():
        if draw.textlength(word,font=f)>width:
            word=word[:35]+'…'
        candidate=(line+' '+word).strip()
        if line and draw.textlength(candidate,font=f)>width:
            result.append(line);line=word
        else:line=candidate
    if line:result.append(line)
    return result

def paragraph(draw,text,y,size=48,bold=False,color=INK,width=900,max_lines=6):
    while True:
        f=font(size,bold); ls=lines(draw,text,f,width)
        if len(ls)<=max_lines or size<=24:break
        size-=2
    if len(ls)>max_lines:ls=ls[:max_lines];ls[-1]=ls[-1].rstrip(' .')+'…'
    for line in ls:
        draw.text((80,y),line,font=f,fill=color);y+=size+15
    return y

def base(index,total):
    im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
    d.rectangle((0,0,18,H),fill=GREEN)
    d.text((80,60),'CAP INVESTISSEMENT',font=font(29,True),fill=GREEN)
    d.line((80,120,1000,120),fill='#355247',width=2)
    d.line((80,1230,1000,1230),fill='#355247',width=2)
    d.text((80,1262),'LES FAITS • LES SOURCES • LE RECUL',font=font(20),fill=MUTED)
    d.text((925,1254),f'{index:02}/{total:02}',font=font(24,True),fill=GREEN)
    return im,d

def encode(im):
    b=BytesIO();im.save(b,format='PNG',optimize=True);return b.getvalue()

def render(items,now):
    """One square card per story, with no redundant cover."""
    cards=[]
    for i,item in enumerate(items,1):
        im=Image.new('RGB',(1080,1080),BG);d=ImageDraw.Draw(im)
        d.rectangle((0,0,16,1080),fill=GREEN)
        d.text((80,55),'CAP INVESTISSEMENT',font=font(30,True),fill=GREEN)
        d.text((900,60),f'{i:02}/{len(items):02}',font=font(24),fill=MUTED)
        d.line((80,115,1000,115),fill='#355247',width=2)
        e=item['editorial']
        paragraph(d,e['topic'],150,32,True,color=GOLD if e['kind']=='macro' else GREEN,max_lines=2)
        paragraph(d,e['scope'],240,36,True,max_lines=2)
        paragraph(d,item['title'],360,58,True,max_lines=5)
        d.rounded_rectangle((60,775,1020,950),radius=20,fill='#1E3E33')
        d.text((80,795),'POUR PRENDRE DU RECUL',font=font(22,True),fill=GREEN)
        paragraph(d,e['note'],835,28,max_lines=3)
        published=item['published'].astimezone(ZoneInfo('Europe/Paris')).strftime('%d/%m/%Y • %H:%M Paris')
        paragraph(d,item['source'],970,22,color=MUTED,max_lines=1)
        d.text((80,1010),published,font=font(22),fill=MUTED)
        cards.append((f'{i:02}-actualite.png',encode(im),item['title'][:1000]))
    return cards
