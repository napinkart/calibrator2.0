"""
Guía de Configuración de Vídeo para DSLR Nikon D90
Para el calibrador LibreWarp

La Nikon D90 NO graba en 1080p, solo en 720p a 24fps.
El sensor CCD es menos sensible que los sensores CMOS modernos.
"""

def get_nikon_d90_settings():
    """
    Configuración óptima de la Nikon D90 para grabar vídeos de calibración.
    """
    settings = {
        "cámara": "Nikon D90",
        "modo": "Manual (M)",
        "vídeo": {
            "resolución": "720p (1280x720)",
            "fps": "24fps (o 30fps si disponible)",
            "calidad": "Alta"
        },
        "exposición": {
            "velocidad_obturación": "1/25s (máximo para evitar parpadeo del proyector)",
            "apertura": "f/4.0 a f/5.6 (más abierto para más luz)",
            "iso": "400 a 800 (crítico para la D90)"
        },
        "enfoque": {
            "modo": "Manual",
            "detalle": "Fijar una vez y bloquear, el foco NO debe moverse"
        },
        "balance_blancos": {
            "modo": "Manual",
            "opción": "Luz de día / Flash / 5500K"
        },
        "audio": {
            "modo": "Desactivado",
            "motivo": "Reduce la carga del procesador y el tamaño del archivo"
        }
    }
    return settings

def generate_streamlit_camera_guide():
    """
    Guía actualizada para mostrar en Streamlit.
    """
    guide = """
## 📷 Configuración de Nikon D90 para Calibración LibreWarp

### ⚠️ IMPORTANTE: No estás tomando FOTOS
¡Excelente! El workflow es correcto: grabas **VÍDEO** de 20-30 segundos.

### PASO A PASO DE LA D90:

1. **MENU -> Vídeo** -> Configurar:
   - Modo: **Manual [M]**
   - Calidad: **Alta**
   - Sonido: **OFF**

2. **CONFIGURACIÓN DE EXPOSICIÓN**:
   - Velocidad de obturación: **1/25s** (crítico para evitar parpadeo)
   - Apertura: **f/4.0** (abre el diafragma al máximo para más luz)
   - ISO: **400** (mínimo aceptable para la D90 en esta situación)

3. **AJUSTES DE VÍDEO**:
   - Enfoque: **Manual AF**
   - Balance de Blancos: **Preestablecido -> Luz de día**

4. **COMPROBACIÓN ANTES DE GRABAR**:
   - Apunta la cámara a la pantalla del calibrador.
   - Proyecta una imagen BLANCA (con el calibrador).
   - Mira el histograma en la D90. La "montaña" del histograma debe estar pegada a la DERECHA.
   - Si no está a la derecha, SUBE EL ISO a 800 o ABRE la apertura.

### 📊 VALORES DE BRILLO ESPERADOS:
- Frame más brillante: >= 240 (ideal)
- Frame más brillante: >= 180 (mínimo aceptable)
- Frame más brillante: < 180 -> **VÍDEO SUBEXPUESTO**

### 🎯 TIPS PARA LA D90:
- La D90 es antigua, SU FRAGUA NO ES SENSIBLE. No tengas miedo de subir a ISO 800.
- La D90 se sobrecalienta. No grabar más de 5 minutos seguidos.
- Usa tarjetas SD de clase 10 para evitar lag.
- Graba en trípode. Cualquier movimiento arruina la calibración.
"""
    return guide

# Configuración para el wizard de Streamlit
def get_dslr_recommendations(camera_model):
    if "Nikon D90" in camera_model:
        return {
            "iso_range": "400-800",
            "shutter": "1/25s",
            "aperture": "f/4 to f/5.6",
            "brightness_target": ">= 240",
            "notes": [
                "La D90 necesita ISO alto (400-800) para el brillo del blanco",
                "Usa apertura amplia (f/4) para compensar la falta de luz",
                "1/25s es el mínimo para evitar parpadeo del proyector"
            ]
        }
    return {}

if __name__ == "__main__":
    settings = get_nikon_d90_settings()
    print("=== CONFIGURACIÓN NIKON D90 ===")
    for key, value in settings.items():
        print(f"{key}: {value}")

    print("\n=== GUÍA STREAMLIT ===")
    print(generate_streamlit_camera_guide())