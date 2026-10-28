# -*- coding: utf-8 -*-
"""AI-07 价值证据链自动化工具（高内聚、可复用）。

一条命令跑通：公开数据集 → COCO 采样转换 → 平台导入 → 审核 → DVC 版本 → A/B 检测对照。
每个子命令独立可用；平台交互全部走公开 REST API（/api/*），不直接碰数据库。

用法示例：
  python scripts/value_chain.py convert --src .cache/realdata/MyData_Fire.zip --out .cache/realdata/real_fire_coco.zip
  python scripts/value_chain.py register --username value_bot --password <pwd>
  python scripts/value_chain.py import --zip .cache/realdata/real_fire_coco.zip \
      --source-url https://doi.org/10.25901/... --license-note "CC BY 4.0 ..."
  python scripts/value_chain.py approve --run <run_id>
  python scripts/value_chain.py version --run <run_id> --name v1.0.0-real-cqu
  python scripts/value_chain.py ab --real v1.0.0-real-cqu --syn v0.2.0-volume-fire
  python scripts/value_chain.py status
"""
import argparse
import http.cookiejar
import io
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
import zipfile

DEFAULT_BASE = 'http://localhost:3000'
FIRE_CATEGORY = [{"id": 1, "name": "fire"}]


class Api:
    """薄会话客户端：Cookie 会话 + Origin 门禁 + 统一错误信息。"""

    def __init__(self, base=DEFAULT_BASE):
        self.base = base.rstrip('/')
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def _open(self, method, path, data=None, headers=None, timeout=120):
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header('Origin', self.base)  # 后端 Origin 白名单要求
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        with self.opener.open(req, timeout=timeout) as r:
            body = r.read()
        return json.loads(body) if body else {}

    def get(self, path):
        return self._open('GET', path)

    def post_json(self, path, payload, timeout=900):
        return self._open('POST', path, json.dumps(payload).encode(), {'Content-Type': 'application/json'}, timeout=timeout)

    def post_multipart(self, path, fields, file_field, file_path, file_name):
        boundary = '----ai07valuechain'
        parts = []
        for k, v in fields.items():
            parts.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s' % (boundary, k, v)).encode())
        with open(file_path, 'rb') as f:
            blob = f.read()
        parts.append(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\n'
                      'Content-Type: application/zip\r\n\r\n' % (boundary, file_field, file_name)).encode())
        parts.append(blob)
        parts.append(('--%s--\r\n' % boundary).encode())
        body = b'\r\n'.join(parts)
        return self._open('POST', path, body, {
            'Content-Type': 'multipart/form-data; boundary=%s' % boundary,
        }, timeout=600)

    def login_or_register(self, username, password, role='tester'):
        auth = self.get('/api/auth')
        if auth.get('user'):
            return auth['user']
        endpoint = '/api/setup' if auth.get('setup_required') else '/api/login'
        try:
            return self.post_json(endpoint, {'username': username, 'password': password})
        except urllib.error.HTTPError as e:
            detail = json.loads(e.read()).get('detail', '')
            if endpoint == '/api/login' and '不正确' in detail:
                return self.post_json('/api/register', {'username': username, 'password': password, 'role': role})
            raise


def cmd_convert(args):
    """Roboflow/YOLO 数据集 zip → 平台可导入的 COCO fire zip（采样+压缩+分组）。"""
    from PIL import Image  # 延迟导入：仅 convert 需要

    src_zip, out_zip = args.src, args.out
    max_side, quality = args.max_side, args.jpeg_quality
    z = zipfile.ZipFile(src_zip)
    names = z.namelist()

    yaml_txt = next((z.read(n).decode('utf-8') for n in names if n.endswith('data.yaml')), '')
    name_match = re.search(r'names:\s*((?:\n?\s*-\s*.+)+)', yaml_txt)
    inline_match = re.search(r'names:\s*\[([^\]]+)\]', yaml_txt)
    if name_match:
        classes = [m.strip().strip("'\"") for m in re.findall(r'-\s*(.+)', name_match.group(1))]
    elif inline_match:
        classes = [m.strip().strip("'\"") for m in inline_match.group(1).split(',')]
    else:
        raise SystemExit('data.yaml 中找不到类别名')
    fire_idx = next((i for i, c in enumerate(classes) if c.strip().lower() == 'fire'), None)
    if fire_idx is None:
        raise SystemExit('类别表中没有 fire 类: %r' % classes)
    print('类别表: %r → fire=%d' % (classes, fire_idx))

    # 收集 (split, image, label) 三元组
    pairs = []
    for n in names:
        if not re.search(r'/(images)/[^/]+\.(jpe?g|png)$', n, re.I):
            continue
        label = re.sub(r'/images/', '/labels/', re.sub(r'\.(jpe?g|png)$', '.txt', n, flags=re.I))
        if label in names:
            split = n.split('/')[0]
            pairs.append((split, n, label))
    print('带标注图片对: %d' % len(pairs))

    # 先分类：有 fire 框 / 无框（负例或非 fire 类）
    with_fire, negatives = [], []
    for split, img, label in pairs:
        boxes = parse_yolo(z.read(label).decode('utf-8'), fire_idx)
        (with_fire if boxes else negatives).append((split, img, boxes))
    print('含 fire 框: %d · 无 fire 框（保留作负例）: %d' % (len(with_fire), len(negatives)))

    def quota(items, cap):
        step = max(1, len(items) // cap) if len(items) > cap else 1
        return items[::step][:cap]

    picked = quota(with_fire, args.max_fire) + quota(negatives, args.max_negative)
    if len(picked) + 1 > 3000:
        raise SystemExit('平台单次导入文件数上限 3000，当前 %d' % (len(picked) + 1))
    print('采样: %d 张（fire %d + 负例 %d）' % (len(picked), min(len(with_fire), args.max_fire), min(len(negatives), args.max_negative)))

    images, annotations = [], []
    buf = io.BytesIO()
    out = zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED)
    for idx, (split, img_name, boxes) in enumerate(picked, start=1):
        stem = os.path.splitext(os.path.basename(img_name))[0]
        # group_id：文件名前导数字（通常为来源视频/批次号）聚类，防训练测试泄漏
        lead = re.match(r'(\d+)', stem)
        cluster = lead.group(1) if lead else str(idx)
        group = '%s-%s-%02d' % (split, cluster[:6], int(cluster) % 3)
        raw = z.read(img_name)
        with Image.open(io.BytesIO(raw)) as im:
            im = im.convert('RGB')
            w0, h0 = im.size
            scale = min(1.0, max_side / max(w0, h0))
            if scale < 1.0:
                im = im.resize((round(w0 * scale), round(h0 * scale)), Image.LANCZOS)
            w, h = im.size
            target = 'images/%05d.jpg' % idx
            chunk = io.BytesIO()
            im.save(chunk, 'JPEG', quality=quality)
            out.writestr(target, chunk.getvalue())
        images.append({'id': idx, 'file_name': os.path.basename(target), 'width': w, 'height': h, 'group_id': group})
        for x, y, x2, y2 in boxes:
            bx, by = x * w, y * h
            annotations.append({'image_id': idx, 'category_id': 1,
                                'bbox': [round(bx, 1), round(by, 1), round((x2 - x) * w, 1), round((y2 - y) * h, 1)],
                                'iscrowd': 0})
    coco = {'images': images, 'annotations': annotations, 'categories': FIRE_CATEGORY}
    out.writestr('coco.json', json.dumps(coco, ensure_ascii=False))
    out.close()
    blob = buf.getvalue()
    if len(blob) > 48 * 1024 * 1024:
        raise SystemExit('产物 %.1fMB 超过 50MB 上限；调低 --jpeg-quality 或 --max-fire/--max-negative' % (len(blob) / 1048576))
    os.makedirs(os.path.dirname(os.path.abspath(out_zip)), exist_ok=True)
    with open(out_zip, 'wb') as f:
        f.write(blob)
    stats = {}
    for im_ in images:
        stats[im_['group_id'].split('-')[0]] = stats.get(im_['group_id'].split('-')[0], 0) + 1
    print('OK %s · %.1fMB · %d 图 / %d 框 · 分组数 %d · 分布 %r'
          % (out_zip, len(blob) / 1048576, len(images), len(annotations), len({i['group_id'] for i in images}), stats))


def parse_yolo(txt, fire_idx):
    boxes = []
    for line in txt.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        if int(float(parts[0])) != fire_idx:
            continue
        cx, cy, bw, bh = (float(v) for v in parts[1:5])
        boxes.append([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2])
    return boxes


def cmd_register(args):
    api = Api(args.base)
    user = api.login_or_register(args.username, args.password, args.role)
    print('OK 已登录:', user)


def cmd_import(args):
    api = Api(args.base)
    api.login_or_register(args.username, args.password)
    result = api.post_multipart('/api/projects/ai07/import-coco', {
        'source_url': args.source_url,
        'license_note': args.license_note,
    }, 'file', args.zip, os.path.basename(args.zip))
    print(json.dumps(result, ensure_ascii=False, indent=1))


def cmd_approve(args):
    api = Api(args.base)
    api.login_or_register(args.username, args.password)
    samples = api.get('/api/projects/ai07/samples')
    pending = [s for s in samples if s['run_id'] == args.run and s['review_status'] == 'pending']
    if args.limit:
        pending = pending[:args.limit]
    print('待审核: %d' % len(pending))
    done = 0
    for s in pending:
        api.post_json('/api/runs/%s/review' % args.run, {
            'sample_id': s['sample_id'], 'boxes': s['boxes'], 'decision': 'approved'})
        done += 1
        if done % 50 == 0:
            print('  已通过 %d/%d' % (done, len(pending)))
    print('OK 审核通过 %d 张（采信导入标注：label_source=imported_coco，人工确认见审计记录）' % done)


def cmd_version(args):
    api = Api(args.base)
    api.login_or_register(args.username, args.password)
    result = api.post_json('/api/projects/ai07/versions', {
        'run_id': args.run, 'name': args.name, 'research_snapshot': True})
    print(json.dumps(result, ensure_ascii=False, indent=1))


def cmd_ab(args):
    api = Api(args.base)
    api.login_or_register(args.username, args.password)
    versions = api.get('/api/projects/ai07/versions')
    by_name = {v['name']: v for v in versions}
    real = by_name.get(args.real)
    syn = by_name.get(args.syn)
    if not real or not syn:
        raise SystemExit('版本不存在: real=%s syn=%s · 现有 %r' % (args.real, args.syn, list(by_name)))
    payload = {'real_version': real['id'], 'synthetic_version': syn['id'],
               'weights': args.weights, 'epochs': args.epochs, 'batch': args.batch,
               'imgsz': args.imgsz, 'seed': args.seed}
    result = api.post_json('/api/projects/ai07/evaluations/detector-comparisons', payload)
    print(json.dumps(result, ensure_ascii=False, indent=1))


def cmd_status(args):
    api = Api(args.base)
    o = api.get('/api/projects/ai07/overview')
    print('候选 %s · 待审 %s · 已通过 %s · 真实 %s' % (o['samples'], o['pending'], o['approved'], o.get('real') or 0))
    for v in api.get('/api/projects/ai07/versions'):
        print('版本 %-24s %-9s %s' % (v['name'], v['status'], (v.get('result') or {}).get('splits') or ''))
    for e in api.get('/api/projects/ai07/experiments')[-3:]:
        print('实验 %s %s → %s' % (e['id'][:8], e['kind'], json.dumps(e.get('result', {}), ensure_ascii=False)[:160]))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--base', default=DEFAULT_BASE)
    sub = p.add_subparsers(dest='cmd', required=True)

    c = sub.add_parser('convert', help='YOLO/Roboflow 数据集 zip → 平台 COCO fire zip')
    c.add_argument('--src', required=True)
    c.add_argument('--out', required=True)
    c.add_argument('--max-fire', type=int, default=900)
    c.add_argument('--max-negative', type=int, default=350)
    c.add_argument('--max-side', type=int, default=640)
    c.add_argument('--jpeg-quality', type=int, default=82)
    c.set_defaults(func=cmd_convert)

    for name, fn, help_ in [('register', cmd_register, '注册/登录并保存会话'),
                            ('import', cmd_import, '导入 COCO zip 为真实数据批次'),
                            ('approve', cmd_approve, '批量通过一个批次的待审样本'),
                            ('version', cmd_version, '发布 DVC 研究快照'),
                            ('ab', cmd_ab, '提交 A/B 检测对照实验'),
                            ('status', cmd_status, '总览/版本/实验状态')]:
        c = sub.add_parser(name, help=help_)
        if name != 'status':
            c.add_argument('--username', default='value_bot')
            c.add_argument('--password', default='value-bot-pass-2026')
        if name == 'register':
            c.add_argument('--role', default='tester')
        if name == 'import':
            c.add_argument('--zip', required=True)
            c.add_argument('--source-url', required=True)
            c.add_argument('--license-note', required=True)
        if name == 'approve':
            c.add_argument('--run', required=True)
            c.add_argument('--limit', type=int, default=0)
        if name == 'version':
            c.add_argument('--run', required=True)
            c.add_argument('--name', required=True)
        if name == 'ab':
            c.add_argument('--real', required=True)
            c.add_argument('--syn', required=True)
            c.add_argument('--weights', default='yolo11n.pt')
            c.add_argument('--epochs', type=int, default=5)
            c.add_argument('--batch', type=int, default=4)
            c.add_argument('--imgsz', type=int, default=384)
            c.add_argument('--seed', type=int, default=42)
        c.set_defaults(func=fn)

    args = p.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
