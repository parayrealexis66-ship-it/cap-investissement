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
    total=len(items)+1; cards=[]
    im,d=base(1,total)
    d.text((80,195),now.astimezone(ZoneInfo('Europe/Paris')).strftime('%d.%m.%Y • %H:%M PARIS'),font=font(26),fill=MUTED)
    paragraph(d,'Le point\nà retenir.',290,94,True,max_lines=3)
    d.rounded_rectangle((80,620,1000,760),radius=24,fill=GREEN)
    d.text((115,655),f"{len(items):02} INFORMATION{'S' if len(items)>1 else ''} SÉLECTIONNÉE{'S' if len(items)>1 else ''}",font=font(34,True),fill=BG)
    scopes=[]
    for item in items:
        scope=item['editorial']['scope']
        if scope not in scopes:scopes.append(scope)
    paragraph(d,' • '.join(scopes),830,42,True,max_lines=4)
    d.text((80,1140),'Ouvrir les images pour parcourir le briefing →',font=font(26),fill=MUTED)
    cards.append(('01-couverture.png',encode(im),'Cap Investissement : briefing de '+str(len(items))+' informations.'))
    for i,item in enumerate(items,2):
        im,d=base(i,total);e=item['editorial']
        d.text((80,185),e['topic'],font=font(29,True),fill=GOLD if e['kind']=='macro' else GREEN)
        paragraph(d,e['scope'],245,46,True,max_lines=2)
        d.text((80,415),'À RETENIR • TITRE DE LA SOURCE',font=font(22),fill=MUTED)
        paragraph(d,item['title'],470,57,True,max_lines=6)
        d.rounded_rectangle((60,930,1020,1120),radius=24,fill='#1E3E33')
        d.text((80,953),'REPÈRE DE LECTURE',font=font(20,True),fill=GREEN)
        paragraph(d,e['note'],993,26,color=INK,max_lines=3)
        published=item['published'].astimezone(ZoneInfo('Europe/Paris')).strftime('%d/%m/%Y %H:%M')
        paragraph(d,f"{item['source']} • {published} Paris",1150,21,color=MUTED,max_lines=2)
        cards.append((f'{i:02}-actualite.png',encode(im),item['title'][:1000]))
    return cards
