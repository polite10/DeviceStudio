"""Native Qt Quick application bootstrap. The C firmware is independent of UI."""
from pathlib import Path
import sys

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick3D import QQuick3D
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from .qt_controller import StudioController
from .windowing import activate_window

QML_MAIN = Path(__file__).resolve().parent / 'qml/Main.qml'


def create_app(*, auto_connect=False, auto_adas=False, arm_sim=False, auto_game3d=False,
               controller=None, argv=None):
    """Return owned application/engine/controller for normal startup or QA."""
    QQuickStyle.setStyle('Basic')
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    # OpenGL (Linux, or QSG_RHI_BACKEND=opengl on Windows) needs a core profile
    # for the 3D scene; Direct3D 11 only takes its depth/stencil sizes. macOS
    # renders with Metal, and Apple's OpenGL 4.1 core crashes Qt's MSAA path.
    if sys.platform != 'darwin':
        QSurfaceFormat.setDefaultFormat(QQuick3D.idealSurfaceFormat())
    app.setApplicationName('ADASLab')
    app.setOrganizationName('ADASLab')
    bridge = controller or StudioController(app, auto_adas=auto_adas, arm_sim=arm_sim)
    engine = QQmlApplicationEngine()
    engine.setInitialProperties({'studio': bridge})
    engine.load(QUrl.fromLocalFile(str(QML_MAIN)))
    if not engine.rootObjects():
        bridge.shutdown()
        raise RuntimeError('ADASLab QML arayüzü yüklenemedi; konsoldaki hataları kontrol edin.')
    window = engine.rootObjects()[0]
    QTimer.singleShot(0, lambda: activate_window(window))
    bridge.shutdownReady.connect(app.quit)
    app.aboutToQuit.connect(bridge.shutdown)
    if auto_game3d:
        QTimer.singleShot(0, lambda: bridge.navigate('game'))
    if auto_connect:
        QTimer.singleShot(350, bridge.connectDevice)
    return app, engine, bridge


def main(auto_connect=False, auto_adas=False, arm_sim=False, auto_game3d=False):
    app, engine, bridge = create_app(auto_connect=auto_connect, auto_adas=auto_adas, arm_sim=arm_sim, auto_game3d=auto_game3d)
    return app.exec()
