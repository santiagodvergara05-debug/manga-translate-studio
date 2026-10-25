"""
Process-level hardware telemetry and system resource monitoring.

Monitors memory consumption (RSS) and queries logical system hardware specs.
"""

import os
import psutil


class SystemMonitor:
    """Monitors live process memory utilization and physical machine capabilities."""

    def __init__(self):
        self.process = psutil.Process(os.getpid())

    def get_stats(self) -> tuple[int, int]:
        """
        Retrieves active process resident set size (RSS) memory consumption in megabytes.

        Returns:
            tuple[int, int]: (process_ram_mb, process_status_flag)
        """
        try:
            ram_bytes = self.process.memory_info().rss
            ram_mb = int(ram_bytes / (1024 * 1024))
            return ram_mb, 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return 0, 0

    @staticmethod
    def get_detailed_specs() -> dict:
        """
        Calculates host system hardware capacity and logical execution specs.

        Returns:
            dict: Map containing total system RAM, execution environment, and OS name.
        """
        total_ram = round(psutil.virtual_memory().total / (1024**3), 1)
        cpu_count = psutil.cpu_count(logical=True) or 1

        return {
            "ram": total_ram,
            "engine": f"Cloud API / Local Multimodal ({cpu_count} CPU Threads)",
            "os": os.name.upper(),
        }