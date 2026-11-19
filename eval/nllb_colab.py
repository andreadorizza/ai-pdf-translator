"""Free baseline: NLLB-200 3.3B (CC-BY-NC) translating the same OCR blocks. Runs on a Colab T4."""
import json, re, sys, time, torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
src, out = sys.argv[1], sys.argv[2]
name = 'facebook/nllb-200-3.3B'
tok = AutoTokenizer.from_pretrained(name, src_lang='lao_Laoo')
model = AutoModelForSeq2SeqLM.from_pretrained(name, torch_dtype=torch.float16).to('cuda').eval()
blocks = json.load(open(src))
def segments(t, n=180):   # NLLB is a sentence model: cut at punctuation, then at spaces
    parts, cur = [], ''
    for piece in re.split(r'(?<=[;:.!?])\s+', t):
        while len(piece) > n:
            cut = piece.rfind(' ', 0, n); cut = cut if cut > 40 else n
            parts.append((cur + ' ' + piece[:cut]).strip()); cur = ''; piece = piece[cut:]
        if len(cur) + len(piece) > n: parts.append(cur.strip()); cur = ''
        cur += ' ' + piece
    if cur.strip(): parts.append(cur.strip())
    return [p for p in parts if p]
segs = [(b['id'], s) for b in blocks for s in segments(b['text'])]
print(len(blocks), 'blocks', len(segs), 'segments', flush=True)
res, t = {}, time.time()
for i in range(0, len(segs), 16):
    batch = segs[i:i + 16]
    enc = tok([s for _, s in batch], return_tensors='pt', padding=True, truncation=True, max_length=400).to('cuda')
    with torch.inference_mode():
        gen = model.generate(**enc, forced_bos_token_id=tok.convert_tokens_to_ids('eng_Latn'), num_beams=4, max_new_tokens=300)
    for (bid, _), e in zip(batch, tok.batch_decode(gen, skip_special_tokens=True)):
        res.setdefault(bid, []).append(e)
    print(i, round(time.time() - t), flush=True)
json.dump({'model': name, 'chunks': [{'translations': {k: ' '.join(v) for k, v in res.items()}}]}, open(out, 'w'), ensure_ascii=False, indent=1)
print('DONE', round(time.time() - t), 's', flush=True)
