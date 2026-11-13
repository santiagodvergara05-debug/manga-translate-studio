"""Provider credentials and model configuration dialog."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from src.backend.ai_client import AIClientManager, FetchModelsWorker
from src.backend.credential_manager import CredentialManager
from src.backend.providers.gemini_provider import GeminiProvider


class APISettingsDialog(QDialog):
    """Edits the saved provider, API credentials, endpoint, and model."""

    def reject(self):
        if self.fetch_worker is not None and self.fetch_worker.isRunning():
            return
        super().reject()

    def closeEvent(self, event):
        if self.fetch_worker is not None and self.fetch_worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)

    def __init__(self, credential_manager: CredentialManager, parent=None):
        super().__init__(parent)
        self.credential_manager = credential_manager
        self._loading = False
        self._drafts = {}
        self._profiles = self.credential_manager.get_connection_profiles()
        self._active_profile_id = self.credential_manager.get_active_connection_profile_id()
        self._loaded_profile_id = ""
        self._loaded_provider = None
        self._loaded_lan_mode = False
        self.fetch_worker = None

        self.setWindowTitle("API and Model Settings")
        self.setMinimumWidth(760)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.form = form

        profile_row = QHBoxLayout()
        self.profile_combo = QComboBox()
        self.profile_name_input = QLineEdit()
        self.profile_name_input.setPlaceholderText("Profile name")
        self.add_profile_button = QPushButton("Add")
        self.remove_profile_button = QPushButton("Remove")
        profile_row.addWidget(self.profile_combo, 2)
        profile_row.addWidget(self.profile_name_input, 2)
        profile_row.addWidget(self.add_profile_button)
        profile_row.addWidget(self.remove_profile_button)
        form.addRow("Connection profile:", profile_row)
        connection_note = QLabel(
            "Choose a saved connection to load its provider, credentials, and model."
        )
        connection_note.setWordWrap(True)
        connection_note.setStyleSheet("color: #888899; font-size: 10px;")
        form.addRow("", connection_note)

        self.provider_combo = QComboBox()
        self.providers = dict(AIClientManager.get_available_providers())
        for provider_id, provider in self.providers.items():
            self.provider_combo.addItem(getattr(provider, "display_name", provider_id.title()), provider_id)
        form.addRow("Provider:", self.provider_combo)

        self.usage_profile_input = QComboBox()
        self.usage_profile_input.setEditable(True)
        self.usage_profile_input.setInsertPolicy(QComboBox.NoInsert)
        self.usage_profile_input.lineEdit().setPlaceholderText("Automatic from credentials")
        known_profiles = set()
        for saved_profile in self._profiles.values():
            saved_name = str(saved_profile.get("credentials", {}).get("usage_profile", "")).strip()
            if saved_name:
                known_profiles.add(saved_name)
        for profile_name in sorted(known_profiles, key=str.casefold):
            self.usage_profile_input.addItem(profile_name)
        self.usage_profile_input.setToolTip(
            "Optional name for an account, project, or connection. Reuse the same name to group usage "
            "from multiple credentials; leave empty to identify it automatically from its credentials."
        )
        form.addRow("Usage group (optional):", self.usage_profile_input)
        profile_note = QLabel(
            "Use the same group name for API keys that share a provider account or project. "
            "Leave empty to track usage separately for this connection."
        )
        profile_note.setWordWrap(True)
        profile_note.setStyleSheet("color: #888899; font-size: 10px;")
        form.addRow("", profile_note)

        self.lan_mode = QCheckBox("Use local Ollama (localhost)")
        form.addRow("Connection:", self.lan_mode)

        self.primary_input = QLineEdit()
        self.primary_label = QLabel("API key:")
        form.addRow(self.primary_label, self.primary_input)

        self.secondary_input = QLineEdit()
        self.secondary_input.setEchoMode(QLineEdit.Password)
        self.secondary_label = QLabel("Cloud API key:")
        form.addRow(self.secondary_label, self.secondary_input)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        form.addRow("Model:", self.model_combo)

        self.thinking_combo = QComboBox()
        self.thinking_combo.setToolTip(
            "Gemini 3 only. Higher levels can increase latency and token usage. "
            "In development, Google may return a thought summary in the console."
        )
        form.addRow("Thinking level:", self.thinking_combo)
        self.model_combo.currentTextChanged.connect(self._update_thinking_levels)
        layout.addLayout(form)

        connect_row = QHBoxLayout()
        self.status_label = QLabel("Credentials are stored in the local application configuration.")
        self.status_label.setWordWrap(True)
        self.connect_button = QPushButton("Test connection and load models")
        self.connect_button.clicked.connect(self.test_connection)
        connect_row.addWidget(self.status_label, 1)
        connect_row.addWidget(self.connect_button)
        layout.addLayout(connect_row)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self._save_and_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        current_provider = str(self.credential_manager.data.get("provider", "gemini")).lower()
        index = self.provider_combo.findData(current_provider)
        self.provider_combo.setCurrentIndex(index if index >= 0 else 0)
        self._loaded_provider = self._provider_id()
        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        self.profile_combo.currentIndexChanged.connect(self._profile_changed)
        self.profile_name_input.textEdited.connect(self._profile_name_changed)
        self.add_profile_button.clicked.connect(self._add_profile)
        self.remove_profile_button.clicked.connect(self._remove_profile)
        self._populate_profiles(self._active_profile_id)
        self.lan_mode.toggled.connect(self._lan_mode_toggled)
        self._update_fields()

    def _provider_id(self) -> str:
        return str(self.provider_combo.currentData() or "gemini")

    def _update_thinking_levels(self, *_):
        if self._provider_id() != "gemini":
            return
        previous = self.thinking_combo.currentText().lower()
        levels = GeminiProvider.supported_thinking_levels(self.model_combo.currentText())
        self.thinking_combo.blockSignals(True)
        self.thinking_combo.clear()
        self.thinking_combo.addItems(levels)
        if previous in levels:
            self.thinking_combo.setCurrentText(previous)
        elif levels:
            self.thinking_combo.setCurrentIndex(0)
        self.thinking_combo.blockSignals(False)

    def _current_provider(self):
        return self.providers[self._provider_id()]

    def _selected_profile_id(self):
        return str(self.profile_combo.currentData() or "")

    def _populate_profiles(self, preferred_id=""):
        provider_id = self._provider_id()
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for profile_id, profile in self._profiles.items():
            if str(profile.get("provider", "")).lower() == provider_id:
                self.profile_combo.addItem(str(profile.get("name") or "Unnamed connection"), profile_id)
        if self.profile_combo.count() == 0:
            profile_id = self._create_profile(provider_id, select=False)
            self.profile_combo.addItem(self._profiles[profile_id]["name"], profile_id)
        index = self.profile_combo.findData(preferred_id)
        self.profile_combo.setCurrentIndex(index if index >= 0 else 0)
        self.profile_combo.blockSignals(False)
        self._update_profile_controls()

    def _update_profile_controls(self):
        profile = self._profiles.get(self._selected_profile_id(), {})
        self.profile_name_input.blockSignals(True)
        self.profile_name_input.setText(str(profile.get("name", "")))
        self.profile_name_input.blockSignals(False)
        provider_id = self._provider_id()
        count = sum(1 for item in self._profiles.values()
                    if str(item.get("provider", "")).lower() == provider_id)
        self.remove_profile_button.setEnabled(count > 1)

    def _create_profile(self, provider_id, select=True):
        profile_id = self.credential_manager.new_connection_profile_id()
        credentials = self.credential_manager.get_provider_credentials(provider_id)
        credentials = dict(credentials)
        if provider_id == "gemini":
            credentials["key"] = ""
        elif provider_id == "ollama":
            credentials["token"] = ""
        credentials["usage_profile"] = ""
        provider_name = getattr(self.providers[provider_id], "display_name", provider_id.title())
        count = sum(1 for item in self._profiles.values()
                    if str(item.get("provider", "")).lower() == provider_id)
        self._profiles[profile_id] = {
            "name": f"{provider_name} {count + 1}",
            "provider": provider_id,
            "credentials": dict(credentials),
        }
        if select:
            self._populate_profiles(profile_id)
        return profile_id

    def _capture_profile_name(self):
        profile_id = self._selected_profile_id()
        name = self.profile_name_input.text().strip()
        if profile_id in self._profiles and name:
            self._profiles[profile_id]["name"] = name
            index = self.profile_combo.findData(profile_id)
            if index >= 0:
                self.profile_combo.setItemText(index, name)

    def _profile_name_changed(self, *_):
        self._capture_profile_name()

    def _profile_changed(self, *_):
        if self._loading:
            return
        if self._loaded_profile_id:
            self._capture_draft(self._loaded_profile_id)
            name = self.profile_name_input.text().strip()
            if name:
                self._profiles[self._loaded_profile_id]["name"] = name
        self._update_profile_controls()
        self._update_fields()

    def _add_profile(self):
        self._capture_draft(self._selected_profile_id())
        self._capture_profile_name()
        self._create_profile(self._provider_id())
        self._update_fields()

    def _remove_profile(self):
        profile_id = self._selected_profile_id()
        provider_id = self._provider_id()
        count = sum(1 for item in self._profiles.values()
                    if str(item.get("provider", "")).lower() == provider_id)
        if not profile_id or count <= 1:
            return
        name = self._profiles[profile_id].get("name", "Unnamed connection")
        answer = QMessageBox.question(
            self, "Remove connection profile", f"Remove the saved connection '{name}'?",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        del self._profiles[profile_id]
        self._drafts.pop(profile_id, None)
        self._populate_profiles()
        self._update_fields()

    def _update_fields(self, *_):
        if self._loading:
            return
        self._loading = True
        try:
            provider_id = self._provider_id()
            provider = self._current_provider()
            profile = self._profiles.get(self._selected_profile_id(), {})
            creds = profile.get("credentials", {})
            draft = self._drafts.get(self._selected_profile_id(), {})
            supports_lan = bool(getattr(provider, "has_lan_mode", False))
            requires_endpoint = bool(getattr(provider, "requires_endpoint", False))
            is_lan = supports_lan and bool(draft.get("lan_mode", creds.get("lan_mode", True)))

            self.lan_mode.setVisible(supports_lan)
            self.lan_mode.setChecked(is_lan)
            self.usage_profile_input.setCurrentText(
                str(draft.get("usage_profile", creds.get("usage_profile", "")))
            )
            connection_label = self.form.labelForField(self.lan_mode)
            if connection_label is not None:
                connection_label.setVisible(supports_lan)
            self.primary_input.setPlaceholderText(
                getattr(provider, "primary_placeholder", "Enter API key...")
            )
            self.primary_label.setText("API endpoint:" if requires_endpoint else "API key:")
            self.primary_input.setEchoMode(
                QLineEdit.Password if getattr(provider, "is_primary_secret", True) else QLineEdit.Normal
            )
            if is_lan:
                self.primary_input.setText(getattr(provider, "default_endpoint", "http://localhost:11434"))
                self.primary_input.setEnabled(False)
            else:
                self.primary_input.setEnabled(True)
                key = "url" if requires_endpoint else "key"
                value = str(draft.get(key, creds.get(key, ""))).strip()
                if requires_endpoint and value in ("", getattr(provider, "default_endpoint", "")):
                    value = getattr(provider, "default_cloud_endpoint", "")
                self.primary_input.setText(value)

            self.secondary_input.setVisible(requires_endpoint and not is_lan)
            token_label = self.form.labelForField(self.secondary_input)
            if token_label is not None:
                token_label.setVisible(requires_endpoint and not is_lan)
            self.secondary_input.setPlaceholderText(
                getattr(provider, "secondary_placeholder", "Enter cloud API token...")
            )
            self.secondary_label.setText("Cloud API key:")
            self.secondary_input.setText(
                str(draft.get("token", creds.get("token", ""))) if requires_endpoint else ""
            )

            self.model_combo.clear()
            models = draft.get("models_list") or creds.get("models_list") or getattr(provider, "default_models", [])
            self.model_combo.addItems([str(model) for model in models])
            self.model_combo.setCurrentText(str(draft.get("model", creds.get("model", ""))))
            self._update_thinking_levels()
            self.thinking_combo.setCurrentText(
                str(draft.get("thinking_level", creds.get("thinking_level", "minimal"))).lower()
            )
            self.thinking_combo.setVisible(provider_id == "gemini")
            self.thinking_combo.setEnabled(provider_id == "gemini" and bool(self.thinking_combo.count()))
            thinking_label = self.form.labelForField(self.thinking_combo)
            if thinking_label is not None:
                thinking_label.setVisible(provider_id == "gemini")
                thinking_label.setText(
                    "Thinking level:" if self.thinking_combo.count()
                    else "Thinking level (model default):"
                )
            self._loaded_lan_mode = is_lan
            self._loaded_profile_id = self._selected_profile_id()
        finally:
            self._loading = False

    def _provider_changed(self, *_):
        if self._loaded_provider:
            self._capture_draft(self._selected_profile_id())
            self._capture_profile_name()
        self._loaded_provider = self._provider_id()
        self._populate_profiles()
        self._update_fields()

    def _lan_mode_toggled(self, checked: bool):
        if self._loading:
            return
        profile_id = self._selected_profile_id()
        self._capture_draft(profile_id, lan_mode=self._loaded_lan_mode)
        if profile_id in self._drafts:
            self._drafts[profile_id]["lan_mode"] = checked
        self._update_fields()

    def _capture_draft(self, profile_id: str, lan_mode=None):
        profile = self._profiles.get(profile_id)
        if not profile:
            return
        provider_id = str(profile.get("provider", self._provider_id())).lower()
        provider = self.providers[provider_id]
        requires_endpoint = bool(getattr(provider, "requires_endpoint", False))
        is_lan = bool(
            getattr(provider, "has_lan_mode", False)
            and (self.lan_mode.isChecked() if lan_mode is None else lan_mode)
        )
        previous = self._drafts.get(profile_id, profile.get("credentials", {}))
        values = {
            "model": self.model_combo.currentText().strip(),
            "models_list": [self.model_combo.itemText(i) for i in range(self.model_combo.count())],
            "usage_profile": self.usage_profile_input.currentText().strip(),
        }
        if provider_id == "gemini" and self.thinking_combo.count():
            values["thinking_level"] = self.thinking_combo.currentText().lower()
        if requires_endpoint:
            values.update({
                "lan_mode": is_lan,
                "url": previous.get("url", "") if is_lan else self.primary_input.text().strip(),
                "token": previous.get("token", "") if is_lan else self.secondary_input.text().strip(),
            })
        else:
            values["key"] = self.primary_input.text().strip()
        self._drafts[profile_id] = values

    def _connection_values(self):
        provider_id = self._provider_id()
        provider = self._current_provider()
        requires_endpoint = bool(getattr(provider, "requires_endpoint", False))
        is_lan = bool(getattr(provider, "has_lan_mode", False) and self.lan_mode.isChecked())

        if requires_endpoint:
            endpoint = (
                getattr(provider, "default_endpoint", "http://localhost:11434")
                if is_lan else self.primary_input.text().strip()
            )
            return provider_id, endpoint, "" if is_lan else self.secondary_input.text().strip()
        return provider_id, self.primary_input.text().strip(), ""

    def test_connection(self):
        provider_id, key_or_url, token = self._connection_values()
        provider = self._current_provider()
        requires_endpoint = bool(getattr(provider, "requires_endpoint", False))
        is_lan = bool(getattr(provider, "has_lan_mode", False) and self.lan_mode.isChecked())

        if not key_or_url:
            self._show_error("Enter the API key or endpoint first.")
            return
        if requires_endpoint and not is_lan and not token:
            self._show_error("Enter the cloud API key first.")
            return

        self.connect_button.setEnabled(False)
        self.button_box.setEnabled(False)
        for control in (
            self.provider_combo,
            self.profile_combo,
            self.profile_name_input,
            self.add_profile_button,
            self.remove_profile_button,
            self.lan_mode,
            self.primary_input,
            self.secondary_input,
            self.usage_profile_input,
            self.model_combo,
        ):
            control.setEnabled(False)
        self.status_label.setText("Checking connection…")
        self.status_label.setStyleSheet("color: #d0d0d0;")
        self._pending_connection = (provider_id, key_or_url, is_lan)
        self.fetch_worker = FetchModelsWorker(provider_id, key_or_url, token)
        self.fetch_worker.finished.connect(self._on_models_loaded)
        self.fetch_worker.start()

    def _on_models_loaded(self, success: bool, models: list, message: str):
        self.connect_button.setEnabled(True)
        self.button_box.setEnabled(True)
        self.provider_combo.setEnabled(True)
        self.profile_combo.setEnabled(True)
        self.profile_name_input.setEnabled(True)
        self.add_profile_button.setEnabled(True)
        self._update_profile_controls()
        self.usage_profile_input.setEnabled(True)
        self.model_combo.setEnabled(True)
        provider = self._current_provider()
        is_lan = bool(getattr(provider, "has_lan_mode", False) and self.lan_mode.isChecked())
        self.lan_mode.setEnabled(bool(getattr(provider, "has_lan_mode", False)))
        self.primary_input.setEnabled(not is_lan)
        self.secondary_input.setEnabled(self.secondary_input.isVisible())
        if not success:
            provider_id, endpoint, is_lan = getattr(
                self, "_pending_connection", (self._provider_id(), "", False)
            )
            if provider_id == "ollama" and is_lan:
                text = f"Ollama daemon is not active or unreachable at {endpoint}. Start it and try again."
            elif provider_id == "ollama":
                text = f"Could not connect to the Ollama API at {endpoint}. Check the endpoint and API key."
            elif provider_id == "gemini":
                text = "Could not connect to the Gemini API. Check the API key and internet connection."
            else:
                text = f"Could not connect to {provider_id}. Check its credentials and endpoint."
            self._show_error(f"{text}\n{message}")
            return

        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #00e676; font-weight: bold;")

        selected = self.model_combo.currentText().strip()
        self.model_combo.clear()
        self.model_combo.addItems(models)
        if selected and self.model_combo.findText(selected) >= 0:
            self.model_combo.setCurrentText(selected)
        elif selected:
            self.model_combo.setCurrentText(selected)
        elif models:
            self.model_combo.setCurrentIndex(0)

    def _show_error(self, text: str):
        self.status_label.setText(text)
        self.status_label.setStyleSheet("color: #ff5252; font-weight: bold;")

    def _save_and_accept(self):
        profile_id = self._selected_profile_id()
        self._capture_draft(profile_id)
        self._capture_profile_name()
        for saved_id, values in self._drafts.items():
            if saved_id in self._profiles:
                self._profiles[saved_id]["credentials"] = values
        if not profile_id or not self.profile_name_input.text().strip():
            self._show_error("Enter a name for this connection profile.")
            return
        try:
            self.credential_manager.save_connection_profiles(self._profiles, profile_id)
        except (ValueError, OSError) as error:
            self._show_error(str(error))
            return
        self.accept()
