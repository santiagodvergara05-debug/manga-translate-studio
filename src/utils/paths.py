import os
import sys

class Paths:
    # 1. BASE_DIR: Carpeta persistente (al lado del .exe o raíz del proyecto)
    if getattr(sys, "frozen", False):
        BASE_DIR = os.path.dirname(sys.executable)
        BUNDLE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
    else:
        BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        BUNDLE_DIR = BASE_DIR

    # 2. Carpetas de datos persistentes (lectura y escritura)
    CACHE = os.path.join(BASE_DIR, "cache")
    LOGS = os.path.join(BASE_DIR, "logs")
    TRANSLATIONS = os.path.join(BASE_DIR, "translations")
    PROCESSED = os.path.join(BASE_DIR, "processed")

    # 3. Recursos estáticos empaquetados
    ASSETS = os.path.join(BUNDLE_DIR, "assets")

    @classmethod
    def initialize(cls):
        """Crea automáticamente las carpetas indispensables si no existen."""
        os.makedirs(cls.CACHE, exist_ok=True)
        os.makedirs(cls.LOGS, exist_ok=True)
        os.makedirs(cls.TRANSLATIONS, exist_ok=True)
        os.makedirs(cls.PROCESSED, exist_ok=True)

    @classmethod
    def ensure_directories(cls):
        """Alias para compatibilidad."""
        cls.initialize()


# Inicialización preventiva al importar el módulo
Paths.initialize()