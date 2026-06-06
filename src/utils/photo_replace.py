"""
photo_replace.py - Replace default portrait media in generated DOCX files.

The resume generator keeps uploaded portraits in resumeData.basicInfo.photo as a
Data URL.  This module post-processes the filled DOCX so preview and Word export
share the same replacement path:

- decode Data URL / raw base64
- honor EXIF orientation
- find likely portrait placeholder images referenced by DrawingML a:blip and
  legacy VML v:imagedata relationships
- center-crop and resize to the template photo frame / original media size
- rewrite the existing media file without changing relationship ids or content
  types

Failures are reported as warnings and never make the DOCX unusable.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import os
import posixpath
import re
import sys
import tempfile
import zipfile
from typing import Dict, Iterable, List, Optional, Tuple

_UTILS_DIR = os.path.dirname(os.path.abspath(__file__))
_LIBS_PATH = os.path.join(_UTILS_DIR, 'libs')
if os.path.exists(_LIBS_PATH) and _LIBS_PATH not in sys.path:
    sys.path.insert(0, _LIBS_PATH)

from lxml import etree as ET

try:  # Pillow is bundled for packaged builds via requirements.txt.
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover - exercised only on misconfigured systems
    Image = None
    ImageOps = None

NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'v': 'urn:schemas-microsoft-com:vml',
    'o': 'urn:schemas-microsoft-com:office:office',
}

REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'
IMAGE_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/image'
EMU_PER_POINT = 12700
EMU_PER_INCH = 914400
EMU_PER_PIXEL = 9525
A4_PAGE_AREA_EMU = 7560000 * 10692000


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _decode_photo_bytes(photo_value: str) -> Optional[bytes]:
    if not photo_value or not isinstance(photo_value, str):
        return None
    raw = photo_value.strip()
    if not raw:
        return None
    if raw.startswith('data:'):
        marker = ';base64,'
        if marker not in raw:
            return None
        raw = raw.split(marker, 1)[1]
    try:
        return base64.b64decode(raw, validate=True)
    except binascii.Error:
        try:
            return base64.b64decode(raw)
        except Exception:
            return None


def _load_photo(photo_value: str):
    if Image is None or ImageOps is None:
        raise RuntimeError('Pillow is not available; cannot replace portrait images')
    photo_bytes = _decode_photo_bytes(photo_value)
    if not photo_bytes:
        return None
    image = Image.open(io.BytesIO(photo_bytes))
    image = ImageOps.exif_transpose(image)
    # Load fully before the BytesIO object goes out of scope.
    image.load()
    return image


def _resolve_relationship_target(part_name: str, target: str) -> str:
    """Resolve a relationship Target to a normalized ZIP member path."""
    if not target:
        return ''
    if target.startswith('/'):
        return target.lstrip('/')
    base_dir = posixpath.dirname(part_name)
    return posixpath.normpath(posixpath.join(base_dir, target))


def _relationships_for_part(zf: zipfile.ZipFile, part_name: str) -> Dict[str, str]:
    rels_path = posixpath.join(
        posixpath.dirname(part_name),
        '_rels',
        posixpath.basename(part_name) + '.rels'
    )
    if rels_path not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read(rels_path))
    rels: Dict[str, str] = {}
    for rel in root.findall(f'{{{REL_NS}}}Relationship'):
        rid = rel.get('Id')
        target = rel.get('Target')
        rel_type = rel.get('Type', '')
        mode = rel.get('TargetMode', '')
        if rid and target and mode.lower() != 'external' and (rel_type == IMAGE_REL or target.startswith('media/') or '/media/' in target):
            rels[rid] = _resolve_relationship_target(part_name, target)
    return rels


def _iter_content_parts(zf: zipfile.ZipFile) -> Iterable[str]:
    names = set(zf.namelist())
    preferred = ['word/document.xml']
    preferred.extend(sorted(n for n in names if re.match(r'word/header\d+\.xml$', n)))
    preferred.extend(sorted(n for n in names if re.match(r'word/footer\d+\.xml$', n)))
    for name in preferred:
        if name in names:
            yield name


def _ancestor(node, tag_names: Iterable[str]):
    tag_set = set(tag_names)
    cur = node
    while cur is not None:
        if cur.tag in tag_set:
            return cur
        cur = cur.getparent()
    return None


def _drawingml_extent(blip) -> Optional[Tuple[float, float]]:
    drawing = _ancestor(blip, [f'{{{NS["wp"]}}}inline', f'{{{NS["wp"]}}}anchor'])
    if drawing is not None:
        ext = drawing.find('wp:extent', namespaces=NS)
        if ext is not None and ext.get('cx') and ext.get('cy'):
            try:
                return float(ext.get('cx')), float(ext.get('cy'))
            except Exception:
                pass
    pic = _ancestor(blip, [f'{{{NS["pic"]}}}pic'])
    if pic is not None:
        ext = pic.find('.//a:xfrm/a:ext', namespaces=NS)
        if ext is not None and ext.get('cx') and ext.get('cy'):
            try:
                return float(ext.get('cx')), float(ext.get('cy'))
            except Exception:
                pass
    return None


def _length_to_emu(value: str) -> Optional[float]:
    value = (value or '').strip()
    match = re.match(r'^(-?\d+(?:\.\d+)?)(pt|in|cm|mm|px)?$', value)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2) or 'px'
    if unit == 'pt':
        return number * EMU_PER_POINT
    if unit == 'in':
        return number * EMU_PER_INCH
    if unit == 'cm':
        return number * EMU_PER_INCH / 2.54
    if unit == 'mm':
        return number * EMU_PER_INCH / 25.4
    return number * EMU_PER_PIXEL


def _vml_extent(imagedata) -> Optional[Tuple[float, float]]:
    shape = _ancestor(imagedata, [f'{{{NS["v"]}}}shape'])
    if shape is None:
        return None
    style = shape.get('style', '') or ''
    width_match = re.search(r'(?:^|;)\s*width\s*:\s*([^;]+)', style)
    height_match = re.search(r'(?:^|;)\s*height\s*:\s*([^;]+)', style)
    if not width_match or not height_match:
        return None
    width = _length_to_emu(width_match.group(1))
    height = _length_to_emu(height_match.group(1))
    if not width or not height or width <= 0 or height <= 0:
        return None
    return width, height


def _collect_referenced_images(zf: zipfile.ZipFile) -> Dict[str, Dict]:
    images: Dict[str, Dict] = {}
    for part in _iter_content_parts(zf):
        rels = _relationships_for_part(zf, part)
        if not rels:
            continue
        try:
            root = ET.fromstring(zf.read(part))
        except Exception:
            continue

        def add_ref(rid: Optional[str], extent: Optional[Tuple[float, float]], source: str):
            if not rid or rid not in rels:
                return
            media_path = rels[rid]
            if not media_path.startswith('word/media/'):
                return
            entry = images.setdefault(media_path, {
                'media_path': media_path,
                'rids': set(),
                'placements': [],
            })
            entry['rids'].add(rid)
            if extent:
                entry['placements'].append({'source': source, 'width_emu': extent[0], 'height_emu': extent[1]})

        for blip in root.xpath('.//a:blip', namespaces=NS):
            rid = blip.get(f'{{{NS["r"]}}}embed') or blip.get(f'{{{NS["r"]}}}link')
            add_ref(rid, _drawingml_extent(blip), 'a:blip')

        for imagedata in root.xpath('.//v:imagedata', namespaces=NS):
            rid = (
                imagedata.get(f'{{{NS["r"]}}}id') or
                imagedata.get(f'{{{NS["r"]}}}embed') or
                imagedata.get(f'{{{NS["o"]}}}relid')
            )
            add_ref(rid, _vml_extent(imagedata), 'v:imagedata')

    for entry in images.values():
        entry['rids'] = sorted(entry['rids'])
    return images


def _has_meaningful_alpha(image) -> bool:
    if image.mode in ('RGBA', 'LA'):
        alpha = image.getchannel('A')
    elif image.mode == 'P' and 'transparency' in image.info:
        alpha = image.convert('RGBA').getchannel('A')
    else:
        return False
    extrema = alpha.getextrema()
    return bool(extrema and extrema[0] < 245)


def _best_display_metrics(placements: List[Dict]) -> Tuple[Optional[float], Optional[float]]:
    ratios: List[Tuple[float, float]] = []
    areas: List[float] = []
    for placement in placements or []:
        w = placement.get('width_emu') or 0
        h = placement.get('height_emu') or 0
        if w > 0 and h > 0:
            ratios.append((w * h, w / h))
            areas.append(w * h)
    ratio = None
    if ratios:
        # Use the largest visible placement when the same image is referenced more than once.
        ratio = sorted(ratios, reverse=True)[0][1]
    area_fraction = max(areas) / A4_PAGE_AREA_EMU if areas else None
    return ratio, area_fraction


def _score_candidate(fmt: str, width: int, height: int, has_alpha: bool, display_ratio: Optional[float], display_area_fraction: Optional[float]) -> int:
    if width <= 0 or height <= 0:
        return -999
    area = width * height
    min_dim = min(width, height)
    max_dim = max(width, height)
    media_ratio = width / height
    target_ratio = display_ratio or media_ratio

    score = 0
    if fmt in ('JPEG', 'JPG'):
        score += 45
    elif fmt == 'PNG':
        score += 5

    if min_dim < 80 or area < 8000:
        score -= 90
    elif 150 <= max_dim <= 900:
        score += 35
    elif max_dim <= 1400:
        score += 15
    else:
        score -= 35

    if 0.70 <= media_ratio <= 1.35:
        score += 25
    elif 0.45 <= media_ratio <= 1.65:
        score += 12
    else:
        score -= 35

    if 0.70 <= target_ratio <= 1.35:
        score += 25
    elif 0.45 <= target_ratio <= 1.65:
        score += 10
    else:
        score -= 30

    if display_area_fraction is not None:
        if 0.004 <= display_area_fraction <= 0.09:
            score += 30
        elif 0.09 < display_area_fraction <= 0.18:
            score += 8
        elif display_area_fraction > 0.25:
            score -= 65

    if has_alpha:
        # Transparent PNGs are usually icons, masks, or decorative texture layers.
        score -= 75

    return score


def inspect_photo_candidates(docx_path: str) -> List[Dict]:
    """Return scored portrait placeholder candidates for tests/diagnostics."""
    if Image is None:
        return []
    candidates: List[Dict] = []
    with zipfile.ZipFile(docx_path, 'r') as zf:
        refs = _collect_referenced_images(zf)
        for media_path, entry in refs.items():
            if media_path not in zf.namelist() or media_path.endswith('/'):
                continue
            data = zf.read(media_path)
            try:
                img = Image.open(io.BytesIO(data))
                img.load()
            except Exception:
                continue
            width, height = img.size
            fmt = (img.format or os.path.splitext(media_path)[1].lstrip('.')).upper()
            display_ratio, display_area_fraction = _best_display_metrics(entry.get('placements', []))
            has_alpha = _has_meaningful_alpha(img)
            score = _score_candidate(fmt, width, height, has_alpha, display_ratio, display_area_fraction)
            candidates.append({
                'media_path': media_path,
                'format': fmt,
                'width': width,
                'height': height,
                'sha1': _sha1(data),
                'score': score,
                'has_alpha': has_alpha,
                'display_ratio': display_ratio,
                'display_area_fraction': display_area_fraction,
                'rids': entry.get('rids', []),
                'placements': entry.get('placements', []),
            })
    return sorted(candidates, key=lambda c: c['score'], reverse=True)


def _style_length_emu(style: str, key: str) -> Optional[float]:
    match = re.search(r'(?:^|;)\s*' + re.escape(key) + r'\s*:\s*([^;]+)', style or '')
    if not match:
        return None
    return _length_to_emu(match.group(1))


def _is_problematic_quicklook_vml_icon(shape) -> bool:
    """Detect tiny custom VML icons that QuickLook scales into giant gray art."""
    shape_id = shape.get('id') or ''
    if shape_id not in {'电话', '日历', '信息', '定位'}:
        return False
    if shape.get('filled') != 't' or not shape.get('fillcolor'):
        return False
    if shape.get(f'{{{NS["o"]}}}spt') != '100':
        return False
    style = shape.get('style', '') or ''
    width = _style_length_emu(style, 'width')
    height = _style_length_emu(style, 'height')
    if not width or not height:
        return False
    # These should be small contact icons.  The relative-size flags are the
    # common marker in the templates where QuickLook ignores the intended size.
    is_small = width < 40 * EMU_PER_POINT and height < 40 * EMU_PER_POINT
    has_relative_flags = 'mso-width-relative:page' in style and 'mso-height-relative:page' in style
    return is_small and has_relative_flags


def _is_problematic_quicklook_drawing_icon(drawing) -> bool:
    doc_pr = drawing.find('.//wp:docPr', namespaces=NS)
    if doc_pr is None or doc_pr.get('name') not in {'电话', '日历', '信息', '定位'}:
        return False
    ext = drawing.find('.//wp:extent', namespaces=NS)
    if ext is None:
        return False
    try:
        width = float(ext.get('cx') or 0)
        height = float(ext.get('cy') or 0)
    except Exception:
        return False
    if width <= 0 or height <= 0:
        return False
    is_small = width < 40 * EMU_PER_POINT and height < 40 * EMU_PER_POINT
    gray_colors = {str(c.get('val') or '').upper() for c in drawing.xpath('.//a:srgbClr', namespaces=NS)}
    return is_small and bool(gray_colors & {'707175', '4F535E'})


def cleanup_empty_vml_imagedata(docx_path: str, output_path: Optional[str] = None) -> Dict:
    """Remove legacy preview artifacts from content parts.

    Some resume templates contain ``<v:imagedata o:title=""/>`` inside VML
    textboxes even though no relationship/source is attached, plus tiny legacy
    contact icons duplicated as DrawingML.  Word tolerates this, but macOS
    QuickLook can render those source-less / tiny nodes as large gray blocks.
    Removing only source-less imagedata and known tiny contact-icon duplicates
    preserves real ``r:id`` / ``o:relid`` images while making preview output
    much closer to Word.
    """
    output_path = output_path or docx_path
    changed_parts: Dict[str, bytes] = {}
    removed = 0
    try:
        with zipfile.ZipFile(docx_path, 'r') as zin:
            for part in _iter_content_parts(zin):
                try:
                    root = ET.fromstring(zin.read(part))
                except Exception:
                    continue
                part_removed = 0
                for imagedata in list(root.xpath('.//v:imagedata', namespaces=NS)):
                    has_source = any(imagedata.get(attr) for attr in [
                        f'{{{NS["r"]}}}id',
                        f'{{{NS["r"]}}}embed',
                        f'{{{NS["o"]}}}relid',
                        'src', 'href'
                    ])
                    if has_source:
                        continue
                    parent = imagedata.getparent()
                    if parent is not None:
                        parent.remove(imagedata)
                        part_removed += 1
                for shape in list(root.xpath('.//v:shape', namespaces=NS)):
                    if not _is_problematic_quicklook_vml_icon(shape):
                        continue
                    parent = shape.getparent()
                    if parent is not None:
                        parent.remove(shape)
                        part_removed += 1
                for drawing in list(root.xpath('.//w:drawing', namespaces=NS)):
                    if not _is_problematic_quicklook_drawing_icon(drawing):
                        continue
                    parent = drawing.getparent()
                    if parent is not None:
                        parent.remove(drawing)
                        part_removed += 1
                if part_removed:
                    removed += part_removed
                    changed_parts[part] = ET.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
            if not changed_parts:
                return {'removed': 0, 'changed': False}

            out_dir = os.path.dirname(os.path.abspath(output_path)) or os.getcwd()
            fd, temp_path = tempfile.mkstemp(prefix='vml_cleanup_', suffix='.docx', dir=out_dir)
            os.close(fd)
            try:
                with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as zout:
                    for item in zin.infolist():
                        if item.filename in changed_parts:
                            zout.writestr(item, changed_parts[item.filename])
                        else:
                            zout.writestr(item, zin.read(item.filename))
                os.replace(temp_path, output_path)
            except Exception:
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
                raise
        return {'removed': removed, 'changed': True}
    except Exception as exc:
        return {'removed': removed, 'changed': False, 'warning': str(exc)}


def _target_size_for_ratio(width: int, height: int, ratio: Optional[float]) -> Tuple[int, int]:
    if not ratio or ratio <= 0:
        return max(1, width), max(1, height)
    current = width / height if height else ratio
    if abs(current - ratio) <= 0.03:
        return max(1, width), max(1, height)
    if ratio >= current:
        new_h = height
        new_w = int(round(new_h * ratio))
    else:
        new_w = width
        new_h = int(round(new_w / ratio))
    return max(80, new_w), max(80, new_h)


def _save_fitted_photo(photo_image, target_size: Tuple[int, int], output_format: str) -> bytes:
    fitted = ImageOps.fit(photo_image, target_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    out = io.BytesIO()
    fmt = output_format.upper()
    if fmt in ('JPG', 'JPEG'):
        if fitted.mode in ('RGBA', 'LA') or (fitted.mode == 'P' and 'transparency' in fitted.info):
            bg = Image.new('RGB', fitted.size, (255, 255, 255))
            bg.paste(fitted.convert('RGBA'), mask=fitted.convert('RGBA').getchannel('A'))
            fitted = bg
        elif fitted.mode != 'RGB':
            fitted = fitted.convert('RGB')
        fitted.save(out, format='JPEG', quality=94, optimize=True)
    elif fmt == 'PNG':
        if fitted.mode not in ('RGB', 'RGBA'):
            fitted = fitted.convert('RGBA')
        fitted.save(out, format='PNG', optimize=True)
    else:
        if fitted.mode != 'RGB':
            fitted = fitted.convert('RGB')
        fitted.save(out, format='JPEG', quality=94, optimize=True)
    return out.getvalue()


def replace_photo_in_docx(docx_path: str, photo_value: str, output_path: Optional[str] = None, max_replacements: int = 1) -> Dict:
    """Replace likely portrait placeholder media in ``docx_path``.

    Returns a diagnostic dict.  The function is intentionally non-throwing for
    normal "no candidate" cases; corrupted inputs/dependency errors are surfaced
    as warnings in the result so callers can keep exporting a usable DOCX.
    """
    output_path = output_path or docx_path
    result = {
        'replaced': False,
        'replaced_count': 0,
        'candidates': [],
        'warnings': [],
    }

    if not photo_value:
        result['warnings'].append('no_photo')
        return result
    if Image is None or ImageOps is None:
        result['warnings'].append('pillow_unavailable')
        return result

    try:
        photo_image = _load_photo(photo_value)
    except Exception as exc:
        result['warnings'].append(f'photo_decode_failed:{exc}')
        return result
    if photo_image is None:
        result['warnings'].append('photo_decode_failed')
        return result

    try:
        candidates = inspect_photo_candidates(docx_path)
    except Exception as exc:
        result['warnings'].append(f'inspect_failed:{exc}')
        return result

    result['candidates'] = candidates
    selected = [c for c in candidates if c.get('score', 0) >= 30][:max(1, max_replacements)]
    if not selected:
        result['warnings'].append('no_portrait_candidate')
        return result

    replacements: Dict[str, bytes] = {}
    for candidate in selected:
        display_ratio = candidate.get('display_ratio') or (candidate['width'] / candidate['height'] if candidate['height'] else None)
        target_size = _target_size_for_ratio(candidate['width'], candidate['height'], display_ratio)
        output_format = candidate.get('format') or os.path.splitext(candidate['media_path'])[1].lstrip('.').upper()
        try:
            replacements[candidate['media_path']] = _save_fitted_photo(photo_image, target_size, output_format)
        except Exception as exc:
            result['warnings'].append(f"render_failed:{candidate['media_path']}:{exc}")

    if not replacements:
        return result

    out_dir = os.path.dirname(os.path.abspath(output_path)) or os.getcwd()
    fd, temp_path = tempfile.mkstemp(prefix='photo_replace_', suffix='.docx', dir=out_dir)
    os.close(fd)
    try:
        with zipfile.ZipFile(docx_path, 'r') as zin:
            with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename in replacements:
                        zout.writestr(item, replacements[item.filename])
                    else:
                        zout.writestr(item, zin.read(item.filename))
        os.replace(temp_path, output_path)
    except Exception as exc:
        try:
            os.unlink(temp_path)
        except Exception:
            pass
        result['warnings'].append(f'zip_write_failed:{exc}')
        return result

    result['replaced'] = True
    result['replaced_count'] = len(replacements)
    result['replaced_media'] = sorted(replacements.keys())
    return result


if __name__ == '__main__':
    import json

    if len(sys.argv) < 3:
        print('Usage: python photo_replace.py <data.json> <docx_path> [output.docx]', file=sys.stderr)
        sys.exit(2)

    data_path = sys.argv[1]
    docx_path = sys.argv[2]
    out_path = sys.argv[3] if len(sys.argv) > 3 else docx_path
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    photo = (data or {}).get('basicInfo', {}).get('photo', '')
    cleanup_empty_vml_imagedata(docx_path, out_path)
    result = replace_photo_in_docx(out_path, photo, out_path)
    print(json.dumps(result, ensure_ascii=False))
    # Missing photo/candidate is a warning, not an export failure.
    sys.exit(0)
