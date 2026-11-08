# Solución al Error "No se encontró el blanco de sincronía"

## Problema Resumido

**Error**: "No se encontró el blanco de sincronía en temp_vid_0.mp4: el frame más brillante de todo el vídeo tiene brillo medio 132"

**Causa**: Vídeos grabados con iPhone 11 en formato **HEVC/H.265** no son compatibles con OpenCV 5.0.0 en Windows.

**Síntomas**:
- Brillo del frame más brillante: ~132/255 (muy bajo, se necesita >180)
- Error en sincronización de vídeo en el wizard de calibración
- Falla al procesar vídeos DSLR para extracción de patrones

## Soluciones Implementadas

### 1. Script de Conversión (`convert_iphone_video.py`)
- **Propósito**: Convertir automáticamente vídeos HEVC/H.265 a H.264/MJPG compatibles
- **Características**:
  - Usa ffmpeg (método preferido)
  - Usa HandBrakeCLI si ffmpeg no está disponible
  - Usa códec H.263 como último recurso
  - Proporciona guía manual si falla la auto-conversión
- **Comando**:
  ```bash
  python convert_iphone_video.py "video_original.mov" "video_convertido.mp4"
  ```

### 2. Validación Mejorada (`check_video.py`)
- **Nueva función**: `validate_video_for_calibrator()`
- **Análisis completo**:
  - Compatibilidad de códecs
  - Perfil de brillo (recomendaciones específicas)
  - Detección de frame de sincronización
  - Evaluación de duración
  - Puntuación de calidad (0-20)
- **Salida**: Puntuación con recomendaciones específicas
  - **15-20**: Video listo para calibrador
  - **10-14**: Aceptable, pero puede fallar
  - **0-9**: Probablemente fallará

### 3. Guía de Solución de Problemas (`VIDEO_TROUBLESHOOTING_GUIDE.md`)
- **Guía completa** para diagnosticar y solucionar el error
- **Lista de verificación pre-grabación**
- **Soluciones manuales para iPhone**
- **Configuración recomendada**

### 4. Interfaz de Usuario Mejorada (`wizard.py`)
- **Validación previa**: Ejecuta `check_video.py` antes de intentar procesamiento
- **Mensajes de error claros**: Muestra la salida completa del diagnóstico
- **Guía paso a paso**: Proporciona solución de problemas detallada
- **Continuación del modo manual**: Si el vídeo es inválido, continúa de todos modos

## Protocolo Recomendado

### Paso 1: Verificar Códec del Vídeo Actual
```bash
# Si tienes una copia del vídeo original
ffprobe -v error -show_entries format=codec_name -of default=noprint_wrappers=1:nokey=1 "tu_video.mov"
# Debe mostrar "h264" o "avc1", NO "hevc" o "h265"
```

### Paso 2: Convertir si es Necesario
```bash
# Usar script auto (recomendado)
python convert_iphone_video.py "video_hevc.mov" "video_convertido.mp4"

# Si falla, usar ffmpeg manualmente
ffmpeg -y -i "video_hevc.mov" -c:v libx264 -preset fast -crf 23 "video_convertido.mp4"
```

### Paso 3: Verificar con check_video.py
```bash
python check_video.py "video_convertido.mp4" --projector 0
```

### Paso 4: Cargar al Calibrador
- Usar el archivo convertido en el wizard
- Los mensajes de error ahora guían específicamente a través del problema

## Solución de Problemas Rápida

### Si el vídeo tiene brillo medio ~132:
**Problema**: El vídeo está subexpuesto
**Solución**: 
- Asegurar que el blanco de sincronización sea visible en la cámara
- Aumentar la exposición o grabar en mejor iluminación
- Posicionar la cámara para que vea toda la pantalla del calibrador

### Si el vídeo está en HEVC/H.265:
**Problema**: Códec incompatible con OpenCV
**Solución**: Convertir usando convert_iphone_video.py o HandBrake

### Si el vídeo es muy corto:
**Problema**: No hay suficiente tiempo para la secuencia
**Solución**: Grabar al menos 15 segundos, recomendado 20-30s

## Resumen del Sistema

### Puntuación del Vídeo (check_video.py)
- **15-20**: ✅ Video listo para calibrador
- **10-14**: ⚠️ Video aceptable, pero puede fallar
- **0-9**: ❌ Video no recomendado, se necesitan conversiones/grabación nueva

### Niveles de Brillo de Sincronización
- **> 280**: ✅ Excelente (máximo para la mayoría de proyectores)
- **> 240**: ✅ Recomendado
- **> 180**: ⚠️ Aceptable
- **< 180**: ❌ Deficiente (causa del error 132)

## Archivos Creados/Modificados

1. **convert_iphone_video.py** (nuevo) - Script de conversión
2. **check_video.py** (modificado) - Validación mejorada con puntuación
3. **wizard.py** (modificado) - Validación previa y mensajes de error mejorados
4. **VIDEO_TROUBLESHOOTING_GUIDE.md** (nuevo) - Guía completa de solución de problemas
5. **FIXES_SUMMARY.md** (nuevo) - Este resumen

## Próximos Pasos

1. **Si tienes el vídeo actual**: Probarlo con check_video.py
2. **Si el vídeo falla**: Seguir la guía de solución de problemas
3. **Si necesitas nuevo vídeo**: Usar el checklist pre-grabación
4. **Si necesitas ayuda**: Proporcionar la salida exacta del error de check_video.py

## Próximas Mejoras Potenciales

- Implementar verificación automática de códec antes de intentar procesamiento
- Agregar corrección automática de exposición para vídeos subexpuestos
- Agregar soporte para visualización en tiempo real del nivel de brillo del vídeo
- Integrar verificación automática del cuadro de sincronización con captura de pantalla