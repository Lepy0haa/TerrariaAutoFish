"""
Распознавание текста встроенным в Windows 10/11 OCR (Windows.Media.Ocr) — для надписи зелья
сонара над поплавком (название того, что клюнуло).

Шрифт Terraria пиксельный, с тёмной обводкой, цветной (цвет = редкость предмета). OCR лучше
читает тёмный текст на светлом: оставляем только яркие пиксели букв, делаем их чёрными на белом
и увеличиваем картинку.
"""
import asyncio

import numpy as np

_engines = {}


def available_languages():
    try:
        from winrt.windows.media.ocr import OcrEngine
        return [l.language_tag for l in OcrEngine.available_recognizer_languages]
    except Exception:
        return []


def _engine(lang):
    if lang not in _engines:
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine
        eng = None
        try:
            if OcrEngine.is_language_supported(Language(lang)):
                eng = OcrEngine.try_create_from_language(Language(lang))
        except Exception:
            eng = None
        _engines[lang] = eng
    return _engines[lang]


def prepare(img, scale=4):
    """Кадр BGR (float) с надписью -> серое изображение для OCR: буквы чёрные, фон белый."""
    img = np.asarray(img, np.float32)
    bright = img.max(2)
    sat = img.max(2) - img.min(2)
    # буквы — яркие (цвет редкости или белые), обводка и фон — тёмные
    letters = (bright > 110) & ((sat > 40) | (bright > 180))
    out = np.where(letters, 0, 255).astype(np.uint8)
    out = np.pad(out, 6, constant_values=255)
    return out.repeat(scale, 0).repeat(scale, 1)


async def _recognize(gray, lang):
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.storage.streams import DataWriter
    h, w = gray.shape
    bgra = np.dstack([gray, gray, gray, np.full_like(gray, 255)]).astype(np.uint8)
    writer = DataWriter()
    writer.write_bytes(bgra.tobytes())
    buf = writer.detach_buffer()
    bmp = SoftwareBitmap.create_copy_from_buffer(buf, BitmapPixelFormat.BGRA8, w, h)
    result = await _engine(lang).recognize_async(bmp)
    return " ".join(line.text for line in result.lines).strip()


def read_text(img, lang="ru", prepared=False):
    """Текст на картинке (BGR). lang — "ru" или "en-US". Пустая строка, если OCR недоступен."""
    if _engine(lang) is None:
        return ""
    gray = img if prepared else prepare(img)
    try:
        return asyncio.run(_recognize(gray, lang))
    except Exception:
        return ""
