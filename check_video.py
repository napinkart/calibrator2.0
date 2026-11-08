"""Diagnóstico de un vídeo grabado para el modo offline (DSLR).

SOLO diagnostica: NO extrae patrones ni guarda frames de patrón. Imprime lo
que OpenCV ve del archivo (resolución, fps, frames decodificados), el brillo
de la zona iluminada (p95) a lo largo del vídeo y si el detector encuentra
el blanco de sincronía, para saber POR QUÉ fallaría un vídeo concreto.

Uso:
    python check_video.py C:\\ruta\\al\\video.mp4
    python check_video.py video.mp4 --projector 0 --hold 0.4 --sync 3

Código de salida: 0 si se decodifica y hay sincronía, 1 si no.
"""
from __future__ import annotations

import argparse
import json
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
from lw.dslr_process import _find_sync_frame, _p95, _small  # noqa: E402


def inspect(path, sync_s):
    print(f"\n=== {path.name} ({path.stat().st_size / 1e6:.1f} MB) ===")
    print(f"OpenCV {cv2.__version__}")

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        print("ERROR: OpenCV no puede abrir el archivo (ruta o contenedor).")
        return False

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    print(f"resolución {w}x{h} | fps {fps:g} | frames declarados {total}")
    if fps and total:
        print(f"duración {total / fps:.1f} s")

    p95s = []
    brightest, brightest_frame = -1.0, None
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        p = _p95(_small(frame))
        p95s.append(p)
        if p > brightest:
            brightest, brightest_frame = p, frame.copy()
    cap.release()

    n = len(p95s)
    print(f"frames decodificados de verdad: {n}")
    if n == 0:
        print("ERROR: el archivo se abre pero no se decodifica ningún frame "
              "(códec no soportado por este OpenCV: prueba a convertir a "
              "H.264/MP4 con HandBrake o ffmpeg).")
        return False

    arr = np.array(p95s)
    print(f"p95 (zona iluminada): min {arr.min():.0f} | mediana "
          f"{np.median(arr):.0f} | max {arr.max():.0f} (frame {int(arr.argmax())})")

    # Mapa temporal: p95 máximo en 40 tramos, para ver dónde está el blanco
    tramos = 40 if n >= 40 else n
    buckets = np.array_split(arr, tramos)
    line = "".join(" .:-=+*#%@"[min(9, int(b.max() // 26))] for b in buckets)
    print("p95 a lo largo del vídeo (cada carácter = 1/40 del vídeo):")
    print(f"  |{line}|")

    out = HERE / "work" / "_check"
    out.mkdir(parents=True, exist_ok=True)
    if brightest_frame is not None:
        cv2.imwrite(str(out / f"{path.stem}_frame_mas_brillante.png"), brightest_frame)
        print(f"guardado el frame más brillante en {out}")

    sync_idx, peak, sync_end = _find_sync_frame(path, sync_s=sync_s)
    if sync_idx is None:
        print(f"NO se encontró el blanco de sincronía (p95 máximo: {peak:.0f}). "
              "Empieza a grabar ANTES de lanzar la secuencia y encuadra la "
              "proyección en el centro del frame.")
        return False
    t0 = f" ({sync_idx / fps:.2f} s)" if fps else ""
    t1 = f" ({sync_end / fps:.2f} s)" if fps and sync_end else ""
    print(f"blanco de sincronía: frames {sync_idx}-{sync_end} "
          f"(p95 pico {peak:.0f}){t0} -> {t1}: ahí empieza la extracción")
    return True


def expected_patterns(projector):
    """Nº de patrones que espera la config para ese proyector, si se lee."""
    try:
        cfg = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
        return len(sequence_names(cfg, projector))
    except Exception as e:
        print(f"(no se pudo leer config.json para contar patrones: {e})")
        return None


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--projector", type=int, default=0)
    ap.add_argument("--hold", type=float, default=0.4,
                    help="segundos por patrón usados al proyectar (informativo)")
    ap.add_argument("--sync", type=float, default=3.0,
                    help="segundos de blanco de sincronía usados al proyectar")
    args = ap.parse_args()

    path = Path(args.video).expanduser()
    if not path.exists():
        sys.exit(f"No existe: {path}")

    n_pat = expected_patterns(args.projector)
    if n_pat is not None:
        print(f"la config espera {n_pat} patrones para el proyector "
              f"{args.projector} (hold {args.hold:g} s -> "
              f"{n_pat * args.hold:.0f} s de secuencia + {args.sync:g} s de "
              "sincronía, sin contar el margen antes/después)")

    ok = inspect(path, args.sync)
    print("\nDiagnóstico terminado: esto NO extrajo patrones; para extraer, "
          "sube el vídeo en la wizard (paso DSLR) o llama a "
          "lw.dslr_process.extract_patterns().")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
