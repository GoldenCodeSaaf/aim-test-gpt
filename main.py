import sys
import threading
import time
import win32api
import onnxruntime as ort

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

from gui.main_window import MainWindow
from core.weapon_detection import WeaponDetector
from core.utils import get_screen_frame, camera
from core.weapon_profiles import WeaponProfiles
from core.recoil_controller import fire_recoil_for_game
from core.aimbot import aim_and_compensate
from core.detector import EnemyDetector
from config.settings_manager import settings_manager

# إعدادات عامة
DETECTION_INTERVAL = 0.05

# بدء الكاميرا (مهم جدًا لـ dxcam)
camera.start()

# مكونات النظام
weapon_profiles = WeaponProfiles()
weapon_detector = WeaponDetector()
enemy_detector = EnemyDetector()

current_weapon_name = None
is_recoil_active = False

def is_left_mouse_pressed():
    """يتحقق مما إذا كان زر الماوس الأيسر مضغوطًا"""
    return win32api.GetKeyState(0x01) < 0

def background_loop(main_window):
    global current_weapon_name, is_recoil_active

    while True:
        # --- وضع الارتداد العام (Universal) ---
        if settings_manager.get('recoil.universal_recoil_enabled'):
            if is_left_mouse_pressed() and not is_recoil_active:
                is_recoil_active = True
                universal_settings = {
                    "name": "Universal",
                    "recoil_strength": settings_manager.get('recoil.universal_recoil_strength'),
                    "delay": 30,
                    "dynamic_recoil": True
                }
                threading.Thread(target=fire_recoil_for_game, args=(universal_settings, True, 50), daemon=True).start()
            elif not is_left_mouse_pressed():
                is_recoil_active = False
            time.sleep(DETECTION_INTERVAL)
            continue

        # --- الوضع القياسي: اكتشاف + تصويب ---
        frame = get_screen_frame()
        if frame is None:
            continue

        # اكتشاف السلاح
        detected_weapon = weapon_detector.detect_weapon(frame)
        if detected_weapon and detected_weapon != current_weapon_name:
            current_weapon_name = detected_weapon
            QTimer.singleShot(0, lambda: main_window.update_current_weapon(current_weapon_name))

        # اكتشاف الأعداء
        conf_threshold = settings_manager.get('detection.confidence_threshold', 0.6)
        enemies = enemy_detector.detect(frame, conf_threshold=conf_threshold)

        if not enemies:
            QTimer.singleShot(0, lambda: main_window.update_status("Searching...", "white"))
            time.sleep(DETECTION_INTERVAL)
            continue

        # اختيار الهدف المناسب
        target = next((e for e in enemies if e['class'] == 'head'), enemies[0])
        x, y, w, h = target["box"]
        target_center = (x + w // 2, y + h // 2)

        # تحويل إلى إحداثيات نسبة لمركز الشاشة
        screen_center = (frame.shape[1] // 2, frame.shape[0] // 2)
        dx = target_center[0] - screen_center[0]
        dy = target_center[1] - screen_center[1]

        # جلب إعدادات السلاح
        weapon_settings = weapon_profiles.get_weapon(current_weapon_name)

        if weapon_settings and is_left_mouse_pressed():
            QTimer.singleShot(0, lambda: main_window.update_status(f"Targeting at {target_center}", "yellow"))
            aim_and_compensate((dx, dy), weapon_settings, dynamic=weapon_settings.get("dynamic_recoil", False), smooth=1.0, sensitivity=1.0)
            QTimer.singleShot(0, lambda: main_window.update_status("Firing!", "red"))
        else:
            if current_weapon_name and is_left_mouse_pressed():
                print(f"[WARNING] Weapon settings not found: {current_weapon_name}")

        time.sleep(DETECTION_INTERVAL)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    threading.Thread(target=background_loop, args=(window,), daemon=True).start()
    sys.exit(app.exec_())

