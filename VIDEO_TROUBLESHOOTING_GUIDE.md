# Guía de Solución de Problemas de Vídeo para el Calibrador

## Error Común: "No se encontró el blanco de sincronía en temp_vid_0.mp4: el frame más brillante de todo el vídeo tiene brillo medio 132"

Este error ocurre cuando el sistema no puede detectar la señal de sincronización (el blanco brillante que indica el inicio de la secuencia de patrones).

## Causas Principales

### 1. Proyectos de grabación
- **iPhone 11/12/13**: Graba en **HEVC/H.265** por defecto (no compatible)
- **iPhone con configuración de grabación**: Debe estar en "H.264" o "Grabación continua"
- **Configuración móvil**: Debe estar en alta calidad, alta resolución, alta precisión de color

### 2. Configuración de la cámara
- **Posición incorrecta**: La cámara no puede ver la pantalla del calibrador
- **Mala iluminación**: El blanco de sincronización no es lo suficientemente brillante
- **Enfoque incorrecto**: Vídeo borroso, el blanco no es distintivo
- **Desajuste de exposición**: El vídeo está subexpuesto o sobreexpuesto

### 3. Proceso de grabación
- **Grabar DESPUÉS de proyectar la secuencia**: Debe grabar EL BLANCO primero
- **Duración insuficiente**: Menos de 10 segundos (se necesitan 15-20s)
- **Códec incompatible**: HEVC/H.265, AV1, iPhone proprietary

## Diagnóstico del Error

El error muestra que el frame más brillante tiene brillo medio **132/255** (muy bajo).

### Niveles de brillo recomendados:
- **Mínimo aceptable**: >180 (frame de sincronización débil)
- **Recomendado**: >240 (frame de sincronía óptimo)
- **Excelente**: >280 (máximo para la mayoría de proyectores)

## Soluciones Inmediatas

### Opción 1: Convertir vídeo actual (si tienes una copia)
```bash
# Usar convert_iphone_video.py (ya creado)
python convert_iphone_video.py "tu_video.mov" "video_convertido.mp4"

# Si falla, usar ffmpeg manualmente
ffmpeg -y -i "video_original.mov" -c:v libx264 -preset fast -crf 23 "video_convertido.mp4"
```

### Opción 2: Grabar nuevo vídeo
1. **Abrir la aplicación calibrador**
2. **Posicionar la cámara** para ver toda la pantalla del calibrador
3. **Verificar iluminación**: La pantalla debe ser visible en la cámara
4. **Iniciar grabación** ANTES de proyectar la secuencia
5. **Proyectar secuencia** (Ctrl+P o el comando apropiado)
6. **Grabar al menos 15-20 segundos** (incluyendo el blanco de sincronización)

## Soluciones Manuales para iPhone

### HandBrake (Windows)
1. Descargar: https://handbrake.fr
2. Abrir vídeo HEVC/H.265
3. Configuración:
   - Formato: MP4
   - Códec de vídeo: x264
   - Calidad: 20 (inferior = más calidad, 18-22 mejor)
   - Resolución: Mantenida (para 1080p)
4. Guardar como "video_convertido.mp4"

### AlternativeTools
- **Shotcut**: Gratis, conversiones rápidas
- **Avidemux**: Simple, interfaz limpia
- **VLC**: Puede convertir códecs

## Lista de Verificación Pre-Grabación

### ✅ Preparación de vídeo
- [ ] Cámara ve toda la pantalla del calibrador
- [ ] Iluminación uniforme (sin sombras)
- [ ] El blanco de sincronización será visible en cámara
- [ ] Grabación en formato .mov o .mp4
- [ ] Códec H.264 (no HEVC/H.265)
- [ ] Resolución 1280x720 o superior

### ✅ Configuración del calibrador
- [ ] Cámara bien enfocada
- [ ] Exposición ajustada (el blanco debe ser brillante)
- [ ] Inicio de grabación ANTES de proyectar secuencia
- [ ] Grabar al menos 15 segundos
- [ ] Guardar con códec compatible

## Usando check_video.py para diagnóstico

Después de convertir o grabar nuevo vídeo:

```bash
python check_video.py "video.mp4" --projector 0
```

La nueva versión de check_video.py muestra:

### 🎯 Resultados de validación:
- Códec del vídeo (compatible/incompatible)
- Perfil de brillo (mínimo/máximo/promedio)
- Detección de frame de sincronización
- Recomendaciones específicas
- Puntuación general (0-20 puntos)

### ✅ Puntajes:
- **15-20**: Video listo para calibrador
- **10-14**: Aceptable, pero puede fallar
- **0-9**: Probablemente fallará

## Solución de Problemas Específicos

### Problema: "brillo medio 132"
**Solución:** El vídeo está subexpuesto. Aumentar la exposición o grabar en mejor iluminación.

### Problema: Códec HEVC/H.265
**Solución:** Convertir a H.264 usando HandBrake o convert_iphone_video.py.

### Problema: Cámara no ve el blanco
**Solución:** Reposicionar cámara, mejorar iluminación, o grabar de nuevo.

### Problema: Vídeo muy corto
**Solución:** Grabar más tiempo (mínimo 15s, recomendado 20-30s).

## Códecs Compatibles

### ✅ Muy Bueno (Recommandado)
- **H.264** (código: h264, avc1)
- **MJPG** (código: MJPG)
- **MP4V** (código: MP4V)

### ❌ Malo (Evitar)
- **HEVC/H.265** (código: hevc, h265)
- **AV1** (código: av01)
- **Códecs propietarios de iPhone**

## Comando Útil Rápido

Si tienes un vídeo iPhone que falló:

```bash
# Comprobar códec actual
ffprobe -v error -show_entries format=codec_name -of default=noprint_wrappers=1:nokey=1 "tu_video.mov"

# Convertir a H.264
ffmpeg -y -i "tu_video.mov" -c:v libx264 -preset fast -crf 23 -c:a aac "video_convertido.mp4"

# Probar con check_video
python check_video.py "video_convertido.mp4"
```

## Recursos

- **Documentación de OpenCV**: https://docs.opencv.org/ para soporte de códecs
- **Documentación de ffmpeg**: https://ffmpeg.org/ para conversiones masivas
- **Comunidad del calibrador**: Para soporte específico con los logs exactos del error

Si sigues teniendo problemas después de seguir esta guía, el sistema ahora mostrará recomendaciones de solución de problemas detalladas para continuar con el modo manual.