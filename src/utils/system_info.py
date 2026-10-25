import os
import psutil

# /////////////////////////////////#
#      APP-SPECIFIC TELEMETRY      #
# /////////////////////////////////#

class SystemMonitor:
    def __init__(self):
        self.process = psutil.Process(os.getpid())

    def get_stats(self):
        """Retorna (app_ram_mb, status_indicator)"""
        ram_bytes = self.process.memory_info().rss
        ram_mb = int(ram_bytes / (1024 * 1024))
        # En una arquitectura orientada a API, indicamos si el proceso local está activo
        return ram_mb, 1

    @staticmethod
    def get_detailed_specs():
        """Calcula especificaciones básicas del sistema local."""
        total_ram = round(psutil.virtual_memory().total / (1024**3), 1)
        cpu_count = psutil.cpu_count(logical=True)

        return {
            "ram": total_ram,
            "engine": f"Cloud API / Local Multimodal ({cpu_count} CPU Threads)",
            "os": os.name.upper()
        }