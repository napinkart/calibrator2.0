"""Extracción offline de patrones desde un vídeo grabado con una DSLR.

Se graba la pantalla mientras el calibrador proyecta la secuencia de
`lw.patterns.make_sequence()`. Este módulo trocea el vídeo en un frame por
patrón y los guarda con el NOMBRE EXACTO del patrón (`black`, `white`,
`col00p`, `col00`, `row00p`, ..., `phx00`, ...), que es lo que necesita
`lw.patterns.Decoder.add()` para reconstruir la secuencia.

Todo es AUTOMÁTICO:

* se recorre el vídeo entero (no importa la duración) hasta encontrar el blanco
  de sincronía, que se reconoce como una MESETA SOSTENIDA de brillo alto en
  el percentil 95 del frame (la zona proyectada es brillante aunque el resto
  del encuadre —techo, piso— sea oscuro, así que la media del frame completo
  no sirve);
* a partir de ahí cada cambio de ESTRUCTURA de la imagen marca un patrón
  nuevo; si eso no recupera todos los patrones esperados (las sinusoides de
  fase se parecen demasiado entre sí), se usa como respaldo el TIEMPO: cada
  patrón se proyectó `hold` segundos, así que se muestrea el centro de cada
  ventana tras el final de la meseta, con el fps real del vídeo;
* los cambios de brillo global (autoexposición, banding del proyector) se
  ignoran, y de cada patrón se guarda el frame más representativo, no el
  primero ni el del medio.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path

import cv2
import numpy as np

SYNC_FLOOR = 100.0    # brillo medio mínimo para que un frame pueda ser el blanco (bajado de 120)
SYNC_JUMP = 1.15      # ... y que destaque un 15 % sobre lo más brillante visto antes (bajado de 1.25)
SYNC_FLAT = 60.0      # desviación típica máxima dentro del frame (el blanco es plano) (subido de 25)
SYNC_STREAK = 2       # frames seguidos que debe mantenerse para darlo por bueno (bajado de 3)
DARK_MEAN = 200.0     # por debajo de esto se considera el primer patrón (negro)
STRUCT_TOL = 6.0      # diferencia de ESTRUCTURA que marca cambio de patrón
BRIGHT_TOL = 60.0     # salto de brillo global que también marca cambio de patrón
MIN_SEG = 2           # menos frames que esto es una transición, no un patrón
SYNC_P95_FRAC = 0.45  # la meseta debe superar baseline + esta fracción del rango p95
SYNC_P95_MIN = 90.0   # ... y nunca por debajo de este p95 absoluto
SEG_BUFFER = 32       # frames que se guardan de un tramo para elegir el mejor
ANALYSIS_WIDTH = 320  # ancho al que se reduce cada frame para analizarlo


# -- utilidades de imagen ----------------------------------------------------
def _small(frame):
    """Copia en gris y reducida del frame, para medir brillo y estructura."""
    h, w = frame.shape[:2]
    if w > ANALYSIS_WIDTH:
        frame = cv2.resize(frame, (ANALYSIS_WIDTH, max(1, int(h * ANALYSIS_WIDTH / w))),
                           interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def _mean(small):
    return float(small.mean())


def _p95(small):
    """Percentil 95 del brillo: representa la zona iluminada del frame.

    La proyección rara vez llena todo el encuadre (siempre se ve algo de
    techo/piso/entorno oscuro), así que la media se diluye y la desviación
    sube. El p95 mide lo brillante que es la parte más iluminada —la señal
    que importa— sin depender de cuánto entorno oscuro haya alrededor.
    """
    return float(np.percentile(small, 95))


def _change(a, b, struct_tol=STRUCT_TOL, bright_tol=BRIGHT_TOL):
    """¿Hay cambio de patrón entre dos frames reducidos?

    Se compara la ESTRUCTURA (imagen menos su brillo medio) y, aparte, un salto
    grande de brillo global. Así una rampa de autoexposición o un frame
    parpadeado por el proyector no cuentan como patrón nuevo, pero sí el paso
    de un patrón negro a otro blanco.
    """
    fa = a.astype(np.float32)
    fb = b.astype(np.float32)
    struct = float(np.mean(np.abs((fa - fa.mean()) - (fb - fb.mean()))))
    bright = abs(float(fa.mean()) - float(fb.mean()))
    return struct > struct_tol or bright > bright_tol


def _best_frame(frames):
    """El frame del tramo más parecido a la mediana del tramo.

    Descarta los frames contaminados por la transición (exposición subiendo o
    bajando) sin necesidad de saber cuántos patrones hay.
    """
    if len(frames) <= 2:
        return frames[len(frames) // 2]
    smalls = np.stack([_small(f) for f in frames]).astype(np.float32)
    med = np.median(smalls, axis=0)
    dist = np.abs(smalls - med).mean(axis=(1, 2))
    return frames[int(np.argmin(dist))]


# -- localización del blanco de sincronía ------------------------------------
def _find_sync_frame_legacy(video_path):
    """Localiza el blanco de sincronía y devuelve (indice, brillo) o (None, pico).

    No se busca un valor absoluto de brillo (un blanco proyectado y grabado con
    una DSLR casi nunca llega a 240: la exposición automática, el viñeteo y la
    luz del local lo dejan en 180-230). Se busca un SALTO de brillo respecto a
    lo grabado antes, en un frame plano (poca variación dentro de la imagen) y
    mantenido varios frames seguidos.

    Así no se confunde con el patrón `white` de la secuencia, que puede ser más
    brillante que el propio blanco de sincronía.

    Se recorre el vídeo ENTERO: si se empieza a grabar mucho antes de lanzar la
    secuencia, el blanco puede caer muy tarde.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el vídeo: {video_path}")

    running = 0.0   # lo más brillante visto hasta ahora (sin contar el blanco)
    peak = 0.0      # máximo absoluto, sólo para el mensaje de error
    streak = 0
    first = None
    idx = -1
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            idx += 1
            small = _small(frame)
            mean = _mean(small)
            if mean > peak:
                peak = mean

            plano = float(small.std()) <= SYNC_FLAT
            if plano and mean >= max(SYNC_FLOOR, running * SYNC_JUMP):
                if streak == 0:
                    first = idx
                streak += 1
                if streak >= SYNC_STREAK:
                    return first, mean
            else:
                streak = 0
                first = None
                if mean > running:
                    running = mean
    finally:
        cap.release()
    return None, peak


def _p95_series(video_path):
    """Devuelve (p95_por_frame, fps) recorriendo el vídeo una vez."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el vídeo: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    series = []
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            series.append(_p95(_small(frame)))
    finally:
        cap.release()
    return np.array(series, dtype=np.float64), fps


def _find_sync_frame(video_path, sync_s=3.0):
    """Localiza el blanco de sincronía como meseta sostenida de p95 alto.

    Devuelve (inicio, pico_p95, fin) donde `fin` es el primer frame YA fuera
    del blanco (ahí empieza el patrón `black`), o (None, pico, None).

    Por qué p95 y no la media: en un encuadre real la proyección ocupa solo
    una banda (techo oscuro arriba, piso abajo). La media del frame completo
    queda diluida (~130 aunque la proyección esté a 220) y la desviación
    supera cualquier límite de "plano". El p95 sí ve la zona proyectada.

    La meseta debe durar al menos la mitad del blanco proyectado (`sync_s`),
    lo que la distingue del patrón `white` de la secuencia (solo `hold`
    segundos). Se busca la PRIMERA meseta así: la sincronía precede a los
    patrones. Si no aparece ninguna, se recurre al detector antiguo de media.
    """
    series, fps = _p95_series(video_path)
    if len(series) == 0:
        return None, 0.0, None
    peak = float(series.max())
    baseline = float(np.percentile(series, 10))
    thr = max(baseline + SYNC_P95_FRAC * (peak - baseline), SYNC_P95_MIN)
    if fps > 0:
        min_len = max(6, int(round(fps * max(sync_s, 0.5) * 0.5)))
    else:
        min_len = 12

    hot = series >= thr
    start = None
    for i in range(len(series)):
        if hot[i]:
            if start is None:
                start = i
        elif start is not None:
            if i - start >= min_len:
                return start, peak, i
            start = None
    if start is not None and len(series) - start >= min_len:
        return start, peak, len(series)

    legacy_idx, legacy_peak = _find_sync_frame_legacy(video_path)
    if legacy_idx is not None:
        return legacy_idx, float(max(peak, legacy_peak)), None
    return None, peak, None


# -- troceado del vídeo en patrones ------------------------------------------
def _glitch(a, last, b):
    """¿`a` es un frame parpadeado entre `last` y `b`?"""
    return _change(a, last) and not _change(b, last)


def _segments(video_path, sync_idx, max_segments):
    """Trocea el vídeo en tramos estables y devuelve (frames, longitudes).

    Se salta todo hasta el blanco de sincronía y el propio blanco. Desde ahí,
    cada cambio de estructura abre un patrón nuevo. Los frames parpadeados
    (banding del proyector, un frame con la exposición disparada) se descartan
    comparándolos con el frame anterior y el siguiente, así que no parten un
    patrón en dos ni desplazan la cuenta.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el vídeo: {video_path}")

    frames, lengths = [], []
    cur = deque(maxlen=SEG_BUFFER)
    ref = None          # frame del blanco de sincronía
    last = None         # frame reducido del último frame válido
    wait_frame = None   # frame pendiente de validación (puede ser un parpadeo)
    wait_small = None
    left_sync = False
    idx = -1

    def cerrar():
        if cur:
            frames.append(_best_frame(list(cur)))
            lengths.append(len(cur))
            cur.clear()

    def procesar(frame, small):
        """Mete un frame validado en el troceado."""
        nonlocal left_sync, last
        if not left_sync:
            if ref is None:
                last = small     # todavía dentro del blanco
                return
            if _change(small, ref):
                left_sync = True
                cur.append(frame)
            last = small
            return
        if _change(small, last):
            cerrar()
            cur.append(frame)
        else:
            cur.append(frame)
        last = small

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            idx += 1
            if idx < sync_idx:
                continue
            small = _small(frame)
            if ref is None:
                ref = small
                last = small
                wait_frame, wait_small = frame, small
                continue

            # Con un frame de retraso podemos saber si el anterior era parpadeo.
            if wait_frame is not None:
                if _glitch(wait_small, last, small):
                    wait_frame, wait_small = frame, small   # se descarta el raro
                    continue
                procesar(wait_frame, wait_small)
                if len(frames) >= max_segments:
                    break
            wait_frame, wait_small = frame, small
    finally:
        cap.release()

    if wait_frame is not None:
        procesar(wait_frame, wait_small)

    cerrar()
    return frames, lengths


def _merge_to_count(frames, lengths, target):
    """Fusiona tramos vecinos hasta quedarse con `target` (parpadeos, ruido).

    Dos tramos separados por un parpadeo son casi idénticos: se fusiona siempre
    la pareja de vecinos más parecida y se conserva el frame del tramo más
    largo (el más alejado de las transiciones).
    """
    frames, lengths = list(frames), list(lengths)
    while len(frames) > target and len(frames) > 1:
        best_i, best_d = 0, None
        for i in range(len(frames) - 1):
            a = _small(frames[i]).astype(np.float32)
            b = _small(frames[i + 1]).astype(np.float32)
            d = float(np.mean(np.abs((a - a.mean()) - (b - b.mean()))))
            if best_d is None or d < best_d:
                best_i, best_d = i, d
        if best_d is not None and best_d > STRUCT_TOL * 1.5:
            # Los dos tramos más parecidos no son el mismo patrón: no se fusiona
            # a ciegas, porque desplazaría todos los patrones siguientes.
            break
        i = best_i
        keep = frames[i] if lengths[i] >= lengths[i + 1] else frames[i + 1]
        frames[i:i + 2] = [keep]
        lengths[i:i + 2] = [lengths[i] + lengths[i + 1]]
    return frames, lengths


# -- modo manual antiguo -----------------------------------------------------
def _by_stride(video_path, names, sync_idx, stride, dark_mean):
    """Modo manual: un frame cada `stride` a partir del blanco de sincronía."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el vídeo: {video_path}")
    out = []
    saved = 0
    skip = 0
    in_sync = False
    idx = -1
    try:
        while saved < len(names):
            ret, frame = cap.read()
            if not ret:
                break
            idx += 1
            if idx < sync_idx:
                continue
            if not in_sync:
                in_sync = True
                continue
            mean = _mean(_small(frame))
            if skip > 0:
                skip -= 1
                continue
            if saved == 0 and mean >= dark_mean:
                # El primer frame oscuro tras la sincronía es el patrón 'black'
                continue
            out.append(frame)
            saved += 1
            skip = int(stride)
    finally:
        cap.release()
    return out


def _video_fps(video_path):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el vídeo: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    cap.release()
    return fps


def _frames_at(video_path, indices):
    """Lee los frames en los índices indicados (buscando uno a uno)."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el vídeo: {video_path}")
    out = []
    try:
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ret, frame = cap.read()
            out.append(frame if ret else None)
    finally:
        cap.release()
    return out


def _by_timing_fit(video_path, n_patterns, sync_end, hold):
    """Respaldo por tiempo AJUSTADO a los cambios reales del vídeo.

    El paso nominal `hold * fps` deriva: el proyector tarda un poco más que
    `hold` por patrón (overhead de flush) y el fps reportado puede no ser
    exacto, así que tras 40 patrones la ventana puede caer en la transición
    siguiente. En su lugar se detectan los puntos de cambio de estructura
    tras la sincronía, se les asigna su índice de patrón y se ajusta una
    recta (inicio + paso * k); el centro de cada patrón sale de esa recta,
    sin deriva acumulada. Los patrones de fase fusionados por estructura
    simplemente no aportan punto de cambio: la recta los interpola.
    Devuelve (frames, detalle) o (None, motivo).
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el vídeo: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    smalls = []
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(sync_end) - 1))
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            smalls.append(_small(frame))
    finally:
        cap.release()
    if len(smalls) < 10:
        return None, "vídeo demasiado corto tras la sincronía"
    base = max(0, int(sync_end) - 1)
    changes = [base + i for i in range(1, len(smalls))
               if _change(smalls[i], smalls[i - 1])]
    if len(changes) < 3:
        return None, "sin puntos de cambio para ajustar el paso"
    intervals = np.diff(changes).astype(np.float64)
    step_guess = float(np.median(intervals)) if len(intervals) else 0.0
    if fps > 0 and hold > 0:
        nominal = hold * fps
        if not (0.5 * nominal <= step_guess <= 1.5 * nominal):
            step_guess = nominal
    if step_guess <= 0:
        return None, "paso estimado inválido"
    # Dedupar cambios pegados (transición de 2 frames) y asignar índice.
    kept = []
    for c in changes:
        if not kept or c - kept[-1] >= max(3.0, step_guess * 0.5):
            kept.append(c)
    ks, cs = [], []
    for c in kept:
        k = int(round((c - kept[0]) / step_guess))
        if not ks or k > ks[-1]:
            ks.append(k)
            cs.append(c)
    if len(cs) < 3:
        return None, "pocos cambios únicos para ajustar"
    slope, intercept = np.polyfit(np.array(ks, float), np.array(cs, float), 1)
    if not np.isfinite(slope) or slope <= 0:
        return None, "ajuste de paso inválido"
    if fps > 0 and hold > 0:
        nominal = hold * fps
        if not (0.5 * nominal <= slope <= 1.5 * nominal):
            return None, f"paso ajustado {slope:.1f} fuera de rango nominal {nominal:.1f}"
    indices = [int(round(intercept + (k + 0.5) * slope)) for k in range(n_patterns)]
    frames = _frames_at(video_path, indices)
    if any(f is None for f in frames):
        return None, "el vídeo se acaba antes de la última ventana"
    return frames, f"tiempo ajustado (paso {slope:.2f} frames, inicio {intercept:.0f})"


def _by_timing(video_path, n_patterns, start_idx, hold):
    """Respaldo por tiempo: el centro de cada ventana de `hold` segundos.

    `patterns` proyecta cada patrón exactamente `hold` s, así que una vez
    localizado el final del blanco de sincronía el patrón k está centrado en
    start + (k + 0.5) * hold * fps. Esto recupera también los patrones de
    fase, que son tan parecidos entre sí que el troceado por estructura los
    fusiona. Devuelve (frames, detalle) o (None, motivo) si no llega.
    """
    fps = _video_fps(video_path)
    if fps <= 0 or hold <= 0:
        return None, "sin fps/hold válidos"
    step = hold * fps
    indices = [int(round(start_idx + (k + 0.5) * step)) for k in range(n_patterns)]
    frames = _frames_at(video_path, indices)
    if any(f is None for f in frames):
        return None, f"el vídeo se acaba antes de la ventana {len(frames)}"
    return frames, f"tiempo (hold {hold:g} s @ {fps:.1f} fps)"


def _clear_pngs(output_dir):
    for f in output_dir.glob("*.png"):
        f.unlink()


def extract_patterns(video_path, output_dir, names=None, num_patterns=32,
                     stride=None, dark_mean=DARK_MEAN, hold=0.4, sync_s=3.0):
    """Extrae un frame por patrón del vídeo y los guarda como `<nombre>.png`.

    names:
        Nombres de patrón EN ORDEN, tal como los devuelve
        `lw.dslr_offline.sequence_names()`. Si se omite se usa el modo antiguo
        (`col0.png`, `col1.png`, ...), que sólo sirve para inspeccionar el
        vídeo: el Decoder no puede decodificar esos nombres.
    hold, sync_s:
        Segundos por patrón y de blanco de sincronía usados al proyectar
        (los mismos que se pasaron a `calibrate.py patterns`). Solo se usan
        para el respaldo por tiempo si el troceado por estructura no
        recupera todos los patrones.
    stride:
        Déjalo en None (recomendado): el troceado es automático. Sólo si se
        indica un entero se usa el modo antiguo de saltar N frames.

    Devuelve el número de frames extraídos.
    """
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if names is None:
        names = [f"col{i}" for i in range(int(num_patterns))]
    else:
        names = list(names)
    if not names:
        raise ValueError("la lista de nombres de patrón está vacía")

    _clear_pngs(output_dir)

    sync_idx, peak, sync_end = _find_sync_frame(video_path, sync_s=sync_s)
    if sync_idx is None:
        raise RuntimeError(
            f"No se encontró el blanco de sincronía en {video_path.name}: el p95 "
            f"(zona más iluminada) máximo de todo el vídeo es {peak:.0f}. Graba "
            "también los 3 s de blanco (empieza a grabar ANTES de lanzar la "
            "secuencia) y encuadra la proyección en el centro del frame.")

    if stride is not None:
        frames = _by_stride(video_path, names, sync_idx, int(stride), dark_mean)
        if len(frames) < len(names):
            raise RuntimeError(
                f"Sólo se extrajeron {len(frames)} de {len(names)} patrones con "
                f"stride={int(stride)}: el vídeo se acabó antes. No indiques "
                "stride para que el troceado sea automático.")
        detail = f"stride {int(stride)}"
    else:
        frames, lengths = _segments(video_path, sync_idx, max_segments=len(names) + 8)
        frames = [f for f, ln in zip(frames, lengths) if ln >= MIN_SEG]
        lengths = [ln for ln in lengths if ln >= MIN_SEG]
        if len(frames) > len(names):
            frames, lengths = _merge_to_count(frames, lengths, len(names))
        detail = "automático"
        if len(frames) != len(names):
            # Respaldo por tiempo: las fases sinusoidales se fusionan al
            # trocear por estructura, pero cada patrón duró `hold` segundos.
            fps = _video_fps(video_path)
            if sync_end is None:
                sync_end = sync_idx + int(round(fps * sync_s)) if fps > 0 else sync_idx
            timed, why = _by_timing_fit(video_path, len(names), sync_end, hold)
            if timed is None:
                timed, why = _by_timing(video_path, len(names), sync_end, hold)
            if timed is not None:
                frames, detail = timed, why
            else:
                raise RuntimeError(
                    f"Se detectaron {len(frames)} patrones en {video_path.name} y se "
                    f"esperaban {len(names)} (config.json); el respaldo por tiempo "
                    f"tampoco llegó ({why}). Comprueba que el vídeo corresponde a "
                    "ese proyector, que no se corta antes de terminar, que el "
                    "hold/sincronía usados al proyectar coinciden con los indicados "
                    "y que el tamaño del proyector y el «cell_size» configurados "
                    "son los que se proyectaron.")

    for name, frame in zip(names, frames):
        cv2.imwrite(str(output_dir / f"{name}.png"), frame)

    print(f"Señal de sincronía detectada (frame {sync_idx}). {len(frames)} patrones "
          f"extraídos [{detail}] en {output_dir}")
    return len(frames)
