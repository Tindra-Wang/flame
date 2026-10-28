"""Remote real-data link import: fetch a dataset archive server-side, unpack a reviewable subset.

Direct ZIP links are streamed to disk; figshare (including institutional hosts) article
pages are resolved through the public API. Private/loopback destinations are refused at
every hop so the platform never fetches attacker-controlled intranet addresses (SSRF).

Accepted archive formats: COCO (coco.json + images/) and YOLO (data.yaml + images/ +
labels/). Remote archives are frequently far larger than the 3000-entry/150MB import
caps (e.g. the raw CQU export), so only a deterministic fire-first sample is extracted
and the annotation file is rewritten to the kept subset.
"""
import io
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

MAX_DOWNLOAD_BYTES = 800 * 1024 * 1024
MAX_FILES = 2999
MAX_UNPACK_BYTES = 150 * 1024 * 1024
USER_AGENT = 'ai07-platform-import/1.0'
# Same sampling defaults as scripts/value_chain.py convert.
YOLO_MAX_FIRE = 900
YOLO_MAX_NEGATIVE = 350
YOLO_MAX_SIDE = 640
YOLO_JPEG_QUALITY = 82


def assert_public_url(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise ValueError('来源链接必须是 http/https 地址')
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except OSError as exc:
        raise ValueError('无法解析来源链接主机：%s' % parsed.hostname) from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        # 198.18.0.0/15 is the fake-IP range used by local VPN/proxy DNS (Clash TUN etc.):
        # every public hostname resolves into it and the proxy forwards the connection,
        # so it is not an intranet target. Real private/loopback ranges stay blocked.
        if ip in ipaddress.ip_network('198.18.0.0/15'):
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError('来源链接不允许指向内网或本机地址')


class _GuardedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        assert_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def resolve_figshare(url):
    """Article page -> downloadable ZIP via the figshare API; None when not an article page."""
    parsed = urllib.parse.urlparse(url)
    match = re.fullmatch(r'/articles/(?:[a-z]+/)?(?:[^/]+/)?(\d{4,})', parsed.path.rstrip('/'))
    if not match:
        return None
    article = match.group(1)
    bases = ['%s://%s/api' % (parsed.scheme, parsed.hostname), 'https://api.figshare.com/v2']
    for base in bases:
        try:
            request = urllib.request.Request('%s/articles/%s' % (base, article), headers={'User-Agent': USER_AGENT})
            with urllib.request.build_opener(_GuardedRedirect).open(request, timeout=30) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            files = [f for f in data.get('files', []) if str(f.get('name', '')).lower().endswith('.zip')]
            if files:
                best = max(files, key=lambda f: f.get('size') or 0)
                return best.get('download_url'), best.get('name') or 'figshare-%s.zip' % article
        except (OSError, ValueError, KeyError):
            continue
    return None


def fetch_remote_archive(url, workdir: Path):
    """Download the dataset ZIP behind a user link. Returns (recorded_url, zip_path, name)."""
    assert_public_url(url)
    resolved, name = url, None
    if not url.lower().split('?')[0].endswith('.zip'):
        hit = resolve_figshare(url)
        if hit:
            resolved, name = hit
            assert_public_url(resolved)
    request = urllib.request.Request(resolved, headers={'User-Agent': USER_AGENT})
    target = workdir / 'remote.zip'
    try:
        with urllib.request.build_opener(_GuardedRedirect).open(request, timeout=120) as resp:
            content_type = (resp.headers.get('Content-Type') or '').lower()
            if 'text/html' in content_type:
                raise ValueError('该链接返回的是网页而不是ZIP；请填数据集的直接下载地址（figshare 条目的 Download 链接即可，页面链接会自动解析）')
            total = 0
            with target.open('wb') as out:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise ValueError('远端压缩包超过800MB下载上限；请先用 scripts/value_chain.py convert 本地采样再上传')
                    out.write(chunk)
    except urllib.error.HTTPError as exc:
        raise ValueError('来源链接下载失败：HTTP %s' % exc.code) from exc
    except urllib.error.URLError as exc:
        raise ValueError('来源链接无法访问：%s' % getattr(exc, 'reason', exc)) from exc
    if not name:
        name = urllib.parse.unquote(urllib.parse.urlparse(resolved).path.rsplit('/', 1)[-1]) or '真实数据链接导入'
    return resolved, target, name


def store_coco_subset(archive, unpack: Path):
    """Extract a fire-first deterministic sample within the import budgets.

    Returns sampling statistics for the audit trail; mode is 'coco' or 'yolo'.
    """
    with zipfile.ZipFile(archive) as z:
        entries = {}
        for item in z.infolist():
            if not item.is_dir():
                entries.setdefault(item.filename.replace('\\', '/'), item)
        coco_name = next((n for n in sorted(entries) if n.endswith('coco.json') and n.count('/') <= 1), None)
        if coco_name:
            return _store_coco(z, entries, coco_name, unpack)
        yaml_name = next((n for n in sorted(entries) if n.endswith('data.yaml') and n.count('/') <= 1), None)
        if yaml_name:
            return _store_yolo(z, entries, yaml_name, unpack)
        raise ValueError('压缩包里既没有 coco.json 也没有 data.yaml（支持 COCO 或 YOLO 格式）')


def _store_coco(z, entries, coco_name, unpack: Path):
    root = coco_name[:-len('coco.json')]
    try:
        coco = json.loads(z.read(entries[coco_name]).decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('coco.json 不是合法 JSON') from exc
    images = coco.get('images') or []

    def member_of(file_name):
        clean = str(file_name or '').replace('\\', '/').lstrip('/')
        if not clean or '..' in clean.split('/'):
            return None
        for cand in (root + clean, root + 'images/' + clean):
            if cand in entries:
                return cand
        return None

    fire_ids = {a.get('image_id') for a in coco.get('annotations') or []}
    ordered = [im for im in images if im.get('id') in fire_ids] + [im for im in images if im.get('id') not in fire_ids]
    budget = MAX_UNPACK_BYTES
    kept, missing, skipped = [], 0, 0
    for image in ordered:
        member = member_of(image.get('file_name', ''))
        if member is None:
            missing += 1
            continue
        size = entries[member].file_size
        if len(kept) >= MAX_FILES or size > budget:
            skipped += 1
            continue
        budget -= size
        kept.append((member, image))
    if missing and not kept:
        raise ValueError('coco.json 引用的图片都不在压缩包的 images 目录里')
    if not kept:
        raise ValueError('压缩包图片超出导入预算，没有可保留样本；请先本地采样')
    keep_ids = {image['id'] for _, image in kept}
    coco['images'] = [im for im in images if im.get('id') in keep_ids]
    coco['annotations'] = [a for a in coco.get('annotations') or [] if a.get('image_id') in keep_ids]
    (unpack / 'coco.json').write_text(json.dumps(coco, ensure_ascii=False), encoding='utf-8')
    images_root = (unpack / 'images').resolve()
    for member, image in kept:
        item = entries[member]
        clean = str(image['file_name']).replace('\\', '/').lstrip('/')
        dest = (unpack / 'images' / clean).resolve()
        if not dest.is_relative_to(images_root) or item.flag_bits & 1:
            raise ValueError('压缩包包含非法路径或加密文件')
        dest.parent.mkdir(parents=True, exist_ok=True)
        with z.open(item) as src, dest.open('wb') as out:
            out.write(src.read())
    return {'mode': 'coco', 'kept': len(kept), 'total': len(images), 'skipped': skipped, 'missing': missing}


def _yolo_classes(yaml_text):
    block = re.search(r'names:\s*((?:\n?\s*-\s*.+)+)', yaml_text)
    inline = re.search(r'names:\s*\[([^\]]+)\]', yaml_text)
    if block:
        classes = [m.strip().strip('\'"') for m in re.findall(r'-\s*(.+)', block.group(1))]
    elif inline:
        classes = [m.strip().strip('\'"') for m in inline.group(1).split(',')]
    else:
        raise ValueError('data.yaml 中找不到类别表')
    fire_index = next((i for i, name in enumerate(classes) if name.strip().lower() == 'fire'), None)
    if fire_index is None:
        raise ValueError('类别表中没有 fire 类：%r' % classes)
    return fire_index


def _yolo_fire_boxes(text, fire_index):
    boxes = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5 or int(float(parts[0])) != fire_index:
            continue
        cx, cy, bw, bh = (float(v) for v in parts[1:5])
        boxes.append([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2])
    return boxes


def _store_yolo(z, entries, yaml_name, unpack: Path):
    from PIL import Image
    fire_index = _yolo_classes(z.read(entries[yaml_name]).decode('utf-8', 'replace'))
    pairs = []
    for name in entries:
        if not re.search(r'/images/[^/]+\.(jpe?g|png)$', name, re.I):
            continue
        label = re.sub(r'/images/', '/labels/', re.sub(r'\.(jpe?g|png)$', '.txt', name, flags=re.I))
        if label in entries:
            pairs.append((name, label))
    if not pairs:
        raise ValueError('YOLO 压缩包里没有成对的 images/labels 数据')
    with_fire, negatives = [], []
    for image_name, label_name in pairs:
        boxes = _yolo_fire_boxes(z.read(entries[label_name]).decode('utf-8', 'replace'), fire_index)
        (with_fire if boxes else negatives).append((image_name, boxes))

    def quota(items, cap):
        step = max(1, len(items) // cap) if len(items) > cap else 1
        return items[::step][:cap]

    picked = quota(with_fire, YOLO_MAX_FIRE) + quota(negatives, YOLO_MAX_NEGATIVE)
    budget = MAX_UNPACK_BYTES - entries[yaml_name].file_size
    images_out, annotations, skipped = [], [], 0
    for index, (image_name, boxes) in enumerate(picked, start=1):
        raw = z.read(entries[image_name])
        with Image.open(io.BytesIO(raw)) as im:
            im = im.convert('RGB')
            width0, height0 = im.size
            scale = min(1.0, YOLO_MAX_SIDE / max(width0, height0))
            if scale < 1.0:
                im = im.resize((round(width0 * scale), round(height0 * scale)), Image.LANCZOS)
            width, height = im.size
            chunk = io.BytesIO()
            im.save(chunk, 'JPEG', quality=YOLO_JPEG_QUALITY)
            blob = chunk.getvalue()
        if len(images_out) >= MAX_FILES or len(blob) > budget:
            skipped += 1
            continue
        budget -= len(blob)
        file_name = 'images/%05d.jpg' % len(images_out)
        dest = (unpack / file_name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
        stem = re.sub(r'\.(jpe?g|png)$', '', image_name.rsplit('/', 1)[-1], flags=re.I)
        lead = re.match(r'(\d+)', stem)
        cluster = lead.group(1) if lead else str(index)
        group = '%s-%s-%02d' % (image_name.split('/')[0], cluster[:6], int(cluster) % 3)
        images_out.append({'id': len(images_out) + 1, 'file_name': file_name.rsplit('/', 1)[-1],
                           'width': width, 'height': height, 'group_id': group})
        for x, y, x2, y2 in boxes:
            annotations.append({'image_id': images_out[-1]['id'], 'category_id': 1,
                                'bbox': [round(x * width, 1), round(y * height, 1),
                                         round((x2 - x) * width, 1), round((y2 - y) * height, 1)],
                                'iscrowd': 0})
    if not images_out:
        raise ValueError('YOLO 压缩包图片超出导入预算，没有可保留样本；请先本地采样')
    coco = {'images': images_out, 'annotations': annotations, 'categories': [{'id': 1, 'name': 'fire'}]}
    (unpack / 'coco.json').write_text(json.dumps(coco, ensure_ascii=False), encoding='utf-8')
    return {'mode': 'yolo', 'kept': len(images_out), 'total': len(pairs), 'skipped': skipped, 'missing': 0}
