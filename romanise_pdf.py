#!/usr/bin/env python3
"""Offline converter for selectable-text, bold-chord songbooks. See README.md."""
from __future__ import annotations
import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
import pymupdf as fitz

NOTES = dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)
NAMES = ['C','Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B']
ROMANS = ['I','bII','II','bIII','III','IV','bV','V','bVI','VI','bVII','VII']
DEGREES = ['1','b2','2','b3','3','4','b5','5','b6','6','b7','7']
QUALITIES = ['M',None,'m',None,'m','M',None,'M',None,'m',None,'dim']
KEY = re.compile(r'^[A-G][#b]?m?$')
CHORD = re.compile(r'^[A-G][#b]?(?:(?:min|maj|dim|aug|sus|add|m|M)|\d+|[#b]\d+|\([#b]?\d+(?:,[#b]?\d+)*\)|[+°])*(?:/(?:[A-G][#b]?|(?:add|maj|[#b])\d+))?$')
ROOT = re.compile(r'^([A-G][#b]?)(min|m(?!aj)|dim)?')
BASS = re.compile(r'^/[A-G][#b]?$')
MARKER = re.compile(r'^\[?\s*(?:(?:(?:UP|DOWN)\s+)?KEY(?:\s+CHANGE)?|MODULATE\s+TO)\s*:?\s*([A-G][#b]?m?)\s*\]?$', re.I)
RED = (163/255, 32/255, 32/255)

def norm(text):
    return text.replace('♯','#').replace('♭','b').replace('−','-').strip()

def pitch(note):
    return (NOTES[note[0]] + (1 if note[1:2]=='#' else -1 if note[1:2]=='b' else 0)) % 12

def tonic(key):
    if not KEY.fullmatch(key):
        raise ValueError(f'Invalid key: {key!r}')
    return (pitch(key) + (3 if key.endswith('m') else 0)) % 12

def chord_core(text):
    text = norm(text)
    return text[1:-1] if text.startswith('(') and text.endswith(')') else text

def is_chord(text):
    core = chord_core(text)
    return bool(CHORD.fullmatch(core) or BASS.fullmatch(core))

def analyse(text):
    text = chord_core(text)
    if BASS.fullmatch(text):
        return pitch(text[1:]), '?'  # A bass movement does not imply a major triad.
    match = re.match(r'^([A-G][#b]?)(.*)', text)
    suffix = match[2].split('/')[0]
    minor = bool(re.match(r'^(min|m(?!aj))', suffix))
    quality = ('dim' if suffix.startswith(('dim','°')) or (minor and 'b5' in suffix)
               else 'aug' if suffix.startswith(('aug','+')) or '#5' in suffix
               else '?' if suffix.startswith(('sus','5')) else 'm' if minor else 'M')
    return pitch(match[1]), quality

def fits(chord, key):
    root, quality = analyse(chord)
    expected = QUALITIES[(root-key)%12]
    return expected is not None and (quality=='?' or quality==expected)

def romanise(text, key, base):
    core = chord_core(text)
    def root_replace(match):
        number = ROMANS[(pitch(match[1])-key)%12]
        return number.lower() + ('dim' if match[2]=='dim' else '') if match[2] else number
    result = ROOT.sub(root_replace, core, count=1)
    result = re.sub(r'/([A-G][#b]?)', lambda m:'/'+DEGREES[(pitch(m[1])-key)%12], result)
    if core != text:
        result = '('+result+')'
    shift = (key-base)%12
    if shift > 6: shift -= 12
    return result + (f' ({shift:+d})' if shift else '')

@dataclass
class Token:
    text: str
    x: float
    y: float
    size: float
    bold: bool
    rects: list
    chord: bool = False
    number: int = 0
    result: str = ''
    key: int = 0

@dataclass
class Row:
    column: int
    y: float
    tokens: list = field(default_factory=list)
    spans: list = field(default_factory=list)
    chord_row: bool = False
    marker: str | None = None

def union_rect(chars):
    result = fitz.Rect(chars[0]['bbox'])
    for c in chars[1:]: result |= fitz.Rect(c['bbox'])
    return result

def extract_page(page, override):
    raw = page.get_text('rawdict')
    spans = [s for b in raw['blocks'] for l in b.get('lines',[]) for s in l['spans']]
    if not spans:
        raise ValueError('No selectable text; this page needs OCR first.')
    headers = [s for s in spans if s['bbox'][1] < page.rect.height*.18 and s['size'] >= 15]
    header = ' '.join(''.join(c['c'] for c in s['chars']) for s in headers)
    match = re.search(r'\[\s*([A-G][#b]?m?)(?:\s*[-–→]\s*([A-G][#b]?m?))?(?=\s*[,\]])', norm(header))
    initial = override.get('initial_key') or (match[1] if match else None)
    if not initial:
        raise ValueError('No bracketed key found in the page heading. Add an initial_key override.')
    tonic(initial)
    cutoff = max([s['bbox'][3] for s in headers] or [50]) + 4
    body = [s for s in spans if s['origin'][1] > cutoff and 9 <= s['size'] <= 14]
    # The supplied format uses a fixed right-column start near 52.5% of the page.
    starts = sum(1 for s in body if s['color'] != 0xffffff and
                 abs(s['bbox'][0] - page.rect.width*.525) < 2)
    two_columns = starts >= 6
    midpoint = page.rect.width/2
    rows = {}
    for s in body:
        # Arrangement order in the header uses a larger size than the chord body.
        if s['size'] > 12.5: continue
        col = int(two_columns and s['bbox'][0] > midpoint)
        bucket = (col, round(s['origin'][1]*2)/2)
        row = rows.setdefault(bucket, Row(col, s['origin'][1]))
        row.spans.append(s)
        if s['color'] == 0xffffff: continue  # These PDFs use white dots for spacing.
        text = ''.join(c['c'] for c in s['chars'])
        for m in re.finditer(r'[|\[\]]|[^\s|\[\]]+', text):
            chars = s['chars'][m.start():m.end()]
            rect = union_rect(chars)
            row.tokens.append(Token(norm(m[0]), rect.x0, s['origin'][1], s['size'],
                                    bool(s['flags'] & 16) or bool(re.search(r'bold|black|heavy', s['font'], re.I)), [rect]))
    ordered = sorted(rows.values(), key=lambda r:(r.column,r.y))
    repairs = []
    # Repair a slash chord wrapped onto the next line (present in June page 4).
    for i, row in enumerate(ordered):
        for token in row.tokens:
            if token.bold and re.fullmatch(r'[A-G][#b]?(?:m|maj|dim|sus)?\d*/', token.text):
                for next_row in ordered[i+1:i+3]:
                    if next_row.column != row.column or not 0 < next_row.y-row.y <= token.size*1.4: continue
                    candidates = [t for t in next_row.tokens if t.bold and
                                  re.fullmatch(r'[A-G][#b]?',t.text) and abs(t.x-token.x)<12]
                    if len(candidates)==1:
                        bass = candidates[0]
                        token.text += bass.text
                        token.rects.extend(bass.rects)
                        next_row.tokens.remove(bass)
                        repairs.append(f'Joined wrapped {token.text} near y={row.y:.1f}.')
                        break
    for row in ordered:
        row.tokens.sort(key=lambda t:t.x)
        text = ' '.join(t.text for t in row.tokens)
        marker = MARKER.fullmatch(text)
        if marker:
            row.marker = marker[1][0].upper()+marker[1][1:].lower()
        for t in row.tokens: t.chord = t.bold and is_chord(t.text)
        def allowed(t):
            # Standalone x means a mute/stop, not an unrecognised lyric word.
            return t.chord or bool(re.fullmatch(r'[|/.:()\[\]\-]+|[xX×](?:\d+)?|N\.?C\.?|Intro:?', t.text)) or bool(
                re.fullmatch(r'\((?:choke|stop|hold|mute|ring|rest)\)', t.text, re.I))
        row.chord_row = any(t.chord for t in row.tokens) and all(allowed(t) for t in row.tokens)
    return initial, header, ordered, two_columns, repairs

def detect(chords, index, current, forced):
    if fits(chords[index].text,current): return current
    window = chords[index:index+8]
    if len(window)<8 or any(i in forced for i in range(index+1,index+8)): return current
    if len({analyse(t.text) for t in window})<3: return current
    if sum(fits(t.text,current) for t in window)>4: return current
    best, winner, tied = 6, current, False
    for candidate in range(12):
        if candidate==current or not fits(window[0].text,candidate): continue
        score = sum(fits(t.text,candidate) for t in window)
        cadence = any(analyse(a.text)==((candidate+7)%12,'M') and
                      analyse(b.text)==(candidate,'M') for a,b in zip(window,window[1:]))
        if score<7 or not cadence: continue
        if score>best: best,winner,tied=score,candidate,False
        elif score==best: tied=True
    return current if tied else winner

def assign_keys(rows, initial, overrides, auto):
    chords, forced, sources = [], {}, {}
    pending = None
    for row in rows:
        if row.marker: pending = row.marker
        if not row.chord_row: continue
        for t in row.tokens:
            if not t.chord: continue
            if pending:
                forced[len(chords)] = tonic(pending)
                sources[len(chords)] = 'printed key marker'
                pending = None
            t.number = len(chords)+1
            chords.append(t)
    for change in overrides.get('changes',[]):
        idx = int(change['chord'])-1
        if not 0 <= idx < len(chords): raise ValueError(f'Invalid override chord number: {idx+1}')
        forced[idx] = tonic(change['key']); sources[idx]='manual override'
    current = base = tonic(initial)
    plan, events = [], []
    explicit, floor = False, 0
    for i,t in enumerate(chords):
        if i in forced:
            candidate = forced[i]
            if candidate != current: events.append(dict(chord=i+1,key=NAMES[candidate],source=sources[i]))
            current,explicit = candidate,True
        elif auto and not explicit:
            candidate = detect(chords,i,current,forced)
            if candidate != current:
                start=i
                while start>floor and start-1 not in forced and fits(chords[start-1].text,candidate): start-=1
                for j in range(start,i): plan[j]=candidate
                events.append(dict(chord=start+1,confirmed_at=i+1,key=NAMES[candidate],source='heuristic - review'))
                current,floor=candidate,i+1
        plan.append(current)
    for t,k in zip(chords,plan):
        t.key=k; t.result=romanise(t.text,k,base)
    return chords,events

def place_row(row, right, size):
    placements=[]
    end=-1e9
    previous=None
    for t in row.tokens:
        text=t.result if t.chord else t.text
        font='hebo' if t.bold else 'helv'
        base,tag=split_label(text)
        width=fitz.get_text_length(base,fontname=font,fontsize=size)
        if tag: width+=1.5+fitz.get_text_length(tag,fontname='helv',fontsize=size*.73)
        gap=3.5 if previous and previous.chord and t.chord else 1.2
        x=max(t.x,end+gap)
        placements.append((t,text,font,x,width,size))
        end=x+width
        previous=t
    return placements,end<=right

def split_label(text):
    match=re.search(r' (\([+-]\d+\))$',text)
    return (text[:match.start()],match[1]) if match else (text,'')

def convert_pdf(data, overrides=None, auto=True, colour=RED):
    """Return (PDF bytes, audit dictionary). Each page starts from its own header key."""
    overrides=overrides or {}
    fitz.TOOLS.set_small_glyph_heights(True)
    doc=fitz.open(stream=data,filetype='pdf')
    report={'pages':[], 'warnings':[], 'converter':'songbook-romaniser 1.2'}
    for page in doc:
        pn=page.number+1
        config=overrides.get('pages',{}).get(str(pn),{})
        info={'page':pn,'status':'unchanged','warnings':[]}
        try:
            initial,title,rows,two_columns,repairs=extract_page(page,config)
            # Convert plausible mixed rows by default; expose them for opt-out.
            # Keep non-chord tokens as text, including arbitrary directions.
            excluded = set(config.get('exclude_rows', []))
            row_id = lambda r: f'{r.column}:{r.y:.2f}'
            info['possible_false_positives'] = []
            info['unresolved_rows'] = []
            for row in rows:
                if not row.chord_row and not row.marker and sum(t.chord for t in row.tokens) >= 2:
                    row.chord_row = True
                    info['possible_false_positives'].append(dict(
                        id=row_id(row), y=round(row.y,2),
                        text=' '.join(t.text for t in row.tokens),
                        excluded=row_id(row) in excluded))
            render = lambda r: r.chord_row and row_id(r) not in excluded
            chords,events=assign_keys(rows,initial,config,auto)
            if not chords: raise ValueError('No confidently identified bold chord rows.')
            placements=[]
            for row in rows:
                if not render(row): continue
                right=page.rect.width/2-9 if two_columns and row.column==0 else page.rect.width-30
                size=min(t.size for t in row.tokens)
                items,ok=place_row(row,right,size)
                while not ok and size>7.5:
                    size=round(size-.25,2);items,ok=place_row(row,right,size)
                if not ok: raise ValueError(f'Crowded row near y={row.y:.1f}: cannot fit legibly. Page left unchanged.')
                if size<9: info['warnings'].append(f'Chord row near y={row.y:.1f} uses {size:g} pt text.')
                placements.extend(items)
            # All placement checks complete before modifying this page.
            for row in rows:
                if not render(row): continue
                for s in row.spans:
                    rect=fitz.Rect(s['bbox']); rect.x0+=.05; rect.x1-=.05; rect.y0+=.05; rect.y1-=.05
                    if not rect.is_empty: page.add_redact_annot(rect,fill=False,cross_out=False)
                for t in row.tokens:
                    for rect in t.rects[1:]: page.add_redact_annot(rect,fill=False,cross_out=False)
            page.apply_redactions(images=0,graphics=0,text=0)
            moved=0
            applied = {t.number for r in rows if render(r) for t in r.tokens if t.chord}
            for t,text,font,x,width,size in placements:
                base,tag=split_label(text)
                page.insert_text((x,t.y),base,fontsize=size,fontname=font,color=colour if t.chord else (0,0,0))
                if tag:
                    tag_x=x+fitz.get_text_length(base,fontname=font,fontsize=size)+1.5
                    page.insert_text((tag_x,t.y-.5),tag,fontsize=size*.73,fontname='helv',color=colour)
                moved+=int(t.chord and x-t.x>1)
            info.update(status='converted',title=title,initial_key=initial,columns=2 if two_columns else 1,
                        chords=sum(t.chord for r in rows if render(r) for t in r.tokens),
                        changes=events,wrapped_chords_repaired=repairs,
                        labels_shifted_right=moved,
                        audit=[dict(chord=t.number,original=t.text,roman=t.result,key=NAMES[t.key],
                                    applied=t.number in applied,
                                    x=round(t.x,2),y=round(t.y,2)) for t in chords])
            if moved: info['warnings'].append(f'{moved} labels moved right to avoid collisions; review dense rows.')
        except ValueError as error:
            info['warnings'].append(str(error))
        report['pages'].append(info)
    result=doc.tobytes(garbage=4,deflate=True)
    doc.close()
    return result,report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('-o','--output',type=Path)
    parser.add_argument('--overrides',type=Path)
    parser.add_argument('--no-auto',action='store_true',help='Use printed/manual changes only.')
    args=parser.parse_args()
    output=args.output or args.input.with_name(args.input.stem+'-roman.pdf')
    if output.resolve()==args.input.resolve(): parser.error('Output must differ from input.')
    config=json.loads(args.overrides.read_text()) if args.overrides else {}
    result,report=convert_pdf(args.input.read_bytes(),config,auto=not args.no_auto)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(result)
    audit=output.with_suffix('.audit.json')
    audit.write_text(json.dumps(report,indent=2),encoding='utf-8')
    for p in report['pages']:
        print(f"Page {p['page']}: {p['status']}; {p.get('chords',0)} chords; {p.get('changes',[])}")
        for warning in p['warnings']: print('  REVIEW:',warning)
    print('PDF:',output,'\nAudit:',audit)

if __name__=='__main__': main()

# python -m streamlit run app.py