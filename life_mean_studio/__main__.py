"""
Life_mean Studio - Main Entry Point

This module launches the PySide6 application.
No execution of agents or services occurs at this point.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import QApplication
from life_mean_studio.launcher.app import LifeMeanStudioApp


def main():
    """Launch the Life_mean Studio application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Life_mean Studio")
    app.setOrganizationName("Life_mean")
    app.setOrganizationDomain("life_mean.local")
    
    window = LifeMeanStudioApp()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
