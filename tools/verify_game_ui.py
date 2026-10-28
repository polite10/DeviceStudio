"""Exercise real QML mouse/keyboard controls against the compiled ARM firmware.

Defaults to ARM simulation. --backend hardware --port PORT uses an already
installed v2 board. Neither backend writes Flash. Use QT_QPA_PLATFORM=offscreen
QT_QUICK_BACKEND=software for headless QA.
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
from PySide6.QtQuick import QQuickWindow, QQuickItem
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from device_studio.qt_app import create_app
from device_studio.qt_controller import StudioController


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-dir', type=Path, default=ROOT / 'build/game-ui-qa')
    parser.add_argument('--backend', choices=('arm','hardware'), default='arm')
    parser.add_argument('--port', help='Physical VCP port; required with --backend hardware')
    args = parser.parse_args()
    if args.backend == 'hardware' and not args.port:
        parser.error('--port is required with --backend hardware')
    args.capture_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(['game-ui-qa'])
    messages = []

    def qt_message(kind, context, text):
        if any(token in text for token in ('TypeError', 'ReferenceError', 'Binding loop',
                                           'Unable to assign', 'Cannot assign', 'does not support customization')):
            messages.append(text)
        elif 'Populating font family aliases' not in text:
            print(text, file=sys.stderr)

    qInstallMessageHandler(qt_message)
    controller = StudioController(arm_sim=args.backend == 'arm', start_timers=False)
    if args.port and args.backend == 'hardware':
        index = next((i for i, port in enumerate(controller.state['ports']) if port['device'] == args.port), None)
        if index is None:
            raise RuntimeError('Requested physical port was not found: ' + args.port)
        controller.selectPort(index)
    app, engine, controller = create_app(controller=controller, argv=['game-ui-qa'])
    window = engine.rootObjects()[0]
    report = dict(backend='ARM_SIM' if args.backend == 'arm' else 'STM32_UART', checks=[], screenshots=[])

    def pump(seconds=.08):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.004)

    def wait(predicate, description, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return
            time.sleep(.004)
        raise AssertionError(description + ': ' + str(controller.gameState) + '\n' + controller.state['statusMessage'] + ' active=' + str(window.isActive()) + ' operation=' + str(controller._active_operation))

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

    def click(name):
        target = item(name)
        check(target.property('enabled') and target.property('visible'), 'Interactive control available: ' + name)
        point = target.mapToScene(target.boundingRect().center())
        check(0 <= point.x() < window.width() and 0 <= point.y() < window.height(), 'Mouse target in window: ' + name)
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         QPoint(round(point.x()), round(point.y())))
        pump(.06)

    def capture(name):
        pump(.08)
        path = args.capture_dir / (name + '.png')
        image = window.grabWindow()
        check(not image.isNull() and image.save(str(path)), 'Rendered QML scene: ' + name)
        report['screenshots'].append(str(path))

    def start():
        window.raise_()
        window.requestActivate()
        wait(lambda: window.isActive(), 'QA window could not gain foreground focus')
        click('gameStartButton')
        wait(lambda: controller.gameState['running'] and controller.gameState['elapsed'] > .1,
             'Game did not start')
        wait(lambda: item('gameViewport').property('activeFocus'), 'Driving viewport did not receive keyboard focus')

    def pause_with_space():
        QTest.keyClick(window, Qt.Key.Key_Space)
        wait(lambda: not controller.state['busy'], 'Space did not finish game pause')
        check(not controller.gameState['running'] and controller.gameState['status'] == 'paused',
              'Space pauses the actual game worker and C firmware')

    try:
        window.requestActivate()
        pump(.2)
        controller.connectDevice()
        wait(lambda: not controller.state['busy'], 'ARM connection did not complete')
        check(controller.state['app'] == 'ADASLab' and controller.gameState['ready'],
              'Compiled ADASLab v2 is connected and game-ready')
        controller.navigate('game')
        pump(.1)
        capture('game-ready')

        # Every mode change is a real mouse interaction with a stable QML button.
        for mode, object_name in [('warn', 'gameModeWarn'), ('off', 'gameModeOff'), ('active', 'gameModeActive')]:
            click(object_name)
            wait(lambda: controller.gameState['mode'] == mode, 'Mode selection did not reach controller')
            pump(.08)  # Let the short ARM configuration transaction finish.
            check(controller.gameState['mode'] == mode, 'Mouse selects mode: ' + mode)
        seed = controller.gameState['seed']
        controller.setGameOption('accEnabled', False)
        pump(.08)
        start()
        viewport = item('gameViewport')
        initial_speed = controller.gameState['egoKmh']
        QTest.keyPress(window, Qt.Key.Key_W)
        pump(.7)
        check(controller.gameState['egoKmh'] > initial_speed + 2,
              'Holding W accelerates the car through live QML input')
        QTest.keyPress(window, Qt.Key.Key_Up)
        QTest.keyRelease(window, Qt.Key.Key_W)
        speed_after_w_release = controller.gameState['egoKmh']
        pump(.4)
        check(controller.gameState['egoKmh'] > speed_after_w_release + 1,
              'Releasing W retains gas while Up is independently held')
        QTest.keyRelease(window, Qt.Key.Key_Up)
        wait(lambda: controller.gameState['accelMps2'] < 0, 'Gas remained stuck after both aliases released')
        check(True, 'Releasing both gas aliases returns to coasting')

        QTest.keyPress(window, Qt.Key.Key_A)
        QTest.keyRelease(window, Qt.Key.Key_A)
        wait(lambda: controller.gameState['targetLane'] == 0, 'A did not request left lane')
        QTest.keyPress(window, Qt.Key.Key_D)
        wait(lambda: controller.gameState['targetLane'] == 1, 'D did not request right lane')
        for _ in range(6):
            app.sendEvent(window, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_D,
                                           Qt.KeyboardModifier.NoModifier, 'd', True, 1))
        pump(.15)
        check(controller.gameState['targetLane'] == 1, 'Keyboard auto-repeat cannot trigger an extra lane change')
        QTest.keyRelease(window, Qt.Key.Key_D)
        check(viewport is item('gameViewport') and viewport.property('activeFocus'),
              'Telemetry updates preserve the same viewport and keyboard focus')
        capture('game-running')
        pause_with_space()

        # Focus loss must clear an intentionally held key before a resume.
        start()
        QTest.keyPress(window, Qt.Key.Key_W)
        pump(.2)
        # Focusing an ancestor retains its nested focus scope's current child;
        # a sibling is required to produce a genuine active-focus loss.
        focus_sink = QQuickItem(window.contentItem())
        focus_sink.setObjectName('qaFocusSink')
        focus_sink.setWidth(1)
        focus_sink.setHeight(1)
        focus_sink.forceActiveFocus(Qt.FocusReason.OtherFocusReason)
        check(not viewport.property('activeFocus'), 'A sibling focus target removes driving focus')
        wait(lambda: not controller.state['busy'], 'Focus loss did not finish pause')
        check(not controller.gameState['running'], 'Focus loss pauses instead of leaving an unattended car')
        QTest.keyRelease(window, Qt.Key.Key_W)
        start()
        wait(lambda: controller.gameState['accelMps2'] < 0, 'A held gas key leaked across focus-loss pause')
        check(True, 'Resuming after focus loss has no stuck throttle')
        pause_with_space()

        # Repeatable seed and road reset; the original paused run had advanced.
        old_elapsed = controller.gameState['elapsed']
        controller.restartGame()
        wait(lambda: controller.gameState['running'] and .05 <= controller.gameState['elapsed'] < old_elapsed,
             'Restart did not reset the traffic timeline')
        check(controller.gameState['seed'] == seed and {c['id'] for c in controller.gameState['traffic']} == {1, 2, 3, 4},
              'Restart preserves the selected seed and replays initial traffic identities')
        wait(lambda: item('gameViewport').property('activeFocus'), 'Restart focus did not settle')
        pause_with_space()

        # Warn/off are playable and never enable an actuator intervention.
        for mode, object_name in [('warn', 'gameModeWarn'), ('off', 'gameModeOff')]:
            click(object_name)
            wait(lambda: controller.gameState['mode'] == mode, 'Support mode did not settle')
            pump(.08)
            start()
            pump(.25)
            check(not controller.gameState['aeb'], mode + ' mode does not apply AEB')
            if mode == 'off':
                check(not controller.gameState['warning'], 'Off mode hides ADAS warnings')
            pause_with_space()

        window.setWidth(1000)
        window.setHeight(720)
        pump(.12)
        capture('game-compact')
        click('gameModeActive')
        pump(.08)
        start()
        check(item('gameViewport').property('activeFocus'), 'Compact layout retains driving focus')
        player = item('gamePlayerCar')
        check(player.y() >= 0 and player.y() + player.height() <= item('gameViewport').height(),
              'Compact player vehicle is fully visible inside the road')
        for name in ('gameSpeedReadout', 'gameGapReadout', 'gameTtcReadout',
                     'gameAccelReadout', 'gameScoreReadout'):
            readout = item(name)
            top_left = readout.mapToScene(readout.boundingRect().topLeft())
            check(top_left.y() >= 83 and top_left.y() + readout.height() <= window.height() - 38,
                  'Compact HUD remains above application footer: ' + name)
        capture('game-compact-running')
        pause_with_space()
        check(not messages, 'No QML runtime errors during mouse, keyboard and telemetry updates')
        report.update(passed=True, graphics_api=window.rendererInterface().graphicsApi().name,
                      elapsed=controller.gameState['elapsed'], mode=controller.gameState['mode'])
    finally:
        controller.releaseGameKeys()
        controller.pauseGame()
        wait(lambda: not controller.state['busy'], 'Worker cleanup timed out', 15)
        controller.requestClose()
        window.hide()
        engine.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    (args.capture_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(passed=True, checks=len(report['checks']), backend=report['backend'])))


if __name__ == '__main__':
    main()
