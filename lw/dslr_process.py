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

SYNC_MEAN = 240.0  # brillo medio del frame de sincronía (blanco puro)
DARK_MEAN = 200.0  # por debajo de esto se considera el primer patrón (negro)


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

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el vídeo: {video_path}")

    saved = 0
    skip = 0
    sync_found = False
    try:
        while saved < len(names):
            ret, frame = cap.read()
            if not ret:
                break
            mean = float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean())

            if not sync_found:
                # Antes de la sincronía (blanco puro) no hay secuencia todavía
                if mean > sync_mean:
                    sync_found = True
                continue
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
            f"No se encontró el frame de sincronía (brillo medio > {sync_mean:.0f}) "
            f"en {video_path}. Graba también el blanco de sincronía.")
    if saved < len(names):
        raise RuntimeError(
            f"Sólo se extrajeron {saved} de {len(names)} patrones: el vídeo se acabó "
            f"antes. Revisa que esté completo y ajusta «stride».")

    print(f"Señal de sincronía detectada. {saved} patrones extraídos en {output_dir}")
    return saved
