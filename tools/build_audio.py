"""Record the final script with Edge neural voices, plus word timings.

Reads Q from index.html (via node), writes
  audio/{n,s}/{qi}-{k}.mp3   k=0 question (female interviewer), k>=1 answer sentences (male)
  audio/cues.json            {"n": {"qi-k": [word start sec, ...]}, "s": {...}}
n = normal speed, s = slow (-25%). Word starts let the app play just the first 1, 2 or half the words.
Run from kaist-interview/:  python tools/build_audio.py
"""
import asyncio, json, os, re, subprocess
import edge_tts

html = open('index.html', encoding='utf-8').read()
qsrc = re.search(r'const Q=(\[.*?\]\]\}\]);', html, re.S).group(1)
Q = json.loads(subprocess.run(['node', '-e', f'process.stdout.write(JSON.stringify({qsrc}))'], capture_output=True, text=True, encoding='utf-8').stdout)
ASKER, ME = 'en-US-AriaNeural', 'en-US-AndrewNeural'
SPEEDS = {'n': '-5%', 's': '-25%'}

async def rec(text, voice, rate, path):
    for tries in range(5):  # Edge TTS sometimes returns no audio; retry
        try:
            starts, audio = [], b''
            async for m in edge_tts.Communicate(text.replace('—', ','), voice, rate=rate, boundary='WordBoundary').stream():
                if m['type'] == 'audio': audio += m['data']
                elif m['type'] == 'WordBoundary': starts.append(round(m['offset'] / 1e7, 3))
            if not audio: raise edge_tts.exceptions.NoAudioReceived
            open(path, 'wb').write(audio)
            return starts
        except edge_tts.exceptions.NoAudioReceived:
            await asyncio.sleep(2 + tries * 3)
    raise SystemExit(f'failed: {text}')

async def main():
    cues = {}
    for sp, rate in SPEEDS.items():
        os.makedirs(f'audio/{sp}', exist_ok=True); cues[sp] = {}
        for qi, q in enumerate(Q):
            for k, (text, voice) in enumerate([(q['q'], ASKER)] + [(en, ME) for en, _ in q['s']]):
                st = await rec(text, voice, rate, f'audio/{sp}/{qi}-{k}.mp3')
                n = len([w for w in text.split(' ') if w != '—'])
                assert len(st) == n, (text, len(st), n)  # app cuts by word index, so counts must match
                cues[sp][f'{qi}-{k}'] = st
    json.dump(cues, open('audio/cues.json', 'w'))
    print('clips:', sum(len(v) for v in cues.values()))

asyncio.run(main())
