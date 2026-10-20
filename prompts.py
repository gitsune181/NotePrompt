"""Đọc niches.json (chỉ đọc) và ghép prompt giống các nút Prom / Go / Img.

Định dạng file lấy theo dữ liệu có sẵn, mỗi entry là 1 Niche hoặc 1 Kênh:
  prompt_solo              : ô "PROMPT riêng"            -> nút Prom
  prompts [{name,text}]    : Prompt A/B/C/D + active    -> nút Go (nối Style)
  prompt_img               : Prompt Gen Ảnh             -> nút Img (nối Style)
  styles [{name,text}]     : Style + active_style (1-based, 0 = không nối)
Các key bắt đầu bằng "__" (trừ "__default__") là dữ liệu phụ, bỏ qua.
"""
import json
import os

def load(path):
    """Trả về list entry đã sắp xếp: Niche trước, Kênh sau, Default cuối."""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError('File không đúng định dạng niches.json')

    entries = []
    for key, cfg in data.items():
        if not isinstance(cfg, dict):
            continue
        if key.startswith('__') and key != '__default__':
            continue
        if key == '__default__':
            kind = 'default'
        else:
            kind = 'channel' if cfg.get('kind') == 'channel' else 'niche'
        entries.append({
            'key': key,
            'name': 'Default' if kind == 'default' else key,
            'kind': kind,
            'color': cfg.get('color') or '',
            'note': (cfg.get('inline_note') or cfg.get('note') or '').strip(),
            'prom': prompt_solo(cfg),
            'go': active_prompt(cfg),
            'img': prompt_img(cfg),
        })

    order = {'niche': 0, 'channel': 1, 'default': 2}
    entries.sort(key=lambda e: (order[e['kind']], e['name'].upper()))
    return entries


def _active_style(cfg):
    styles = cfg.get('styles')
    if not isinstance(styles, list):
        return ''
    try:
        si = int(cfg.get('active_style', 0))
    except (TypeError, ValueError):
        si = 0
    if 1 <= si <= len(styles):
        s = styles[si - 1]
        return ((s.get('text') if isinstance(s, dict) else s) or '').strip()
    return ''


def prompt_solo(cfg):
    """Nút Prom: ô PROMPT riêng, không nối Style."""
    return cfg.get('prompt_solo') or ''


def active_prompt(cfg):
    """Nút Go: Prompt A/B/C/D đang chọn "Đang chạy" + Style đang dùng."""
    arr = cfg.get('prompts')
    if isinstance(arr, list) and arr:
        items = [(v.get('text') if isinstance(v, dict) else v) or '' for v in arr]
    elif (cfg.get('prompt_a') or '').strip():
        items = [cfg['prompt_a']]
    else:
        return ''
    try:
        ai = int(cfg.get('active', 1))
    except (TypeError, ValueError):
        ai = 1
    if not 1 <= ai <= len(items):
        ai = 1
    text = items[ai - 1]
    style = _active_style(cfg)
    if style:
        text = (text.rstrip() + '\n\n' + style) if text.strip() else style
    return text


def prompt_img(cfg):
    """Nút Img: Prompt Gen Ảnh + Style đang dùng."""
    text = (cfg.get('prompt_img') or '').strip()
    if not text:
        return ''
    style = _active_style(cfg)
    if style:
        text = text.rstrip() + '\n\n' + style
    return text


def mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None
