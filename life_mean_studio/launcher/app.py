"""
Life_mean Studio - Main Application Window

Main window with navigation between all modules.
No execution of agents or services occurs at this point.
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
    QLCDNumber, QGraphicsView, QGridLayout, QSlider
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QRect, QSize, QPoint
from PySide6.QtGui import QIcon, QPixmap, QFont, QColor, QPainter, QAction, QActionGroup

from life_mean_studio.engine.storage import StudioStorage
from life_mean_studio.workflows.manager import WorkflowManager
from life_mean_studio.workflows import WorkflowConfig, AgentConfig
from life_mean_studio.prompts.collection import PromptCollection

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
        
        # UI state
        self.current_mode = "simple"  # simple or dev
        self.preferences = self._load_preferences()
        
        # Setup UI
        self._setup_ui()
        self._apply_theme()
        
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
        
        # Add pages to stack
        self.central_widget.addWidget(self.home_page)
        self.central_widget.addWidget(self.services_page)
        self.central_widget.addWidget(self.workflows_page)
        self.central_widget.addWidget(self.prompts_page)
        self.central_widget.addWidget(self.console_page)
        self.central_widget.addWidget(self.dev_page)
        self.central_widget.addWidget(self.packages_page)
        self.central_widget.addWidget(self.settings_page)
        
        # Setup toolbar
        self._setup_toolbar()
        
        # Setup status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Life_mean Studio - Phase C: UI Only. No agent execution.")
        
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
        ]
        
        action_group = QActionGroup(self)
        for name, index in nav_actions:
            action = QAction(name, self)
            action.setCheckable(True)
            action.triggered.connect(lambda idx=index: self._navigate_to(idx))
            action_group.addAction(action)
            toolbar.addAction(action)
        
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
        """Navigate to a page."""
        self.central_widget.setCurrentIndex(index)
        
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
        subtitle = QLabel("Phase C: PySide6 Interface - No Agent Execution")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        
        # Quick Run Section
        quick_run = self._create_quick_run_section()
        layout.addWidget(quick_run)
        
        # Status
        status = QLabel("Status: UI Only. RUN/STOP buttons are disabled.")
        status.setAlignment(Qt.AlignCenter)
        status.setStyleSheet("color: #ffaa00;")
        layout.addWidget(status)
        
        return widget
    
    def _create_quick_run_section(self):
        """Create the Quick Run section."""
        group = QGroupBox("Quick Run")
        layout = QFormLayout(group)
        
        # Workflow selector (disabled)
        self.workflow_combo = QComboBox()
        self._load_workflows_to_combo()
        self.workflow_combo.setEnabled(False)
        layout.addRow("Workflow:", self.workflow_combo)
        
        # Model selector (disabled, but populated with real models when available)
        self.model_combo = QComboBox()
        self.model_combo.addItem("(detecting models…)" if not _in_pytest() else "(models unavailable in tests)")
        self.model_combo.setEnabled(False)
        layout.addRow("Model:", self.model_combo)
        # Populate with real models from the LLM backend (best-effort, async)
        if not _in_pytest():
            QTimer.singleShot(0, self._load_real_models)
        
        # Mode selector
        self.mode_select = QComboBox()
        self.mode_select.addItems(["Python Only", "Python + Dashboard", "Dashboard Only", "Backend Only"])
        layout.addRow("Launch Mode:", self.mode_select)
        
        # Compression toggle (disabled)
        self.compression_check = QCheckBox("Compression ON")
        self.compression_check.setEnabled(False)
        layout.addRow("Compression:", self.compression_check)
        
        # RUN button (disabled)
        self.run_btn = QPushButton("RUN")
        self.run_btn.setEnabled(False)
        self.run_btn.setStyleSheet("background-color: #cc0000; color: white; font-weight: bold;")
        layout.addRow("", self.run_btn)
        
        # STOP button (disabled)
        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setEnabled(False)
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
        edit_btn.setEnabled(False)  # Will be enabled when item selected
        btn_layout.addWidget(edit_btn)
        
        duplicate_btn = QPushButton("Duplicate")
        duplicate_btn.setEnabled(False)
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
        layout = QFormLayout(dialog)
        
        name_edit = QLineEdit()
        layout.addRow("Name:", name_edit)
        
        mode_combo = QComboBox()
        mode_combo.addItems(["single", "multi"])
        layout.addRow("Mode:", mode_combo)
        
        ok_btn = QPushButton("Create")
        cancel_btn = QPushButton("Cancel")
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addRow("", btn_layout)
        
        ok_btn.clicked.connect(lambda: self._save_new_workflow(dialog, name_edit.text(), mode_combo.currentText()))
        cancel_btn.clicked.connect(dialog.reject)
        
        dialog.exec()
    
    def _save_new_workflow(self, dialog, name, mode):
        """Save a new workflow."""
        if not name:
            QMessageBox.warning(self, "Error", "Name is required")
            return
        
        config = {"mode": mode, "name": name}
        try:
            wf_id = self.workflow_manager.create(WorkflowConfig(name=name, mode=mode))
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
        # Navigate to home page with workflow selected
        self._navigate_to(0)
        # In a real app, we would set the combo box value here
    
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
        btn_layout.addWidget(edit_btn)
        
        duplicate_btn = QPushButton("Duplicate")
        btn_layout.addWidget(duplicate_btn)
        
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
            item = QListWidgetItem(f"{prompt['name']} ({prompt['category']})")
            item.setData(Qt.UserRole, prompt["id"])
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
            item = QListWidgetItem(f"{prompt['name']} ({prompt['category']})")
            item.setData(Qt.UserRole, prompt["id"])
            self.prompt_list.addItem(item)
    
    def _create_console_page(self):
        """Create the agent console page."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        title = QLabel("Agent Console")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        layout.addWidget(title)
        
        # Status label
        status_label = QLabel("No session connected")
        status_label.setStyleSheet("color: #888888; font-style: italic;")
        layout.addWidget(status_label)
        
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
        agent_tab = QWidget()
        agent_layout = QVBoxLayout(agent_tab)
        agent_layout.addWidget(QLabel("Agent Builder - Not Implemented"))
        agent_layout.addWidget(QLabel("Status: Phase D"))
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

Note: No agent execution is occurring.
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
        info = QLabel(".lmpack format - Not Implemented\nImport/Export buttons are disabled.")
        info.setStyleSheet("color: #888888;")
        layout.addWidget(info)
        
        # Buttons (disabled)
        btn_layout = QHBoxLayout()
        import_btn = QPushButton("Import Package")
        import_btn.setEnabled(False)
        export_btn = QPushButton("Export Package")
        export_btn.setEnabled(False)
        btn_layout.addWidget(import_btn)
        btn_layout.addWidget(export_btn)
        layout.addLayout(btn_layout)
        
        return widget
    
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
    
    def closeEvent(self, event):
        """Handle window close."""
        # Kill any pending health-check timer so it never fires after close.
        timer_id = getattr(self, "_health_timer_id", None)
        if timer_id is not None:
            try:
                QTimer.killTimer(timer_id)
            except Exception:
                pass
            self._health_timer_id = None
        self._save_preferences()
        event.accept()
