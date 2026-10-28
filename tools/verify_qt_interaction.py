"""Exercise real QML pointer/keyboard interaction across background refreshes.

Uses only a fake serial device. Run with QT_QPA_PLATFORM=offscreen and
QT_QUICK_BACKEND=software for headless QA. No physical port or Flash is touched.
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
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQml import QQmlExpression
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import getCppPointer, isValid

from device_studio.qt_app import create_app
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
        window.requestActivate()
        pump(.25)
        bridge.connectDevice()
        wait(lambda: bridge.state['connected'] and not bridge.state['busy'])
        bridge.navigate('adas')
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
        click(item('nav_adas'))
        check(bridge.state['page'] == 'adas', 'Navigation remains usable after refresh')

        # An open ComboBox popup is a user interaction state, not telemetry.
        selector = item('scenarioSelector')
        selector_address = getCppPointer(selector)[0]
        click(selector)
        expression = QQmlExpression(engine.rootContext(), selector, 'popup')
        popup, _ = expression.evaluate()
        check(not expression.hasError() and popup is not None,
              'Scenario popup is inspectable through its real QML property')
        check(bool(popup.property('visible')), 'Scenario popup opens with a real mouse click')
        initial_status = device.status_count
        pump(1.4)
        check(device.status_count > initial_status, 'Heartbeat occurred while scenario popup was open')
        check(isValid(selector) and getCppPointer(item('scenarioSelector'))[0] == selector_address,
              'Scenario control identity is stable during refresh')
        check(bool(popup.property('visible')), 'Scenario popup remains open across refresh')
        QTest.keyClick(window, Qt.Key.Key_Escape)
        pump(.1)

        # Preserve uncommitted text, focus and cursor in an editable value.
        speed = item('targetSpeed')
        editor = speed.property('contentItem')
        click(editor)
        QMetaObject.invokeMethod(editor, 'selectAll', Qt.ConnectionType.DirectConnection)
        for key in (Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_3):
            QTest.keyClick(window, key)
        pump(.1)
        check(str(editor.property('text')) == '123', 'Speed editor accepts a keyboard draft: ' + str(editor.property('text')))
        cursor = editor.property('cursorPosition')
        pump(1.4)
        check(str(editor.property('text')) == '123', 'Uncommitted speed draft survives heartbeat')
        check(bool(editor.property('activeFocus')) and editor.property('cursorPosition') == cursor,
              'Speed editor keeps focus and cursor across heartbeat')
        QTest.keyClick(window, Qt.Key.Key_Return)
        wait(lambda: bridge.state['targetKmh'] == 123)
        check(bridge.state['targetKmh'] == 123, 'Committing the draft updates controller options')

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
