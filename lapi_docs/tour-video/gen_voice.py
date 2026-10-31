"""Record the tour narration with a neural voice and keep word timings for captions and scene sync."""
import asyncio, json, pathlib, re, sys
import edge_tts

OUT = pathlib.Path(__file__).parent
VOICE = sys.argv[1] if len(sys.argv) > 1 else 'en-US-AriaNeural'
# One flowing voice-over; each line is a scene (the renderer times scenes from these sentences).
SCENES = [
    ('welcome', "Meet Lapi. Your documents, spreadsheets, databases and apps, connected into one knowledge base, so you can simply ask."),
    ('connect', "Add knowledge in seconds: upload files, snap a photo on your phone, or connect cloud storage like Google Drive and SharePoint. A step-by-step guide helps with each one."),
    ('unify', "Lapi reads every page, even scans, and keeps it all in datasets, indexed with the models your administrator chose."),
    ('ask', "Then just ask, in plain words. Every answer shows its sources, so you can check it."),
    ('extract', "Need data out? Lapi suggests the fields, pulls them out, and you review each value next to its source."),
    ('skills', "Teach the agent with skills: a short playbook for a kind of document. Add one once, and Lapi uses it whenever it fits."),
    ('secure', "Single sign-on, access per dataset, and an activity log keep everything safe. You're ready. Start with Quick start on your dashboard."),
]


async def main():
    text = ' '.join(line for _, line in SCENES)
    communicate = edge_tts.Communicate(text, VOICE, rate='-4%', pitch='+0Hz', boundary='WordBoundary')
    words = []
    with open(OUT / 'voice.mp3', 'wb') as audio:
        async for chunk in communicate.stream():
            if chunk['type'] == 'audio': audio.write(chunk['data'])
            elif chunk['type'] == 'WordBoundary':
                words.append({'t': chunk['offset'] / 1e7, 'd': chunk['duration'] / 1e7, 'w': chunk['text']})
    assert words, 'no word boundaries from the voice service'
    # Scene boundaries: find each scene's first two words in the spoken word stream, in order.
    norm = lambda w: re.sub(r'[^a-z0-9]', '', w.lower())
    scenes, i = [], 0
    for n, (sid, line) in enumerate(SCENES):
        first = [norm(w) for w in line.split()[:2]]
        j = i
        while j < len(words) - 1 and not (norm(words[j]['w']).startswith(first[0]) and norm(words[j + 1]['w']).startswith(first[1][:3])): j += 1
        scenes.append({'id': sid, 'text': line, 'start': round(words[j]['t'], 3)})
        i = j + 1
    for n, s in enumerate(scenes):
        last = words[-1] if n == len(scenes) - 1 else words[max(0, [k for k, w in enumerate(words) if w['t'] >= scenes[n + 1]['start']][0] - 1)]
        s['end'] = round(last['t'] + last['d'], 3)
    json.dump({'voice': VOICE, 'words': words, 'scenes': scenes}, open(OUT / 'voice.json', 'w'), indent=1)
    print('words', len(words), 'end', scenes[-1]['end'])
    for s in scenes: print(f"{s['id']:8} {s['start']:6.2f} - {s['end']:6.2f}")

asyncio.run(main())
