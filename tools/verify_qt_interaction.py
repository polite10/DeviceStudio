"""Exercise real QML pointer/keyboard interaction across background refreshes.

Uses only a fake serial device and the native Qt renderer. No physical port
or Flash is touched; the embedded View3D requires an RHI GPU backend.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QEvent, QMetaObject
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import getCppPointer, isValid

from device_studio.qt_app import create_app
from device_studio.windowing import activate_window
from device_studio.qt_controller import StudioController


class InteractionDevice:
    def __init__(self, port):
        self.current = None
        self.status_count = 0

    def detect(self):
        self.current = dict(app='ADASLab', id=3, version=1, protocol=1,
                            boot=1, boot_version=2, ready=True, error='',
                            state=dict(mode='WAITING', ego=0, lead=0, gap=0,
                                       ttc=-1, a=0, fresh=False, ms=0, gpu=0, frames=0))
        return deepcopy(self.current)

    def runtime(self, command, **kwargs):
        self.status_count += 1
        self.current['state'].update(gpu=self.status_count, frames=self.status_count)
        return deepcopy(self.current)

    def close(self):
        pass


def main():
    app = QApplication.instance() or QApplication(['studio-interaction-qa'])
    device = InteractionDevice('fixture')
    with patch('serial.tools.list_ports.comports', return_value=[
            SimpleNamespace(device='ui-interaction-fixture', description='STLINK-V3')]):
        bridge = StudioController(device_factory=lambda port: device, start_timers=True)
    app, engine, bridge = create_app(controller=bridge, argv=['studio-interaction-qa'])
    window = engine.rootObjects()[0]
    checks = []

    def check(condition, description):
        if not condition:
            raise AssertionError(description)
        checks.append(description)
        print('PASS: ' + description, flush=True)

    def pump(seconds=.12):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.005)

    def wait(predicate, timeout=4):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return
            time.sleep(.005)
        raise AssertionError('Timed out waiting for Qt interaction: ' + bridge.state['statusMessage'])

    def item(name):
        result = window.findChild(QObject, name)
        # Repeater delegates can have a visual parent without being QObject
        # children of the window. Search the scene tree as well.
        pending = [window.contentItem()]
        while result is None and pending:
            current = pending.pop()
            if current.objectName() == name:
                result = current
                break
            result = current.findChild(QObject, name)
            pending.extend(current.childItems())
        if result is None:
            raise AssertionError('Missing named QML control: ' + name)
        return result

    def center(control):
        point = control.mapToScene(QPointF(control.width() / 2, control.height() / 2))
        return QPoint(round(point.x()), round(point.y()))

    def click(control):
        QTest.mouseClick(window, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, center(control))
        pump(.1)

    try:
        activate_window(window)
        pump(.25)
        bridge.connectDevice()
        wait(lambda: bridge.state['connected'] and not bridge.state['busy'])
        bridge.navigate('game')
        pump(.15)

        # A normal human click can span a status update; it must not be lost
        # because the delegate was replaced or became disabled mid-press.
        nav = item('nav_firmware')
        address = getCppPointer(nav)[0]
        initial_status = device.status_count
        position = center(nav)
        QTest.mousePress(window, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, position)
        pump(1.4)
        check(device.status_count > initial_status, 'Heartbeat occurred while navigation button was held')
        check(isValid(nav) and getCppPointer(item('nav_firmware'))[0] == address,
              'Navigation delegate survives a heartbeat while pressed')
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier, position)
        pump(.15)
        check(bridge.state['page'] == 'firmware', 'Release completes the held navigation click')
        click(item('nav_game'))
        check(bridge.state['page'] == 'game', 'Navigation remains usable after refresh')

        viewport = item('driveViewport')
        viewport_address = getCppPointer(viewport)[0]
        initial_status = device.status_count
        pump(1.4)
        check(device.status_count > initial_status, 'Heartbeat continues with the embedded 3D scene')
        check(isValid(viewport) and getCppPointer(item('driveViewport'))[0] == viewport_address,
              'Background refresh preserves the same 3D viewport')
        check(window.findChild(QObject, 'scenarioSelector') is None,
              'Removed ADASLab settings are absent from the live UI')

        click(item('nav_console'))
        field = item('commandField')
        click(field)
        for key in (Qt.Key.Key_H, Qt.Key.Key_E, Qt.Key.Key_L, Qt.Key.Key_L, Qt.Key.Key_O):
            QTest.keyClick(window, key, Qt.KeyboardModifier.ShiftModifier)
        QMetaObject.invokeMethod(field, 'selectAll', Qt.ConnectionType.DirectConnection)
        selected = field.property('selectedText')
        pump(1.4)
        check(str(field.property('text')).upper() == 'HELLO', 'Console command draft survives status updates: ' + str(field.property('text')))
        check(bool(field.property('activeFocus')) and field.property('selectedText') == selected,
              'Console text selection and focus survive status updates')
        check(not bridge.state['busy'], 'Background refresh leaves command controls enabled')
        address = getCppPointer(field)[0]
        QTest.keyClick(window, Qt.Key.Key_Right)
        QTest.keyClick(window, Qt.Key.Key_1)
        pump(1.4)
        check(str(field.property('text')).upper() == 'HELLO1', 'An unfinished command draft survives another heartbeat: ' + str(field.property('text')))
        check(getCppPointer(item('commandField'))[0] == address, 'Command editor identity remains stable')
    finally:
        bridge.stopOperation()
        wait(lambda: not bridge.state['busy'])
        bridge.requestClose()
        window.hide()
        engine.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    output = ROOT / 'build/qt-interaction-report.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(dict(passed=True, checks=checks,
        scope='Actual QML pointer/keyboard events with fake UART; no hardware'),
        ensure_ascii=False, indent=2) + '\n')
    print(f'{len(checks)} actual QML interaction checks passed.')


if __name__ == '__main__':
    main()
