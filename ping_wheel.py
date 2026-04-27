"""
LoL Ping Wheel - v1.2
=====================
Cambios v1.2 sobre v1.1:
- Autostart con Windows: toggle en el tray menu para iniciar la app
  automaticamente al login (registry HKCU\\...\\Run, no requiere admin)

Cambios previos (v1.1):
- Sonidos OGG: QMediaPlayer reproduce los SFX al dropear cada ping
- Ondas mas grandes: WIDGET_SIZE 360, RING_MAX_W 160
- Toggle "Silenciar" en el tray menu
- Dialog de config rediseado, sin fixed size
- Modificadores extendidos: Ctrl/Alt/Shift/Win + combos +
  todas las letras A-Z + 0-9 + F1-F12
- Botones laterales del mouse: x1 (atras) y x2 (adelante)
- Singleton lock con QSharedMemory: una sola instancia

Estructura:
    ping_wheel.py
    icons/
        Caution_ping.png, Retreat_ping.png, etc.
    sounds/
        Caution_ping_SFX.ogg, Retreat_ping_SFX.ogg, etc.

Build:
    Doble click en build.bat
"""

import os
import sys
import json
import math
import ctypes
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QWidget, QSystemTrayIcon, QMenu, QDialog,
    QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QMessageBox, QFormLayout,
)
from PySide6.QtCore import (
    Qt, QPointF, QTimer, Signal, QObject, QRectF, QUrl, QSharedMemory,
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QFont, QCursor, QPainterPath,
    QRadialGradient, QPixmap, QRegion, QIcon, QAction,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from pynput import mouse, keyboard


# ===================================================================
# Paths
# ===================================================================
def get_paths():
    if getattr(sys, 'frozen', False):
        bundled_dir = Path(sys._MEIPASS)
    else:
        bundled_dir = Path(__file__).resolve().parent

    if sys.platform == "win32":
        appdata = os.environ.get("LOCALAPPDATA", str(Path.home()))
        config_dir = Path(appdata) / "PingWheel"
    else:
        config_dir = Path.home() / ".config" / "ping_wheel"

    config_dir.mkdir(parents=True, exist_ok=True)
    return bundled_dir, config_dir


BUNDLED_DIR, CONFIG_DIR = get_paths()
ICONS_DIR = BUNDLED_DIR / "icons"
SOUNDS_DIR = BUNDLED_DIR / "sounds"
CONFIG_FILE = CONFIG_DIR / "config.json"


# ===================================================================
# Config
# ===================================================================
DEFAULT_CONFIG = {
    "modifier": "ctrl",
    "button": "left",
    "enabled": True,
    "muted": False,
    "volume": 0.7,
}


def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return {**DEFAULT_CONFIG, **cfg}
        except Exception as e:
            print(f"[CONFIG] Error cargando: {e}")
    return DEFAULT_CONFIG.copy()


def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"[CONFIG] Error guardando: {e}")


# ===================================================================
# Pings (con sonidos)
# ===================================================================
PINGS = [
    {"label": "RETIRADA",     "color": "#E74C3C",
     "icon":  "Retreat_ping.png",
     "sound": "Retreat_ping_SFX.ogg",         "angle":   90},
    {"label": "VISION",      "color": "#E74C3C",
     "icon":  "Enemy_Vision_ping.png",
     "sound": "Bait_ping_SFX.ogg",            "angle":   135},
    {"label": "EN CAMINO",    "color": "#3498DB",
     "icon":  "On_My_Way_ping_colorblind.png",
     "sound": "On_My_Way_ping_far_SFX.ogg",   "angle":    0},
    {"label": "ATACAR",       "color": "#F1C40F",
     "icon":  "All_In_ping.png",
     "sound": "All_In_ping_SFX.ogg",          "angle":  -45},
    {"label": "AVANZAR",      "color": "#2ECC71",
     "icon":  "Assist_Me_ping.png",
     "sound": "Push_ping_SFX.ogg",            "angle":  -90},
    {"label": "NECESITO VISION",     "color": "#2ECC71",
     "icon":  "Need_Vision_ping.png",
     "sound": "Hold_ping_SFX.ogg",            "angle": -135},
    {"label": "DESAPARECIDO", "color": "#F1C40F",
     "icon":  "Enemy_Missing_ping.png",
     "sound": "Enemy_Missing_ping_SFX.ogg",   "angle":  180},
    {"label": "ASISTENCIA",   "color": "#2ECC71",
     "icon":  "Push_ping.png",
     "sound": "Assist_Me_ping_SFX.ogg",       "angle":  45},
]

CAUTION = {"label": "CUIDADO", "color": "#F1C40F",
           "icon": "Caution_ping.png",
           "sound": "Caution_ping_SFX.ogg"}

GOLD = QColor(201, 169, 90)
GOLD_DIM = QColor(140, 115, 60)
BG_DEEP = QColor(13, 24, 32, 235)
BG_INNER = QColor(18, 38, 50, 245)
SECTOR_TINT_DARK = QColor(0, 0, 0, 60)
SECTOR_TINT_LIGHT = QColor(255, 255, 255, 8)


# ===================================================================
# Sound player: pre-carga un QMediaPlayer por sonido
# ===================================================================
class SoundPlayer:
    """Pre-carga todos los sonidos como QMediaPlayer.
    Un player por archivo permite reproducir varios pings solapados
    (cada player toca su sonido sin interferir con los demas)."""

    def __init__(self, config):
        self.config = config
        self.players = {}

        all_sounds = [p["sound"] for p in PINGS] + [CAUTION["sound"]]
        for sound_file in set(all_sounds):
            path = SOUNDS_DIR / sound_file
            if not path.exists():
                print(f"[SOUND] No encontrado: {path}")
                continue
            try:
                player = QMediaPlayer()
                output = QAudioOutput()
                player.setAudioOutput(output)
                player.setSource(QUrl.fromLocalFile(str(path)))
                self.players[sound_file] = (player, output)
            except Exception as e:
                print(f"[SOUND] Error cargando {sound_file}: {e}")

    def play(self, sound_file):
        if self.config.get("muted", False):
            return
        if sound_file not in self.players:
            return
        player, output = self.players[sound_file]
        volume = float(self.config.get("volume", 0.7))
        output.setVolume(max(0.0, min(1.0, volume)))
        # Rebobinar para que pings rapidos del mismo tipo se oigan
        player.setPosition(0)
        player.play()


# ===================================================================
# Win32 API tweaks (DWM + SetWindowRgn)
# ===================================================================
_dwm_initialized = False
_DwmSetWindowAttribute = None
_winrgn_initialized = False
_CreateEllipticRgn = None
_SetWindowRgn = None


def _init_win32():
    global _dwm_initialized, _DwmSetWindowAttribute
    global _winrgn_initialized, _CreateEllipticRgn, _SetWindowRgn

    if sys.platform != "win32":
        return

    if not _dwm_initialized:
        try:
            from ctypes import wintypes
            dwmapi = ctypes.windll.dwmapi
            dwmapi.DwmSetWindowAttribute.argtypes = [
                wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
            ]
            dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
            _DwmSetWindowAttribute = dwmapi.DwmSetWindowAttribute
            _dwm_initialized = True
        except Exception as e:
            print(f"[WIN32] DWM init fallo: {e}")

    if not _winrgn_initialized:
        try:
            gdi32 = ctypes.windll.gdi32
            user32 = ctypes.windll.user32
            gdi32.CreateEllipticRgn.argtypes = [
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ]
            gdi32.CreateEllipticRgn.restype = ctypes.c_void_p
            user32.SetWindowRgn.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool,
            ]
            user32.SetWindowRgn.restype = ctypes.c_int
            _CreateEllipticRgn = gdi32.CreateEllipticRgn
            _SetWindowRgn = user32.SetWindowRgn
            _winrgn_initialized = True
        except Exception as e:
            print(f"[WIN32] Region init fallo: {e}")


def kill_windows_chrome(hwnd_int):
    if sys.platform != "win32":
        return
    _init_win32()
    if _DwmSetWindowAttribute is None:
        return

    def _set(attr_id, value, label):
        v = ctypes.c_uint(value & 0xFFFFFFFF)
        try:
            hr = _DwmSetWindowAttribute(
                hwnd_int, attr_id, ctypes.byref(v), ctypes.sizeof(v),
            )
            if hr != 0:
                print(f"[DWM] {label} fallo: HRESULT={hr:#010x}")
        except Exception as e:
            print(f"[DWM] {label} excepcion: {e}")

    _set(34, 0xFFFFFFFE, "BORDER_COLOR=NONE")
    _set(33, 1, "CORNER=DONOTROUND")
    _set(2, 1, "NCRENDERING=DISABLED")
    _set(3, 1, "TRANSITIONS=FORCE_DISABLED")


def apply_elliptic_region(hwnd_int, width, height):
    if sys.platform != "win32":
        return
    _init_win32()
    if _CreateEllipticRgn is None or _SetWindowRgn is None:
        return
    try:
        hrgn = _CreateEllipticRgn(0, 0, width, height)
        if not hrgn:
            return
        _SetWindowRgn(hwnd_int, hrgn, True)
    except Exception as e:
        print(f"[WINRGN] excepcion: {e}")


# ===================================================================
# Autostart con Windows (registry HKCU\...\Run)
# ===================================================================
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_VALUE_NAME = "PingWheel"


def _get_executable_path():
    """Devuelve la ruta completa al .exe (si esta empaquetado) o al
    script .py con el python que lo corre. Esto es lo que registramos
    para que Windows lo ejecute al inicio."""
    if getattr(sys, 'frozen', False):
        # Empaquetado con PyInstaller: sys.executable es el .exe
        return f'"{sys.executable}"'
    # En desarrollo: python.exe + path al script
    script = Path(__file__).resolve()
    return f'"{sys.executable}" "{script}"'


def is_autostart_enabled():
    """True si la app esta configurada para iniciar con Windows."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY,
                            0, winreg.KEY_READ) as key:
            try:
                value, _ = winreg.QueryValueEx(key, AUTOSTART_VALUE_NAME)
                return bool(value)
            except FileNotFoundError:
                return False
    except Exception as e:
        print(f"[AUTOSTART] Error leyendo: {e}")
        return False


def set_autostart(enabled):
    """Activa o desactiva el inicio con Windows.
    Escribe en HKEY_CURRENT_USER (no requiere admin)."""
    if sys.platform != "win32":
        print("[AUTOSTART] Solo soportado en Windows")
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY,
                            0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                exe_path = _get_executable_path()
                winreg.SetValueEx(
                    key, AUTOSTART_VALUE_NAME, 0,
                    winreg.REG_SZ, exe_path,
                )
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_VALUE_NAME)
                except FileNotFoundError:
                    pass  # ya no existia, ok
        return True
    except Exception as e:
        print(f"[AUTOSTART] Error escribiendo: {e}")
        return False


# ===================================================================
def ease_out_back(t):
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def ease_out_quad(t):
    return 1 - (1 - t) ** 2


def load_pixmap(filename):
    path = ICONS_DIR / filename
    if path.exists():
        return QPixmap(str(path))
    print(f"[WARN] Icono no encontrado: {path}")
    return QPixmap()


# ===================================================================
class BorderlessOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAutoFillBackground(False)

        self.create()
        self._apply_native_tweaks()

    def _apply_native_tweaks(self):
        try:
            hwnd = int(self.winId())
            kill_windows_chrome(hwnd)
            if self.width() > 0 and self.height() > 0:
                apply_elliptic_region(hwnd, self.width(), self.height())
        except Exception as e:
            print(f"[NATIVE] excepcion: {e}")

    def _apply_circular_mask(self):
        if self.width() > 0 and self.height() > 0:
            self.setMask(QRegion(self.rect(), QRegion.Ellipse))

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_circular_mask()
        self._apply_native_tweaks()

    def resizeEvent(self, event):
        self._apply_circular_mask()
        self._apply_native_tweaks()
        super().resizeEvent(event)


# ===================================================================
# Animacion del ping dropeado (mas grande, las ondas no se cortan)
# ===================================================================
class PingAnimation(BorderlessOverlay):
    DURATION_MS = 1800
    WIDGET_SIZE = 360       # antes 260: ahora el ring de 320px de
                            # ancho cabe con margen para que no se corte
    ICON_BASE_SIZE = 60
    RING_MAX_W = 160        # ancho radial; el ring termina con
                            # diametro = RING_MAX_W * 2 = 320px
    RING_ASPECT = 0.32

    def __init__(self, x, y, icon, color_hex):
        super().__init__()
        size = self.WIDGET_SIZE
        self.setGeometry(x - size // 2, y - size // 2, size, size)

        if icon and not icon.isNull():
            self.icon = icon.scaled(
                self.ICON_BASE_SIZE, self.ICON_BASE_SIZE,
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
        else:
            self.icon = QPixmap()

        self.color = QColor(color_hex)
        self.elapsed_ms = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

        self.show()
        self.raise_()

    def _tick(self):
        self.elapsed_ms += 16
        if self.elapsed_ms >= self.DURATION_MS:
            self.timer.stop()
            self.hide()
            # NO usar deleteLater: si la lista del wheel todavia tiene
            # referencia, isVisible() truena con RuntimeError. Dejamos
            # que Python lo GC'ee cuando la lista lo suelte.
            return
        self.update()

    def _draw_ground_ring(self, p, cx, ground_y, progress, thickness):
        if progress <= 0 or progress >= 1:
            return
        w = progress * self.RING_MAX_W * 2
        h = w * self.RING_ASPECT
        alpha = int((1 - progress) * 220)
        c = QColor(self.color)
        c.setAlpha(alpha)
        p.setPen(QPen(c, thickness))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, ground_y), w / 2, h / 2)

    def paintEvent(self, event):
        if self.icon.isNull():
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        cx = self.width() / 2
        cy = self.height() / 2
        t = self.elapsed_ms / self.DURATION_MS

        if t < 0.083:
            phase = t / 0.083
            scale = ease_out_back(phase) * 1.3
            opacity = phase
        elif t < 0.139:
            phase = (t - 0.083) / 0.056
            scale = 1.3 - phase * 0.3
            opacity = 1.0
        elif t < 0.667:
            scale = 1.0
            opacity = 1.0
        else:
            phase = (t - 0.667) / 0.333
            scale = 1.0 + phase * 0.15
            opacity = 1.0 - ease_out_quad(phase)

        ground_y = cy + self.ICON_BASE_SIZE / 2 - 4

        if 0 <= t < 0.55:
            self._draw_ground_ring(p, cx, ground_y, t / 0.55, 3)
        if 0.15 <= t < 0.70:
            self._draw_ground_ring(p, cx, ground_y, (t - 0.15) / 0.55, 2)

        p.setOpacity(max(0.0, min(1.0, opacity)))
        p.save()
        p.translate(cx, cy)
        p.scale(scale, scale)
        p.drawPixmap(
            int(-self.icon.width() / 2),
            int(-self.icon.height() / 2),
            self.icon,
        )
        p.restore()


# ===================================================================
class WheelSignals(QObject):
    show_wheel = Signal(int, int)
    hide_wheel = Signal()


# ===================================================================
class PingWheel(BorderlessOverlay):
    RADIUS = 155
    INNER_RADIUS = 72
    DEAD_ZONE = 50

    ICON_SIZE_NORMAL = 44
    ICON_SIZE_HOVER = 56
    CENTER_ICON_SIZE = 38

    def __init__(self, signals, sound_player):
        super().__init__()

        self.sound_player = sound_player
        self.center = QPointF(0, 0)
        self.click_pos = (0, 0)
        self.hovered = -1

        self.icons_normal = []
        self.icons_hover = []
        self.icons_full = []
        for ping in PINGS:
            pix = load_pixmap(ping["icon"])
            if not pix.isNull():
                self.icons_normal.append(pix.scaled(
                    self.ICON_SIZE_NORMAL, self.ICON_SIZE_NORMAL,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                ))
                self.icons_hover.append(pix.scaled(
                    self.ICON_SIZE_HOVER, self.ICON_SIZE_HOVER,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                ))
                self.icons_full.append(pix)
            else:
                self.icons_normal.append(None)
                self.icons_hover.append(None)
                self.icons_full.append(QPixmap())

        caution_full = load_pixmap(CAUTION["icon"])
        self.caution_center = (
            caution_full.scaled(
                self.CENTER_ICON_SIZE, self.CENTER_ICON_SIZE,
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            if not caution_full.isNull() else None
        )
        self.caution_full = caution_full

        self._animations = []

        signals.show_wheel.connect(self.show_at)
        signals.hide_wheel.connect(self.commit_and_hide)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_hover)

        size = self.RADIUS * 2 + 30
        self.resize(size, size)

    def show_at(self, x, y):
        size = self.RADIUS * 2 + 30
        self.setGeometry(x - size // 2, y - size // 2, size, size)
        self.center = QPointF(size / 2, size / 2)
        self.click_pos = (x, y)
        self.hovered = -1
        self._apply_native_tweaks()
        self._apply_circular_mask()
        self.show()
        self.raise_()
        self.timer.start(16)

    def commit_and_hide(self):
        try:
            self.timer.stop()

            alive = []
            for a in self._animations:
                try:
                    if a.isVisible():
                        alive.append(a)
                except RuntimeError:
                    pass
            self._animations = alive

            x, y = self.click_pos
            if 0 <= self.hovered < len(PINGS):
                ping = PINGS[self.hovered]
                icon = self.icons_full[self.hovered]
                color = ping["color"]
                sound = ping["sound"]
            else:
                icon = self.caution_full
                color = CAUTION["color"]
                sound = CAUTION["sound"]

            if not icon.isNull():
                try:
                    anim = PingAnimation(x, y, icon, color)
                    self._animations.append(anim)
                except Exception as e:
                    print(f"[ANIM] Error: {e}")

            # Reproducir sonido (silenciosamente respeta el mute)
            try:
                self.sound_player.play(sound)
            except Exception as e:
                print(f"[SOUND] Error reproduciendo: {e}")
        finally:
            self.hide()

    def _update_hover(self):
        global_pos = QCursor.pos()
        local = self.mapFromGlobal(global_pos)
        dx = local.x() - self.center.x()
        dy = local.y() - self.center.y()
        dist = math.hypot(dx, dy)

        if dist < self.DEAD_ZONE:
            new_hover = -1
        else:
            angle = math.degrees(math.atan2(-dy, dx))
            best, best_diff = -1, 999
            for i, ping in enumerate(PINGS):
                diff = abs(((angle - ping["angle"] + 180) % 360) - 180)
                if diff < best_diff:
                    best_diff = diff
                    best = i
            new_hover = best

        if new_hover != self.hovered:
            self.hovered = new_hover
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        cx = self.width() / 2
        cy = self.height() / 2
        center = QPointF(cx, cy)

        bg = QRadialGradient(center, self.RADIUS)
        bg.setColorAt(0.0, BG_DEEP)
        bg.setColorAt(1.0, QColor(8, 16, 22, 235))
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawEllipse(center, self.RADIUS, self.RADIUS)

        rect = QRectF(
            cx - self.RADIUS, cy - self.RADIUS,
            self.RADIUS * 2, self.RADIUS * 2,
        )

        for i, ping in enumerate(PINGS):
            is_hover = (i == self.hovered)
            path = QPainterPath()
            path.moveTo(center)
            path.arcTo(rect, ping["angle"] - 22.5, 45)
            path.closeSubpath()

            if is_hover:
                base = QColor(ping["color"])
                base.setAlpha(140)
                p.setBrush(base)
                p.setPen(Qt.NoPen)
            else:
                p.setBrush(SECTOR_TINT_DARK if i % 2 == 0 else SECTOR_TINT_LIGHT)
                p.setPen(Qt.NoPen)
            p.drawPath(path)

        p.setPen(QPen(GOLD_DIM, 1))
        for ping in PINGS:
            a = math.radians(ping["angle"] - 22.5)
            x1 = cx + math.cos(a) * self.INNER_RADIUS
            y1 = cy - math.sin(a) * self.INNER_RADIUS
            x2 = cx + math.cos(a) * self.RADIUS
            y2 = cy - math.sin(a) * self.RADIUS
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(GOLD, 1.5))
        p.drawEllipse(center, self.RADIUS, self.RADIUS)

        for i, ping in enumerate(PINGS):
            is_hover = (i == self.hovered)
            rad = math.radians(ping["angle"])
            tx = cx + math.cos(rad) * (self.RADIUS * 0.72)
            ty = cy - math.sin(rad) * (self.RADIUS * 0.72)

            icon = self.icons_hover[i] if is_hover else self.icons_normal[i]
            if icon is not None:
                p.drawPixmap(
                    int(tx - icon.width() / 2),
                    int(ty - icon.height() / 2),
                    icon,
                )

        p.setBrush(BG_INNER)
        p.setPen(QPen(GOLD, 2))
        p.drawEllipse(center, self.INNER_RADIUS, self.INNER_RADIUS)

        if self.caution_center is not None:
            p.drawPixmap(
                int(cx - self.caution_center.width() / 2),
                int(cy - self.INNER_RADIUS / 2 - self.caution_center.height() / 2 + 6),
                self.caution_center,
            )

        if 0 <= self.hovered < len(PINGS):
            label = PINGS[self.hovered]["label"]
            label_color = QColor(PINGS[self.hovered]["color"])
        else:
            label = CAUTION["label"]
            label_color = QColor(CAUTION["color"])

        p.setPen(label_color)
        p.setFont(QFont("Arial", 10, QFont.Bold))
        p.drawText(
            QRectF(cx - self.INNER_RADIUS, cy + 14,
                   self.INNER_RADIUS * 2, 20),
            Qt.AlignCenter, label,
        )


# ===================================================================
# Listas de hotkey
# ===================================================================
def _build_modifier_options():
    base = [
        ("none", "(ninguno)"),
        ("ctrl", "Ctrl"),
        ("alt", "Alt"),
        ("shift", "Shift"),
        ("win", "Windows"),
        ("ctrl+shift", "Ctrl + Shift"),
        ("ctrl+alt", "Ctrl + Alt"),
        ("ctrl+win", "Ctrl + Windows"),
        ("alt+shift", "Alt + Shift"),
    ]
    letters = [(c, c.upper()) for c in "abcdefghijklmnopqrstuvwxyz"]
    digits = [(str(n), str(n)) for n in range(10)]
    fkeys = [(f"f{i}", f"F{i}") for i in range(1, 13)]
    return base + letters + digits + fkeys


MODIFIER_OPTIONS = _build_modifier_options()

BUTTON_OPTIONS = [
    ("left", "Izquierdo"),
    ("right", "Derecho"),
    ("middle", "Medio (rueda)"),
    ("x1", "Lateral 1 (atras)"),
    ("x2", "Lateral 2 (adelante)"),
]


# ===================================================================
# Dialog de configuracion
# ===================================================================
DIALOG_QSS = """
QDialog { background: #1a2530; color: #d8d8d8; }
QLabel { color: #c8c8c8; }
QComboBox {
    background: #0f1820; color: #e8e8e8;
    border: 1px solid #c9a95a; padding: 6px 10px;
    border-radius: 4px; min-height: 22px;
    min-width: 180px;
}
QComboBox:hover { border-color: #ffd166; }
QComboBox QAbstractItemView {
    background: #0f1820; color: #e8e8e8;
    selection-background-color: #c9a95a;
    selection-color: #0f1820;
    border: 1px solid #c9a95a;
}
QPushButton {
    background: #243340; color: #e8e8e8;
    border: 1px solid #c9a95a; padding: 8px 18px;
    border-radius: 4px; font-weight: bold;
    min-width: 80px;
}
QPushButton:hover { background: #c9a95a; color: #0f1820; }
QPushButton#primary { background: #c9a95a; color: #0f1820; }
QPushButton#primary:hover { background: #ffd166; }
"""


class HotkeyConfigDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Configurar atajo")
        self.setMinimumSize(420, 280)
        self.setStyleSheet(DIALOG_QSS)
        # Flags explicitos: dialog completo, on top, con boton de cerrar
        self.setWindowFlags(
            Qt.Dialog
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("Combinacion para abrir la rueda")
        title.setStyleSheet(
            "font-weight: bold; font-size: 14px; color: #c9a95a;"
        )
        layout.addWidget(title)

        info = QLabel(
            "Mantén presionada la tecla modificadora y haz click con\n"
            "el botón configurado del mouse para abrir la rueda."
        )
        info.setStyleSheet("color: #a0a8b0; font-size: 11px;")
        layout.addWidget(info)

        layout.addSpacing(6)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft)

        self.modifier_combo = QComboBox()
        for value, label in MODIFIER_OPTIONS:
            self.modifier_combo.addItem(label, value)
        idx = self.modifier_combo.findData(config.get("modifier", "ctrl"))
        if idx >= 0:
            self.modifier_combo.setCurrentIndex(idx)
        # Limitar el dropdown para que no sea infinito
        self.modifier_combo.setMaxVisibleItems(15)
        form.addRow("Tecla modificadora:", self.modifier_combo)

        self.button_combo = QComboBox()
        for value, label in BUTTON_OPTIONS:
            self.button_combo.addItem(label, value)
        idx = self.button_combo.findData(config.get("button", "left"))
        if idx >= 0:
            self.button_combo.setCurrentIndex(idx)
        form.addRow("Boton del mouse:", self.button_combo)

        layout.addLayout(form)
        layout.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancelar")
        save_btn = QPushButton("Guardar")
        save_btn.setObjectName("primary")
        cancel_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _save(self):
        modifier = self.modifier_combo.currentData()
        button = self.button_combo.currentData()

        if modifier == "none" and button == "left":
            QMessageBox.warning(
                self, "Combinacion peligrosa",
                "Sin modificador + click izquierdo abriria la rueda con\n"
                "cada click. Elige una combinacion mas especifica.",
            )
            return

        self.config["modifier"] = modifier
        self.config["button"] = button
        save_config(self.config)
        self.accept()


# ===================================================================
# System tray
# ===================================================================
class TrayApp(QObject):
    def __init__(self, config, sound_player, on_quit):
        super().__init__()
        self.config = config
        self.sound_player = sound_player
        self.on_quit = on_quit

        icon_path = ICONS_DIR / "Caution_ping.png"
        if icon_path.exists():
            icon = QIcon(str(icon_path))
        else:
            icon = self._make_default_icon()

        self.tray = QSystemTrayIcon(icon)
        self.tray.setToolTip("Ping Wheel")

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background: #1a2530; color: #e0e0e0;
                    border: 1px solid #c9a95a; padding: 4px; }
            QMenu::item { padding: 6px 24px; }
            QMenu::item:selected { background: #c9a95a; color: #0f1820; }
            QMenu::separator { height: 1px; background: #3a4858;
                               margin: 4px 8px; }
        """)

        self.toggle_action = QAction("Activado", self)
        self.toggle_action.setCheckable(True)
        self.toggle_action.setChecked(config.get("enabled", True))
        self.toggle_action.triggered.connect(self._toggle_enabled)
        menu.addAction(self.toggle_action)

        self.mute_action = QAction("Silenciar sonidos", self)
        self.mute_action.setCheckable(True)
        self.mute_action.setChecked(config.get("muted", False))
        self.mute_action.triggered.connect(self._toggle_muted)
        menu.addAction(self.mute_action)

        # Toggle de inicio con Windows. Lee el estado actual del registry
        # para que el check refleje la realidad (no el config.json).
        self.autostart_action = QAction("Iniciar con Windows", self)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(is_autostart_enabled())
        self.autostart_action.triggered.connect(self._toggle_autostart)
        menu.addAction(self.autostart_action)

        menu.addSeparator()

        config_action = QAction("Configurar atajo...", self)
        config_action.triggered.connect(self._open_config)
        menu.addAction(config_action)

        about_action = QAction("Acerca de", self)
        about_action.triggered.connect(self._show_about)
        menu.addAction(about_action)

        menu.addSeparator()

        quit_action = QAction("Salir", self)
        quit_action.triggered.connect(self.on_quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        self._dialog = None

    def _toggle_enabled(self, checked):
        self.config["enabled"] = checked
        save_config(self.config)
        msg = "Activado" if checked else "Desactivado"
        self.tray.showMessage("Ping Wheel", msg, QSystemTrayIcon.Information, 1500)

    def _toggle_muted(self, checked):
        self.config["muted"] = checked
        save_config(self.config)
        msg = "Sonido silenciado" if checked else "Sonido activado"
        self.tray.showMessage("Ping Wheel", msg, QSystemTrayIcon.Information, 1500)

    def _toggle_autostart(self, checked):
        ok = set_autostart(checked)
        if not ok:
            # Revertir el check si la operacion fallo
            self.autostart_action.setChecked(not checked)
            QMessageBox.warning(
                None, "Ping Wheel",
                "No se pudo modificar el inicio automatico.\n"
                "Verifica los permisos de tu usuario.",
            )
            return
        msg = ("Iniciara automaticamente con Windows" if checked
               else "Inicio automatico desactivado")
        self.tray.showMessage("Ping Wheel", msg, QSystemTrayIcon.Information, 2000)

    def _open_config(self):
        self._dialog = HotkeyConfigDialog(self.config)
        self._dialog.exec()

    def _show_about(self):
        QMessageBox.information(
            None, "Acerca de Ping Wheel",
            "Ping Wheel v1.2\n\n"
            "Rueda de pings estilo League of Legends.\n\n"
            f"Atajo actual: {self._format_hotkey()}\n\n"
            f"Config: {CONFIG_FILE}\n"
            f"Sonidos: {'Silenciados' if self.config.get('muted') else 'Activos'}\n"
            f"Autostart: {'Activado' if is_autostart_enabled() else 'Desactivado'}",
        )

    def _format_hotkey(self):
        mod = self.config.get("modifier", "ctrl")
        btn = self.config.get("button", "left")
        mod_label = dict(MODIFIER_OPTIONS).get(mod, mod)
        btn_label = dict(BUTTON_OPTIONS).get(btn, btn)
        return f"{mod_label} + click {btn_label.lower()}"

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._open_config()

    def _make_default_icon(self):
        pix = QPixmap(32, 32)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(GOLD)
        p.setPen(QPen(QColor(80, 60, 30), 1))
        p.drawEllipse(2, 2, 28, 28)
        p.setPen(QColor(20, 30, 40))
        p.setFont(QFont("Arial", 16, QFont.Bold))
        p.drawText(pix.rect(), Qt.AlignCenter, "?")
        p.end()
        return QIcon(pix)


# ===================================================================
# Listeners (hotkey extendido con cualquier tecla)
# ===================================================================
def _key_to_id(key):
    """Devuelve un id string para teclas relevantes, o None.
    Normaliza las teclas a strings que comparamos contra el config."""
    # Modificadores
    if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
        return "ctrl"
    if key in (keyboard.Key.alt_l, keyboard.Key.alt_r,
               getattr(keyboard.Key, 'alt_gr', None)):
        return "alt"
    if key in (keyboard.Key.shift_l, keyboard.Key.shift_r):
        return "shift"
    if key in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r):
        return "win"
    # F-keys
    for i in range(1, 13):
        f_key = getattr(keyboard.Key, f'f{i}', None)
        if f_key is not None and key == f_key:
            return f"f{i}"
    # Caracteres
    if hasattr(key, 'char') and key.char and len(key.char) == 1:
        c = key.char.lower()
        if c.isalnum():
            return c
    return None


def _name_to_button(name):
    """Mapea string del config a Button de pynput. None si no aplica."""
    direct = {
        "left": mouse.Button.left,
        "right": mouse.Button.right,
        "middle": mouse.Button.middle,
    }
    if name in direct:
        return direct[name]
    # Botones laterales: pynput los expone diferente segun OS
    if name == "x1":
        for attr in ("x1", "button8"):
            b = getattr(mouse.Button, attr, None)
            if b is not None:
                return b
    elif name == "x2":
        for attr in ("x2", "button9"):
            b = getattr(mouse.Button, attr, None)
            if b is not None:
                return b
    return None


def setup_listeners(signals, config):
    """Listeners que leen el config dinamicamente.
    Llevamos un set de teclas presionadas y comparamos con el modificador
    configurado (que puede ser una sola tecla, un combo, o vacio).
    """
    pressed_keys = set()
    state = {"active": False}

    def on_press(key):
        kid = _key_to_id(key)
        if kid:
            pressed_keys.add(kid)

    def on_release(key):
        kid = _key_to_id(key)
        if kid and kid in pressed_keys:
            pressed_keys.discard(kid)

    def is_modifier_active():
        required = config.get("modifier", "ctrl")
        if required == "none":
            return len(pressed_keys) == 0
        required_set = set(required.split("+"))
        # Match exacto: el set de teclas presionadas debe ser igual
        # al set requerido. Evita activaciones accidentales (ej. si
        # configuras "Ctrl", Ctrl+Shift+click NO activa).
        return required_set == pressed_keys

    def on_click(x, y, button, pressed):
        if not config.get("enabled", True):
            if not pressed and state["active"]:
                state["active"] = False
                signals.hide_wheel.emit()
            return

        target = _name_to_button(config.get("button", "left"))
        if target is None or button != target:
            return

        if pressed and is_modifier_active():
            state["active"] = True
            signals.show_wheel.emit(int(x), int(y))
        elif not pressed and state["active"]:
            state["active"] = False
            signals.hide_wheel.emit()

    kb = keyboard.Listener(on_press=on_press, on_release=on_release)
    ms = mouse.Listener(on_click=on_click)
    kb.start()
    ms.start()
    return kb, ms


# ===================================================================
# Singleton lock
# ===================================================================
def acquire_singleton():
    """Devuelve QSharedMemory si somos la unica instancia, None si no.
    El handle hay que mantenerlo vivo durante toda la ejecucion para
    que no lo libere el GC."""
    sm = QSharedMemory("PingWheelSingleInstance_v1")
    if sm.attach():
        # Ya hay otra instancia
        sm.detach()
        return None
    if not sm.create(1):
        return None
    return sm


# ===================================================================
# Main
# ===================================================================
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Singleton check ANTES de configurar nada
    singleton = acquire_singleton()
    if singleton is None:
        QMessageBox.information(
            None, "Ping Wheel",
            "Ping Wheel ya esta corriendo.\n\n"
            "Si no lo ves, busca el icono dorado en la barra del\n"
            "sistema (abajo a la derecha).",
        )
        sys.exit(0)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None, "Error",
            "No se puede acceder al system tray.",
        )
        sys.exit(1)

    config = load_config()
    sound_player = SoundPlayer(config)

    signals = WheelSignals()
    wheel = PingWheel(signals, sound_player)

    def quit_app():
        wheel.hide()
        app.quit()

    tray = TrayApp(config, sound_player, on_quit=quit_app)
    _kb, _ms = setup_listeners(signals, config)

    print(f"Ping Wheel v1.2 corriendo.")
    print(f"Config: {CONFIG_FILE}")
    print(f"Iconos: {ICONS_DIR}")
    print(f"Sonidos: {SOUNDS_DIR}")
    print(f"Atajo: {tray._format_hotkey()}")
    print(f"Autostart: {'activado' if is_autostart_enabled() else 'desactivado'}")

    # Mantener referencia al singleton durante toda la ejecucion
    app._singleton_lock = singleton

    sys.exit(app.exec())


if __name__ == "__main__":
    main()