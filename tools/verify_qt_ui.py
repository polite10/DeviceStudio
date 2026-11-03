"""Load the real QML, exercise its actions and render every page.

Default uses a UI fixture, never a port. --backend arm runs the actual ARM ELF;
--backend hardware uses the already installed firmware, without flashing.
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QObject, QMetaObject, Qt, qInstallMessageHandler, QEvent
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWidgets import QApplication
from device_studio.qt_controller import StudioController
from device_studio.qt_app import create_app


class FixtureDevice:
    def __init__(self, port):
        self.current = None
    def detect(self):
        return self.runtime('HELLO')
    def runtime(self, command, **kwargs):
        old = self.current['state'] if self.current else {}
        if command.startswith('S:'):
            fields = command.split(':')
            old = dict(mode='ACC', fresh=True, ms=int(fields[1]), ego=int(fields[2]),
                       lead=int(fields[3]), gap=int(fields[4]), a=0, ttc=-1, gpu=0, frames=0, error='')
        elif command == 'PAUSE':
            old = dict(old, mode='PAUSED', a=0)
        self.current = dict(app='ADASLab', id=3, version=3, protocol=1, boot=1,
                            boot_version=2, ready=True, error='', state=old)
        return self.current
    def close(self):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=['fixture', 'arm', 'hardware'], default='fixture')
    parser.add_argument('--seconds', type=float, default=4)
    parser.add_argument('--capture-dir', type=Path, default=ROOT / 'build/qt-preview')
    parser.add_argument('--port')
    args = parser.parse_args()
    args.capture_dir.mkdir(parents=True, exist_ok=True)
    warnings = []
    def messages(kind, context, text):
        if any(word in text for word in ('TypeError', 'ReferenceError', 'Binding loop', 'Unable to assign', 'Cannot assign')):
            warnings.append(text)
        elif 'Populating font family aliases' not in text:
            print(text, file=sys.stderr)
    qInstallMessageHandler(messages)
    app = QApplication.instance() or QApplication(['studio-ui-qa'])
    bridge = StudioController(device_factory=FixtureDevice if args.backend == 'fixture' else None,
                              arm_sim=args.backend == 'arm', start_timers=False)
    app, engine, bridge = create_app(controller=bridge, argv=['studio-ui-qa'])
    window = engine.rootObjects()[0]
    report = dict(backend=args.backend, checks=[], screenshots=[])
    def check(condition, description):
        if not condition:
            raise AssertionError(description)
        report['checks'].append(description)
        print('PASS: ' + description, flush=True)
    def pump(seconds=.1):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            app.processEvents()
            time.sleep(.005)
    def wait(predicate, timeout=5):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            app.processEvents()
            if predicate():
                return
            time.sleep(.005)
        raise AssertionError('Qt operation timed out: ' + bridge.state['statusMessage'])
    def item(name):
        obj = window.findChild(QObject, name)
        check(obj is not None, 'QML control exists: ' + name)
        return obj
    def capture(name):
        pump(.2)
        image = window.grabWindow()
        check(not image.isNull() and image.width() >= 1000, 'Rendered scene: ' + name)
        path = args.capture_dir / (name + '.png')
        check(image.save(str(path)), 'Saved scene: ' + name)
        report['screenshots'].append(str(path))
    try:
        pump(.35)
        report['graphics_api'] = window.rendererInterface().graphicsApi().name
        check(window.objectName() == 'mainWindow', 'Qt Quick application window loaded')
        check(not item('drive3DView').property('available'), '3D view clearly indicates missing device connection')
        capture('offline')
        if args.port:
            index = next(i for i, p in enumerate(bridge.state['ports']) if p['device'] == args.port)
            bridge.selectPort(index)
        if args.backend == 'fixture' and not bridge.state['ports']:
            # UI fixture does not need an actual port; keep the selection local.
            bridge._state.update(ports=[dict(device='ui-fixture', label='UI fixture')], portIndex=0)
        check(QMetaObject.invokeMethod(item('connectionButton'), 'clicked', Qt.ConnectionType.DirectConnection), 'Connection action reaches Python')
        wait(lambda: not bridge.state['busy'], 20)
        check(bridge.state['connected'] and bridge.state['app'] == 'ADASLab', 'Backend identity appears in QML: ' +
              str((bridge.state['connected'], bridge.state['app'], bridge.state['statusMessage'])))
        if args.backend == 'fixture':
            bridge._state['backendLabel'] = 'Arayüz testi · sanal cihaz'
            bridge._publish()
        check(item('drive3DView').property('available'), 'Embedded 3D page recognizes compatible firmware')
        check(window.findChild(QObject, 'scenarioSelector') is None, 'Old ADASLab page is removed')
        check(window.findChild(QObject, 'gameStartButton') is None, 'PC start controls are replaced by watch instructions')
        capture('3d-ready')
        window.setWidth(1000)
        window.setHeight(720)
        capture('3d-compact')
        for name in ('watchMode', 'watchTarget', 'driveSpeed'):
            obj = item(name)
            point = obj.mapToScene(obj.boundingRect().topLeft())
            check(point.x() >= 0 and point.y() >= 83 and point.x() + obj.width() <= window.width() + 1 and point.y() + obj.height() <= window.height() - 38,
                  'Compact HUD stays within content area: ' + name)
        window.setWidth(1360)
        window.setHeight(900)
        for page in ('firmware', 'duello', 'console'):
            bridge.navigate(page)
            capture(page)
        field = item('commandField')
        field.setProperty('text', 'STATUS')
        check(QMetaObject.invokeMethod(field, 'accepted', Qt.ConnectionType.DirectConnection), 'Console action reaches Python')
        wait(lambda: not bridge.state['busy'])
        check(any('Komut: STATUS' in line for line in bridge.state['logs']), 'Console result is logged')
        bridge.navigate('firmware')
        if args.backend != 'arm':
            bridge.loadFirmware(str(ROOT / 'Firmware/ADASLab.dfw'))
            bridge.requestUpload()
            pump(.1)
            check(bool(item('confirmationDialog').property('visible')), 'Firmware confirmation is visible in QML')
            capture('firmware-confirmation')
            bridge.confirmAction(False)
            check(not bridge.state['busy'], 'Declining upload never starts a transfer')
        check(not warnings, 'No QML runtime binding errors')
        report.update(passed=True, telemetry=bridge.state['telemetry'])
    finally:
        bridge.stopOperation()
        wait(lambda: not bridge.state['busy'], 25)
        bridge.requestClose()
        window.hide()
        engine.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    (args.capture_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(passed=True, checks=len(report['checks']), backend=args.backend), ensure_ascii=False))


if __name__ == '__main__':
    main()
