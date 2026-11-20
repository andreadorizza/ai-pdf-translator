"""Headless mode: the same files, translated through a provider API instead of an agent's subagents.
Used by the Colab notebook, the self-test and scripts.

  anthropic  ANTHROPIC_API_KEY
  openai     OPENAI_API_KEY, any OpenAI-compatible API with --base-url (OpenRouter, Gemini, a local server)
"""
import base64
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests


class Service:
    def __init__(self, name, model, base_url=None):
        self.name, self.model = name, model
        if name == 'anthropic':
            self.key = os.environ.get('ANTHROPIC_API_KEY')
            self.url = (base_url or 'https://api.anthropic.com') + '/v1/messages'
        elif name == 'openai':
            self.key = os.environ.get('OPENAI_API_KEY')
            self.url = (base_url or 'https://api.openai.com/v1').rstrip('/') + '/chat/completions'
        else:
            raise SystemExit(f'Unknown service "{name}": use anthropic or openai')
        if not self.key:
            raise SystemExit(f'Set {"ANTHROPIC_API_KEY" if name == "anthropic" else "OPENAI_API_KEY"} first.')
        self.usage = {'input_tokens': 0, 'output_tokens': 0, 'calls': 0}

    def ask(self, system, text, images=()):
        for attempt in range(4):
            try:
                out = self._ask(system, text, images)
                body = out[out.index('{'): out.rindex('}') + 1]
                return json.loads(body)
            except (requests.RequestException, ValueError, KeyError) as e:
                err = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f'{self.name} {self.model} failed after 4 attempts: {err}')

    def _ask(self, system, text, images):
        if self.name == 'anthropic':
            content = [{'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png',
                                                    'data': base64.b64encode(Path(i).read_bytes()).decode()}}
                       for i in images] + [{'type': 'text', 'text': text}]
            r = requests.post(self.url, timeout=600, headers={
                'x-api-key': self.key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
                json={'model': self.model, 'max_tokens': 16000, 'system': system,
                      'messages': [{'role': 'user', 'content': content}]})
            r.raise_for_status()
            d = r.json()
            self._count(d['usage'].get('input_tokens', 0), d['usage'].get('output_tokens', 0))
            return ''.join(b.get('text', '') for b in d['content'])
        content = [{'type': 'text', 'text': text}] + [
            {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(Path(i).read_bytes()).decode()}}
            for i in images]
        r = requests.post(self.url, timeout=600, headers={'Authorization': f'Bearer {self.key}'},
                          json={'model': self.model, 'messages': [{'role': 'system', 'content': system},
                                                                  {'role': 'user', 'content': content}]})
        r.raise_for_status()
        d = r.json()
        u = d.get('usage') or {}
        self._count(u.get('prompt_tokens', 0), u.get('completion_tokens', 0))
        return d['choices'][0]['message']['content']

    def _count(self, i, o):
        self.usage['input_tokens'] += i
        self.usage['output_tokens'] += o
        self.usage['calls'] += 1


def _read(work, name):
    return (Path(work) / name).read_text()


def terms(work, svc):
    work = Path(work)
    out = work / 'terms' / 'terms.json'
    if out.exists():
        return
    cands = json.loads((work / 'terms' / 'candidates.json').read_text())
    if not cands['phrases'] and not cands['definitions']:
        out.write_text('{}')
        return
    res = svc.ask(_read(work, 'TERMS.md') + '\nReturn only the JSON object.', json.dumps(cands, ensure_ascii=False))
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1))


def translate_batches(work, svc, workers=4):
    work = Path(work)
    todo = [f for f in sorted((work / 'batches').glob('*.json')) if not (work / json.loads(f.read_text())['output']).exists()]

    def one(f):
        b = json.loads(f.read_text())
        terms = b['terms'] if isinstance(b['terms'], dict) else {}
        system = b['instructions'] + (('\n\nTerms (source = English):\n' + '\n'.join(f'{k} = {v}' for k, v in terms.items()))
                                      if terms else '') + '\nReturn only the JSON object for the output file.'
        res = svc.ask(system, json.dumps({k: b[k] for k in ('batch', 'paragraphs')}, ensure_ascii=False))
        res['batch'] = b['batch']
        (work / b['output']).write_text(json.dumps(res, ensure_ascii=False, indent=1))
        return b['batch'], len(b['paragraphs']), len(res.get('translations', {}))

    with ThreadPoolExecutor(workers) as ex:
        for batch, n, got in ex.map(one, todo):
            print(f'  batch {batch}: {got}/{n} paragraphs', flush=True)


def pictures(work, svc, workers=4):
    """Read the contact sheets of every picture task (headless mode)."""
    work = Path(work)
    system = _read(work, 'PICTURES.md') + '\nThe contact sheets are attached in the order listed. Return only the JSON object.'
    todo = [f for f in sorted((work / 'pictures').glob('[0-9][0-9][0-9].json'))
            if not (work / json.loads(f.read_text())['output']).exists()]

    def one(f):
        task = json.loads(f.read_text())
        listing = json.dumps([{'picture': s['picture'], 'sheet': i + 1} for i, s in enumerate(task['sheets'])])
        res = svc.ask(system, 'Sheets, in order: ' + listing, [work / s['file'] for s in task['sheets']])
        (work / task['output']).write_text(json.dumps(res, ensure_ascii=False, indent=1))
        return task['task'], sum(len(v) for v in res.values())

    with ThreadPoolExecutor(workers) as ex:
        for name, n in ex.map(one, todo):
            print(f'  pictures {name}: {n} labels', flush=True)


def scan_check(work, svc, files, workers=4):
    work = Path(work)
    system = _read(work, 'SCANCHECK.md') + '\nThe crops are attached in the order of the items. Return only the JSON object.'

    def one(f):
        c = json.loads(f.read_text())
        out = work / c['output']
        if out.exists():
            return c['check'], 0
        items = [{k: v for k, v in it.items() if k != 'image'} for it in c['items']]
        res = svc.ask(system, json.dumps(items, ensure_ascii=False), [work / it['image'] for it in c['items']])
        out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
        return c['check'], sum(bool(r.get('changed')) for r in res.values())

    with ThreadPoolExecutor(workers) as ex:
        for check, changed in ex.map(one, files):
            print(f'  scan check {check}: {changed} changed', flush=True)
