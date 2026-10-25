import os
import sys
import shutil
import subprocess

def build():
    print("[*] Iniciando compilación de Manga Translate Studio...")

    # Rutas base
    root_dir = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(root_dir, "dist")
    build_dir = os.path.join(root_dir, "build")
    icon_path = os.path.join(root_dir, "assets", "icon.ico")

    # Comando base de PyInstaller
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=MangaTranslateStudio",
        "--noconfirm",
        "--clean",
        "--windowed",  # Sin ventana negra de consola
        f"--icon={icon_path}",
        # Empaquetar assets y estilos dentro de la aplicación
        f"--add-data={os.path.join(root_dir, 'assets')}{os.pathsep}assets",
        f"--add-data={os.path.join(root_dir, 'src', 'frontend', 'styles.qss')}{os.pathsep}src/frontend",
        # Incluir librerías ocultas que PySide6 a veces no detecta en el escaneo
        "--hidden-import=PySide6.QtSvg",
        "--hidden-import=PySide6.QtSvgWidgets",
        "--hidden-import=requests",
        "--hidden-import=PIL",
        "--hidden-import=cv2",
        "--hidden-import=numpy",
        "main.py"
    ]

    print("[*] Ejecutando comando de PyInstaller...")
    subprocess.run(cmd, check=True)

    # Crear carpetas esenciales al lado del ejecutable recién generado
    output_folder = os.path.join(dist_dir, "MangaTranslateStudio")
    print(f"[*] Preparando estructura de carpetas en: {output_folder}")

    for folder in ["cache", "logs", "translations"]:
        os.makedirs(os.path.join(output_folder, folder), exist_ok=True)

    print("\n" + "=" * 65)
    print(" ¡COMPILACIÓN COMPLETADA EXITOSAMENTE!")
    print(f" Tu ejecutable está listo en: {output_folder}")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    build()