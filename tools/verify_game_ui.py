"""Verify the embedded Qt Quick 3D scene with real keyboard events and C firmware.

Default: compiled ARM firmware, including the watch's actual touch handler.
--backend hardware --port PORT: existing board, G/H protocol equivalents of
watch actions. No Flash writes. Reports and window captures go to capture-dir.
Run with native Qt RHI (Metal on macOS); the software backend cannot render 3D.
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QObject, QPoint, QEvent, Qt, qInstallMessageHandler
from PySide6.QtGui import QKeyEvent
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from device_studio.qt_app import create_app
from device_studio.windowing import activate_window
from device_studio.qt_controller import StudioController


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-dir', type=Path, default=ROOT / 'build/embedded-3d-qa')
    parser.add_argument('--backend', choices=('arm', 'hardware'), default='arm')
    parser.add_argument('--port')
    args = parser.parse_args()
    if args.backend == 'hardware' and not args.port:
        parser.error('--port is required with --backend hardware')
    args.capture_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication(['embedded-3d-qa'])
    errors = []
    def message(kind, context, text):
        if any(token in text for token in ('TypeError', 'ReferenceError', 'Binding loop', 'Unable to assign',
                                           'Cannot assign', 'Failed to load', 'not functional', 'Failed to create')):
            errors.append(text)
        print(text, file=sys.stderr)
    qInstallMessageHandler(message)
    controller = StudioController(arm_sim=args.backend == 'arm', start_timers=False)
    if args.port:
        index = next(i for i, port in enumerate(controller.state['ports']) if port['device'] == args.port)
        controller.selectPort(index)
    app, engine, controller = create_app(controller=controller, argv=['embedded-3d-qa'])
    window = engine.rootObjects()[0]
    report = dict(backend='ARM_SIM' if args.backend == 'arm' else 'STM32_UART', checks=[], screenshots=[])

    def pump(seconds=.1):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(.003)

    def wait(predicate, description, timeout=8):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            app.processEvents()
            if predicate():
                return
            time.sleep(.003)
        raise AssertionError(description + ': ' + controller.state['statusMessage'] + ' ' + str(controller.gameState))

    def check(condition, description):
        if not condition:
            raise AssertionError(description)
        report['checks'].append(description)
        print('PASS: ' + description, flush=True)

    def item(name):
        result = window.findChild(QObject, name)
        if result is None:
            raise AssertionError('Missing QML object: ' + name)
        return result

    def capture(name):
        pump(.12)
        path = args.capture_dir / (name + '.png')
        frame = window.grabWindow()
        check(not frame.isNull() and frame.save(str(path)), 'Real Studio window capture: ' + name)
        report['screenshots'].append(str(path))

    def idle():
        wait(lambda: controller._worker is None and not controller.state['busy'], 'Worker did not finish')

    def command(command):
        idle()
        controller._job('command', lambda: controller._device.runtime(command))
        idle()

    def heartbeat():
        idle()
        controller._heartbeat()
        wait(lambda: controller._active_operation != 'heartbeat', 'Panel read did not finish')
        pump(.03)

    def watch_action(action):
        idle()
        if args.backend == 'arm':
            def touch():
                check(controller._device.call('adas_game_touch', action) == 1,
                      'Actual ARM watch touch handler accepted action ' + str(action))
                return controller._device.runtime('J')
            controller._job('command', touch)
            idle()
        else:
            if action != 6:
                raise ValueError('Hardware configuration uses G protocol, touch injection is ARM-only')
            command('H:' + str(int(not controller.gameState['running'])))
        heartbeat()

    def start():
        activate_window(window)
        wait(window.isActive, 'Studio window did not become active')
        watch_action(6)
        wait(lambda: controller.gameState['running'] and controller.gameState['elapsed'] >= .1, 'Watch BASLAT did not start Studio')
        wait(lambda: item('driveViewport').property('activeFocus'), '3D view did not receive keyboard focus')

    def pause():
        QTest.keyClick(window, Qt.Key.Key_Space)
        idle()
        check(not controller.gameState['running'], 'Space pauses the worker and releases pedals')

    def configure(mode, acc=False):
        command(f'G:{mode}:{int(acc)}:3000:2200')
        heartbeat()
        check(controller.gameState['mode'] == ['active', 'warn', 'off'][mode], 'Watch mode is displayed in Studio: ' + str(mode))
        check(controller.gameState['targetKmh'] == 108 and controller.gameState['headwayMs'] == 2200,
              'Watch target and headway are read back without PC controls')
        controller._game_world = None

    try:
        activate_window(window)
        pump(.25)
        controller.connectDevice()
        idle()
        command('H:0')  # Clear a pre-existing watch request before controlled QA.
        heartbeat()
        check(controller.gameState['ready'] and controller.state['page'] == 'game', 'ADASLab v2 routes directly to the embedded 3D view')
        check(item('embeddedDriveScene').metaObject().className().startswith('QQuick3DViewport'), 'Scene is a real Qt Quick 3D View3D inside Studio')
        check(window.findChild(QObject, 'gameView') is None and window.findChild(QObject, 'scenarioSelector') is None,
              'Old 2D game and ADASLab experiment controls are absent')
        check(controller._game3d_process is None and controller._game3d_bridge is None, 'No external Godot window or TCP renderer is opened')
        check(len(app.topLevelWindows()) == 1, 'There is a single Studio application window')
        configure(0)
        capture('studio-3d-ready')
        viewport = item('driveViewport')
        start()
        check(controller.gameState['running'], 'Watch BASLAT starts the embedded game through panel polling')
        speed = controller.gameState['egoKmh']
        QTest.keyPress(window, Qt.Key.Key_W)
        pump(.7)
        check(controller.gameState['egoKmh'] > speed + 2, 'W accelerates through actual C firmware samples')
        QTest.keyPress(window, Qt.Key.Key_Up)
        QTest.keyRelease(window, Qt.Key.Key_W)
        speed = controller.gameState['egoKmh']
        pump(.4)
        check(controller.gameState['egoKmh'] > speed + 1, 'Up remains held independently after W release')
        QTest.keyRelease(window, Qt.Key.Key_Up)
        wait(lambda: controller.gameState['accelMps2'] < 0, 'Throttle did not release')
        speed = controller.gameState['egoKmh']
        QTest.keyPress(window, Qt.Key.Key_S)
        pump(.3)
        QTest.keyRelease(window, Qt.Key.Key_S)
        check(controller.gameState['egoKmh'] < speed - 1, 'S brakes through live QML input')
        QTest.keyClick(window, Qt.Key.Key_A)
        wait(lambda: controller.gameState['targetLane'] == 0, 'A did not steer left')
        QTest.keyPress(window, Qt.Key.Key_D)
        wait(lambda: controller.gameState['targetLane'] == 1, 'D did not steer right')
        for _ in range(6):
            app.sendEvent(window, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_D, Qt.KeyboardModifier.NoModifier, 'd', True, 1))
        pump(.2)
        check(controller.gameState['targetLane'] == 1, 'Auto-repeat does not create extra lane changes')
        QTest.keyRelease(window, Qt.Key.Key_D)
        check(item('driveViewport') is viewport and viewport.property('activeFocus'), 'Live telemetry preserves viewport identity and keyboard focus')
        old_camera = item('drive3DView').property('hoodCamera')
        QTest.keyClick(window, Qt.Key.Key_C)
        check(item('drive3DView').property('hoodCamera') != old_camera, 'C switches the 3D camera in the same window')
        QTest.keyClick(window, Qt.Key.Key_C)
        capture('studio-3d-driving')
        pause()
        start()
        QTest.keyPress(window, Qt.Key.Key_W)
        pump(.15)
        sink = QQuickItem(window.contentItem())
        sink.setSize(viewport.size())
        sink.forceActiveFocus(Qt.FocusReason.OtherFocusReason)
        idle()
        check(not controller.gameState['running'], 'Loss of keyboard focus pauses driving')
        QTest.keyRelease(window, Qt.Key.Key_W)
        start()
        wait(lambda: controller.gameState['accelMps2'] < 0, 'Gas leaked across pause')
        check(True, 'Watch resume has no stuck accelerator')
        pause()
        # Exercise the watch pause path while the worker owns the port. ARM's
        # touch is called between samples via the snapshot callback on its owner.
        start()
        if args.backend == 'arm':
            original = controller._game_runner.emit
            def pause_from_card(snapshot):
                original(snapshot)
                controller._device.call('adas_game_touch', 6)
                controller._game_runner.emit = original
            controller._game_runner.emit = pause_from_card
            idle()
            check(controller.gameState['status'] == 'paused', 'Actual watch pause touch stops the embedded game')
        else:
            # H cannot be sent concurrently with the serial worker; card pause
            # itself is covered by the compiled touch-handler test above.
            pause()
        for mode in (1, 2):
            configure(mode)
            start()
            pump(.3)
            check(not controller.gameState['aeb'], 'Warning/off mode cannot actuate AEB: ' + str(mode))
            if mode == 2:
                check(not controller.gameState['warning'], 'Off mode hides ADAS warnings')
            pause()
        configure(0, True)
        start()
        wait(lambda: controller.gameState['egoKmh'] > 52, 'ACC did not accelerate')
        check(controller.gameState['accelMps2'] > 0, 'ACC from the watch accelerates without a held gas key')
        pause()
        configure(0)
        start()
        QTest.keyPress(window, Qt.Key.Key_W)
        wait(lambda: controller.gameState['aeb'], 'C firmware did not engage AEB', 22)
        check(controller.gameState['accelMps2'] < -7, 'AEB overrides a held gas key with real MCU emergency braking')
        capture('studio-3d-aeb')
        QTest.keyRelease(window, Qt.Key.Key_W)
        pause()
        window.setWidth(1000)
        window.setHeight(720)
        pump(.2)
        start()
        check(viewport.property('activeFocus'), 'Minimum window size retains keyboard focus')
        for name in ('driveSpeed', 'watchMode', 'watchTarget', 'watchHeadway'):
            obj = item(name)
            point = obj.mapToScene(obj.boundingRect().topLeft())
            check(83 <= point.y() < window.height() - 38, 'Compact layout keeps control visible: ' + name)
        capture('studio-3d-compact')
        pause()
        check(not errors, 'No QML, model-loading, shader or binding errors: ' + str(errors))
        check(window.rendererInterface().graphicsApi().name != 'Software', '3D scene uses native GPU rendering')
        report.update(passed=True, graphics_api=window.rendererInterface().graphicsApi().name,
                      window_count=len(app.topLevelWindows()), external_game_process=False,
                      watch_test='actual ARM touch handler' if args.backend == 'arm' else 'hardware G/H protocol equivalent')
    finally:
        controller.releaseGameKeys()
        controller.pauseGame()
        idle()
        # Leave the board in its usual ready state with its previous default settings.
        command('G:0:0:2500:1800')
        controller.requestClose()
        window.hide()
        engine.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    (args.capture_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(passed=True, checks=len(report['checks']), backend=report['backend'])))


if __name__ == '__main__':
    main()
