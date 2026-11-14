"""Editable provider pricing and local API usage history dialog."""

from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from src.utils.i18n import tr


class UsagePricingDialog(QDialog):
    def __init__(
        self, usage_manager, provider: str, model: str, connection_profile_id: str = "",
        parent=None, *, connection_profile_name: str = "", connection_profiles: dict | None = None,
    ):
        super().__init__(parent)
        self.usage_manager = usage_manager
        self.provider = provider.lower()
        self.model = model
        self.connection_profile_id = connection_profile_id or "legacy"
        self.connection_profile_name = connection_profile_name or "Legacy / unassigned"
        self.connection_profiles = connection_profiles or {}
        self.data = usage_manager.load_tables()
        self.setWindowTitle(tr("usage_pricing.usage_pricing"))
        self.setMinimumSize(940, 580)
        self.resize(1080, 680)
        self.setStyleSheet("QDialog { background: #121217; color: #e0e0e0; }")

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self._build_usage_tab()
        self._build_prices_tab()

        footer = QHBoxLayout()
        footer.addStretch()
        self.btn_close = QPushButton(tr("usage_pricing.save_close"))
        self.btn_close.clicked.connect(self._save_and_close)
        footer.addWidget(self.btn_close)
        layout.addLayout(footer)

    def _new_table(self, headers: list[str], editable_columns: set[int] | None = None):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.horizontalHeader().setStretchLastSection(True)
        if editable_columns is None:
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        return table

    def _put(self, table, row: int, column: int, value, editable=True):
        item = QTableWidgetItem("" if value is None else str(value))
        if str(value).strip().lower() == "not configured":
            item.setForeground(QColor("#ff5252"))
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        table.setItem(row, column, item)

    def _build_usage_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.lbl_usage_summary = QLabel()
        self.lbl_usage_summary.setWordWrap(True)
        layout.addWidget(self.lbl_usage_summary)
        note = QLabel(
            tr("usage_pricing.history_stores_token_counts_model_names")
        )
        note.setStyleSheet("color: #888899; font-size: 10px;")
        layout.addWidget(note)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel(tr("common.provider")))
        self.provider_filter = QComboBox()
        self.provider_filter.addItem(tr("usage_pricing.current_title", title=self.provider.title()), self.provider)
        self.provider_filter.addItem(tr("usage_pricing.all_providers"), "*")
        known_providers = sorted({
            str(row.get("provider", "")).lower()
            for row in self.usage_manager.load_history()
            if row.get("provider")
        })
        for provider_name in known_providers:
            if provider_name != self.provider:
                self.provider_filter.addItem(provider_name.title(), provider_name)
        filter_row.addWidget(self.provider_filter)
        filter_row.addStretch()
        self.clear_history_button = QPushButton(tr("usage_pricing.clear_all_history"))
        self.clear_history_button.setToolTip(
            tr("usage_pricing.delete_request_records_price_tables_and")
        )
        self.clear_history_button.clicked.connect(self._clear_usage_history)
        filter_row.addWidget(self.clear_history_button)
        layout.addLayout(filter_row)

        self.history_table = self._new_table(
            ["Time", "Provider", "Model", "Connection", "Requests", "Input", "Cache", "Output", "Est. USD"]
        )
        layout.addWidget(self.history_table, 1)
        self.provider_filter.currentIndexChanged.connect(self._refresh_usage_history)
        self._refresh_usage_history()
        self.tabs.addTab(tab, tr("usage_pricing.usage"))

    def _refresh_usage_history(self, *_):
        if not hasattr(self, "history_table"):
            return
        provider_value = str(self.provider_filter.currentData() or "*")
        history = self.usage_manager.load_history()
        filtered = [
            entry for entry in history
            if (provider_value == "*" or str(entry.get("provider", "")).lower() == provider_value)
        ]
        displayed = filtered[-250:]
        self.history_table.setRowCount(len(displayed))
        for row_idx, entry in enumerate(reversed(displayed)):
            timestamp = str(entry.get("timestamp", ""))
            try:
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
            except ValueError:
                pass
            values = [
                timestamp,
                entry.get("provider", ""),
                entry.get("model", ""),
                self.connection_profiles.get(
                    str(entry.get("connection_profile_id", "legacy")),
                    "Legacy / unassigned" if "connection_profile_id" not in entry else "Removed connection",
                ),
                entry.get("requests", 1),
                f"{int(entry.get('input_tokens', 0)):,}",
                f"{int(entry.get('cached_input_tokens', 0)):,}" if entry.get("cache_reported", "cached_input_tokens" in entry) else "—",
                f"{int(entry.get('output_tokens', 0)):,}",
                "—" if entry.get("cost_usd") is None else f"~${float(entry['cost_usd']):.6f}",
            ]
            for col, value in enumerate(values):
                self._put(self.history_table, row_idx, col, value, editable=False)

        provider_filter = None if provider_value == "*" else provider_value
        total, priced_rows, request_rows = self.usage_manager.total_cost(
            provider=provider_filter
        )
        provider_label = "All providers" if provider_filter is None else provider_filter.title()
        cache_pct = self.usage_manager.recent_cache_percent(
            self.provider, self.model, connection_profile_id=self.connection_profile_id
        ) if self.model else None
        cache_text = f"Recent cache match: {cache_pct:g}%" if cache_pct is not None else "Recent cache match: not reported"
        self.lbl_usage_summary.setText(
            tr("usage_pricing.showing_provider_label_connection_connec", provider_label=provider_label, connection_profile_name=self.connection_profile_name, value=self.model or 'No model selected', request_rows=request_rows, priced_rows=priced_rows, total=format(total, '.6f'), cache_text=cache_text)
        )

    def _clear_usage_history(self):
        if not self.usage_manager.load_history():
            return
        answer = QMessageBox.question(
            self,
            tr("usage_pricing.clear_all_usage_history"),
            tr("usage_pricing.delete_all_recorded_usage_history_for"),
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.usage_manager.clear_history()
            self._refresh_usage_history()
        except OSError as exc:
            QMessageBox.warning(self, tr("usage_pricing.could_not_clear_history"), str(exc))

    def _build_prices_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.lbl_price_status = QLabel()
        self.lbl_price_status.setStyleSheet("color: #ff5252; font-weight: bold;")
        layout.addWidget(self.lbl_price_status)
        note = QLabel(
            tr("usage_pricing.editable_price_list_in_usd_per")
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #a0a0ad; font-size: 10px;")
        layout.addWidget(note)

        self.prices_table = self._new_table(
            ["Provider", "Model / prefix", "Plan", "Input / M", "Cached input / M", "Output / M"],
            {0, 1, 2, 3, 4, 5},
        )
        # Avoid the platform's alternate-row palette (which can render as dark red on Windows).
        self.prices_table.setAlternatingRowColors(False)
        self.prices_table.setStyleSheet(
            "QTableWidget { background-color: #0b0b0e; color: #e0e0e0; gridline-color: #2a2a35; }"
            "QTableWidget::item:selected { background-color: #263849; color: #ffffff; }"
        )
        self.prices_table.horizontalHeader().setStretchLastSection(False)
        for column, width in enumerate((95, 230, 85, 110, 135, 110)):
            self.prices_table.setColumnWidth(column, width)
        self._load_price_rows(self.data.get("prices", []))
        self.prices_table.itemChanged.connect(self._update_price_status)
        layout.addWidget(self.prices_table, 1)
        self._update_price_status()

        row = QHBoxLayout()
        add = QPushButton(tr("usage_pricing.add_price"))
        add.clicked.connect(self._add_price_row)
        remove = QPushButton(tr("usage_pricing.remove_selected"))
        remove.clicked.connect(lambda: self.prices_table.removeRow(self.prices_table.currentRow()) if self.prices_table.currentRow() >= 0 else None)
        remove_all = QPushButton(tr("usage_pricing.remove_all"))
        remove_all.clicked.connect(self._remove_all_prices)
        import_btn = QPushButton(tr("usage_pricing.import_json"))
        import_btn.clicked.connect(self._import_prices)
        export_btn = QPushButton(tr("usage_pricing.export_json"))
        export_btn.clicked.connect(self._export_prices)
        row.addWidget(add)
        row.addWidget(remove)
        row.addWidget(remove_all)
        row.addStretch()
        row.addWidget(import_btn)
        row.addWidget(export_btn)
        layout.addLayout(row)
        self.tabs.addTab(tab, tr("usage_pricing.prices"))

    def _remove_all_prices(self):
        if self.prices_table.rowCount() == 0:
            return
        answer = QMessageBox.question(
            self,
            tr("usage_pricing.remove_all_prices"),
            tr("usage_pricing.remove_every_price_row_from_the"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.prices_table.setRowCount(0)
        self.data["prices"] = []
        self._update_price_status()

    def _load_price_rows(self, prices: list[dict]):
        self.prices_table.setRowCount(len(prices))
        for row_idx, price in enumerate(prices):
            values = [
                price.get("provider", ""),
                price.get("model", ""),
                price.get("plan", "any"),
                self._rate_display(price.get("input_usd_per_million")),
                (
                    price.get("cached_input_usd_per_million")
                    if price.get("cached_input_usd_per_million") is not None
                    else ("Same as input" if price.get("input_usd_per_million") is not None else "Not configured")
                ),
                self._rate_display(price.get("output_usd_per_million")),
            ]
            for col, value in enumerate(values):
                self._put(self.prices_table, row_idx, col, value)

    def _active_price_plan(self):
        if self.provider == "gemini":
            return "paid"
        if self.provider == "ollama" and self.usage_manager._is_ollama_off_peak():
            return "off-peak"
        return "any"

    def _add_price_row(self):
        row = self.prices_table.rowCount()
        self.prices_table.insertRow(row)
        values = [self.provider, "", "any", "", "", ""]
        for col, value in enumerate(values):
            self._put(self.prices_table, row, col, value)
        self.prices_table.setCurrentCell(row, 1)
        self.prices_table.editItem(self.prices_table.item(row, 1))

    def _prices_from_table(self):
        result = []
        for row in range(self.prices_table.rowCount()):
            def cell(column):
                item = self.prices_table.item(row, column)
                return item.text().strip() if item else ""

            provider, model, plan = cell(0).lower(), cell(1), cell(2).lower() or "any"
            if not provider or not model:
                continue
            try:
                input_price = self._optional_price(cell(3))
                cached_price = self._optional_price(cell(4))
                output_price = self._optional_price(cell(5))
            except ValueError as exc:
                raise ValueError(f"Invalid price in row {row + 1}.") from exc
            numeric_prices = [value for value in (input_price, cached_price, output_price) if value is not None]
            if numeric_prices and min(numeric_prices) < 0:
                raise ValueError(f"Prices cannot be negative (row {row + 1}).")
            if plan not in ("any", "free", "paid", "off-peak"):
                raise ValueError(f"Plan must be any, free, paid, or off-peak (row {row + 1}).")
            if not numeric_prices:
                continue
            result.append({
                "provider": provider,
                "model": model,
                "plan": plan,
                "input_usd_per_million": input_price,
                "cached_input_usd_per_million": cached_price,
                "output_usd_per_million": output_price,
            })
        return result

    @staticmethod
    def _optional_price(value: str):
        value = value.strip()
        if not value or value.lower() in ("not configured", "same as input", "n/a", "-"):
            return None
        return float(value.replace(",", "."))

    def _update_price_status(self, *_):
        if not hasattr(self, "prices_table") or not hasattr(self, "lbl_price_status"):
            return
        try:
            prices = self._prices_from_table()
        except ValueError:
            configured = False
        else:
            active_plan = self._active_price_plan()
            matching = [
                row for row in prices
                if row["provider"] == self.provider
                and self.usage_manager._matches(row["model"], self.model)
                and row["plan"] in (active_plan, "any")
            ]
            if not matching and self.provider == "gemini":
                matching = [
                    row for row in prices
                    if row["provider"] == "gemini"
                    and self.usage_manager._matches(row["model"], self.model)
                    and row["plan"] == "free"
                ]
            matching.sort(key=lambda row: (row["plan"] != active_plan, -len(row["model"])))
            configured = bool(
                matching
                and matching[0]["input_usd_per_million"] is not None
                and matching[0]["output_usd_per_million"] is not None
            )
        model_text = self.model or "selected model"
        if configured:
            self.lbl_price_status.setText(tr("usage_pricing.model_text_price_configured", model_text=model_text))
            self.lbl_price_status.setStyleSheet("color: #00e676; font-weight: bold;")
        else:
            self.lbl_price_status.setText(tr("usage_pricing.model_text_not_configured", model_text=model_text))
            self.lbl_price_status.setStyleSheet("color: #ff5252; font-weight: bold;")

    def _import_prices(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("usage_pricing.import_price_table"), "", tr("usage_pricing.json_files_json"))
        if not path:
            return
        try:
            imported = self.usage_manager.import_prices(path)
            # Imports are additive: replace only rows with the same provider/model/plan key.
            current = self._prices_from_table()
            merged = {
                self._price_key(row): row
                for row in current
            }
            for row in imported:
                merged[self._price_key(row)] = row
            self.data["prices"] = list(merged.values())
            self._load_price_rows(self.data["prices"])
            self._update_price_status()
            QMessageBox.information(
                self, tr("usage_pricing.price_table_imported"),
                tr("usage_pricing.imported_count_price_row_s_existing", count=len(imported)),
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, tr("usage_pricing.import_failed"), str(exc))

    @staticmethod
    def _price_key(row: dict) -> tuple[str, str, str]:
        return (
            str(row.get("provider", "")).strip().lower(),
            str(row.get("model", "")).strip().lower(),
            str(row.get("plan", "any")).strip().lower() or "any",
        )

    def _export_prices(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("usage_pricing.export_price_table"), "pricing_tables.json", tr("usage_pricing.json_files_json"))
        if not path:
            return
        try:
            self.usage_manager.export_prices(path, self._prices_from_table())
            QMessageBox.information(self, tr("usage_pricing.price_table_exported"), tr("usage_pricing.saved_to_path", path=path))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, tr("usage_pricing.export_failed"), str(exc))

    @staticmethod
    def _rate_display(value):
        return "Not configured" if value in (None, "") else value

    def _save_and_close(self):
        try:
            self.usage_manager.save_prices(self._prices_from_table())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, tr("usage_pricing.could_not_save"), str(exc))
            return
        self.accept()
