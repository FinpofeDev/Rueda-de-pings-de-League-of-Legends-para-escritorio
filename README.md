# Ping Wheel

Rueda de pings estilo **League of Legends** para tu escritorio. Usa la rueda radial de 8 direcciones del juego desde cualquier parte de Windows: mantén un atajo, mueve el mouse al sector, suelta, y el ping aparece en pantalla con su sonido y animación originales.

![demo](docs/demo.gif)

## Características

- **8 pings + Caution** con los iconos y sonidos originales del juego
- **Atajo configurable**: cualquier modificador (Ctrl/Alt/Shift/Win, combos, letras A-Z, números, F1-F12) + cualquier botón del mouse (incluyendo botones laterales)
- **Animación al soltar**: drop con bounce, ondas en perspectiva, fade-out — igual que en LoL
- **System tray icon**: activar/desactivar, silenciar, configurar atajo, salir
- **Una sola instancia**: el `.exe` se bloquea contra ejecuciones duplicadas
- **Persistencia**: la configuración se guarda en `%APPDATA%/PingWheel/`
- **Portable**: el `.exe` final no requiere Python ni librerías

## Cómo usar

1. Descarga `PingWheel.exe` de [Releases](../../releases) (o compílalo desde código).
2. Ejecútalo. Aparece un ícono dorado en la barra de tareas.
3. Por defecto: `Ctrl + click izquierdo` mantenido abre la rueda.
4. Mueve el mouse al sector que quieras y suelta.
5. Click derecho en el ícono del tray para configurar.

## Compilar desde código

Requiere Python 3.10+ (3.12 recomendado).

```bash
git clone https://github.com/<tu-usuario>/ping-wheel.git
cd ping-wheel
pip install -r requirements.txt
python ping_wheel.py
```

### Generar el .exe portable (Windows)

```bash
build.bat
```

El ejecutable queda en `dist/PingWheel.exe`. Lo puedes copiar a cualquier PC con Windows sin instalar nada más.

## Estructura del proyecto

```
ping-wheel/
├── ping_wheel.py        # codigo principal
├── build.bat            # script de compilacion a .exe
├── requirements.txt     # dependencias
├── icons/               # iconos PNG de los pings
└── sounds/              # sonidos OGG de los pings
```

## Tecnología

- **Python 3** + **PySide6** (Qt6) para la UI y el rendering
- **pynput** para los hooks globales de teclado/mouse
- **QMediaPlayer** para reproducir los sonidos OGG
- **Win32 API** (DWM + SetWindowRgn) para los overlays sin borde
- **PyInstaller** + **Pillow** para empaquetar el `.exe`

## Limitaciones conocidas

- El click se propaga a la app de atrás. Si abres la rueda sobre una ventana, esa ventana recibe el click. Workaround: usa el atajo en escritorio o áreas neutras, o configura un atajo con un botón menos invasivo (botón medio, lateral).
- El antivirus puede flaggear el `.exe` por usar hooks globales (comportamiento normal de cualquier app que detecte atajos del sistema).
- En Windows 11 muestra "App no reconocida" la primera vez. Click en "Más información" → "Ejecutar de todas formas".

## Créditos

Iconos y sonidos: © Riot Games. Este proyecto es un fan project no afiliado a Riot.

## Licencia

MIT — ver [LICENSE](LICENSE).
