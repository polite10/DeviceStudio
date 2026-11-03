"""Verify the embedded Qt Quick 3D scene with real keyboard events and C firmware.

Default: compiled ARM firmware, including the watch's actual touch handler.
--backend hardware --port PORT: existing board, G/H protocol equivalents of
watch actions. No Flash writes. Reports and window captures go to capture-dir.
Run with native Qt RHI (Metal on macOS); the software backend cannot render 3D.
"""
import argparse
import dataclasses
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QObject, QPoint, QPointF, QEvent, QSettings, Qt, qInstallMessageHandler
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
    # Known defaults for the remembered car and drawings; never the user's own.
    settings_dir = tempfile.TemporaryDirectory()
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, settings_dir.name)
    app = QApplication(['embedded-3d-qa'])
    errors = []
    def message(kind, context, text):
        if any(token in text for token in ('TypeError', 'ReferenceError', 'Binding loop', 'Unable to assign',
                                           'Cannot assign', 'Failed to load', 'not functional', 'Failed to create')):
            errors.append(text)
        print(text, file=sys.stderr)
    qInstallMessageHandler(message)
    controller = StudioController(arm_sim=args.backend == 'arm', start_timers=False)
    # A careless driver must not end these timed key checks at random.
    plain_config = controller._game_config
    controller._game_config = lambda: dataclasses.replace(plain_config(), surprises=False)
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
            raise AssertionError(description + ' [' + str(controller.gameState['status']) + ', lane ' + str(controller.gameState['egoLane']) + ']')
        report['checks'].append(description)
        print('PASS: ' + description, flush=True)

    def item(name):
        result = window.findChild(QObject, name)
        # Repeater delegates are only reachable through the visual tree.
        pending = [window.contentItem()]
        while result is None and pending:
            current = pending.pop()
            if current.objectName() == name:
                result = current
            pending.extend(current.childItems())
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
        QTest.keyClick(window, Qt.Key.Key_Escape)
        idle()
        check(not controller.gameState['running'], 'Esc pauses the worker and releases pedals')

    def click(name):
        control = item(name)
        check(control.property('visible'), 'Control is on screen: ' + name)
        point = control.mapToScene(QPointF(control.width() / 2, control.height() / 2))
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         QPoint(round(point.x()), round(point.y())))
        pump(.05)

    def watch_running():
        return controller._device.current['state']['grun']

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
        check(controller.gameState['ready'] and controller.state['page'] == 'game', 'ADASLab v3 routes directly to the embedded 3D view')
        check(item('embeddedDriveScene').metaObject().className().startswith('QQuick3DViewport'), 'Scene is a real Qt Quick 3D View3D inside Studio')
        check(window.findChild(QObject, 'gameView') is None and window.findChild(QObject, 'scenarioSelector') is None,
              'Old 2D game and ADASLab experiment controls are absent')
        check(controller._game3d_process is None and controller._game3d_bridge is None, 'No external Godot window or TCP renderer is opened')
        check(len(app.topLevelWindows()) == 1, 'There is a single Studio application window')
        configure(0)
        # The timed pedal checks need the Model 3's instant torque: the default
        # Şahin spends its first half second of throttle on a gear change.
        click('car_model3')
        check(controller.gameState['vehicle'] == 'model3', 'Car picker selects the Model 3')
        capture('studio-3d-ready')
        viewport = item('driveViewport')
        start()
        check(controller.gameState['running'], 'Watch BASLAT starts the embedded game through panel polling')
        speed = controller.gameState['egoKmh']
        clock = item('driveClock')
        frames = []
        def frame():
            kin = item('drive3DView').property('kin')
            frames.append((clock.property('frameTime'), kin.property('distance').toNumber()))
        clock.triggered.connect(frame)
        QTest.keyPress(window, Qt.Key.Key_W)
        pump(.7)
        check(controller.gameState['egoKmh'] > speed + 2, 'W accelerates through actual C firmware samples')
        pump(.8)
        clock.triggered.disconnect(frame)
        steps = [(b[1] - a[1], b[0]) for a, b in zip(frames, frames[1:]) if b[0] > 0]
        check(len(steps) > 30 and all(step >= -1e-6 for step, _ in steps), 'Rendered road distance never moves backwards between frames')
        speeds = [step / dt for step, dt in steps if dt < 0.05]
        changes = sorted(abs(b - a) for a, b in zip(speeds, speeds[1:]))
        report['motion'] = dict(frames=len(frames), frame_ms_p50=round(sorted(dt for _, dt in steps)[len(steps) // 2] * 1000, 2),
                                speed_change_p95_mps=round(changes[int(len(changes) * .95)], 3))
        check(report['motion']['speed_change_p95_mps'] < 1.0, 'Interpolated motion has no 20 Hz speed steps: ' + str(report['motion']))
        check(item('driveRadar') is not None, 'Sensor view is part of the driving HUD')
        wait(lambda: item('leadTarget').property('visible'), 'Lead vehicle bracket did not appear')
        check(True, 'Projected bracket marks the lead vehicle in the 3D scene')
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
        pump(.3)
        speed = controller.gameState['egoKmh']
        QTest.keyPress(window, Qt.Key.Key_Space)
        pump(.5)
        check(controller.gameState['running'] and controller.gameState['egoKmh'] < speed - 1, 'Space brakes and does not pause')
        QTest.keyRelease(window, Qt.Key.Key_Space)
        QTest.keyPress(window, Qt.Key.Key_W)
        wait(lambda: controller.gameState['egoKmh'] > 60, 'W did not reach lane keeping speed', 15)
        QTest.keyRelease(window, Qt.Key.Key_W)
        lane = controller.gameState['egoLane']
        QTest.keyPress(window, Qt.Key.Key_A)
        pump(.25)
        check(controller.gameState['wheel'] < -.2, 'A turns the steering wheel while it is held: ' + str(controller.gameState['wheel']))
        wait(lambda: controller.gameState['egoLane'] < lane - .03, 'A did not move the car left')
        QTest.keyRelease(window, Qt.Key.Key_A)
        pump(.6)
        check(abs(controller.gameState['wheel']) < .2, 'The wheel comes back when A is released')
        check(.5 < controller.gameState['egoLane'] < 1.5 and controller.gameState['egoSignal'] == 0, 'A tap does not change lanes or signal')
        QTest.keyClick(window, Qt.Key.Key_Q)
        wait(lambda: controller.gameState['egoSignal'] == -1, 'Q did not latch the left indicator')
        for _ in range(4):
            app.sendEvent(window, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Q, Qt.KeyboardModifier.NoModifier, 'q', True, 1))
        pump(.2)
        check(controller.gameState['egoSignal'] == -1, 'Auto-repeat does not toggle the indicator')
        QTest.keyClick(window, Qt.Key.Key_E)
        wait(lambda: controller.gameState['egoSignal'] == 1, 'E did not switch to the right indicator')
        QTest.keyClick(window, Qt.Key.Key_E)
        wait(lambda: controller.gameState['egoSignal'] == 0, 'E again did not cancel the indicator')
        check(item('driveViewport') is viewport and viewport.property('activeFocus'), 'Live telemetry preserves viewport identity and keyboard focus')
        def frame_ms(seconds=1.5):
            times = []
            def note():
                times.append(clock.property('frameTime'))
            clock.triggered.connect(note)
            pump(seconds)
            clock.triggered.disconnect(note)
            times = sorted(time for time in times if time > 0)
            return round(times[len(times) // 2] * 1000, 2)
        report['chase_frame_ms_p50'] = frame_ms()
        check(item('blindZoneLeft').property('visible') and item('blindZoneRight').property('visible'), 'Blind zones lie on the road in the follow camera')
        check(item('chaseSteering').property('visible') and not item('driveCockpit').property('visible'), 'The follow camera shows the small wheel and lamps, not the cockpit')
        capture('studio-3d-driving')
        old_camera = item('drive3DView').property('hoodCamera')
        QTest.keyClick(window, Qt.Key.Key_C)
        check(item('drive3DView').property('hoodCamera') != old_camera, 'C switches the 3D camera in the same window')
        pump(.2)
        check(item('driveCockpit').property('visible') and item('driveSteeringWheel').property('visible'), 'The pilot camera sits behind a steering wheel')
        check(item('mirrorLeftView').property('visible') and item('mirrorRightView').property('visible'), 'The pilot camera has two wing mirrors')
        check(not item('blindZoneLeft').property('visible'), 'Road zones give way to the mirrors in the pilot camera')
        report['pilot_frame_ms_p50'] = frame_ms()
        check(report['pilot_frame_ms_p50'] < 34, 'The mirrors leave a smooth frame rate: ' + str(report['pilot_frame_ms_p50']) + ' ms')
        QTest.keyPress(window, Qt.Key.Key_D)
        pump(.5)
        check(controller.gameState['wheel'] > .5, 'The pilot view wheel follows D')
        capture('studio-3d-pilot')
        QTest.keyRelease(window, Qt.Key.Key_D)
        QTest.keyClick(window, Qt.Key.Key_C)
        pump(.2)
        # The drawings in front of the car are chosen one by one, mid-drive.
        wait(lambda: item('leadTarget').property('visible') and item('followCorridor').property('visible'), 'Drawings are not showing')
        click('indicatorCorridor')
        pump(.1)
        check(not item('followCorridor').property('visible') and item('leadTarget').property('visible'), 'Corridor switch hides only the corridor')
        click('indicatorBracket')
        pump(.1)
        check(not item('leadTarget').property('visible'), 'Bracket switch hides the lead vehicle bracket')
        check(item('driveRadar').property('visible'), 'Sensor view has its own switch')
        click('indicatorSensors')
        pump(.1)
        check(not item('driveRadar').property('visible'), 'Sensor switch hides the sensor view')
        click('indicatorBlindSpot')
        pump(.1)
        check(not item('blindZoneLeft').property('visible') and not item('chaseSteering').property('visible'), 'Blind spot switch hides the road zones')
        check(viewport.property('activeFocus') and controller.gameState['running'], 'Switches neither take keyboard focus nor pause the drive')
        capture('studio-3d-drawings-off')
        pump(.6)  # Settings writes are delayed.
        check([QSettings().value('drive/' + key, type=bool) for key in ('corridor', 'bracket', 'sensors', 'blindSpot')] == [False] * 4,
              'Drawing choices are remembered across sessions')
        QTest.keyClick(window, Qt.Key.Key_V)
        pump(.1)
        check(item('followCorridor').property('visible') and item('leadTarget').property('visible'), 'V brings both road drawings back')
        QTest.keyClick(window, Qt.Key.Key_V)
        pump(.1)
        check(not item('followCorridor').property('visible') and not item('leadTarget').property('visible'), 'V hides both road drawings')
        for name in ('indicatorCorridor', 'indicatorBracket', 'indicatorBlindSpot', 'indicatorSensors'):
            click(name)
        pump(.1)
        wait(lambda: item('followCorridor').property('visible') and item('driveRadar').property('visible'), 'Switches did not turn the drawings back on')
        check(True, 'Switches turn the drawings back on')
        # Studio and watch each start and pause, and always agree.
        check(watch_running(), 'Watch shows the drive as running')
        click('drivePauseButton')
        idle()
        pump(.05)
        check(controller.gameState['status'] == 'paused' and not watch_running(), 'Studio DURAKLAT pauses Studio and the watch')
        elapsed = controller.gameState['elapsed']
        check(controller.state['statusMessage'] == '', 'Pause leaves no stale status message')
        check(item('driveStartButton').property('caption') == 'DEVAM ET', 'Start button offers to continue a paused drive')
        capture('studio-3d-paused')
        click('driveStartButton')
        # The watch hears H:1 only after the worker's RESET and V replies.
        wait(lambda: controller.gameState['running'] and controller.gameState['elapsed'] > elapsed and watch_running(), 'Studio BAŞLAT did not resume')
        check(True, 'Studio BAŞLAT resumes the same road and the watch follows')
        wait(lambda: viewport.property('activeFocus'), 'Studio BAŞLAT did not hand the keyboard to the road')
        check(True, 'Studio BAŞLAT hands the keyboard to the road')
        pause()
        check(not watch_running(), 'Esc pause shows on the watch')
        elapsed = controller.gameState['elapsed']
        start()
        check(controller.gameState['elapsed'] >= elapsed, 'Watch BAŞLAT resumes a drive paused in Studio')
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
            elapsed = controller.gameState['elapsed']
            click('driveStartButton')
            wait(lambda: controller.gameState['running'] and controller.gameState['elapsed'] > elapsed and watch_running(), 'Studio BAŞLAT did not resume after a watch pause')
            check(True, 'Studio BAŞLAT resumes a drive paused on the watch')
            pause()
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
        check(item('clusterAcc').property('lit'), 'Cluster ACC telltale is lit while the watch enables ACC')
        pause()
        configure(0)
        start()
        QTest.keyPress(window, Qt.Key.Key_W)
        wait(lambda: controller.gameState['aeb'], 'C firmware did not engage AEB', 22)
        # Brake pressure builds over 0.12 s after the firmware's request.
        wait(lambda: controller.gameState['accelMps2'] < -7, 'AEB did not brake against the held gas key', 2)
        check(True, 'AEB overrides a held gas key with real MCU emergency braking')
        check(item('clusterAeb').property('lit') and item('driveWarning').property('text') == 'AEB · ACİL FREN',
              'AEB telltale and banner follow the firmware emergency state')
        capture('studio-3d-aeb')
        QTest.keyRelease(window, Qt.Key.Key_W)
        pause()
        window.setWidth(1000)
        window.setHeight(720)
        pump(.2)
        start()
        check(viewport.property('activeFocus'), 'Minimum window size retains keyboard focus')
        for name in ('driveSpeed', 'watchMode', 'watchTarget', 'watchHeadway', 'drivePauseButton', 'indicatorSensors', 'indicatorBlindSpot'):
            obj = item(name)
            point = obj.mapToScene(obj.boundingRect().topLeft())
            check(83 <= point.y() < window.height() - 38, 'Compact layout keeps control visible: ' + name)
            check(point.x() + obj.width() <= window.width(), 'Compact layout keeps control inside the window: ' + name)
        capture('studio-3d-compact')
        pause()
        obj = item('driveStartButton')
        point = obj.mapToScene(obj.boundingRect().bottomRight())
        check(point.y() < item('driveViewport').mapToScene(QPointF(0, item('driveViewport').height())).y() and point.x() <= window.width(),
              'Compact layout keeps the start button inside the road view')
        capture('studio-3d-compact-paused')
        # Esc's restart leaves the paused road for the car picker, no crash needed.
        check(item('driveChooseCarButton').property('visible'), 'The pause menu offers a restart')
        capture('studio-3d-paused-menu')
        click('driveChooseCarButton')
        idle()
        wait(lambda: controller.gameState['status'] == 'ready', 'Restart did not leave the paused road')
        pump(.1)
        check(controller.gameState['elapsed'] == 0 and controller.gameState['distance'] == 0 and controller._game_world is None, 'Restart forgets the paused drive')
        check(item('carPicker').property('visible') and not item('driveChooseCarButton').property('visible'), 'Restart goes back to the car picker')
        capture('studio-3d-picker-after-restart')
        # The flying car adds two gauges: everything must still fit this window.
        click('car_roadster')
        ego, camera = item('egoVehicle3D'), item('driveCamera')
        click('driveStartButton')
        wait(lambda: controller.gameState['launching'], 'The flying car did not start with its ramp climb')
        pump(.3)
        check(ego.property('z') > -24 and controller.gameState['elapsed'] == 0, 'The car moves up its ramp while the plant waits')
        QTest.keyClick(window, Qt.Key.Key_Escape)
        idle()
        check(controller.gameState['status'] == 'ready' and not watch_running(), 'Esc on the ramp stops the launch, on the watch too')
        pump(.2)
        check(ego.property('z') == -24 and ego.property('y') == 0, 'The car goes back to wait before the ramp')
        launch, clock = [], item('driveClock')
        def launch_frame():
            kin = item('drive3DView').property('kin')
            position = camera.property('position')
            launch.append(dict(launching=controller.gameState['launching'], intro=kin.property('intro').toNumber(), car=(ego.property('y'), ego.property('z')),
                               altitude=ego.property('altitude'), camera=(position.x(), position.y(), position.z())))
        clock.triggered.connect(launch_frame)
        click('driveStartButton')
        wait(lambda: controller.gameState['running'] and controller.gameState['elapsed'] > 3.5, 'Studio BAŞLAT did not start the flying car', 12)
        clock.triggered.disconnect(launch_frame)
        climb = [frame for frame in launch if frame['launching']]
        check(climb and all(frame['camera'][0] > 15 for frame in climb), 'The climb is filmed from far off the road, never from inside the car')
        check(abs(climb[-1]['car'][0] - item('drive3DView').property('rampCeiling')) < .01 and abs(climb[-1]['car'][1]) < .01, 'The car stops on the ceiling before the release')
        falling = [frame for frame in launch if not frame['launching'] and frame['intro'] >= 0]
        check(falling and falling[0]['altitude'] > 7, 'The drop starts from the ceiling, after the climb')
        landed = next(frame for frame in launch[launch.index(falling[0]):] if frame['intro'] < 0)
        check(landed['altitude'] < .05 and abs(landed['camera'][0]) < .3 and abs(landed['camera'][1] - 3.3) < .3 and abs(landed['camera'][2] - 9.2) < .4,
              'The camera reaches the normal view exactly as the car lands: ' + str(landed))
        steps = [max(abs(a - b) for a, b in zip(one['camera'], two['camera'])) for one, two in zip(launch, launch[1:])]
        check(max(steps) < 1, 'The camera never jumps from the start to the landing: ' + str(round(max(steps), 3)))
        for name in ('airGauge', 'driveRadar', 'drivePauseButton', 'indicatorSensors'):
            obj = item(name)
            check(obj.mapToScene(QPointF(obj.width(), 0)).x() <= window.width(), 'Flying car still fits the narrowest window: ' + name)
        capture('studio-3d-compact-flying')
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
