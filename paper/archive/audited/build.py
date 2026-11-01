from pathlib import Path
import re,json,csv,os
from copy import deepcopy
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH,WD_BREAK,WD_TAB_ALIGNMENT
from docx.enum.section import WD_SECTION_START
from docx.enum.table import WD_TABLE_ALIGNMENT,WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=HERE
DATA=json.loads((ROOT/'work/v9/sumo_analysis.json').read_text())
TEXT=(HERE/'manuscript.txt').read_text()
TEXT=re.sub(r'^(#{1,2} [^\n]+|@APPENDIX [^\n]+)\n',r'\1\n\n',TEXT,flags=re.M)
unknown=set()
helpers=(ROOT/'work/v9/document_helpers.py').read_text()
exec(helpers[:helpers.index('def hyperlink')],globals())
SYMS.update({'lceil':'⌈','rceil':'⌉','ldots':'…','approx':'≈','eta':'η'})

# Each equation is rebuilt from mathematical source; no original OMML is reused.
def math_run(para,s):
    script_letters={'A':'𝒜','B':'ℬ','C':'𝒞','D':'𝒟','E':'ℰ','F':'ℱ','G':'𝒢','H':'ℋ','I':'ℐ','J':'𝒥','K':'𝒦','L':'ℒ','M':'ℳ','N':'𝒩','O':'𝒪','P':'𝒫','Q':'𝒬','R':'ℛ','S':'𝒮','T':'𝒯','U':'𝒰','V':'𝒱','W':'𝒲','X':'𝒳','Y':'𝒴','Z':'𝒵'}
    s=re.sub(r'\\mathcal\s*(?:\{([A-Z])\}|([A-Z]))',lambda m:script_letters[m[1] or m[2]],s)
    s=re.sub(r'\\mathbb\s*(?:\{E\}|E)', '𝔼',s)
    om=OxmlElement('m:oMath')
    for x in MathParser(s).parse():om.append(x)
    for r in om.iter(qn('m:r')):
        pr=OxmlElement('w:rPr');fonts=OxmlElement('w:rFonts')
        fonts.set(qn('w:ascii'),'Cambria Math');fonts.set(qn('w:hAnsi'),'Cambria Math');pr.append(fonts)
        sz=OxmlElement('w:sz');sz.set(qn('w:val'),'20');pr.append(sz)
        if r.find(qn('m:rPr')) is not None:
            italic=OxmlElement('w:i');italic.set(qn('w:val'),'false');pr.append(italic)
        r.insert(1 if r.find(qn('m:rPr')) is not None else 0,pr)
    para._p.append(om)

refs=json.loads((HERE/'references.json').read_text())
order=list(dict.fromkeys(re.findall(r'\[(R\d+)\]',TEXT)))
mapping={key:i+1 for i,key in enumerate(order)}
assert set(order)==set(refs)
def cite(t):return re.sub(r'\[(R\d+)\]',lambda m:f'[{mapping[m[1]]}]',t)

doc=Document();sec=doc.sections[0]
for s in [sec]:
    s.page_width=Inches(8.5);s.page_height=Inches(11)
    s.left_margin=s.right_margin=Inches(.70)
    s.top_margin=Inches(.52);s.bottom_margin=Inches(.62)
    s.header_distance=Inches(.2);s.footer_distance=Inches(.24)
WIDTH=7.10;GAP=.23;COL=(WIDTH-GAP)/2
for nm in ['Normal','Body Text','Title','Subtitle','Heading 1','Heading 2','Heading 3','Caption']:
    st=doc.styles[nm];st.font.name='Times New Roman';st.font.color.rgb=RGBColor(0,0,0)
    st.paragraph_format.widow_control=True
    st.paragraph_format.space_after=Pt(0)
for st in doc.styles:
    if st.type==1:
        if st.element.pPr is not None:
            for e in list(st.element.pPr.findall(qn('w:pBdr'))):st.element.pPr.remove(e)
        if st.element.rPr is not None:
            fonts=st.element.rPr.find(qn('w:rFonts'))
            if fonts is not None:
                for key in list(fonts.attrib):
                    if key.endswith('Theme'):del fonts.attrib[key]
normal=doc.styles['Normal'];normal.font.size=Pt(10.2)
normal.paragraph_format.line_spacing=1.03;normal.paragraph_format.space_after=Pt(3)
normal.paragraph_format.first_line_indent=Inches(.13)
normal.paragraph_format.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY
for nm,size in [('Heading 1',10.2),('Heading 2',9.4)]:
    st=doc.styles[nm];st.font.name='Arial';st.font.size=Pt(size);st.font.bold=True
    st.font.italic=nm=='Heading 2';pf=st.paragraph_format
    pf.keep_with_next=True;pf.space_before=Pt(7 if nm=='Heading 1' else 5)
    pf.space_after=Pt(3);pf.first_line_indent=Inches(0)
    pf.alignment=WD_ALIGN_PARAGRAPH.LEFT
st=doc.styles['Title'];st.font.name='Times New Roman';st.font.size=Pt(17);st.font.bold=True
st.paragraph_format.alignment=WD_ALIGN_PARAGRAPH.CENTER
st.paragraph_format.space_after=Pt(12);st.paragraph_format.first_line_indent=Inches(0)
st.paragraph_format.keep_with_next=True
foot=sec.footer.paragraphs[0];foot.alignment=WD_ALIGN_PARAGRAPH.CENTER
foot.paragraph_format.first_line_indent=Inches(0)
fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');foot._p.append(fld)
settings=doc.settings.element
hy=OxmlElement('w:autoHyphenation');hy.set(qn('w:val'),'true');settings.append(hy)

eqs=[];figs=[];tables=[];sections=[]
def p(t,style=None):
    para=doc.add_paragraph(style=style)
    parts=re.split(r'(\$[^$]+\$|\*\*.*?\*\*)',cite(t))
    for i,part in enumerate(parts):
        if part.startswith('$') and part.endswith('$'):
            suffix=''
            if i+1<len(parts):
                match=re.match(r'^[,.;:]+',parts[i+1])
                if match:suffix=match[0];parts[i+1]=parts[i+1][len(suffix):]
            math_run(para,part[1:-1]+suffix)
        elif part.startswith('**'):para.add_run(part[2:-2]).bold=True
        else:para.add_run(part)
    return para
def equation(t):
    if doc.paragraphs and len(doc.paragraphs[-1].text)<160:
        doc.paragraphs[-1].paragraph_format.keep_with_next=True
    eqs.append(t);a=doc.add_paragraph();pf=a.paragraph_format
    pf.first_line_indent=Inches(0);pf.space_before=Pt(3);pf.space_after=Pt(5)
    pf.alignment=WD_ALIGN_PARAGRAPH.LEFT;pf.keep_together=True
    pf.tab_stops.add_tab_stop(Inches(COL/2-.15),WD_TAB_ALIGNMENT.CENTER)
    pf.tab_stops.add_tab_stop(Inches(COL),WD_TAB_ALIGNMENT.RIGHT)
    a.add_run('\t');math_run(a,t);a.add_run(f'\t({len(eqs)})').font.size=Pt(9)
def roman(n):
    r=''
    for k,v in [(1000,'M'),(900,'CM'),(500,'D'),(400,'CD'),(100,'C'),(90,'XC'),(50,'L'),(40,'XL'),(10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I')]:
        while n>=k:r+=v;n-=k
    return r
def figure(name,caption):
    path=HERE/'figures'/name
    if not path.exists():path=ROOT/'work/v9/figures'/name
    a=doc.add_paragraph();a.paragraph_format.first_line_indent=Inches(0)
    a.paragraph_format.keep_with_next=True;a.alignment=WD_ALIGN_PARAGRAPH.CENTER
    a.add_run().add_picture(str(path),width=Inches(COL))
    figs.append(name)
    c=p(f'Fig. {len(figs)}. {caption}')
    c.paragraph_format.first_line_indent=Inches(0);c.paragraph_format.space_after=Pt(7)
    c.paragraph_format.keep_together=True
    for r in c.runs:r.font.size=Pt(8.3)
    for el in a._p.iter(qn('wp:docPr')):el.set('descr',caption)
def table(headers,rows,caption,widths=None):
    tables.append(caption)
    a=p('TABLE '+roman(len(tables))+'\n'+caption)
    a.alignment=WD_ALIGN_PARAGRAPH.CENTER;a.paragraph_format.first_line_indent=Inches(0)
    a.paragraph_format.keep_with_next=True;a.paragraph_format.space_before=Pt(6)
    for r in a.runs:r.font.size=Pt(8.1)
    t=doc.add_table(rows=1,cols=len(headers));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    widths=widths or [COL/len(headers)]*len(headers)
    assert abs(sum(widths)-COL)<.01,(widths,COL)
    for c,w in zip(t.columns,widths):c.width=Inches(w)
    for row_index,row in enumerate([headers]+rows):
        cells=t.rows[0].cells if row is headers else t.add_row().cells
        for i,(cell,txt) in enumerate(zip(cells,row)):
            cell.width=Inches(widths[i]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            para=cell.paragraphs[0];para.paragraph_format.first_line_indent=Inches(0)
            para.paragraph_format.space_after=Pt(0);para.paragraph_format.line_spacing=1
            para.alignment=WD_ALIGN_PARAGRAPH.CENTER
            if len(rows)<=12 and row_index<len(rows):para.paragraph_format.keep_with_next=True
            run=para.add_run(str(txt));run.font.size=Pt(8);run.bold=row is headers
            tcpr=cell._tc.get_or_add_tcPr();m=OxmlElement('w:tcMar')
            for side in ['top','bottom','left','right']:
                e=OxmlElement('w:'+side);e.set(qn('w:w'),'35');e.set(qn('w:type'),'dxa');m.append(e)
            tcpr.append(m)
        trpr=cells[0]._tc.getparent().get_or_add_trPr();nr=OxmlElement('w:cantSplit');trpr.append(nr)
    h=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(h)
    bd=OxmlElement('w:tblBorders')
    for side in ['top','bottom','left','right','insideH','insideV']:
        e=OxmlElement('w:'+side);e.set(qn('w:val'),'single' if side in ['top','bottom','insideH'] else 'nil')
        e.set(qn('w:sz'),'4');e.set(qn('w:color'),'999999' if side=='insideH' else '000000');bd.append(e)
    t._tbl.tblPr.append(bd)
    return t

NAMES={'P0':'S0','P1':'SEQ','P2':'JFAST','P3':'JSEL'}
def ci(x):return f"{x['mean']:.2f}\n[{x['lo']:.2f}, {x['hi']:.2f}]"
def addtable(key):
    if key=='inventory':
        table(['Experiment','Seeds¹','Runs'],[['Corrected mesoscopic','200','14,400'],['Initial development','6','168'],['Escalation development','6','132'],['Primary microscopic','48','1,728'],['Secondary microscopic','12','264']], 'Experimental inventory',[1.86,.70,COL-2.56])
        a=p('¹ Seeds per condition; the same seed identifiers recur across conditions. Development is excluded from primary inference.')
        for r in a.runs:r.font.size=Pt(8)
    elif key=='aggregate':
        rows=[]
        for key,name in NAMES.items():
            m=DATA['aggregate'][key];rows.append([name]+[f"{m[k]['mean']:.2f}" for k in ['time_s','A_vh','Dplus_vh','deltaJ_vh']])
        table(['Policy','Time\n(s)','A\n(veh-h)','D⁺\n(veh-h)','ΔJ\n(veh-h)'],rows,'Balanced microscopic means',[.62,.65,.72,.72,COL-2.71])
    elif key=='full_results':
        for load in [.6,.8,.95]:
            rows=[]
            for z in DATA['cells']:
                if z['load']!=load:continue
                m=z['metrics'];rows.append([z['missions'],NAMES[z['policy']]]+[f"{m[k]['mean']:.2f}" for k in ['time_s','A_vh','Dplus_vh','deltaJ_vh']])
            table(['Dose','Policy','Time\n(s)','A\n(veh-h)','D⁺\n(veh-h)','ΔJ\n(veh-h)'],rows,f'Cell means at nominal load {load:.2f}',[.34,.55,.65,.62,.62,COL-2.78])
    elif key=='full_contrasts':
        for metrics,title in [(['time_s','A_vh'],'Time and spatial exposure'),(['Dplus_vh','deltaJ_vh'],'Individual and signed residence')]:
            rows=[]
            for z in DATA['contrasts']:
                if z['comparison']=='P3-P2':rows.append([f"{z['load']:.2f} / {z['missions']}"]+[ci(z['metrics'][k]) for k in metrics])
            headers=['Load / dose']+(['Time (s)','A (veh-h)'] if metrics[0]=='time_s' else ['D⁺ (veh-h)','ΔJ (veh-h)'])
            table(headers,rows,'JSEL minus JFAST: '+title.lower()+'. Mean [95% CI].',[.68,1.37,COL-2.05])
    elif key=='sensitivities':
        names={'sensitivity':'0.25 s step','ablation':'No escalation','adaptive_base':'Longest count','exact_counts':'Frequent counts'}
        a=p('For Tables VIII–X, “No escalation” is unguarded minus guarded JSEL. Other rows give the change in the JSEL-minus-JFAST effect. Each load uses 12 paired seeds.')
        a.paragraph_format.first_line_indent=Inches(0)
        a.paragraph_format.keep_with_next=True
        for r in a.runs:r.font.size=Pt(8)
        for metric,title in [('time_s','duration (s)'),('A_vh','spatial exposure (vehicle-hours)'),('Dplus_vh','positive individual residence (vehicle-hours)')]:
            rows=[[names[z['phase']],f"{z['load']:.2f}",ci(z['metrics'][metric])] for z in DATA['sensitivities']]
            table(['Change','Load','Mean [95% CI]'],rows,'Sensitivity in '+title,[1.25,.45,COL-1.70])
    elif key=='rare_events':
        rows=[]
        for z in DATA['cells']:
            if z['policy']!='P3':continue
            lo,hi=z['over600_episode_CP95']
            rows.append([f"{z['load']:.2f} / {z['missions']}",str(z['over600_episodes'])+'/48',f'{100*lo:.3f}–{100*hi:.3f}%'])
        table(['Load / dose','Late episodes','Exact 95% interval'],rows,'JSEL episodes with at least one mission above 600 s',[.77,1.01,COL-1.78])

def algo():
    lines=[
      ('Algorithm 1. One control update and route scoring',0),
      ('Receive available counts; hold stale observations.',0),
      ('For each active ambulance on a regular link:',0),
      ('Update completed-link credit and current-link progress.',1),
      ('If selective and progress deficit > γ:',1),
      ('Set its irreversible flag; clear its lease; replan now.',2),
      ('On link entry or escalation:',1),
      ('Generate mode-specific route–action candidates.',2),
      ('Score every candidate using Procedure SCORE.',2),
      ('In JSEL, filter by the global minimum ETA + ε.',2),
      ('Prefer burden, then ETA and deterministic identifiers.',2),
      ('Apply 10 s incumbent preference only within that cap.',2),
      ('In other modes, use the specified time-oriented choice.',2),
      ('Install the continuation and retain its local action.',2),
      ('Remove an old-link lease on regular-link departure.',1),
      ('For a current selective lease:',1),
      ('On first observed own green, set absolute expiry to',2),
      ('now + max(0, requested hold − elapsed green).',3),
      ('If expiry reached, admission age ≥ 120 s, or no',2),
      ('receiving headroom: remove and mark nonrenewable.',3),
      ('Otherwise forward the admitted request.',2),
      ('Without a lease, apply trigger and admission gates;',1),
      ('do not re-admit an expiry/headroom-finished pair.',2),
      ('Use aggressive requests in aggressive modes.',1),
      ('Order conflicting requests by dispatch time and ID.',0),
      ('Execute service-age protection and legal stage changes.',0),
      ('Before each half-step, record the left-endpoint census;',0),
      ('then advance and collect insertion/completion events.',1),
      ('Procedure SCORE(route, action, mode)',0),
      ('Initialize ETA and burden to zero.',0),
      ('For each regular link in the continuation:',0),
      ('Add remaining/current or full/downstream free-flow',1),
      ('time and the received-count discharge proxy.',2),
      ('Set arrival offset τ to the accumulated ETA.',1),
      ('If its downstream node is unsignalized: continue.',1),
      ('Forecast residual nominal wait from the current stage.',1),
      ('For S0/SEQ forecasts or action (0,0): add nominal',1),
      ('wait and no burden; continue.',2),
      ('Estimate legal-switch delay, feasibility, and headroom.',1),
      ('Compute the local benefit and burden score.',1),
      ('Admit benefit using the selected mode’s gates.',1),
      ('Add residual wait minus admitted benefit, clipped',1),
      ('at zero, and add burden only if admitted.',2),
      ('Return accumulated ETA and admitted burden.',0),
    ]
    for i,(txt,indent) in enumerate(lines):
        a=p(txt);a.paragraph_format.first_line_indent=Inches(0)
        a.paragraph_format.left_indent=Inches(indent*.10)
        a.paragraph_format.space_after=Pt(1);a.paragraph_format.line_spacing=1
        a.paragraph_format.alignment=WD_ALIGN_PARAGRAPH.LEFT
        a.paragraph_format.keep_with_next=i==0
        for r in a.runs:r.font.size=Pt(8.8);r.bold=i==0

title=re.search(r'^@TITLE (.*)$',TEXT,re.M)[1]
subtitle=re.search(r'^@SUBTITLE (.*)$',TEXT,re.M)[1]
a=p(title+': '+subtitle,'Title')
for r in a.runs:r.font.name='Times New Roman';r.font.size=Pt(17);r.bold=True
abstract=re.search(r'^@ABSTRACT (.*)$',TEXT,re.M)[1]
a=p('**Abstract.** '+abstract);a.paragraph_format.first_line_indent=Inches(0)
a.paragraph_format.space_after=Pt(8)
for r in a.runs:r.font.size=Pt(9.7)
a=p('**Keywords.** '+re.search(r'^@KEYWORDS (.*)$',TEXT,re.M)[1]);a.paragraph_format.first_line_indent=Inches(0)
a.paragraph_format.space_after=Pt(10)
for r in a.runs:r.font.size=Pt(9.2)
newsec=doc.add_section(WD_SECTION_START.CONTINUOUS)
cols=newsec._sectPr.find(qn('w:cols'));cols.set(qn('w:num'),'2');cols.set(qn('w:space'),str(round(GAP*1440)))
number=0;sub=0
for block in re.split(r'\n\s*\n',TEXT[TEXT.index('# Introduction'):]):
    block=block.strip()
    if not block:continue
    if block.startswith('$$'):
        for eq in re.findall(r'\$\$(.*?)\$\$',block,re.S):equation(eq.strip())
    elif block.startswith('## '):
        sub+=1;p(chr(64+sub)+'. '+block[3:],'Heading 2')
    elif block.startswith('# '):
        number+=1;sub=0;sections.append(block[2:]);p(roman(number)+'. '+block[2:],'Heading 1')
    elif block.startswith('@APPENDIX '):
        letter,text=block[10:].split('|');sub=0;p('Appendix '+letter+'\n'+text,'Heading 1')
    elif block=='@REFERENCES':
        p('References','Heading 1')
        for key in order:
            a=p(f'[{mapping[key]}] '+refs[key]);pf=a.paragraph_format
            pf.first_line_indent=Inches(-.20);pf.left_indent=Inches(.20)
            pf.space_after=Pt(3);pf.keep_together=True
            # Allow line breaks at natural URL delimiters without altering targets.
            for r in a.runs:r.font.size=Pt(8.5)
    elif block.startswith('@FIG '):figure(*block[5:].split('|',1))
    elif block.startswith('@TABLE '):addtable(block[7:])
    elif block=='@ALGORITHM':algo()
    else:p(block.replace('\n',' '))

assert not unknown,unknown
doc.core_properties.title=title
doc.core_properties.subject='Joint ambulance routing and selective traffic signal priority'
doc.core_properties.author='';doc.core_properties.last_modified_by=''
doc.core_properties.comments=''
file=OUT/'AmbuGo_Audited_Research_Paper.docx';doc.save(file)
(HERE/'equations.json').write_text(json.dumps(eqs,indent=2))
(HERE/'structure.json').write_text(json.dumps({'sections':sections,'equations':len(eqs),'figures':figs,'tables':tables,'references':mapping},indent=2))

# Publish complete episode-level intervals separately from bootstrap fractions.
with (OUT/'Episode_Reliability.csv').open('w',newline='') as f:
    w=csv.writer(f);w.writerow(['load','scheduled_missions','policy','episodes','episodes_with_mission_above_600s','episode_probability_CP95_lower','episode_probability_CP95_upper','scheduled_mission_evaluations','completed_missions','unfinished_missions'])
    for z in DATA['cells']:
        w.writerow([z['load'],z['missions'],NAMES[z['policy']],48,z['over600_episodes'],*z['over600_episode_CP95'],z['missions_total'],z['missions_completed'],z['missions_total']-z['missions_completed']])
print(file);print('Equations',len(eqs),'tables',len(tables),'references',len(order))
