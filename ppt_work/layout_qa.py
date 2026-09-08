import json, pathlib, itertools
for p in sorted(pathlib.Path('ppt_work/final-layout').glob('*.json')):
    data=json.loads(p.read_text(encoding='utf-8'))
    sw,sh=data['slide']['frame']['width'],data['slide']['frame']['height']
    elements=[(e.get('name') or e.get('id'), e.get('kind'), e.get('bbox'), e.get('text'), e) for e in data.get('elements',[]) if isinstance(e.get('bbox'),list) and len(e['bbox'])==4]
    outside=[e[:4] for e in elements if e[2][0]<0 or e[2][1]<0 or e[2][0]+e[2][2]>sw or e[2][1]+e[2][3]>sh]
    textels=[e for e in elements if e[3]]
    overlaps=[]
    for a,b in itertools.combinations(textels,2):
        ax,ay,aw,ah=a[2]; bx,by,bw,bh=b[2]
        ix=max(0,min(ax+aw,bx+bw)-max(ax,bx)); iy=max(0,min(ay+ah,by+bh)-max(ay,by)); area=ix*iy
        if area>1: overlaps.append((a[0],b[0],round(area,1),a[3][:20],b[3][:20]))
    print(p.name,'slide elements',len(elements),'outside',len(outside),'text-text overlaps',len(overlaps))
    if outside: print('OUTSIDE',outside)
    if overlaps: print('OVERLAPS',overlaps)
    for name,kind,bbox,text,e in textels:
        line_count=e.get('textLayout',{}).get('lineCount')
        print(f"{name:34} bbox={bbox} chars={len(text)} rendered_lines={line_count} source_lines={text.count(chr(10))+1}")
