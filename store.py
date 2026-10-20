"""File dữ liệu riêng của NotePrompt (sửa được trong app), tách khỏi niches.json của Auto Prompt.

Định dạng:
  {"app": "NotePrompt", "version": 1,
   "items": [{"key", "kind": niche|channel|default, "note", "prom", "go", "img"}]}
Lần đầu chạy thì chép dữ liệu từ niches.json sang (Go/Img đã nối sẵn Style).
"""
import json
import os

import prompts

FIELDS = ('prom', 'go', 'img')
KINDS = ('niche', 'channel', 'default')


def _clean(raw):
    kind = raw.get('kind') if raw.get('kind') in KINDS else 'niche'
    item = {'key': str(raw.get('key') or '').strip(), 'kind': kind,
            'note': str(raw.get('note') or '')}
    for f in FIELDS:
        item[f] = str(raw.get(f) or '')
    return item


def load(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get('items'), list):
        raise ValueError('File không đúng định dạng dữ liệu NotePrompt')
    items = [_clean(x) for x in data['items'] if isinstance(x, dict)]
    return [x for x in items if x['key']]


def save(path, items):
    """Ghi qua file tạm rồi thay thế, để không bị hỏng file nếu đang ghi dở."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    data = {'app': 'NotePrompt', 'version': 1, 'items': [_clean(x) for x in items]}
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def from_niches(path):
    """Đọc niches.json (chỉ đọc) và chuyển sang dạng item của NotePrompt."""
    out = []
    for e in prompts.load(path):
        out.append(_clean({'key': 'Default' if e['kind'] == 'default' else e['key'],
                           'kind': e['kind'], 'note': e['note'],
                           'prom': e['prom'], 'go': e['go'], 'img': e['img']}))
    return out


# ---------------------------------------------------------------- lịch sử sửa
HISTORY_KEEP = 20   # số bản cũ giữ lại cho mỗi niche/kênh


def load_history(path):
    """{key: [{'time': 'dd/mm/yyyy HH:MM', 'values': {key, note, prom, go, img}}, ...]} — mới nhất trước."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if isinstance(v, list)} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_history(path, history):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
