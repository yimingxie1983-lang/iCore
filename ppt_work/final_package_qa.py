import zipfile,re,pathlib,json
p=pathlib.Path(r'iCore案例PPT_临床辅助诊断与药物临床试验.pptx')
z=zipfile.ZipFile(p)
bad=z.testzip()
slides=[n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)]
empty=[]
prompts=[]
a_re=re.compile(r'<a:t>(.*?)</a:t>',re.S)
for n in slides:
    x=z.read(n).decode('utf-8')
    for m in re.finditer(r'<p:sp[\s\S]*?</p:sp>',x):
        b=m.group(0)
        if '<p:ph' in b and not ''.join(a_re.findall(b)).strip():
            empty.append((n,re.search(r'<p:ph[^>]*>',b).group(0)))
    for t in a_re.findall(x):
        if '单击此处' in t or 'Click to add' in t or 'lorem ipsum' in t.lower():
            prompts.append((n,t))
print(json.dumps({'zip_bad':bad,'slide_count':len(slides),'slides':slides,'empty_placeholders':empty,'prompt_texts':prompts},ensure_ascii=False,indent=2))
