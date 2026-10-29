"""Native Qt Quick application bootstrap. The C firmware is independent of UI."""
from pathlib import Path
import sys

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from .qt_controller import StudioController

QML_MAIN = Path(__file__).resolve().parent / 'qml/Main.qml'


def create_app(*, auto_connect=False, auto_adas=False, arm_sim=False, auto_game3d=False,
               controller=None, argv=None):
    """Return owned application/engine/controller for normal startup or QA."""
    QQuickStyle.setStyle('Basic')
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName('Device Studio')
    app.setOrganizationName('DeviceStudio')
    bridge = controller or StudioController(app, auto_adas=auto_adas, arm_sim=arm_sim)
    engine = QQmlApplicationEngine()
    engine.setInitialProperties({'studio': bridge})
    engine.load(QUrl.fromLocalFile(str(QML_MAIN)))
    if not engine.rootObjects():
        bridge.shutdown()
        raise RuntimeError('Studio QML arayüzü yüklenemedi; konsoldaki hataları kontrol edin.')
    bridge.shutdownReady.connect(app.quit)
    app.aboutToQuit.connect(bridge.shutdown)
    if auto_game3d:
        QTimer.singleShot(200, bridge.openGame3D)
    if auto_connect:
        QTimer.singleShot(350, bridge.connectDevice)
    return app, engine, bridge


def main(auto_connect=False, auto_adas=False, arm_sim=False, auto_game3d=False):
    app, engine, bridge = create_app(auto_connect=auto_connect, auto_adas=auto_adas, arm_sim=arm_sim, auto_game3d=auto_game3d)
    return app.exec()
