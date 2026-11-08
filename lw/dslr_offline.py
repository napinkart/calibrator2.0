"""Escaneo offline: decodifica frames ya capturados (por ejemplo de un vídeo DSLR).

Sustituye a la captura en vivo de `lw.pipeline._capture_sequence()` alimentando
el mismo `patterns.Decoder` con imágenes de disco, con el mismo nombre de patrón,
y guarda `work/scan_projN.npz` con el mismo formato, de modo que los pasos
siguientes (compute, verify) no notan la diferencia.
"""
from __future__ import annotations

import copy
import shutil
from pathlib import Path

import cv2
import numpy as np

from lw import patterns
from lw.config import normalize


def _scan_params(cfg, projector_index):
    """Normaliza la config y devuelve los parámetros del escaneo.

    Hay que pasar por `lw.config.normalize()`: en config.json los proyectores
    sólo tienen name/display/output, y width/height/rect los calcula normalize()
    a partir del layout del display. Sin eso no hay tamaño de proyector.
    """
    cfg = normalize(copy.deepcopy(cfg))
    sc = cfg["scan"]
    proj = cfg["projectors"][int(projector_index)]
    return (
        sc,
        proj,
        int(proj["width"]),
        int(proj["height"]),
        int(sc.get("cell_size", 16)),
        int(sc.get("phase_steps", 8)),
        float(sc.get("phase_period", 32)),
    )


def sequence_names(cfg, projector_index):
    """Nombres de patrón en el orden proyectado, para ese proyector.

    Salen del propio generador (`patterns.make_sequence`) para que no exista una
    segunda copia del nombrado que pueda desincronizarse del Decoder.
    """
    sc, _proj, w, h, cell, phase_steps, phase_period = _scan_params(cfg, projector_index)
    return [name for name, _ in patterns.make_sequence(
        w, h, cell, sc.get("pattern_intensity", 255), phase_steps, phase_period, False)]


def run_offline_scan(cfg, projector_index, work_dir, log=print):
    """Decodifica `work/raw_projN/<patrón>.png` y guarda `work/scan_projN.npz`.

    Devuelve el dict decodificado (el mismo que produce el escaneo en vivo).
    """
    work = Path(work_dir)
    sc, proj, w, h, cell, phase_steps, phase_period = _scan_params(cfg, projector_index)
    raw_dir = work / f"raw_proj{projector_index}"
    if not raw_dir.is_dir():
        raise RuntimeError(f"No existe la carpeta de frames {raw_dir}")

    decoder = patterns.Decoder(w, h, cell, sc.get("min_contrast", 10),
                               sc.get("white_threshold", 25), phase_period, phase_steps)

    names = sequence_names(cfg, projector_index)
    missing = [n for n in names if not (raw_dir / f"{n}.png").exists()]
    if missing:
        raise RuntimeError(
            f"Faltan {len(missing)} de {len(names)} patrones en {raw_dir}: "
            + ", ".join(missing[:8]) + ("..." if len(missing) > 8 else "")
            + ". Extrae primero el vídeo con extract_patterns().")

    for name in names:
        img = cv2.imread(str(raw_dir / f"{name}.png"), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise RuntimeError(f"No se pudo leer {raw_dir / (name + '.png')}")
        decoder.add(name, img)

    dec = decoder.result()
    out = work / f"scan_proj{projector_index}.npz"
    np.savez_compressed(out, width=w, height=h, cell=cell, **dec)
    log(f"Proyector {projector_index} ({proj.get('name', '?')}): {len(names)} patrones, "
        f"{dec['valid'].mean() * 100:.1f}% de píxeles válidos -> {out.name}")

    # Los mismos artefactos que escribe el escaneo en vivo, para que la wizard
    # los trate igual: sin ellos el paso de bordes cree que no se escaneó.
    # all_white_proj{i}.png = el frame blanco extraído del vídeo (misma pose
    # de cámara y proyector en blanco que la captura en vivo equivalente).
    white_png = raw_dir / "white.png"
    if white_png.is_file():
        shutil.copyfile(white_png, work / f"all_white_proj{projector_index}.png")
    try:
        from lw.pipeline import contact_sheet, decoded_preview
        sheet = contact_sheet(raw_dir)
        if sheet is not None:
            cv2.imwrite(str(work / f"captures_proj{projector_index}.png"), sheet)
        cv2.imwrite(str(work / f"decoded_proj{projector_index}.png"),
                    decoded_preview(dec, w, h, cell))
    except Exception as e:  # el preview no bloquea el escaneo
        log(f"(aviso: no se pudieron generar previews: {e})")
    return dec
