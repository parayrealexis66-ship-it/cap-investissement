from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import simpleSplit

def render(data, path):
    c = Canvas(path, pagesize=(500,740), invariant=1)
    c.setTitle("Cap Investissement | Revue de presse")
    def line(x,y,t,font,size,color):
        c.setFillColor(HexColor(color))
        c.setFont(font,size)
        c.drawString(x,y,t)
    c.setFillColor(HexColor('#173c35'))
    c.rect(0,635,500,105,fill=1,stroke=0)
    line(28,711,'CAP INVESTISSEMENT','Helvetica-Bold',11,'#c5e6ce')
    line(28,669,'Revue de presse','Times-Bold',34,'#ffffff')
    line(30,649,data['date'],'Helvetica',11,'#ffffff')
    y=610
    for company,title,facts,question,source in data['sections']:
        line(28,y,company.upper(),'Helvetica-Bold',10,'#287557')
        y-=22
        line(28,y,title,'Times-Bold',19,'#183a32')
        for para in [facts,question]:
            y-=17
            for row in simpleSplit(para,'Helvetica',11,444):
                line(28,y,row,'Helvetica',11,'#22362e')
                y-=14
            y+=8
        y-=12
        line(28,y,source,'Helvetica-Oblique',9,'#405b50')
        y-=29
    assert y>0
    c.save()
