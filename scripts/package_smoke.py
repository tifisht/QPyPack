"""Open the packaged Qt UI and report its resources, version and clean exit."""
import json
import sys
import tempfile
import traceback
from pathlib import Path


def run(report_path):
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from qpypack import main

    report_path = Path(report_path).resolve()
    result = {"status": "failed", "version": main.__version__}
    exit_code = 1
    app = QApplication([sys.argv[0]])
    with tempfile.TemporaryDirectory(prefix="qpypack-smoke-") as settings:
        main.CONFIG_FILE = str(Path(settings) / "config.ini")
        window = main.MainWindow()
        window.show()

        def finish():
            nonlocal exit_code
            try:
                resources = Path(main.__file__).parent
                locales = sorted((resources / "locales").glob("*.json"))
                assert locales, "Packaged translations are missing"
                for locale in locales:
                    assert isinstance(json.loads(locale.read_text(encoding="utf-8")), dict)
                assert not QIcon(str(resources / "icon.ico")).isNull(), "Packaged icon is missing"
                assert not QIcon(main.get_resource_path("icon.ico")).isNull(), "UI icon lookup failed"
                assert window.isVisible(), "Main window did not open"
                assert window.settings_panel.scanner_thread.wait(30000), "Python scanner did not stop"
                app.processEvents()
                image = window.grab()
                assert not image.isNull(), "Could not render main window"
                assert image.save(str(report_path.with_suffix(".png"))), "Could not save UI rendering"
                result.update(status="passed", locales=[p.name for p in locales],
                              module=main.__file__, frozen=bool(getattr(sys, "frozen", False)))
                exit_code = 0
            except Exception:
                result["error"] = traceback.format_exc()
            finally:
                window.close()
                report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
                app.exit(exit_code)

        QTimer.singleShot(250, finish)
        app.exec()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1]))
