import cv2
import numpy as np
from pathlib import Path

def extract_patterns(video_path, output_dir, num_patterns=32):
    """
    Extrae patrones de un video grabado con DSLR.
    Detecta el inicio de la secuencia mediante un frame de sincronía (Blanco Puro).
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video: {video_path}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Limpiar archivos previos
    for f in output_dir.glob("col*.png"):
        f.unlink()

    pattern_count = 0
    sync_found = False

    while pattern_count < num_patterns:
        ret, frame = cap.read()
        if not ret: break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_val = np.mean(gray)

        if not sync_found:
            # Buscamos el blanco puro de sincronía (media > 240)
            if mean_val > 240:
                sync_found = True
                print("Señal de sincronía detectada (blanco puro).")
        else:
            # Una vez detectada la sincronía, el primer frame que NOTA un cambio
            # drástico de media es el inicio de nuestra secuencia
            if mean_val < 200:
                # Esto es una simplificación: el sistema espera una secuencia de patrones.
                # Para mayor robustez, el script guardará todos los frames detectados.
                # El calibrador luego usará los que necesite.
                cv2.imwrite(str(output_dir / f"col{pattern_count}.png"), frame)
                pattern_count += 1
                # Saltar frames para evitar capturar el mismo patrón varias veces (asumiendo 30fps)
                for _ in range(15): cap.read()

    cap.release()
    return pattern_count
