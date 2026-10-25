from PySide6.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QTextEdit, QPushButton
from src.utils.system_info import SystemMonitor
from src.utils.config import Config

# /////////////////////////////////#
#     STUDIO KNOWLEDGE BASE        #
# /////////////////////////////////#

class HelpSystem(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{Config.APP_NAME} - User Manual")
        self.resize(760, 560)
        self.setStyleSheet(f"background-color: {Config.COLOR_PANEL}; color: {Config.COLOR_TEXT}; font-family: 'Segoe UI';")

        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # ==========================================
        # PESTAÑA 1: ATAJOS DE TECLADO Y RATÓN
        # ==========================================
        tab_shortcuts = QTextEdit()
        tab_shortcuts.setReadOnly(True)
        tab_shortcuts.setHtml(
            "<h3 style='color: #00d4ff;'>⌨️ Atajos de Teclado y Ratón</h3>"
            "<p><i>Nota: Los atajos de una sola tecla se pausan automáticamente al escribir dentro de un cuadro de texto.</i></p>"
            "<table border='0' cellpadding='5' width='100%'>"
            "<tr><td colspan='2'><b style='color: #00d4ff;'>— Navegación y Herramientas —</b></td></tr>"
            "<tr><td width='35%'><b>[M]</b></td><td>Herramienta Mano / Desplazamiento del lienzo</td></tr>"
            "<tr><td><b>[X]</b></td><td>Herramienta de Rotulación (Activa modo Typesetter)</td></tr>"
            "<tr><td><b>Mantener [Espacio]</b></td><td>Desplazamiento rápido temporal (Pan)</td></tr>"
            "<tr><td><b>Rueda del ratón</b></td><td>Zoom in / Zoom out en el visor</td></tr>"
            "<tr><td colspan='2'><hr></td></tr>"
            "<tr><td colspan='2'><b style='color: #00d4ff;'>— Manipulación de Globos y Texto —</b></td></tr>"
            "<tr><td><b>Doble Clic</b></td><td>Editar texto de una caja existente</td></tr>"
            "<tr><td><b>Ctrl + Rueda</b></td><td>Aumentar o reducir tamaño de fuente dinámicamente</td></tr>"
            "<tr><td><b>Ctrl + Shift + Rueda</b></td><td>Rotar texto seleccionado en pasos de 5°</td></tr>"
            "<tr><td><b>[Delete] / Clic Derecho</b></td><td>Eliminar texto seleccionado (regresa la línea a la cola <code>[ + ]</code>)</td></tr>"
            "<tr><td colspan='2'><hr></td></tr>"
            "<tr><td colspan='2'><b style='color: #00d4ff;'>— Procesamiento —</b></td></tr>"
            "<tr><td><b>RUN BATCH TRANSLATE</b></td><td>Traduce secuencialmente todas las páginas marcadas</td></tr>"
            "</table>"
        )

        # ==========================================
        # PESTAÑA 2: IA Y TRADUCCIÓN MULTIMODAL
        # ==========================================
        tab_ai = QTextEdit()
        tab_ai.setReadOnly(True)
        tab_ai.setHtml(
            "<h3 style='color: #00d4ff;'>🤖 Traducción Asistida por Visión Multimodal</h3>"
            "<p>La aplicación prescinde de motores OCR convencionales y se comunica directamente con LLMs de visión (Gemini u Ollama local) para analizar la escena completa:</p>"
            "<h4>1. Ventajas del Enfoque Multimodal</h4>"
            "<ul>"
            "<li><b>Lectura de contexto:</b> El modelo entiende expresiones visuales, jerarquía de diálogo y orden de viñeta en lugar de simples cadenas aisladas.</li>"
            "<li><b>Aislamiento de globos:</b> El sistema exige una respuesta estructurada en formato JSON para que ningún globo visual se fusione accidentalmente con otro.</li>"
            "<li><b>Opciones en español neutro:</b> Por cada globo se proporcionan variantes con diferentes sinónimos o registros adaptables.</li>"
            "</ul>"
            "<h4>2. Flujo de Trabajo en la Página</h4>"
            "<ol>"
            "<li>Selecciona la página en la lista izquierda.</li>"
            "<li>Haz clic en <b>Traducir Página Actual</b>.</li>"
            "<li>En el panel derecho aparecerá una tarjeta por cada globo detectado con un selector desplegable de alternativas y un campo editable.</li>"
            "<li>Ajusta las palabras deseadas y presiona <b>Aplicar a la Cola y al .TXT</b>.</li>"
            "</ol>"
        )

        # ==========================================
        # PESTAÑA 3: FORMATO DE GUION (.TXT)
        # ==========================================
        tab_script = QTextEdit()
        tab_script.setReadOnly(True)
        tab_script.setHtml(
            "<h3 style='color: #00d4ff;'>📄 Formato del Guion Estructurado (.TXT)</h3>"
            "<p>El programa genera y lee archivos de guion estándar listos para maquetación colaborativa.</p>"
            "<h4>Reglas de Estructura</h4>"
            "<ul>"
            "<li><b>Bloque delimitador:</b> Todo el contenido traducido se almacena estrictamente entre las etiquetas <code>&lt;translation&gt; ... &lt;/translation&gt;</code>.</li>"
            "<li><b>Encabezados de imagen:</b> Cada página se declara con el formato <code>Image X [archivo.jpg]</code>.</li>"
            "<li><b>Diálogos con viñeta:</b> Cada globo de texto corresponde a una línea que inicia con un guion (<code>-</code>). Las líneas con guion vacío se ignoran.</li>"
            "<li><b>Saltos de línea:</b> Usa <code>//</code> dentro de un diálogo para forzar un salto de renglón dentro de la misma caja de texto.</li>"
            "<li><b>Notas y comentarios:</b> Cualquier línea que empiece con <code>#</code> o cualquier texto fuera de las etiquetas de traducción es ignorado por el lector.</li>"
            "</ul>"
        )

        # ==========================================
        # PESTAÑA 4: TIPOGRAFÍA Y TYPESETTER
        # ==========================================
        tab_typesetter = QTextEdit()
        tab_typesetter.setReadOnly(True)
        tab_typesetter.setHtml(
            "<h3 style='color: #00d4ff;'>🔤 Rotulación y Gestor Tipográfico</h3>"
            "<p>En la categoría <b>TYPESETTER</b> puedes previsualizar y afinar los textos generados sobre la página activa:</p>"
            "<ul>"
            "<li><b>Cola Lazy ([ + ] ➔ [ ✓ ]):</b> Los textos del guion se colocan en la lista como elementos pendientes <code>[ + ]</code>. Al hacer clic sobre ellos, se colocan en el lienzo con la fuente y estilo activos.</li>"
            "<li><b>Fuentes Favoritas y Alias:</b> Marca fuentes recurrentes con la estrella (★) o define nombres personalizados (ej: <i>Grito [CC Wild Words]</i>) guardados automáticamente en <code>font_presets.json</code>.</li>"
            "<li><b>Trazo Exterior (Outer Stroke):</b> Habilita contorno vectorial exterior con control de grosor y opacidad para facilitar la lectura sobre fondos oscuros o detallados.</li>"
            "<li><b>Tiradores de Transformación (Gizmos):</b> Las esquinas blancas escalan el tamaño de la fuente, los laterales cian ajustan el ancho de caja y el círculo superior permite rotar libremente.</li>"
            "</ul>"
        )

        # ==========================================
        # PESTAÑA 5: PROCESAMIENTO POR LOTES
        # ==========================================
        tab_batch = QTextEdit()
        tab_batch.setReadOnly(True)
        tab_batch.setHtml(
            "<h3 style='color: #00d4ff;'>⚡ Procesamiento por Lotes y Rendimiento</h3>"
            "<h4>Ejecución Secuencial</h4>"
            "<ul>"
            "<li>Al hacer clic en <b>RUN BATCH TRANSLATE</b>, el programa toma cada página marcada en la lista y la procesa en orden.</li>"
            "<li><b>Control de Cuota (Rate Limit):</b> Se incluye una pausa automática entre página y página para evitar sobrecargar los límites de peticiones por minuto (RPM) de las API.</li>"
            "<li><b>Procesamiento Stateless:</b> Cada imagen se envía de manera independiente sin arrastrar historiales extensos de conversación, evitando errores por desbordamiento de contexto de tokens.</li>"
            "<li><b>Persistencia automática:</b> Al finalizar el lote, todos los diálogos se consolidan y guardan en el archivo <code>translation_script.txt</code>.</li>"
            "</ul>"
        )

        # ==========================================
        # PESTAÑA 6: DIAGNÓSTICO DEL SISTEMA
        # ==========================================
        specs = SystemMonitor.get_detailed_specs()
        tab_hardware = QTextEdit()
        tab_hardware.setReadOnly(True)
        tab_hardware.setHtml(
            "<h3 style='color: #00d4ff;'>💻 Diagnóstico de Recursos</h3>"
            f"<p><b>Motor de Detección:</b> {specs.get('engine', 'CPU / Red')}</p>"
            f"<p><b>Memoria RAM del Sistema:</b> {specs.get('ram', 'N/D')} GB</p>"
            "<hr>"
            "<h4>Optimizaciones de Memoria</h4>"
            "<ul>"
            "<li><b>Carga bajo demanda:</b> La visualización de imágenes utiliza decodificación selectiva mediante OpenCV para liberar buffers cuando no se están visualizando.</li>"
            "<li><b>Compresión Base64 al vuelo:</b> Las imágenes se escalan en memoria a un tamaño eficiente antes de transmitirse, reduciendo el consumo de ancho de banda y latencia de red.</li>"
            "</ul>"
        )

        tabs.addTab(tab_shortcuts, "Atajos")
        tabs.addTab(tab_ai, "Traducción IA")
        tabs.addTab(tab_script, "Guion (.txt)")
        tabs.addTab(tab_typesetter, "Typesetter")
        tabs.addTab(tab_batch, "Lotes")
        tabs.addTab(tab_hardware, "Sistema")
        layout.addWidget(tabs)

        close_btn = QPushButton("CERRAR")
        close_btn.setStyleSheet(f"background-color: {Config.COLOR_BG}; padding: 6px; border: 1px solid #2a2a32;")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    @staticmethod
    def show_guide(parent):
        dialog = HelpSystem(parent)
        dialog.exec()