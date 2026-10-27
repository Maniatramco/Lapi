"""Sentence-level answer validation for agentic chat (WS2).

Every factual sentence must cite a source read in this turn, and the numbers,
dates and names it states must appear in the sources it cites. Failing
sentences are repaired once by the model, then removed, and the answer says how
many were removed. No sentence is ever "fixed" by attaching a citation the
model did not choose.
"""
import json
import re

CITE = re.compile(r'\[(\d+(?:\s*,\s*\d+)*)\]')
NUMBER = re.compile(r'(?<![\w\[])(?:[$€£₹]\s?)?\d[\d,]*(?:\.\d+)?%?(?![\w\]])')
DATE = re.compile(r'\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? \d{1,2}(?:st|nd|rd|th)?,? \d{4}|\d{1,2}(?:st|nd|rd|th)? (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]* \d{4})\b')
NAME = re.compile(r'\b([A-Z][a-z]+(?:[ -](?:[A-Z][a-z]+|[A-Z]\.|de|van|von|da|bin))+)\b')
NO_CLAIM = re.compile(r'^(?:hi|hello|hey|thanks|thank you|you\'re welcome|sure|okay|ok)\b|'
                      r'\b(?:could not find|couldn\'t find|did not find|didn\'t find|no (?:evidence|source|record|result|document)s?\b|'
                      r'not (?:found|available|in the (?:sources|evidence|documents))|isn\'t (?:stated|mentioned)|is not (?:stated|mentioned)|'
                      r'would you like|do you want|let me know|which (?:one|dataset|document)|please (?:choose|select|clarify|confirm))', re.I)
STOP_NAMES = {'The', 'This', 'That', 'These', 'Those', 'A', 'An', 'In', 'On', 'For', 'Your', 'Our', 'Each', 'All', 'Total', 'Both',
              'Yes', 'No', 'Based', 'According', 'From', 'Of', 'And', 'Or', 'If', 'It', 'Its', 'There', 'Here', 'Note', 'Overall',
              'Saved', 'Lapi', 'Review', 'Dataset', 'Datasets', 'Document', 'Documents', 'Prompt', 'Prompts', 'Chat', 'Extraction',
              'Extractions', 'Upload', 'Settings', 'Model', 'Models', 'Default', 'Skills', 'Memory', 'Instructions', 'Unified'}


def sentences(answer):
    """Split into (text, start, end) units: list items, table rows and sentences."""
    out = []; pos = 0
    for line in answer.split('\n'):
        start = pos; pos += len(line) + 1
        stripped = line.strip()
        if not stripped: continue
        if stripped.startswith('|'):
            out.append((line, start, start + len(line))); continue
        # A sentence ends at . ! ? followed by optional citations, then space + capital/digit/quote.
        last = 0
        for m in re.finditer(r'[.!?](?:\s*\[\d+(?:\s*,\s*\d+)*\])*(?=\s+(?:[A-Z0-9"“(]|$))', line):
            out.append((line[last:m.end()], start + last, start + m.end())); last = m.end()
        if line[last:].strip(): out.append((line[last:], start + last, start + len(line)))
    return [(t, a, b) for t, a, b in out if t.strip()]


def cited(text):
    return [int(n) for group in CITE.findall(text) for n in re.split(r'\s*,\s*', group)]


def _plain(text):
    return CITE.sub('', text)


def needs_citation(text):
    s = _plain(text).strip(' -*>#\t')
    if not s or set(s) <= set('|-: '): return False
    if s.endswith('?') or s.endswith(':') and len(s.split()) <= 10: return False
    if re.fullmatch(r'\*{0,2}[^.!?]{1,60}\*{0,2}', s) and not NUMBER.search(s) and len(s.split()) <= 6: return False  # heading/label
    if NO_CLAIM.search(s) and not NUMBER.search(s): return False
    names = [m[1] for m in NAME.finditer(s) if re.split(r'[ -]', m[1])[0] not in STOP_NAMES]
    return bool(NUMBER.search(s) or DATE.search(s) or names or len(s.split()) >= 5)


def _norm(text):
    return re.sub(r'\s+', ' ', str(text)).casefold()


def _number_forms(token):
    raw = token.strip('$€£₹ %')
    plain = raw.replace(',', '')
    forms = {raw, plain}
    try:
        value = float(plain)
        forms |= {f'{value:,.2f}', f'{value:.2f}', f'{value:,.0f}', f'{value:.0f}' if value == int(value) else plain}
        if value == int(value): forms.add(str(int(value)))
    except ValueError:
        pass
    return {f for f in forms if f}


def unsupported_values(text, sources):
    """Numbers, dates and multi-word names in text that no cited source contains."""
    corpus = _norm(' '.join(s.get('text', '') if isinstance(s.get('text'), str) else json.dumps(s.get('text'), ensure_ascii=False)
                            for s in sources) + ' ' + ' '.join(str(s.get('document_name', '')) for s in sources))
    digits = corpus.replace(',', '')
    missing = []
    body = _plain(text)
    body = re.sub(r'^\s*(?:[-*]|\d+[.)])\s+', '', body)  # list markers are not values
    for m in DATE.finditer(body):
        if _norm(m[0]) not in corpus: missing.append(m[0])
    body_wo_dates = DATE.sub(' ', body)
    for m in NUMBER.finditer(body_wo_dates):
        token = m[0]
        if re.fullmatch(r'\d', token.strip('%')): continue  # single digits ("2 documents") are often counted, verified below
        if not any(f.casefold() in corpus or f.casefold() in digits for f in _number_forms(token)): missing.append(token)
    for m in NAME.finditer(body):
        name = m[1]
        if re.split(r'[ -]', name)[0] in STOP_NAMES or m.start() == len(body) - len(body.lstrip()): continue
        if _norm(name) not in corpus: missing.append(name)
    return list(dict.fromkeys(missing))


def check(answer, sources, weak_score=None):
    """Return problems: [{sentence, reason, detail}] for one answer."""
    by_index = {s['index']: s for s in sources}
    problems = []
    for text, start, end in sentences(answer):
        refs = cited(text)
        unknown = [n for n in refs if n not in by_index]
        if unknown:
            problems.append({'sentence': text.strip(), 'start': start, 'end': end, 'reason': 'unknown_citation', 'detail': unknown}); continue
        if not refs:
            if needs_citation(text):
                problems.append({'sentence': text.strip(), 'start': start, 'end': end, 'reason': 'uncited_claim', 'detail': None})
            continue
        chosen = [by_index[n] for n in refs]
        missing = unsupported_values(text, chosen)
        if missing:
            problems.append({'sentence': text.strip(), 'start': start, 'end': end, 'reason': 'unsupported_value', 'detail': missing[:5]}); continue
        if weak_score is not None:
            scores = [s['score'] for s in chosen if isinstance(s.get('score'), (int, float))]
            if scores and len(scores) == len(chosen) and max(scores) < weak_score:
                problems.append({'sentence': text.strip(), 'start': start, 'end': end, 'reason': 'weak_support', 'detail': max(scores)})
    return problems


def feedback(problems):
    lines = []
    for p in problems[:12]:
        what = {'uncited_claim': 'has no citation',
                'unknown_citation': 'cites sources that were not read this turn: ' + str(p['detail']),
                'unsupported_value': 'states values not found in its cited sources: ' + ', '.join(map(str, p['detail'] or [])),
                'weak_support': 'cites only weakly matching sources'}[p['reason']]
        lines.append('- "' + p['sentence'][:200] + '" ' + what)
    return ('Your answer failed the citation check:\n' + '\n'.join(lines) +
            '\nRewrite the whole answer. Cite every factual sentence with [n] from sources read in this turn, use only values those sources contain, '
            'call more tools if you need evidence, and drop claims you cannot support.')


def remove(answer, problems):
    """Drop failing sentences; say how many were removed."""
    if not problems: return answer, 0
    spans = sorted((p['start'], p['end']) for p in problems)
    out = []; last = 0
    for start, end in spans:
        out.append(answer[last:start]); last = end
    out.append(answer[last:])
    text = ''.join(out)
    text = re.sub(r'\n[ \t]*(?:[-*]|\d+[.)])[ \t]*(?=\n|$)', '', text)  # emptied list items
    text = re.sub(r'[ \t]+\n', '\n', re.sub(r'\n{3,}', '\n\n', text)).strip()
    removed = len(spans)
    if not re.search(r'\w', _plain(text)):
        return ("I couldn't find enough evidence in your sources to answer that reliably. "
                'Try naming the document or field, or check that the documents have finished indexing.'), removed
    note = f'\n\n_{removed} statement{"s" if removed != 1 else ""} removed because {"they" if removed != 1 else "it"} could not be matched to a cited source._'
    return text + note, removed


def normalize(answer, sources):
    """Unify citation formats like [1, 2] and 【1】 into [1][2]; drop duplicate adjacent refs."""
    answer = re.sub(r'【(\d+)】', r'[\1]', answer)
    answer = CITE.sub(lambda m: ''.join(f'[{n}]' for n in dict.fromkeys(re.split(r'\s*,\s*', m[1]))), answer)
    return re.sub(r'(\[\d+\])(?:\s*\1)+', r'\1', answer)


def rich(sources, answer):
    """Citations actually used, renumbered in order of first use, with snippets."""
    used = list(dict.fromkeys(cited(answer)))
    by_index = {s['index']: s for s in sources}
    mapping = {old: new for new, old in enumerate([n for n in used if n in by_index], 1)}
    text = CITE.sub(lambda m: ''.join(f'[{mapping[int(n)]}]' for n in re.split(r'\s*,\s*', m[1]) if int(n) in mapping), answer)
    out = []
    for old, new in mapping.items():
        s = dict(by_index[old], index=new)
        body = s.get('text') if isinstance(s.get('text'), str) else json.dumps(s.get('text'), ensure_ascii=False)
        s['snippet'] = _snippet(body or '', text, new)
        out.append(s)
    return text, out


def _snippet(body, answer, index):
    """≤200 chars of the source around the first term the citing sentence shares with it."""
    flat = re.sub(r'\s+', ' ', body).strip()
    if len(flat) <= 200: return flat
    sentence = next((t for t, _, _ in sentences(answer) if f'[{index}]' in t), '')
    terms = sorted({w for w in re.findall(r'[\w$€£₹.,%-]{4,}', _plain(sentence))}, key=len, reverse=True)
    low = flat.casefold()
    for term in terms:
        at = low.find(term.casefold().strip('.,'))
        if at >= 0:
            start = max(0, at - 80)
            return ('…' if start else '') + flat[start:start + 198].strip() + '…'
    return flat[:199] + '…'
