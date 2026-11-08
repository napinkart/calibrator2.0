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

# Additional validation function to help diagnose video issues
def validate_video_for_calibrator(path):
    """
    Comprehensive validation of a video for the calibrator system.
    Returns detailed analysis and recommendations.
    """
    print("\n" + "="*60)
    print("VALIDACIÓN DETALLADA DEL VÍDEO PARA EL CALIBRADOR")
    print("="*60)

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        print("❌ ERROR: No se puede abrir el vídeo con OpenCV")
        return False

    # Basic video info
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
    tag = "".join(chr((fourcc >> (8 * i)) & 0xFF) for i in range(4)).strip("\x00 ")

    print(f"📹 INFORMACIÓN BÁSICA:")
    print(f"   Resolución: {w}x{h}")
    print(f"   FPS: {fps}")
    print(f"   Duración: {(total / fps) if total else 0:.1f}s")
    print(f"   Códec: '{tag}' (FourCC: {fourcc})")
    print(f"   Frames: {total}")

    # Check codec compatibility
    compatible_codecs = ['h264', 'avc1', 'H264', 'MP4V', 'MJPG', 'mp4v']
    is_compatible = tag.lower() in compatible_codecs

    print(f"\n🔍 VERIFICACIÓN DE COMPATIBILIDAD:")
    if is_compatible:
        print(f"   ✅ Códec compatible: '{tag}'")
    else:
        print(f"   ❌ CÓDEC NO COMPATIBLE: '{tag}'")
        print(f"      El calibrador solo soporta: {', '.join(compatible_codecs)}")
        print(f"      Problema: OpenCV 5.0.0 en Windows tiene soporte limitado")

    # Check brightness profile
    print(f"\n🌡️ ANÁLISIS DE BRILLO:")
    means = []
    brightest = 0.0
    sync_candidate_frame = -1
    sync_candidates = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        m = _mean(frame)
        means.append(m)
        if m > brightest:
            brightest = m

        # Look for potential sync white frames (brightest in video)
        if brightest > 220 and len(sync_candidates) < 5:
            sync_candidates.append((len(means)-1, m))
            if sync_candidate_frame == -1:
                sync_candidate_frame = len(means)-1

    cap.release()

    if not means:
        print("   ❌ No se pudieron leer frames del vídeo")
        return False

    arr = np.array(means)
    print(f"   Brillo medio mínimo: {arr.min():.0f}")
    print(f"   Brillo medio máximo: {arr.max():.0f} (frame {int(arr.argmax())})")
    print(f"   Brillo medio global: {arr.mean():.0f}")
    print(f"   Mediana: {np.median(arr):.0f}")

    # Check for sync white frame
    sync_frame_found = False
    if brightest > 180:
        print(f"\n✨ POSIBLE FRAME DE SINCRONÍA ENCONTRADO:")
        print(f"   Brillo máximo: {brightest:.0f} (frame {int(arr.argmax())})")
        if sync_candidate_frame >= 0:
            print(f"   Potencial sync en frame {sync_candidate_frame}")
            sync_frame_found = True
    else:
        print(f"\n❌ PROBLEMA DE SINCRONÍA:")
        print(f"   El brillo máximo ({brightest:.0f}) es muy bajo para la señal de sincronía")
        print(f"   Se necesita > 180, se recomienda > 240 para mejor detección")

    # Check duration
    duration = total / fps if total and fps else 0
    if duration < 10:
        print(f"\n⚠️  DURACIÓN INSUFICIENTE:")
        print(f"   Duración del vídeo: {duration:.1f}s")
        print(f"   Se recomienda al menos 15-20s para grabar la secuencia completa")

    # Check brightness distribution
    high_brightness_frames = (arr > 200).sum()
    print(f"\n📊 DISTRIBUCIÓN DE BRILLO:")
    print(f"   Frames > 200: {high_brightness_frames} ({high_brightness_frames/len(arr)*100:.1f}%)")
    print(f"   Frames > 180: {(arr > 180).sum()} ({(arr > 180).sum()/len(arr)*100:.1f}%)")
    print(f"   Frames > 240: {(arr > 240).sum()} ({(arr > 240).sum()/len(arr)*100:.1f}%)")

    # Overall assessment
    print(f"\n🎯 EVALUACIÓN GENERAL:")
    score = 0
    max_score = 20

    if is_compatible:
        print(f"   ✅ Códec compatible: +3")
        score += 3
    else:
        print(f"   ❌ Códec incompatible: 0")

    if brightest > 240:
        print(f"   ✅ Excelente brillo de sincronía: +5")
        score += 5
    elif brightest > 200:
        print(f"   ⚠️  Brillo de sincronía aceptable: +2")
        score += 2
    else:
        print(f"   ❌ Brillo de sincronía deficiente: 0")

    if duration >= 15:
        print(f"   ✅ Duración adecuada: +3")
        score += 3
    elif duration >= 10:
        print(f"   ⚠️  Duración aceptable: +1")
        score += 1
    else:
        print(f"   ❌ Duración insuficiente: 0")

    if high_brightness_frames / len(arr) > 0.1:
        print(f"   ✅ Suficientes frames brillantes: +2")
        score += 2
    else:
        print(f"   ❌ Pocos frames brillantes: 0")

    print(f"   Resolución ({w}x{h}): {'✅ Bueno' if w >= 1280 and h >= 720 else '⚠️ Aceptable' if w >= 640 else '❌ Baja'}: +{3 if w >= 1280 and h >= 720 else 1 if w >= 640 else 0}")
    score += (3 if w >= 1280 and h >= 720 else 1 if w >= 640 else 0)

    print(f"   FPS ({fps}): {'✅ Bueno' if fps >= 30 else '⚠️ Aceptable' if fps >= 15 else '❌ Bajo'}: +{3 if fps >= 30 else 1 if fps >= 15 else 0}")
    score += (3 if fps >=  Labrador else 1 if fps >= 15 else 0)

    print(f"   FPS ({fps}): {'✅ Bueno' if fps >= 30 else '⚠️ Aceptable' if fps >= 15 else '❌ Bajo'}: +{3 if fps >= 30 else 1 if fps >= 15 else 0}")
    score += (3 if fps >= 30 else 1 if fps >= 15 else 0)

    print(f"\n📋 RESULTADO FINAL:")
    if score >= 15:
        print(f"   ✅ Video RECOMENDADO para calibrador (puntuación: {score}/{max_score})")
        return True
    else:
        print(f"   ⚠️ Video NO RECOMENDADO (puntuación: {score}/{max_score})")
        print(f"   Se recomiendan conversiones manuales o nuevo grabado")
        return False

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--projector", type=int, default=0)
    ap.add_argument("--stride", type=int, default=None,
                    help="forzar el modo antiguo con un stride concreto")
    ap.add_argument("--validate-only", action="store_true",
                    help="solo hacer validación, no intentar extracción")
    args = ap.parse_args()

    path = Path(args.video).expanduser()
    if not path.exists():
        sys.exit(f"No existe: {path}")

    # First, validate the video
    print(f"\n🔬 VALIDACIÓN DEL VÍDEO: {path.name}")
    validation_ok = validate_video_for_calibrator(path)

    if validation_ok and not args.validate_only:
        # If validation passed, run the original analysis
        print(f"\n" + "="*60)
        print(f"ANÁLISIS COMPLETO DEL VÍDEO: {path.name}")
        print("="*60)
        info = inspect(path)
        if info:
            try_extract(path, args.projector, args.stride)
    elif not validation_ok:
        # Show troubleshooting guide
        print(f"\n" + "="*60)
        print("SOLUCIÓN DE PROBLEMAS DETALLADA")
        print("="*60)

        print(f"\n🔧 Pasos recomendados para solucionar:")
        print(f"\n1️⃣  Solución inmediata (si tienes permisos):")
        print(f"   Abrir terminal en el directorio del vídeo")
        print(f"   Ejecutar: ffmpeg -y -i input_video.mov -c:v libx264 -preset fast -crf 23 converted_video.mp4")
        print(f"   Reemplazar input_video.mov con tu archivo real")

        print(f"\n2️⃣  Manual (HandBrake):")
        print(f"   Descargar: https://handbrake.fr")
        print(f"   Abrir video > Formato: MP4 > Códec: x264 > Calidad: 20")
        print(f"   Guardar como 'converted_video.mp4'")

        print(f"\n3️⃣  Grabar nuevo vídeo:")
        print(f"   Abrir la aplicación calibrador")
        print(f"   Asegurarse que la cámara vea la pantalla completamente")
        print(f"   Iniciar grabación ANTES de proyectar la secuencia")
        print(f"   Proyectar secuencia con: Ctrl+P (o similar)")
        print(f"   Grabar al menos 20 segundos")

        print(f"\n4️⃣  Configuración recomendada:")
        print(f"   Resolución: 1920x1080 (o al menos 1280x720)")
        print(f"   FPS: 30 (o 60 si es posible)")
        print(f"   Códec: H.264 (no HEVC/H.265)")
        print(f"   Atención al brillo: el blanco debe ser muy brillante (>240)")

        print(f"\n5️⃣  Cómo mejorar el brillo del vídeo:")
        print(f"   Asegurar que el blanco de sincronía sea visible para la cámara")
        print(f"   Enfocar correctamente (no con poca luz)")
        print(f"   Aumentar la exposición si el vídeo está subexpuesto")
        print(f"   Grabar en lugar bien iluminado")

        # Try extraction anyway for backward compatibility
        try:
            try_extract(path, args.projector, args.stride)
        except Exception as e:
            print(f"\n❌ Falló incluso la extracción: {e}")
            return
    else:
        print(f"\n✅ Vídeo válido, continuando con extracción normal...")
        info = inspect(path)
        if info:
            try_extract(path, args.projector, args.stride)


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
