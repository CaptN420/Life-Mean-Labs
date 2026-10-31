"""
Life_mean Studio - Main Application Window

Main window with navigation between all modules.
RUN / STOP gear the real Life_mean experiment engine via the StudioRunner.
"""

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QLabel, QPushButton, QFrame, QScrollArea,
    QToolBar, QMessageBox, QDialog, QLineEdit, QListWidget,
    QListWidgetItem, QTextEdit, QComboBox, QSpinBox, QCheckBox,
    QGroupBox, QFormLayout, QTabWidget, QSplitter, QTreeView,
    QTableWidget, QTableWidgetItem, QHeaderView, QMenu, QProgressBar,
    QStatusBar, QToolButton, QSizePolicy, QDateEdit, QTimeEdit,
    QFileDialog, QInputDialog, QTreeWidget, QTreeWidgetItem, QDockWidget,
    QLCDNumber, QGraphicsView, QGridLayout, QSlider, QListWidget as QListWidgetW
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QRect, QSize, QPoint
from PySide6.QtGui import QIcon, QPixmap, QFont, QColor, QPainter, QAction, QActionGroup

from life_mean_studio.engine.storage import StudioStorage
from life_mean_studio.engine.runner import StudioRunner, RunnerError
from life_mean_studio.workflows.manager import WorkflowManager
from life_mean_studio.workflows import WorkflowConfig, AgentConfig
from life_mean_studio.prompts.collection import PromptCollection
from life_mean_studio.engine.python_executor import get_executor, PythonEnvironment
from life_mean_studio.engine.agent_manager import AgentManager, TestResult
from life_mean_studio.engine.package_manager import PackageManager

import json
import os
from pathlib import Path
from datetime import datetime


def _in_pytest() -> bool:
    """True when running under pytest (auto-probes are skipped in tests)."""
    return "PYTEST_CURRENT_TEST" in os.environ


class LifeMeanStudioApp(QMainWindow):
    """Main application window for Life_mean Studio."""

    def __init__(self, storage=None):
        super().__init__()
        self.setWindowTitle("Life_mean Studio")
        self.resize(1200, 800)

        # Initialize storage (injectable for tests)
        if storage is not None:
            self.storage = storage
        else:
            self.storage = StudioStorage()
        self.workflow_manager = WorkflowManager(self.storage)
        self.prompt_collection = PromptCollection(self.storage)
        
        # Real engine runner: wire RUN/STOP to the genuine Life_mean pipeline.
        try:
            self.runner = StudioRunner(self.storage)
        except Exception as exc:  # pragma: no cover - engine import failure
            self.runner = None
            print(f"[Studio] engine runner unavailable: {exc}")
        
        # Seed default workflow templates so Quick Run always has a valid target.
        if not _in_pytest():
            try:
                if not self.workflow_manager.list_all():
                    self.workflow_manager.seed_defaults()
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[Studio] could not seed workflows: {exc}")

        # Initialize agent manager
        self.agent_manager = AgentManager(self.storage)
        self.package_manager = PackageManager(self.storage, self.agent_manager, self.workflow_manager)

        # UI state
        self.current_mode = "simple"  # simple or dev
        self.preferences = self._load_preferences()
        
        # Setup UI
        self._setup_ui()
        self._apply_theme()
        
        # Live runner poll (consumes engine events into the Console + buttons).
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_runner)
        if not _in_pytest():
            self._poll_timer.start(700)
        
    def _load_preferences(self):
        """Load saved preferences."""
        pref_path = Path.home() / ".life_mean_studio" / "preferences.json"
        if pref_path.exists():
            try:
                with open(pref_path, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            "theme": "dark",
            "mode": "simple",
            "geometry": None,
            "state": None
        }
    
    def _save_preferences(self):
        """Save preferences."""
        pref_path = Path.home() / ".life_mean_studio"
        pref_path.mkdir(parents=True, exist_ok=True)
        geometry = self.saveGeometry()
        state = self.saveState()
        self.preferences["geometry"] = bytes(geometry).hex()
        self.preferences["state"] = bytes(state).hex()
        with open(pref_path / "preferences.json", 'w') as f:
            json.dump(self.preferences, f, indent=2)
    
    def _apply_theme(self):
        """Apply dark theme."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QStatusBar {
                background-color: #2d2d2d;
                color: #cccccc;
            }
            QToolBar {
                background-color: #2d2d2d;
                border-bottom: 1px solid #3f3f3f;
            }
            QToolButton {
                color: #cccccc;
                padding: 5px;
            }
            QToolButton:hover {
                background-color: #3f3f3f;
            }
            QToolButton:checked {
                background-color: #0e639c;
            }
        """)
    
    def _setup_ui(self):
        """Setup the main UI layout."""
        # Central widget with stacked pages
        self.central_widget = QStackedWidget()
        self.setCentralWidget(self.central_widget)
        
        # Create pages
        self.home_page = self._create_home_page()
        self.services_page = self._create_services_page()
        self.workflows_page = self._create_workflows_page()
        self.prompts_page = self._create_prompts_page()
        self.console_page = self._create_console_page()
        self.dev_page = self._create_dev_page()
        self.packages_page = self._create_packages_page()
        self.settings_page = self._create_settings_page()
        self.code_playground_page = self._create_code_playground_page()

        # Add pages to stack
        self.central_widget.addWidget(self.home_page)
        self.central_widget.addWidget(self.services_page)
        self.central_widget.addWidget(self.workflows_page)
        self.central_widget.addWidget(self.prompts_page)
        self.central_widget.addWidget(self.console_page)
        self.central_widget.addWidget(self.dev_page)
        self.central_widget.addWidget(self.packages_page)
        self.central_widget.addWidget(self.settings_page)
        self.central_widget.addWidget(self.code_playground_page)
        
        # Setup toolbar
        self._setup_toolbar()
        
        # Setup status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Life_mean Studio — ready. RUN/STOP drive the real engine.")
        
    def _setup_toolbar(self):
        """Setup the main toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)
        
        # Navigation actions
        nav_actions = [
            ("Home", 0),
            ("Services", 1),
            ("Workflows", 2),
            ("Prompts", 3),
            ("Console", 4),
            ("Dev Studio", 5),
            ("Packages", 6),
            ("Settings", 7),
            ("Code Playground", 8),
        ]
        
        self._nav_actions = {}
        action_group = QActionGroup(self)
        for name, index in nav_actions:
            action = QAction(name, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked, idx=index: self._navigate_to(idx))
            action_group.addAction(action)
            toolbar.addAction(action)
            self._nav_actions[index] = action
        
        # Set Home as active by default
        self._navigate_to(0)
        
        # Mode toggle
        self.mode_action = QAction("DEV Mode", self)
        self.mode_action.setCheckable(True)
        self.mode_action.toggled.connect(self._toggle_mode)
        toolbar.addSeparator()
        toolbar.addAction(self.mode_action)
        
        # Dashboard button
        dashboard_action = QAction("Open Dashboard", self)
        dashboard_action.triggered.connect(self._open_dashboard)
        toolbar.addAction(dashboard_action)
    
    def _navigate_to(self, index):
        """Navigate to a page and update active button."""
        self.central_widget.setCurrentIndex(index)
        # Update active button state
        for idx, action in self._nav_actions.items():
            action.setChecked(idx == index)

    def _toggle_mode(self, checked):
        """Toggle between simple and dev mode."""
        self.current_mode = "dev" if checked else "simple"
        self.mode_action.setText("Simple Mode" if checked else "DEV Mode")
        
    def _open_dashboard(self):
        """Open the dashboard URL."""
        # Life_mean Docker dashboard runs on port 8080
        dashboard_url = "http://localhost:8080/dashboard"
        try:
            import webbrowser
            webbrowser.open(dashboard_url)
        except Exception as e:
            QMessageBox.warning(self, "Dashboard", f"Could not open dashboard: {e}")
    
    def _create_home_page(self):
        """Create the home/quick run page."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Title
        title = QLabel("Life_mean Studio")
        title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Subtitle
        subtitle = QLabel("Life_mean Studio — contrôle du vrai moteur")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        
        # Quick Run Section
        quick_run = self._create_quick_run_section()
        layout.addWidget(quick_run)
        
        # Status
        self.home_status_label = QLabel("Prêt. Sélectionnez un workflow puis RUN.")
        self.home_status_label.setAlignment(Qt.AlignCenter)
        self.home_status_label.setStyleSheet("color: #4caf50; font-weight: bold;")
        layout.addWidget(self.home_status_label)
        
        return widget
    
    def _create_quick_run_section(self):
        """Create the Quick Run section."""
        group = QGroupBox("Quick Run")
        layout = QFormLayout(group)
        
        # Workflow selector (enabled — drives the real run)
        self.workflow_combo = QComboBox()
        self._load_workflows_to_combo()
        self.workflow_combo.setEnabled(True)
        layout.addRow("Workflow:", self.workflow_combo)
        
        # Model selector — informational: lists models available on the LLM
        # backend. The engine resolves its own model from the configured
        # credentials, so this is a live readout, not a mutated setting.
        self.model_combo = QComboBox()
        self.model_combo.addItem("(detecting models…)" if not _in_pytest() else "(models unavailable in tests)")
        self.model_combo.setEnabled(True)
        layout.addRow("Modèles dispo:", self.model_combo)
        # Populate with real models from the LLM backend (best-effort, async)
        if not _in_pytest():
            QTimer.singleShot(0, self._load_real_models)
        
        # Execution mode selector — deterministic pipeline or multi-agent debate
        self.mode_select = QComboBox()
        self.mode_select.addItems(["Deterministic", "Multi-Agent (Debate)"])
        layout.addRow("Execution Mode:", self.mode_select)
        
        # Compression toggle (engine-level feature; kept read-only for now)
        self.compression_check = QCheckBox("Compression ON")
        self.compression_check.setEnabled(False)
        layout.addRow("Compression:", self.compression_check)
        
        # RUN button (enabled — starts a real engine run)
        self.run_btn = QPushButton("RUN")
        self.run_btn.setEnabled(True)
        self.run_btn.setStyleSheet("background-color: #0e639c; color: white; font-weight: bold;")
        self.run_btn.clicked.connect(self._on_run)
        layout.addRow("", self.run_btn)
        
        # STOP button (enabled once a run starts)
        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        layout.addRow("", self.stop_btn)
        
        return group
    
    def _load_workflows_to_combo(self):
        """Load workflows into the combo box."""
        self.workflow_combo.clear()
        for wf in self.workflow_manager.list_all():
            self.workflow_combo.addItem(wf["name"], wf["id"])
    
    def _load_real_models(self):
        """Populate the model combo with real models from the LLM backend.

        Best-effort and non-fatal: if the backend is unreachable, the combo
        keeps a placeholder. Never executes anything — read-only listing.
        """
        try:
            from life_mean_studio.engine.health import load_available_models
            models = load_available_models()
        except Exception:
            models = []
        
        # Guard: combo may have been torn down (e.g. window closed quickly).
        try:
            if not models:
                return
            current = self.model_combo.currentText()
            self.model_combo.clear()
            for model in models:
                self.model_combo.addItem(model)
            if current in models:
                self.model_combo.setCurrentText(current)
        except RuntimeError:
            # Widget deleted (window closed before async callback fired)
            pass
    
    # ------------------------------------------------------------------ runner
    
    def _build_run_config(self) -> dict:
        """Compute the engine config from the current Quick Run selection."""
        wf_id = self.workflow_combo.itemData(self.workflow_combo.currentIndex()) \
            if self.workflow_combo.currentIndex() >= 0 else None
        workflow = self.workflow_manager.get(wf_id) if wf_id else None
        if workflow is None:
            from life_mean_studio.workflows import WorkflowConfig
            workflow = WorkflowConfig(name="Quick Run")
        debate = self.mode_select.currentIndex() == 1  # "Multi-Agent (Debate)"
        return StudioRunner.build_config(workflow, debate=debate), wf_id
    
    def _on_run(self):
        """Start a real engine run via the StudioRunner."""
        if self.runner is None:
            self.home_status_label.setText("Runner indisponible (import moteur échoué).")
            return
        try:
            if self.runner.is_active():
                self._append_console("RUN ignoré : un run est déjà en cours.")
                return
            config, wf_id = self._build_run_config()
            experiment_id = self.runner.start(config, workflow_id=wf_id)
        except RunnerError as exc:
            self.home_status_label.setText(f"Erreur : {exc}")
            self._append_console(f"[RUN] {exc}")
            return
        except Exception as exc:
            self.home_status_label.setText(f"Erreur : {exc}")
            self._append_console(f"[RUN] erreur inattendue : {exc}")
            return
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        mode = "deterministic" if not config.get("debate") else "debate"
        self.home_status_label.setText(
            f"Run {experiment_id} en cours ({mode} · {config.get('num_tasks')} tâches).")
        self._append_console(f"[RUN] {experiment_id} · {mode} · {config.get('domain')} · "
                             f"{config.get('num_tasks')} tâches — lancé.")
        self._poll_runner()
    
    def _on_stop(self):
        """Request a real cancellation of the running experiment."""
        if self.runner is None or not self.runner.stop():
            self._append_console("[STOP] aucun run actif à arrêter.")
            return
        self._append_console("[STOP] demande d'annulation envoyée…")
    
    def _poll_runner(self):
        """Drain runner events into the Console and refresh control state."""
        if getattr(self, "runner", None) is None:
            return
        try:
            for item in self.runner.drain_events():
                ev, data = item.get("event"), item.get("data", {})
                exp = data.get("experiment_id", "?")
                if ev == "started":
                    self._append_console(f"[moteur] {exp} démarré.")
                    self._refresh_run_buttons(True)
                elif ev == "stop_requested":
                    self._append_console(f"[moteur] arrêt demandé pour {exp}.")
                elif ev == "finished":
                    status = data.get("status")
                    metrics = data.get("metrics", {})
                    line = (f"[moteur] {exp} terminé — {status}"
                            + (f" (valides {metrics.get('tasks_valid', 0)}/"
                               f"{metrics.get('tasks_completed', 0)})"
                               if metrics.get("tasks_completed") else ""))
                    self._append_console(line)
                    if status == "failed" and metrics.get("errors"):
                        for err in metrics["errors"][-3:]:
                            self._append_console(f"    erreur : {err}")
                    self._refresh_run_buttons(False)
                    self.home_status_label.setText(
                        f"Run terminé — {status}."
                        if status != "completed" else "Run terminé avec succès.")
        except Exception as exc:  # pragma: no cover - defensive
            self._append_console(f"[poll] {exc}")
    
    def _refresh_run_buttons(self, running: bool):
        self.run_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
    
    def _append_console(self, text: str):
        if getattr(self, "console_output", None) is None:
            return
        stamp = datetime.now().strftime("%H:%M:%S")
        try:
            self.console_output.append(f"[{stamp}] {text}")
        except RuntimeError:
            pass
    
    def _create_services_page(self):
        """Create the services page."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        title = QLabel("Services")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        layout.addWidget(title)
        
        # Service table
        self.service_table = QTableWidget()
        self.service_table.setColumnCount(4)
        self.service_table.setHorizontalHeaderLabels(["Service", "Status", "Details", "Latency"])
        self.service_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.service_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        # Row header hidden (cleaner look)
        self.service_table.verticalHeader().setVisible(False)
        
        layout.addWidget(self.service_table)
        
        # Health check buttons
        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("Run Health Check")
        refresh_btn.clicked.connect(self._run_health_check)
        btn_layout.addWidget(refresh_btn)
        
        note = QLabel("Statuses are real probes (LLM backend, dashboard, orchestrator, storage).")
        note.setStyleSheet("color: #888888; font-style: italic;")
        btn_layout.addWidget(note)
        layout.addLayout(btn_layout)
        
        # Disabled legacy action buttons (Phase C: no service control)
        disabled_actions = QHBoxLayout()
        legacy_btn = QPushButton("Start / Stop Services")
        legacy_btn.setEnabled(False)
        disabled_actions.addWidget(legacy_btn)
        layout.addLayout(disabled_actions)
        
        # Initial status
        self.health_status_label = QLabel("Health: not yet checked")
        layout.addWidget(self.health_status_label)
        
        # Auto-run once on creation (non-blocking in UI thread via short timeout)
        # Skipped under pytest so tests don't make real network probes.
        if not _in_pytest():
            self._health_timer_id = QTimer.singleShot(100, self._run_health_check)
        else:
            self._health_timer_id = None
        
        return widget
    
    def _run_health_check(self):
        """Run real health checks and populate the services table."""
        from life_mean_studio.engine.health import run_all_health_checks
        
        self.health_status_label.setText("Health: checking…")
        
        try:
            summary = run_all_health_checks(self.storage)
            checks = summary["checks"]
        except Exception as e:
            self.health_status_label.setText(f"Health: error — {e}")
            return
        
        self.service_table.setRowCount(len(checks))
        status_colors = {
            "ok": "#4caf50",
            "degraded": "#ffaa00",
            "error": "#cc0000",
            "unknown": "#888888",
        }
        
        for row, check in enumerate(checks):
            self.service_table.setItem(row, 0, QTableWidgetItem(check["name"]))
            
            status_item = QTableWidgetItem(check["status"])
            color = status_colors.get(check["status"], "#888888")
            status_item.setForeground(QColor(color))
            self.service_table.setItem(row, 1, status_item)
            
            self.service_table.setItem(row, 2, QTableWidgetItem(check["detail"]))
            
            latency = check.get("latency_ms")
            latency_text = f"{latency:.0f} ms" if latency is not None else "—"
            self.service_table.setItem(row, 3, QTableWidgetItem(latency_text))
        
        self.service_table.resizeColumnsToContents()
        self.health_status_label.setText(f"Health: {summary['overall']} (checked {summary['timestamp']})")
    
    def _create_workflows_page(self):
        """Create the workflows page."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        title = QLabel("Workflow Library")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        layout.addWidget(title)
        
        # Workflow list
        self.workflow_list = QListWidget()
        self._refresh_workflow_list()
        layout.addWidget(self.workflow_list)
        
        # Buttons
        btn_layout = QHBoxLayout()

        create_btn = QPushButton("Create New")
        create_btn.clicked.connect(self._create_workflow)
        btn_layout.addWidget(create_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_workflow)
        btn_layout.addWidget(edit_btn)

        duplicate_btn = QPushButton("Duplicate")
        duplicate_btn.clicked.connect(self._duplicate_workflow)
        btn_layout.addWidget(duplicate_btn)

        load_btn = QPushButton("Load to Quick Run")
        load_btn.clicked.connect(self._load_workflow_to_quick_run)
        btn_layout.addWidget(load_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self._delete_workflow)
        btn_layout.addWidget(delete_btn)

        layout.addLayout(btn_layout)
        
        return widget
    
    def _refresh_workflow_list(self):
        """Refresh the workflow list."""
        self.workflow_list.clear()
        for wf in self.workflow_manager.list_all():
            item = QListWidgetItem(f"{wf['name']} ({wf['version']})")
            item.setData(Qt.UserRole, wf["id"])
            self.workflow_list.addItem(item)
    
    def _create_workflow(self):
        """Create a new workflow."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Create Workflow")
        dialog.resize(400, 350)
        layout = QFormLayout(dialog)
        
        name_edit = QLineEdit()
        layout.addRow("Name:", name_edit)
        
        description_edit = QLineEdit()
        description_edit.setPlaceholderText("Optional description...")
        layout.addRow("Description:", description_edit)
        
        mode_combo = QComboBox()
        mode_combo.addItems(["single", "multi"])
        layout.addRow("Mode:", mode_combo)
        
        domain_combo = QComboBox()
        domain_combo.addItems(["math", "code", "science", "philosophy", "general"])
        layout.addRow("Domain:", domain_combo)
        
        num_tasks_spin = QSpinBox()
        num_tasks_spin.setRange(1, 100)
        num_tasks_spin.setValue(10)
        layout.addRow("Num Tasks:", num_tasks_spin)
        
        seed_spin = QSpinBox()
        seed_spin.setRange(0, 999999)
        seed_spin.setValue(42)
        layout.addRow("Seed:", seed_spin)
        
        ok_btn = QPushButton("Create")
        cancel_btn = QPushButton("Cancel")
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addRow("", btn_layout)
        
        ok_btn.clicked.connect(lambda: self._save_new_workflow(
            dialog, name_edit.text(), mode_combo.currentText(),
            domain_combo.currentText(), num_tasks_spin.value(), seed_spin.value()))
        cancel_btn.clicked.connect(dialog.reject)
        
        dialog.exec()

    def _save_new_workflow(self, dialog, name, mode, domain="math", num_tasks=10, seed=42):
        """Save a new workflow."""
        if not name:
            QMessageBox.warning(self, "Error", "Name is required")
            return
        
        try:
            config = WorkflowConfig(
                name=name,
                description="",
                mode=mode,
                domain=domain,
                num_tasks=num_tasks,
                seed=seed,
            )
            wf_id = self.workflow_manager.create(config)
            self._refresh_workflow_list()
            dialog.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create workflow: {e}")
    
    def _delete_workflow(self):
        """Delete selected workflow."""
        item = self.workflow_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Warning", "No workflow selected")
            return
        
        wf_id = item.data(Qt.UserRole)
        reply = QMessageBox.question(self, "Confirm", "Delete this workflow?", 
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.workflow_manager.delete(wf_id)
            self._refresh_workflow_list()
    
    def _load_workflow_to_quick_run(self):
        """Load selected workflow to Quick Run."""
        item = self.workflow_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Warning", "No workflow selected")
            return

        wf_id = item.data(Qt.UserRole)
        # Navigate to home page and select the workflow
        self._navigate_to(0)
        # Set combo box to the selected workflow
        for i in range(self.workflow_combo.count()):
            if self.workflow_combo.itemData(i) == wf_id:
                self.workflow_combo.setCurrentIndex(i)
                break

    def _edit_workflow(self):
        """Edit selected workflow."""
        item = self.workflow_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Warning", "No workflow selected")
            return
        wf_id = item.data(Qt.UserRole)
        config = self.workflow_manager.get(wf_id)
        if not config:
            QMessageBox.critical(self, "Error", "Could not load workflow for editing")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Workflow")
        layout = QFormLayout(dialog)
        name_edit = QLineEdit(config.name)
        layout.addRow("Name:", name_edit)
        mode_combo = QComboBox()
        mode_combo.addItems(["single", "multi"])
        mode_combo.setCurrentText(config.mode)
        layout.addRow("Mode:", mode_combo)
        domain_combo = QComboBox()
        domain_combo.addItems(["math", "code", "science", "philosophy", "general"])
        domain_combo.setCurrentText(config.domain)
        layout.addRow("Domain:", domain_combo)
        num_tasks_spin = QSpinBox()
        num_tasks_spin.setRange(1, 100)
        num_tasks_spin.setValue(config.num_tasks)
        layout.addRow("Num Tasks:", num_tasks_spin)
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addRow("", btn_layout)
        ok_btn.clicked.connect(lambda: self._save_edited_workflow(dialog, wf_id, name_edit.text(), mode_combo.currentText(), domain_combo.currentText(), num_tasks_spin.value()))
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec()

    def _save_edited_workflow(self, dialog, wf_id, name, mode, domain, num_tasks):
        if not name:
            QMessageBox.warning(self, "Error", "Name is required")
            return
        try:
            self.workflow_manager.update(wf_id, {"config": WorkflowConfig(name=name, description="", mode=mode, domain=domain, num_tasks=num_tasks).to_dict()})
            self._refresh_workflow_list()
            dialog.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update workflow: {e}")

    def _duplicate_workflow(self):
        """Duplicate selected workflow."""
        item = self.workflow_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Warning", "No workflow selected")
            return
        wf_id = item.data(Qt.UserRole)
        config = self.workflow_manager.get(wf_id)
        if not config:
            QMessageBox.critical(self, "Error", "Could not load workflow for duplication")
            return
        try:
            new_config = WorkflowConfig(name=f"{config.name} (Copy)", description=config.description, mode=config.mode, domain=config.domain, num_tasks=config.num_tasks, seed=config.seed)
            self.workflow_manager.create(new_config)
            self._refresh_workflow_list()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to duplicate workflow: {e}")

    def _edit_prompt(self):
        """Edit selected prompt."""
        item = self.prompt_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Warning", "No prompt selected")
            return
        prompt_id = item.data(Qt.UserRole)
        prompt = self.prompt_collection.get(prompt_id)
        if not prompt:
            QMessageBox.critical(self, "Error", "Could not load prompt for editing")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Prompt")
        layout = QFormLayout(dialog)
        name_edit = QLineEdit(prompt.name)
        layout.addRow("Name:", name_edit)
        category_combo = QComboBox()
        category_combo.addItems(["general", "coding", "security", "research"])
        category_combo.setCurrentText(prompt.category)
        layout.addRow("Category:", category_combo)
        content_edit = QTextEdit()
        content_edit.setPlainText(prompt.content)
        layout.addRow("Content:", content_edit)
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addRow("", btn_layout)
        ok_btn.clicked.connect(lambda: self._save_edited_prompt(dialog, prompt_id, name_edit.text(), category_combo.currentText(), content_edit.toPlainText()))
        cancel_btn.clicked.connect(dialog.reject)
        dialog.exec()

    def _save_edited_prompt(self, dialog, prompt_id, name, category, content):
        if not name or not content:
            QMessageBox.warning(self, "Error", "Name and content are required")
            return
        try:
            self.prompt_collection.update(prompt_id, {"name": name, "category": category, "content": content})
            self._refresh_prompt_list()
            dialog.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update prompt: {e}")

    def _duplicate_prompt(self):
        """Duplicate selected prompt."""
        item = self.prompt_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Warning", "No prompt selected")
            return
        prompt_id = item.data(Qt.UserRole)
        prompt = self.prompt_collection.get(prompt_id)
        if not prompt:
            QMessageBox.critical(self, "Error", "Could not load prompt for duplication")
            return
        try:
            self.prompt_collection.create(f"{prompt.name} (Copy)", prompt.content, prompt.category)
            self._refresh_prompt_list()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to duplicate prompt: {e}")

    def _delete_prompt(self):
        """Delete selected prompt."""
        item = self.prompt_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Warning", "No prompt selected")
            return
        prompt_id = item.data(Qt.UserRole)
        reply = QMessageBox.question(self, "Confirm", "Delete this prompt?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.prompt_collection.delete(prompt_id)
            self._refresh_prompt_list()
    
    def _create_prompts_page(self):
        """Create the prompts page."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        title = QLabel("Prompt Collection")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        layout.addWidget(title)
        
        # Prompt list
        self.prompt_list = QListWidget()
        self._refresh_prompt_list()
        layout.addWidget(self.prompt_list)
        
        # Buttons
        btn_layout = QHBoxLayout()

        create_btn = QPushButton("Create New")
        create_btn.clicked.connect(self._create_prompt)
        btn_layout.addWidget(create_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_prompt)
        btn_layout.addWidget(edit_btn)

        duplicate_btn = QPushButton("Duplicate")
        duplicate_btn.clicked.connect(self._duplicate_prompt)
        btn_layout.addWidget(duplicate_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self._delete_prompt)
        btn_layout.addWidget(delete_btn)

        search_edit = QLineEdit()
        search_edit.setPlaceholderText("Search prompts...")
        search_edit.textChanged.connect(self._search_prompts)
        btn_layout.addWidget(search_edit)

        layout.addLayout(btn_layout)
        
        return widget
    
    def _refresh_prompt_list(self):
        """Refresh the prompt list."""
        self.prompt_list.clear()
        for prompt in self.prompt_collection.list_all():
            item = QListWidgetItem(f"{prompt.name} ({prompt.category})")
            item.setData(Qt.UserRole, prompt.id)
            self.prompt_list.addItem(item)
    
    def _create_prompt(self):
        """Create a new prompt."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Create Prompt")
        layout = QFormLayout(dialog)
        
        name_edit = QLineEdit()
        layout.addRow("Name:", name_edit)
        
        category_combo = QComboBox()
        category_combo.addItems(["general", "coding", "security", "research"])
        layout.addRow("Category:", category_combo)
        
        content_edit = QTextEdit()
        content_edit.setPlaceholderText("Prompt content...")
        layout.addRow("Content:", content_edit)
        
        ok_btn = QPushButton("Create")
        cancel_btn = QPushButton("Cancel")
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addRow("", btn_layout)
        
        ok_btn.clicked.connect(lambda: self._save_new_prompt(dialog, name_edit.text(), 
                                                              category_combo.currentText(),
                                                              content_edit.toPlainText()))
        cancel_btn.clicked.connect(dialog.reject)
        
        dialog.exec()
    
    def _save_new_prompt(self, dialog, name, category, content):
        """Save a new prompt."""
        if not name or not content:
            QMessageBox.warning(self, "Error", "Name and content are required")
            return
        
        try:
            prompt_id = self.prompt_collection.create(name, content, category)
            self._refresh_prompt_list()
            dialog.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create prompt: {e}")
    
    def _search_prompts(self, query):
        """Search prompts."""
        self.prompt_list.clear()
        for prompt in self.prompt_collection.search(query):
            item = QListWidgetItem(f"{prompt.name} ({prompt.category})")
            item.setData(Qt.UserRole, prompt.id)
            self.prompt_list.addItem(item)
    
    def _create_console_page(self):
        """Create the agent console page."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        title = QLabel("Agent Console")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        layout.addWidget(title)
        
        # Status label
        self.console_status_label = QLabel("Aucune session en cours")
        self.console_status_label.setStyleSheet("color: #888888; font-style: italic;")
        layout.addWidget(self.console_status_label)
        
        # Message display
        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setFont(QFont("Consolas", 10))
        layout.addWidget(self.console_output)
        
        # Filters
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter by type:"))
        type_combo = QComboBox()
        type_combo.addItems(["all", "message", "tool", "error", "event"])
        filter_layout.addWidget(type_combo)
        layout.addLayout(filter_layout)
        
        return widget
    
    def _create_dev_page(self):
        """Create the dev studio page."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        title = QLabel("Developer Studio")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        layout.addWidget(title)
        
        # Tabs for different sections
        tabs = QTabWidget()
        
        # Agent Builder tab
        agent_tab = self._create_agent_builder_page()
        tabs.addTab(agent_tab, "Agent Builder")
        
        # Workflow Builder tab
        wf_tab = QWidget()
        wf_layout = QVBoxLayout(wf_tab)
        wf_layout.addWidget(QLabel("Workflow Builder - Connect to Phase B"))
        wf_layout.addWidget(QLabel(f"Workflows available: {len(self.workflow_manager.list_all())}"))
        tabs.addTab(wf_tab, "Workflow Builder")
        
        # Model Settings tab
        model_tab = QWidget()
        model_layout = QVBoxLayout(model_tab)
        model_layout.addWidget(QLabel("Model Settings"))
        model_form = QFormLayout()
        model_form.addRow("Base URL:", QLineEdit("http://localhost:1234/v1"))
        model_form.addRow("Model:", QLineEdit("kwaipilot_kat-coder-v2.5-dev"))
        model_layout.addLayout(model_form)
        tabs.addTab(model_tab, "Model Settings")
        
        # Tool Registry tab
        tool_tab = QWidget()
        tool_layout = QVBoxLayout(tool_tab)
        tool_layout.addWidget(QLabel("Tool Registry - Not Implemented"))
        tool_layout.addWidget(QLabel("Status: Phase D"))
        tabs.addTab(tool_tab, "Tool Registry")
        
        # Diagnostics tab
        diag_tab = QWidget()
        diag_layout = QVBoxLayout(diag_tab)
        diag_layout.addWidget(QLabel("Developer Diagnostics"))
        diag_text = QTextEdit()
        diag_text.setReadOnly(True)
        diag_text.setFont(QFont("Consolas", 10))
        diag_text.setText(f"""Life_mean Studio Diagnostics
========================
Phase: C (PySide6 UI)
Storage: Connected
Workflows: {len(self.workflow_manager.list_all())}
Prompts: {len(self.prompt_collection.list_all())}
Mode: {self.current_mode}

Note: RUN/STOP pilotent le vrai moteur (StudioRunner → ExperimentUIController).
""")
        diag_layout.addWidget(diag_text)
        tabs.addTab(diag_tab, "Diagnostics")
        
        layout.addWidget(tabs)
        
        return widget
    
    def _create_packages_page(self):
        """Create the packages page."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        title = QLabel("Packages")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        layout.addWidget(title)

        # Info label
        self.package_info_label = QLabel(".lmpack format v1.0 — Import and export agents & workflows")
        self.package_info_label.setStyleSheet("color: #888888;")
        layout.addWidget(self.package_info_label)

        # Agent selection list
        agent_label = QLabel("Export these agents (leave empty = all):")
        layout.addWidget(agent_label)
        self.package_agent_list = QListWidget()
        self._refresh_package_agent_list()
        layout.addWidget(self.package_agent_list)

        # Workflow selection list
        wf_label = QLabel("Export these workflows (leave empty = all):")
        layout.addWidget(wf_label)
        self.package_workflow_list = QListWidget()
        self._refresh_package_workflow_list()
        layout.addWidget(self.package_workflow_list)

        # Buttons
        btn_layout = QHBoxLayout()
        self.import_btn = QPushButton("Import Package")
        self.import_btn.clicked.connect(self._on_import_package)
        self.export_btn = QPushButton("Export Package")
        self.export_btn.clicked.connect(self._on_export_package)
        btn_layout.addWidget(self.import_btn)
        btn_layout.addWidget(self.export_btn)
        layout.addLayout(btn_layout)

        # Status label
        self.package_status_label = QLabel("")
        self.package_status_label.setStyleSheet("color: #4caf50;")
        layout.addWidget(self.package_status_label)

        return widget

    def _refresh_package_agent_list(self):
        """Populate the agent selection list."""
        self.package_agent_list.clear()
        for agent in self.agent_manager.list_all():
            item = QListWidgetItem(f"{agent['name']} ({agent['persona']})")
            item.setData(Qt.UserRole, agent["id"])
            self.package_agent_list.addItem(item)

    def _refresh_package_workflow_list(self):
        """Populate the workflow selection list."""
        self.package_workflow_list.clear()
        for wf in self.workflow_manager.list_all():
            item = QListWidgetItem(f"{wf['name']} ({wf['version']})")
            item.setData(Qt.UserRole, wf["id"])
            self.package_workflow_list.addItem(item)

    def _on_import_package(self):
        """Import a .lmpack package."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Package", "", "Life_mean Packages (*.lmpack);;All Files (*)"
        )
        if not path:
            return

        self.package_status_label.setStyleSheet("color: #ffaa00;")
        self.package_status_label.setText("Importing…")

        result = self.package_manager.import_package(path)
        if result.success:
            self.package_status_label.setStyleSheet("color: #4caf50;")
            self.package_status_label.setText(result.message)
            self._refresh_package_agent_list()
            self._refresh_package_workflow_list()
        else:
            self.package_status_label.setStyleSheet("color: #cc0000;")
            errors = "\\n".join(f"  • {e}" for e in result.errors)
            QMessageBox.critical(self, "Import Error", f"Could not import package:\\n{errors}")

    def _on_export_package(self):
        """Export agents/workflows to a .lmpack package."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Package", "", "Life_mean Packages (*.lmpack);;All Files (*)"
        )
        if not path:
            return

        # Collect selected agent IDs (empty selection = all)
        agent_ids = [item.data(Qt.UserRole) for item in self.package_agent_list.selectedItems()]
        workflow_ids = [item.data(Qt.UserRole) for item in self.package_workflow_list.selectedItems()]

        result = self.package_manager.export_package(
            output_path=path,
            agent_ids=agent_ids if agent_ids else None,
            workflow_ids=workflow_ids if workflow_ids else None,
        )
        if result.success:
            self.package_status_label.setStyleSheet("color: #4caf50;")
            self.package_status_label.setText(result.message)
            QMessageBox.information(self, "Export OK", result.message)
        else:
            self.package_status_label.setStyleSheet("color: #cc0000;")
            errors = "\\n".join(f"  • {e}" for e in result.errors)
            QMessageBox.critical(self, "Export Error", f"Could not export package:\\n{errors}")
    
    def _create_settings_page(self):
        """Create the settings page."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        title = QLabel("Settings")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        layout.addWidget(title)
        
        # Settings form
        settings_form = QFormLayout()
        
        # Theme
        theme_combo = QComboBox()
        theme_combo.addItems(["Dark", "Light"])
        settings_form.addRow("Theme:", theme_combo)
        
        # Language
        lang_combo = QComboBox()
        lang_combo.addItems(["English", "French"])
        settings_form.addRow("Language:", lang_combo)
        
        layout.addLayout(settings_form)
        
        # Save button
        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self._save_preferences)
        layout.addWidget(save_btn)
        
        return widget

    def _create_code_playground_page(self):
        """Create the Code Playground page for executing Python code."""
        from PySide6.QtWidgets import QSplitter, QLabel as QLabelW, QComboBox as QComboBoxW, \
            QTextEdit as QTextEditW, QPushButton as QPushButtonW, QVBoxLayout as QVBoxLayoutW, \
            QHBoxLayout as QHBoxLayoutW, QWidget as QWidgetW, QGroupBox as QGroupBoxW, \
            QFormLayout as QFormLayoutW, QSpinBox as QSpinBoxW, QCheckBox as QCheckBoxW
        
        widget = QWidgetW()
        layout = QVBoxLayoutW(widget)
        
        title = QLabelW("Code Playground")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        layout.addWidget(title)
        
        # Top section: environment selector and controls
        controls = QHBoxLayoutW()
        
        # Environment selector
        env_label = QLabelW("Environment:")
        self.code_env_combo = QComboBoxW()
        self._load_python_environments()
        controls.addWidget(env_label)
        controls.addWidget(self.code_env_combo)
        
        # Timeout
        timeout_label = QLabelW("Timeout (s):")
        self.code_timeout_spin = QSpinBoxW()
        self.code_timeout_spin.setRange(1, 300)
        self.code_timeout_spin.setValue(30)
        controls.addWidget(timeout_label)
        controls.addWidget(self.code_timeout_spin)
        
        # Run button
        self.code_run_btn = QPushButtonW("▶ Run")
        self.code_run_btn.setStyleSheet("background-color: #0e639c; color: white; font-weight: bold; padding: 8px 20px;")
        self.code_run_btn.clicked.connect(self._run_code)
        controls.addWidget(self.code_run_btn)
        
        # Clear button
        clear_btn = QPushButtonW("Clear")
        clear_btn.clicked.connect(self._clear_output)
        controls.addWidget(clear_btn)
        
        layout.addLayout(controls)
        
        # Main splitter: editor | output
        splitter = QSplitter(Qt.Horizontal)
        
        # Editor panel
        editor_widget = QWidgetW()
        editor_layout = QVBoxLayoutW(editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        
        self.code_editor = QTextEditW()
        self.code_editor.setFont(QFont("Consolas", 10))
        self.code_editor.setPlaceholderText("# Write Python code here...\nprint('Hello from Code Playground!')")
        editor_layout.addWidget(self.code_editor)
        
        splitter.addWidget(editor_widget)
        
        # Output panel
        output_widget = QWidgetW()
        output_layout = QVBoxLayoutW(output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        
        output_label = QLabelW("Output:")
        output_layout.addWidget(output_label)
        
        self.code_output = QTextEditW()
        self.code_output.setReadOnly(True)
        self.code_output.setFont(QFont("Consolas", 10))
        self.code_output.setPlaceholderText("Execution output will appear here...")
        output_layout.addWidget(self.code_output)
        
        splitter.addWidget(output_widget)
        splitter.setSizes([500, 500])
        
        layout.addWidget(splitter)
        
        # History panel at bottom
        history_label = QLabelW("Execution History:")
        layout.addWidget(history_label)
        
        self.code_history_list = QListWidgetW()
        self._refresh_execution_history()
        layout.addWidget(self.code_history_list)
        
        return widget

    def _load_python_environments(self):
        """Load available Python environments into the combo box."""
        try:
            from life_mean_studio.engine.python_executor import get_executor
            executor = get_executor()
            envs = executor.list_environments()
            self.code_env_combo.clear()
            for env in envs:
                self.code_env_combo.addItem(env["name"], env["path"])
        except Exception as exc:
            self.code_output.append(f"Warning: Could not load environments: {exc}")

    def _run_code(self):
        """Execute the code in the editor."""
        code = self.code_editor.toPlainText()
        if not code.strip():
            self.code_output.append("// Error: No code to execute")
            return
        
        env_name = self.code_env_combo.currentText()
        timeout = self.code_timeout_spin.value()
        
        self.code_run_btn.setEnabled(False)
        self.code_output.append(f"\n// Running with {env_name} (timeout: {timeout}s)...")
        self.code_output.append("//" + "=" * 50)
        
        try:
            from life_mean_studio.engine.python_executor import get_executor
            executor = get_executor()
            
            result = executor.execute_code(
                code,
                timeout_seconds=timeout,
                env_name=env_name if env_name != "System Python" else None
            )
            
            if result.success:
                self.code_output.append(f"// ✓ Success ({result.execution_time_ms:.1f}ms)")
                if result.stdout:
                    self.code_output.append(result.stdout)
            else:
                self.code_output.append(f"// ✗ Failed: {result.error_type or 'RuntimeError'}")
                if result.stderr:
                    self.code_output.append(result.stderr)
            
            # Add to history
            self._add_to_history(env_name, code, result)
            
        except Exception as exc:
            self.code_output.append(f"// ✗ Execution error: {exc}")
        
        self.code_run_btn.setEnabled(True)
        self.code_output.append("//" + "=" * 50)

    def _clear_output(self):
        """Clear the output panel."""
        self.code_output.clear()

    def _add_to_history(self, env: str, code: str, result) -> None:
        """Add execution to history list."""
        from datetime import datetime
        preview = code[:50].replace('\n', ' ') + '...' if len(code) > 50 else code.replace('\n', ' ')
        status = "✓" if result.success else "✗"
        time_str = datetime.now().strftime("%H:%M:%S")
        item = QListWidgetItem(f"[{time_str}] {status} {env}: {preview}")
        self.code_history_list.insertItem(0, item)

    def _refresh_execution_history(self):
        """Refresh the execution history list."""
        try:
            from life_mean_studio.engine.python_executor import get_executor
            executor = get_executor()
            history = executor.get_execution_history(limit=20)
            self.code_history_list.clear()
            for entry in reversed(history):
                result = entry.get("result", {})
                status = "✓" if result.get("success") else "✗"
                time_str = datetime.fromtimestamp(entry["timestamp"]).strftime("%H:%M:%S")
                item = QListWidgetItem(f"[{time_str}] {status} {entry['env']}: {entry['code_preview']}")
                self.code_history_list.addItem(item)
        except Exception:
            pass

    # ------------------------------------------------------------------ Agent Builder

    def _create_agent_builder_page(self):
        """Create the Agent Builder page."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        title = QLabel("Agent Builder")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        layout.addWidget(title)

        # Main splitter: list | form
        splitter = QSplitter(Qt.Horizontal)

        # Left panel: agent list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.agent_list = QListWidget()
        self._refresh_agent_list()
        left_layout.addWidget(self.agent_list)

        # Agent list buttons
        btn_layout = QHBoxLayout()
        dup_btn = QPushButton("Duplicate")
        dup_btn.clicked.connect(self._duplicate_agent)
        del_btn = QPushButton("Delete")
        del_btn.clicked.connect(self._delete_agent)
        btn_layout.addWidget(dup_btn)
        btn_layout.addWidget(del_btn)
        left_layout.addLayout(btn_layout)

        splitter.addWidget(left_panel)

        # Right panel: agent form
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Agent info
        info_layout = QFormLayout()
        self.agent_name_edit = QLineEdit()
        self.agent_name_edit.setPlaceholderText("Agent name...")
        info_layout.addRow("Name:", self.agent_name_edit)

        self.agent_persona_combo = QComboBox()
        self.agent_persona_combo.addItems(["general", "scientist", "researcher", "analyst", "writer", "coder"])
        info_layout.addRow("Persona:", self.agent_persona_combo)

        self.agent_model_combo = QComboBox()
        self.agent_model_combo.setEditable(True)
        self.agent_model_combo.setPlaceholderText("Select model...")
        self._load_models_to_combo()
        info_layout.addRow("Model:", self.agent_model_combo)

        self.agent_provider_combo = QComboBox()
        self.agent_provider_combo.addItems(["lm-studio", "openai", "anthropic", "azure", "groq"])
        info_layout.addRow("Provider:", self.agent_provider_combo)

        right_layout.addLayout(info_layout)

        # System prompt
        prompt_label = QLabel("System Prompt:")
        right_layout.addWidget(prompt_label)
        self.agent_prompt_edit = QTextEdit()
        self.agent_prompt_edit.setMinimumHeight(150)
        self.agent_prompt_edit.setPlaceholderText("Enter the system prompt for this agent...")
        right_layout.addWidget(self.agent_prompt_edit)

        # Config (JSON)
        config_label = QLabel("Config (JSON, optional):")
        right_layout.addWidget(config_label)
        self.agent_config_edit = QTextEdit()
        self.agent_config_edit.setMinimumHeight(80)
        self.agent_config_edit.setPlaceholderText('{"temperature": 0.7, "max_tokens": 1024}')
        right_layout.addWidget(self.agent_config_edit)

        # Buttons
        btn_row = QHBoxLayout()
        create_btn = QPushButton("Create")
        create_btn.setStyleSheet("background-color: #0e639c; color: white; font-weight: bold;")
        create_btn.clicked.connect(self._create_agent)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_agent)
        test_btn = QPushButton("Test Agent")
        test_btn.clicked.connect(self._test_agent)
        btn_row.addWidget(create_btn)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(test_btn)
        right_layout.addLayout(btn_row)

        # Test output
        test_label = QLabel("Test Output:")
        right_layout.addWidget(test_label)
        self.agent_test_output = QTextEdit()
        self.agent_test_output.setReadOnly(True)
        self.agent_test_output.setMinimumHeight(100)
        right_layout.addWidget(self.agent_test_output)

        splitter.addWidget(right_panel)
        splitter.setSizes([300, 500])

        layout.addWidget(splitter)

        # Search
        search_layout = QHBoxLayout()
        search_edit = QLineEdit()
        search_edit.setPlaceholderText("Search agents...")
        search_edit.textChanged.connect(self._search_agents)
        search_layout.addWidget(search_edit)
        layout.addLayout(search_layout)

        return widget

    def _load_models_to_combo(self):
        """Load available models from LLM backend."""
        try:
            models = self.agent_manager.get_available_models()
            self.agent_model_combo.clear()
            if not models:
                self.agent_model_combo.addItem("qwen3.5-2b (default)")
            else:
                for model in models:
                    self.agent_model_combo.addItem(model)
        except Exception:
            self.agent_model_combo.addItem("qwen3.5-2b (default)")

    def _refresh_agent_list(self):
        """Refresh the agent list."""
        self.agent_list.clear()
        for agent in self.agent_manager.list_all():
            status = "✓" if agent["enabled"] else "✗"
            item = QListWidgetItem(f"{status} {agent['name']} ({agent['persona']})")
            item.setData(Qt.UserRole, agent["id"])
            self.agent_list.addItem(item)

    def _select_agent(self):
        """Load selected agent into the form."""
        item = self.agent_list.currentItem()
        if not item:
            return
        agent_id = item.data(Qt.UserRole)
        agent = self.agent_manager.get(agent_id)
        if not agent:
            return

        self.agent_name_edit.setText(agent["name"])
        self.agent_persona_combo.setCurrentText(agent["persona"])
        # Set model
        model_text = agent.get("model") or "qwen3.5-2b"
        idx = self.agent_model_combo.findText(model_text)
        if idx >= 0:
            self.agent_model_combo.setCurrentIndex(idx)
        else:
            self.agent_model_combo.setEditText(model_text)
        # Set provider
        provider_text = agent.get("provider") or "lm-studio"
        idx = self.agent_provider_combo.findText(provider_text)
        if idx >= 0:
            self.agent_provider_combo.setCurrentIndex(idx)
        # Set prompt
        self.agent_prompt_edit.setPlainText(agent["system_prompt"])
        # Set config
        config_str = json.dumps(agent.get("config", {}), indent=2, ensure_ascii=False)
        self.agent_config_edit.setPlainText(config_str)

    def _create_agent(self):
        """Create a new agent."""
        name = self.agent_name_edit.text().strip()
        system_prompt = self.agent_prompt_edit.toPlainText().strip()
        persona = self.agent_persona_combo.currentText()
        model = self.agent_model_combo.currentText()
        if model == "(select model...)" or not model:
            model = "qwen3.5-2b"
        provider = self.agent_provider_combo.currentText()

        config = {}
        try:
            config_str = self.agent_config_edit.toPlainText().strip()
            if config_str:
                config = json.loads(config_str)
        except json.JSONDecodeError:
            QMessageBox.warning(self, "Config Error", "Invalid JSON in config field")
            return

        result = self.agent_manager.create(
            name=name,
            system_prompt=system_prompt,
            persona=persona,
            model=model,
            provider=provider,
            config=config,
        )
        if result.success:
            self._refresh_agent_list()
            self.agent_test_output.append(f"✓ Agent '{name}' created.")
        else:
            QMessageBox.critical(self, "Error", f"Failed to create agent: {result.message}")

    def _save_agent(self):
        """Save changes to selected agent."""
        item = self.agent_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Warning", "No agent selected")
            return
        agent_id = item.data(Qt.UserRole)
        name = self.agent_name_edit.text().strip()
        system_prompt = self.agent_prompt_edit.toPlainText().strip()
        persona = self.agent_persona_combo.currentText()
        model = self.agent_model_combo.currentText() or "qwen3.5-2b"
        provider = self.agent_provider_combo.currentText()

        config = {}
        try:
            config_str = self.agent_config_edit.toPlainText().strip()
            if config_str:
                config = json.loads(config_str)
        except json.JSONDecodeError:
            QMessageBox.warning(self, "Config Error", "Invalid JSON in config field")
            return

        result = self.agent_manager.update(agent_id, {
            "name": name,
            "system_prompt": system_prompt,
            "persona": persona,
            "model": model,
            "provider": provider,
            "config": config,
        })
        if result.success:
            self._refresh_agent_list()
            self.agent_test_output.append(f"✓ Agent '{name}' saved.")
        else:
            QMessageBox.critical(self, "Error", f"Failed to save agent: {result.message}")

    def _delete_agent(self):
        """Delete selected agent."""
        item = self.agent_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Warning", "No agent selected")
            return
        agent_id = item.data(Qt.UserRole)
        agent = self.agent_manager.get(agent_id)
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete agent '{agent['name']}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            result = self.agent_manager.delete(agent_id)
            if result.success:
                self._refresh_agent_list()
                self.agent_test_output.append(f"✓ Agent deleted.")
            else:
                QMessageBox.critical(self, "Error", f"Failed to delete agent: {result.message}")

    def _duplicate_agent(self):
        """Duplicate selected agent."""
        item = self.agent_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Warning", "No agent selected")
            return
        agent_id = item.data(Qt.UserRole)
        result = self.agent_manager.duplicate(agent_id)
        if result.success:
            self._refresh_agent_list()
            self.agent_test_output.append(f"✓ Agent duplicated.")
        else:
            QMessageBox.critical(self, "Error", f"Failed to duplicate agent: {result.message}")

    def _test_agent(self):
        """Test selected agent with a sample prompt."""
        item = self.agent_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Warning", "No agent selected")
            return
        agent_id = item.data(Qt.UserRole)
        agent = self.agent_manager.get(agent_id)

        # Use the system prompt as context, send a test question
        test_prompt = "Hello, please introduce yourself and describe your capabilities."

        self.agent_test_output.append(f"\n// Testing agent '{agent['name']}'...")
        self.agent_test_output.append("// Sending prompt to LLM backend...")

        result = self.agent_manager.test_agent(agent_id, test_prompt)

        if result.success:
            self.agent_test_output.append(f"✓ Response ({result.latency_ms:.0f}ms):")
            self.agent_test_output.append(result.response)
        else:
            self.agent_test_output.append(f"✗ Error: {result.error}")

    def _search_agents(self, query: str):
        """Search agents by query."""
        self.agent_list.clear()
        for agent in self.agent_manager.search(query):
            status = "✓" if agent["enabled"] else "✗"
            item = QListWidgetItem(f"{status} {agent['name']} ({agent['persona']})")
            item.setData(Qt.UserRole, agent["id"])
            self.agent_list.addItem(item)

    def closeEvent(self, event):
        """Handle window close."""
        timer_id = getattr(self, "_health_timer_id", None)
        if timer_id is not None:
            try:
                QTimer.killTimer(timer_id)
            except Exception:
                pass
            self._health_timer_id = None
        self._save_preferences()
        event.accept()
