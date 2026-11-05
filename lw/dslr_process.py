"""Extracción offline de patrones desde un vídeo grabado con una DSLR.

Se graba la pantalla mientras el calibrador proyecta la secuencia de
`lw.patterns.make_sequence()`. Este módulo trocea el vídeo en un frame por
patrón y los guarda con el NOMBRE EXACTO del patrón (`black`, `white`,
`col00p`, `col00`, `row00p`, ..., `phx00`, ...), que es lo que necesita
`lw.patterns.Decoder.add()` para reconstruir la secuencia. Antes se guardaban
como `col0.png`, `col1.png`, ... y el decoder no podía decodificarlos.
"""
from __future__ import annotations

from pathlib import Path

import cv2

SYNC_MEAN = 240.0  # brillo medio del frame de sincronía (blanco puro "ideal")
SYNC_MIN = 170.0   # mínimo aceptable si la cámara subexpone el blanco
DARK_MEAN = 200.0  # por debajo de esto se considera el primer patrón (negro)
def _frame_mean(frame):
    """Brillo medio 0-255 del frame (se reduce para que vídeos largos vayan rápido)."""
    h, w = frame.shape[:2]
    if w > 320:
        frame = cv2.resize(frame, (320, max(1, int(h * 320 / w))),
                           interpolation=cv2.INTER_AREA)
    return float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean())


def _sync_threshold(video_path, sync_mean, probe_frames=None):
    """Devuelve (umbral, brillo_max, frames_leidos) para el blanco de sincronía.

    Un blanco proyectado y grabado con una cámara casi nunca llega a 240 de
    brillo medio (exposición automática, viñeteo, luz ambiente del local), así
    que si el umbral nominal no aparece en el vídeo se baja hasta algo por
    debajo del frame más brillante. Devuelve `umbral=None` si ni ese frame
    parece un blanco.

    Se recorre el vídeo ENTERO (no sólo el principio): si se empieza a grabar
    mucho antes de lanzar la secuencia, el blanco puede caer muy tarde.
    `probe_frames` permite limitar el sondeo a los N primeros frames.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el vídeo: {video_path}")
    peak = 0.0
    n = 0
    try:
        while probe_frames is None or n < int(probe_frames):
            ret, frame = cap.read()
            if not ret:
                break
            n += 1
            mean = _frame_mean(frame)
            if mean > peak:
                peak = mean
            if mean > sync_mean:
                # El blanco nominal está ahí: no hace falta seguir mirando.
                return sync_mean, peak, n
    finally:
        cap.release()

    if peak >= SYNC_MIN:
        # Blanco más apagado de lo ideal: se acepta un 90 % del frame más
        # brillante, que en una grabación real es el blanco de sincronía.
        return min(sync_mean, max(SYNC_MIN, peak * 0.9)), peak, n
    return None, peak, n


def extract_patterns(video_path, output_dir, names=None, num_patterns=32,
                     stride=15, sync_mean=SYNC_MEAN, dark_mean=DARK_MEAN):
    """Extrae un frame por patrón del vídeo y los guarda como `<nombre>.png`.

    names:
        Nombres de patrón EN ORDEN, tal como los devuelve
        `lw.dslr_offline.sequence_names()`. Si se omite se mantiene el modo
        antiguo (`col0.png`, `col1.png`, ...), que sólo sirve para inspeccionar
        el vídeo: el Decoder no puede decodificar esos nombres.
    stride:
        Frames que se descartan entre patrón y patrón (ajustar a los fps y a la
        duración de cada patrón en pantalla).
    sync_mean:
        Umbral de brillo del blanco de sincronía. Si el vídeo no llega a él se
        relaja automáticamente (ver `_sync_threshold`).

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

    # Limpiar capturas previas
    for f in output_dir.glob("*.png"):
        f.unlink()

    threshold, peak, probed = _sync_threshold(video_path, sync_mean)
    if probed == 0:
        raise RuntimeError(
            f"OpenCV no pudo decodificar ningún frame de {video_path.name}. "
            "El contenedor se abre pero el códec no (típico con HEVC/H.265 o "
            "vídeos de iPhone). Conviértelo a H.264/MP4 y vuelve a subirlo.")
    if threshold is None:
        raise RuntimeError(
            f"No se encontró el frame de sincronía en {video_path.name}: de {probed} "
            f"frames leídos, el más brillante tiene brillo medio {peak:.0f} "
            f"(se necesita al menos {SYNC_MIN:.0f}). "
            "Graba también el blanco de sincronía: empieza a grabar ANTES de "
            "lanzar la secuencia, con la exposición fija y el local a oscuras.")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el vídeo: {video_path}")

    saved = 0
    skip = 0
    sync_found = False
    sync_mean_seen = 0.0
    frames_after_sync = 0
    try:
        while saved < len(names):
            ret, frame = cap.read()
            if not ret:
                break
            mean = _frame_mean(frame)

            if not sync_found:
                # Antes de la sincronía (blanco puro) no hay secuencia todavía
                if mean > threshold:
                    sync_found = True
                    sync_mean_seen = mean
                continue
            frames_after_sync += 1
            if skip > 0:
                skip -= 1
                continue
            if saved == 0 and mean >= dark_mean:
                # El primer frame oscuro tras la sincronía es el patrón 'black'
                continue

            cv2.imwrite(str(output_dir / f"{names[saved]}.png"), frame)
            saved += 1
            skip = int(stride)
    finally:
        cap.release()

    if not sync_found:
        raise RuntimeError(
            f"No se encontró el frame de sincronía (brillo medio > {threshold:.0f}) "
            f"en {video_path}. Graba también el blanco de sincronía.")
    if saved < len(names):
        frames_left = frames_after_sync
        sugg = max(0, frames_left // len(names) - 1)
        raise RuntimeError(
            f"Sólo se extrajeron {saved} de {len(names)} patrones: el vídeo se acabó "
            f"antes ({frames_left} frames después del blanco de sincronía). "
            f"Con {frames_left} frames, el «stride» adecuado sería {sugg} "
            f"(ahora {int(stride)}). O el vídeo está incompleto.")

    print(f"Señal de sincronía detectada (brillo medio {sync_mean_seen:.0f}, "
          f"umbral {threshold:.0f}). {saved} patrones extraídos en {output_dir}")
    return saved
