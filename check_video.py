"""Diagnóstico de un vídeo grabado para el modo offline (DSLR).

Imprime lo que OpenCV ve del archivo (códec, resolución, fps, frames), el
brillo medio frame a frame y pruebas la extracción de patrones de verdad, para
saber POR QUÉ falla un vídeo concreto.

Uso:
    python check_video.py C:\\ruta\\al\\video.mp4
    python check_video.py video.mp4 --projector 0 --hold 0.4
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

# La consola de Windows (cp1252) no puede escribir acentos ni signos raros:
# forzamos UTF-8 para que el diagnóstico no reviente al imprimir.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lw.dslr_offline import sequence_names  # noqa: E402
from lw.dslr_process import _find_sync_frame, extract_patterns  # noqa: E402


def _mean(frame):
    """Brillo medio 0-255 (se reduce el ancho para que sea rápido)."""
    h, w = frame.shape[:2]
    if w > 320:
        frame = cv2.resize(frame, (320, max(1, int(h * 320 / w))),
                           interpolation=cv2.INTER_AREA)
    return float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean())


def inspect(path):
    print(f"\n=== {path.name} ({path.stat().st_size / 1e6:.1f} MB) ===")
    print(f"OpenCV {cv2.__version__}")

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        print("ERROR: OpenCV no puede abrir el archivo (ruta o contenedor).")
        return None

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
    tag = "".join(chr((fourcc >> (8 * i)) & 0xFF) for i in range(4)).strip("\x00 ")
    print(f"resolución {w}x{h} | fps {fps:g} | frames {total} | códec '{tag}'")
    if fps:
        print(f"duración {(total / fps) if total else 0:.1f} s")

    means = []
    brightest, brightest_frame = -1.0, None
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        m = _mean(frame)
        means.append(m)
        if m > brightest:
            brightest, brightest_frame = m, frame.copy()
    cap.release()

    n = len(means)
    print(f"frames decodificados de verdad: {n}")
    if n == 0:
        print("ERROR: el archivo se abre pero no se decodifica ningún frame "
              "(códec no soportado: HEVC/H.265, AV1, iPhone, etc.). "
              "Conviértelo a H.264/MP4.")
        return None

    arr = np.array(means)
    print(f"brillo medio: min {arr.min():.0f} | mediana {np.median(arr):.0f} "
          f"| max {arr.max():.0f} (frame {int(arr.argmax())})")
    for thr in (240, 220, 200, 170, 150, 100):
        print(f"  frames con brillo > {thr}: {int((arr > thr).sum())}")

    # Mapa temporal: máximo de brillo en 40 tramos, para ver dónde está el blanco
    tramos = 40 if n >= 40 else n
    buckets = np.array_split(arr, tramos)
    line = "".join(" .:-=+*#%@"[min(9, int(b.max() // 26))] for b in buckets)
    print("brillo a lo largo del vídeo (cada carácter = 1/40 del vídeo):")
    print(f"  |{line}|")

    out = HERE / "work" / "_check"
    out.mkdir(parents=True, exist_ok=True)
    if brightest_frame is not None:
        cv2.imwrite(str(out / f"{path.stem}_frame_mas_brillante.png"), brightest_frame)
        print(f"guardado el frame más brillante en {out}")

    sync_idx, peak = _find_sync_frame(path)
    if sync_idx is None:
        print(f"NO se encontró el blanco de sincronía (frame más brillante: {peak:.0f})")
    else:
        t = f" ({sync_idx / fps:.2f} s)" if fps else ""
        print(f"blanco de sincronía en el frame {sync_idx}{t}: ahí empieza la extracción")
    return {"means": arr, "fps": fps, "n": n}


def try_extract(path, projector, stride=None):
    cfg_path = HERE / "config.json"
    try:
        import json
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        names = sequence_names(cfg, projector)
    except Exception as e:
        print(f"\nNo se pudo leer config.json ({e}): se prueba con 36 nombres genéricos.")
        names = [f"p{i}" for i in range(36)]

    out = HERE / "work" / "_check" / "raw"
    modo = "automático" if stride is None else f"stride {stride} forzado"
    print(f"\n== Prueba real: {len(names)} patrones, troceado {modo} ==")
    try:
        n = extract_patterns(Path(path), out, names=names,
                             stride=None if stride is None else int(stride))
        falta = [x for x in names if not (out / f"{x}.png").exists()]
        print(f"OK: {n} patrones extraídos, faltan {len(falta)}: {falta[:5]}")
    except Exception as e:
        print(f"FALLA: {type(e).__name__}: {e}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--projector", type=int, default=0)
    ap.add_argument("--stride", type=int, default=None,
                    help="forzar el modo antiguo con un stride concreto")
    args = ap.parse_args()

    path = Path(args.video).expanduser()
    if not path.exists():
        sys.exit(f"No existe: {path}")
    info = inspect(path)
    if info:
        try_extract(path, args.projector, args.stride)


if __name__ == "__main__":
    main()
