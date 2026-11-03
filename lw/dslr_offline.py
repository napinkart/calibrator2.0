# dslr_offline.py
import numpy as np
import cv2
from pathlib import Path
from lw import patterns

def run_offline_scan(cfg, projector_index, work_dir):
    work = Path(work_dir)
    raw_dir = work / f"raw_proj{projector_index}"

    # 1. Cargar configuración de patrones
    sc = cfg["scan"]
    cell = sc.get("cell_size", 16)
    w, h = cfg["projectors"][projector_index]["width"], cfg["projectors"][projector_index]["height"]
    phase_steps = sc.get("phase_steps", 8)

    # Decoder necesita saber las dimensiones exactas
    decoder = patterns.Decoder(w, h, cell, sc.get("min_contrast", 10),
                               sc.get("white_threshold", 25), sc.get("phase_period", 32),
                               phase_steps)

    # 2. Alimentar el decoder con los archivos extraídos
    # Asegurar orden numérico
    pattern_files = sorted(list(raw_dir.glob("col*.png")), key=lambda p: int(p.stem[3:]))
    if not pattern_files:
        raise RuntimeError(f"No hay patrones extraídos en {raw_dir}")

    for p in pattern_files:
        img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        # El decoder.add recibe el nombre del patrón y la imagen
        # Usamos 'col' como nombre genérico ya que el pipeline espera el orden de la secuencia
        decoder.add("col", img)

    # 3. Finalizar como un escaneo normal
    dec = decoder.result()
    # Guardar igual que lo hace el pipeline.py
    np.savez_compressed(work / f"scan_proj{projector_index}.npz",
                        width=w, height=h, cell=cell, **dec)
    print(f"Escaneo offline completado para proyector {projector_index}")
