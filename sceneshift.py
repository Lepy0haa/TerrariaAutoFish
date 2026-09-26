"""
Сдвиг всей картинки: персонажа толкнуло (враг, течение, падение) или камера уехала — вода, стены и
всё остальное на экране сдвинулись на одно и то же расстояние, а точка заброса и отметка поплавка
остались на месте экрана и смотрят уже не туда.

Сравниваем снимок места рыбалки после удачного заброса со снимком сейчас фазовой корреляцией
(через БПФ): она находит, на сколько сдвинулась картинка целиком, и не обращает внимания на
яркость. Персонажа (камера держит его в центре — он не двигается) и поплавок не учитываем.
"""
import numpy as np

MIN_PEAK = 0.12     # уверенность совпадения (пик корреляции): ниже — это не сдвиг, а другая картинка
MIN_RATIO = 1.6     # ...и пик заметно выше любого другого места (иначе картинка однообразная)


def gray(frame):
    return frame[:, :, :3].astype(np.float64).mean(2)


def _soft(mask, r=12):
    """Маска с плавными краями (резкий край — неподвижный «узор», он тянет к нулевому сдвигу)."""
    m = mask.astype(np.float64)
    for axis in (0, 1):
        c = np.cumsum(np.pad(m, [(r + 1, r) if a == axis else (0, 0) for a in (0, 1)], mode="edge"), axis)
        m = (np.take(c, range(2 * r + 1, c.shape[axis]), axis) - np.take(c, range(0, c.shape[axis] - 2 * r - 1), axis)) / (2 * r + 1)
    return m


def _prepare(g, weight):
    """Без среднего, с весом: окно Ханна и маска с плавными краями — края не мешают."""
    g = g - (g * weight).sum() / max(weight.sum(), 1e-9)
    return g * weight


def estimate(before, after, mask=None):
    """На сколько сдвинулась картинка: (dx, dy, уверенность) — содержимое, бывшее в точке p,
    теперь в p + (dx, dy). None — сдвиг не определить уверенно. before/after — серые (H, W),
    mask — какие пиксели учитывать (True)."""
    if before.shape != after.shape or min(before.shape) < 16:
        return None
    h, w = before.shape
    weight = np.outer(np.hanning(h), np.hanning(w))
    if mask is not None:
        weight = weight * _soft(mask)
    a, b = _prepare(before, weight), _prepare(after, weight)
    fa, fb = np.fft.rfft2(a), np.fft.rfft2(b)
    cross = fb * np.conj(fa)
    cross /= np.abs(cross) + 1e-9
    # полосы во всю ширину или высоту (кромка воды, небо) сдвигаются только в одну сторону и дают
    # ложный пик на оси — эти частоты не учитываем
    cross[0, :] = 0
    cross[:, 0] = 0
    corr = np.fft.irfft2(cross, s=a.shape)
    h, w = corr.shape
    y, x = np.unravel_index(int(corr.argmax()), corr.shape)
    peak = float(corr[y, x])
    # второй по силе пик — вне окрестности первого
    c2 = corr.copy()
    for yy in range(y - 3, y + 4):
        for xx in range(x - 3, x + 4):
            c2[yy % h, xx % w] = -1
    second = max(float(c2.max()), 1e-6)
    if peak < MIN_PEAK or peak / second < MIN_RATIO:
        return None
    dy = y if y <= h // 2 else y - h
    dx = x if x <= w // 2 else x - w
    return int(dx), int(dy), peak
