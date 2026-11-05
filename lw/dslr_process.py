"""Extracción offline de patrones desde un vídeo grabado con una DSLR.

Se graba la pantalla mientras el calibrador proyecta la secuencia de
`lw.patterns.make_sequence()`. Este módulo trocea el vídeo en un frame por
patrón y los guarda con el NOMBRE EXACTO del patrón (`black`, `white`,
`col00p`, `col00`, `row00p`, ..., `phx00`, ...), que es lo que necesita
`lw.patterns.Decoder.add()` para reconstruir la secuencia.

Todo es AUTOMÁTICO:

* se recorre el vídeo entero (no importa la duración) hasta encontrar el blanco
  de sincronía, que se reconoce por ser un salto de brillo plano y sostenido;
* a partir de ahí cada cambio de ESTRUCTURA de la imagen marca un patrón
  nuevo, así que no hacen falta fps, segundos por patrón ni stride;
* los cambios de brillo global (autoexposición, banding del proyector) se
  ignoran, y de cada patrón se guarda el frame más representativo, no el
  primero ni el del medio.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path

import cv2
import numpy as np

SYNC_FLOOR = 120.0    # brillo medio mínimo para que un frame pueda ser el blanco
SYNC_JUMP = 1.25      # ... y que destaque un 25 % sobre lo más brillante visto antes
SYNC_FLAT = 25.0      # desviación típica máxima dentro del frame (el blanco es plano)
SYNC_STREAK = 3       # frames seguidos que debe mantenerse para darlo por bueno
DARK_MEAN = 200.0     # por debajo de esto se considera el primer patrón (negro)
STRUCT_TOL = 6.0      # diferencia de ESTRUCTURA que marca cambio de patrón
BRIGHT_TOL = 60.0     # salto de brillo global que también marca cambio de patrón
MIN_SEG = 2           # menos frames que esto es una transición, no un patrón
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
def _find_sync_frame(video_path):
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


def _clear_pngs(output_dir):
    for f in output_dir.glob("*.png"):
        f.unlink()


def extract_patterns(video_path, output_dir, names=None, num_patterns=32,
                     stride=None, dark_mean=DARK_MEAN):
    """Extrae un frame por patrón del vídeo y los guarda como `<nombre>.png`.

    names:
        Nombres de patrón EN ORDEN, tal como los devuelve
        `lw.dslr_offline.sequence_names()`. Si se omite se usa el modo antiguo
        (`col0.png`, `col1.png`, ...), que sólo sirve para inspeccionar el
        vídeo: el Decoder no puede decodificar esos nombres.
    stride:
        Déjalo en None (recomendado): el troceado es automático y no necesita
        saber fps ni segundos por patrón. Sólo si se indica un entero se usa el
        modo antiguo de saltar N frames entre patrón y patrón.

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

    sync_idx, peak = _find_sync_frame(video_path)
    if sync_idx is None:
        raise RuntimeError(
            f"No se encontró el blanco de sincronía en {video_path.name}: el frame "
            f"más brillante de todo el vídeo tiene brillo medio {peak:.0f}. Graba "
            "también los 3 s de blanco (empieza a grabar ANTES de lanzar la "
            "secuencia) y comprueba que el códec sea MJPG/AVI o H.264/MP4.")

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
        if len(frames) != len(names):
            raise RuntimeError(
                f"Se detectaron {len(frames)} patrones en {video_path.name} y se "
                f"esperaban {len(names)} (config.json). Comprueba que el vídeo "
                "corresponde a ese proyector, que no se corta antes de terminar y "
                "que el tamaño del proyector y el «cell_size» configurados son los "
                "que se proyectaron.")
        detail = "automático"

    for name, frame in zip(names, frames):
        cv2.imwrite(str(output_dir / f"{name}.png"), frame)

    print(f"Señal de sincronía detectada (frame {sync_idx}). {len(frames)} patrones "
          f"extraídos [{detail}] en {output_dir}")
    return len(frames)
