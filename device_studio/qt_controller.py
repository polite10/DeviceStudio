"""Qt-facing application controller; UART/SWD work has one exclusive owner.

The transport, package validator and ADAS plant are independent of QML. Workers
publish plain values to queues; only the Qt thread changes properties. Closing
an active job requests cancellation and waits for the owner's cleanup.
"""
import csv
from collections import deque
from copy import deepcopy
import json
from pathlib import Path
import queue
import struct
import subprocess
import threading
import time

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer
from PySide6.QtWidgets import QFileDialog
import serial.tools.list_ports

from .connection import Device
from .protocol import Firmware, ProtocolError
from .adas_sim import Config, Runner, SCENARIOS
from .game_sim import GameConfig, GameRunner, DriverInput, MODES, MODE_NAMES
from . import programmer
from .godot_bridge import GodotBridge, find_godot

ROOT = Path(__file__).resolve().parents[1]
MODE_LABELS = {
    'WAITING': 'Ölçüm bekleniyor', 'ACC': 'Takip kontrolü',
    'AEB': 'Acil fren etkin', 'WARNING': 'Çarpışma uyarısı',
    'PAUSED': 'Duraklatıldı', 'NO_DATA': 'Veri kesildi',
    'MONITOR': 'Yalnız izleme',
}
SCENARIO_DESCRIPTIONS = {
    'brake': 'Öndeki araç üçüncü saniyede fren yapar. ACC ve acil fren tepkisini izleyin.',
    'follow': 'Daha yavaş araca yaklaşın. ACC hızınızı takip mesafesine göre ayarlar.',
    'cutin': 'Üçüncü saniyede önünüze bir araç girer. Mesafe ve risk değişimini izleyin.',
    'cruise': 'İki araç aynı hızla ilerler. Sabit takip ve bağlantıyı kontrol edin.',
    'dropout': 'Ölçüm akışı kısa süre kesilir. Kartın NO_DATA korumasını izleyin.',
}


def empty_telemetry():
    return dict(mode='WAITING', modeLabel='Bağlantı bekleniyor', egoKmh=0.,
                leadKmh=0., gapM=0., ttcSeconds=-1., accelMps2=0., simSeconds=0.,
                cycle=0, rttMs=0., overruns=0, computeUs=0, gpu=0, frames=0,
                frameMaxMs=0, fresh=False, present=False, collision=False)


class StudioController(QObject):
    stateChanged = Signal()
    liveChanged = Signal()
    portsChanged = Signal()
    gameChanged = Signal()
    shutdownReady = Signal()

    def __init__(self, parent=None, *, device_factory=None, programmer_api=None,
                 auto_adas=False, arm_sim=False, start_timers=True):
        super().__init__(parent)
        self._factory = device_factory or Device
        self._programmer = programmer_api or programmer
        self._auto_adas = auto_adas
        self._arm_sim = arm_sim
        self._device = None
        self._firmware = None
        self._runner = None
        self._worker = None
        self._active_operation = None
        self._deferred = deque()
        self._last_controls = None
        self._last_live = None
        self._last_game = None
        self._game_runner = None
        self._game_world = None
        self._game_inputs = DriverInput()
        self._window_active = True
        self._game3d_bridge = None
        self._game3d_active = False
        self._game3d_process = None
        self._game3d_phase = 'closed'
        self._game3d_executable = None
        self._game3d_log = None
        self._game3d_last_send = 0.
        self._game = dict(connected=False, ready=False, running=False, mode='active', accEnabled=False,
                          targetKmh=90, headwayMs=1800, seed=42, status='ready',
                          hint='ADASLab v2 firmware’ine bağlanın. WASD veya yön tuşlarıyla sürün.',
                          elapsed=0., remaining=120., distance=0., egoKmh=0., egoLane=1., targetLane=1,
                          accelMps2=0., ttc=-1., gap=-1., warning=False, aeb=False, traffic=[],
                          score=0, collisions=0, nearMisses=0, warnings=0, interventions=0,
                          reactionMs=-1, results=[], rttMs=0., overruns=0, devicePanel=False,
                          renderer3dAvailable=find_godot(ROOT) is not None,
                          renderer3dConnected=False, renderer3dMessage='3B sürüş penceresi kapalı')
        self._cancel = threading.Event()
        self._events = queue.Queue()
        self._snapshots = queue.Queue(maxsize=2)
        self._pending = None
        self._closing = False
        self._last_live_write = 0.
        self._write_live = start_timers
        self._state = dict(
            page='game', ports=[], portIndex=-1, connected=False, busy=False,
            running=False, operation='idle', cancellable=False, app='', appVersion='',
            bootText='Henüz kontrol edilmedi', connectionText='Bağlantı bekleniyor',
            backendLabel='ARM simülasyonu' if arm_sim else 'STM32 · USB / UART',
            firmwareName='', firmwarePath='', firmwareSummary='Bir .dfw paketi seçin',
            progress=0., progressText='Yüklemeye hazır', statusMessage='', statusTone='info',
            scenario='brake', scenarios=[dict(value=k, text=v, description=SCENARIO_DESCRIPTIONS[k])
                                          for k, v in SCENARIOS.items()],
            targetKmh=90, headwayMs=1800, accEnabled=True, aebEnabled=True,
            noiseEnabled=False, repeatEnabled=True, telemetry=empty_telemetry(),
            history=[], logs=[], appState='{}',
            duello=dict(gun='—', action='—', ammo=0, targetHp=0, walking=False),
            confirmation=dict(visible=False, title='', message='', action=''),
        )
        self._drain_timer = QTimer(self)
        self._drain_timer.setInterval(20)
        self._drain_timer.timeout.connect(self._drain)
        self._drain_timer.start()
        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(1200)
        self._heartbeat_timer.timeout.connect(self._heartbeat)
        if start_timers:
            self._heartbeat_timer.start()
        self.refreshPorts()

    @Property('QVariantMap', notify=stateChanged)
    def state(self):
        # QVariant conversion creates the QML value snapshot. Do not expose any
        # live device/model object or let workers mutate this map.
        return deepcopy(self._state)

    @Property('QVariantMap', notify=liveChanged)
    def liveState(self):
        return {key: deepcopy(self._state[key]) for key in ('telemetry', 'history', 'appState', 'duello')}

    @Property('QVariantMap', notify=gameChanged)
    def gameState(self):
        return deepcopy(self._game)

    @Property('QVariantList', notify=portsChanged)
    def ports(self):
        return deepcopy(self._state['ports'])

    @Property('QVariantList', constant=True)
    def scenarios(self):
        return deepcopy(self._state['scenarios'])

    def _publish(self):
        live = self.liveState
        controls = {key: value for key, value in self._state.items()
                    if key not in ('telemetry', 'history', 'appState', 'duello')}
        if controls != self._last_controls:
            self._last_controls = deepcopy(controls)
            self.stateChanged.emit()
        if live != self._last_live:
            self._last_live = live
            self.liveChanged.emit()
        if self._game != self._last_game:
            self._last_game = deepcopy(self._game)
            self.gameChanged.emit()

    def _defer_if_heartbeat(self, action):
        if self._active_operation == 'heartbeat' and not self._closing:
            if len(self._deferred) < 16:
                self._deferred.append(action)
            return True
        return False

    def _run_deferred(self):
        while self._deferred and self._worker is None and not self._closing:
            self._deferred.popleft()()

    def _log(self, message):
        stamp = time.strftime('%H:%M:%S')
        self._state['logs'] = (self._state['logs'] + [f'{stamp}  {message}'])[-250:]

    def _message(self, text, tone='info'):
        self._state.update(statusMessage=str(text), statusTone=tone)
        self._log(str(text))
        self._publish()

    def _idle(self):
        return self._worker is None and not self._state['busy'] and not self._closing and self._pending is None

    def _require_device(self, *, runtime=False):
        if not self._idle():
            return False
        if not self._device or not self._state['connected']:
            self._message('Önce cihaza bağlanın.', 'warning')
            return False
        if runtime and self._state['app'] == 'DeviceBoot':
            self._message('Kart bootloader modunda. Önce bir uygulama başlatın.', 'warning')
            return False
        return True

    def _job(self, operation, fn, success=None):
        if not self._idle():
            return False
        self._cancel.clear()
        def work():
            try:
                if self._cancel.is_set():
                    raise InterruptedError('İşlem başlamadan iptal edildi.')
                self._events.put(('done', fn(), success))
            except Exception as exc:
                self._events.put(('error', str(exc), None))

        self._worker = threading.Thread(target=work, name='studio-' + operation, daemon=True)
        self._active_operation = operation
        # Reserve ownership before notifying QML: synchronous signal handlers
        # may request close/another action while stateChanged is delivered.
        if operation != 'heartbeat':
            self._state.update(busy=True, operation=operation, running=operation in ('adas', 'game'),
                               cancellable=operation in ('adas', 'game', 'upload'))
        self._publish()
        self._worker.start()
        return True

    def _emit_snapshot(self, value):
        try:
            self._snapshots.put_nowait(value)
        except queue.Full:
            try:
                self._snapshots.get_nowait()
            except queue.Empty:
                pass
            try:
                self._snapshots.put_nowait(value)
            except queue.Full:
                pass

    @Slot()
    def _drain(self):
        self._poll_game_3d()
        changed = False
        latest = None
        while True:
            try:
                latest = self._snapshots.get_nowait()
            except queue.Empty:
                break
        if latest:
            if 'game' in latest:
                self._apply_game_snapshot(latest)
            else:
                self._apply_snapshot(latest)
            changed = True
        for _ in range(150):
            try:
                kind, value, callback = self._events.get_nowait()
            except queue.Empty:
                break
            changed = True
            if kind == 'progress':
                self._state.update(progress=float(value[0]), progressText=value[1])
            elif kind == 'log':
                self._log(value)
            else:
                operation = self._active_operation
                # The result is enqueued after fn's finally has released UART.
                self._worker = None
                self._active_operation = None
                if operation != 'heartbeat':
                    self._state.update(busy=False, running=False, operation='idle', cancellable=False)
                if operation == 'game':
                    self._game['running'] = False
                if kind == 'error':
                    cancelled = self._cancel.is_set() and operation == 'upload'
                    self._drop_device()
                    self._state.update(statusMessage=value,
                                       statusTone='warning' if cancelled else 'error')
                    self._log(('İşlem iptal edildi: ' if cancelled else 'Hata: ') + value)
                else:
                    if isinstance(value, dict) and value.get('app'):
                        self._apply_response(value)
                    if callback:
                        callback(value)
                    if operation in ('adas', 'game'):
                        # Runner sends PAUSE in its finally. Show that actual
                        # last response rather than its preceding live sample.
                        current = getattr(self._device, 'current', None)
                        if current and current.get('app'):
                            self._apply_response(current)
                if self._closing:
                    self._finish_close()
                else:
                    self._run_deferred()
        if changed:
            self._publish()

    def _apply_response(self, response, *, route=False):
        app = response.get('app', '')
        if not app:
            return
        self._state.update(connected=True, app=app, appVersion=str(response.get('version', '')),
                           connectionText='Bağlı', appState=json.dumps(response.get('state', {}), ensure_ascii=False, indent=2))
        self._game.update(connected=app == 'ADASLab', ready=app == 'ADASLab' and response.get('version', 0) >= 2)
        self._game['hint'] = ('W / ↑ gaz · S / ↓ fren · A–D / ← → şerit · Boşluk duraklat' if self._game['ready']
                              else 'Trafik oyunu için ADASLab v2 firmware’ini yükleyin.')
        if response.get('backend') == 'ARM_SIM':
            self._state['backendLabel'] = 'ARM simülasyonu · fiziksel kart kullanılmıyor'
        if app == 'DeviceBoot':
            self._state['bootText'] = f'DeviceBoot v{response.get("version", "?")} · çalışıyor'
            self._state['connectionText'] = 'Kurtarma / yükleme modu' if not response.get('valid') else 'Bootloader bağlı'
        else:
            self._state['bootText'] = (f'DeviceBoot v{response.get("boot_version", 1)} kurulu'
                                       if response.get('boot') == 1 else 'Tanınan bootloader bulunamadı')
        if app == 'ADASLab':
            s = response.get('state', {})
            t = dict(self._state['telemetry'])
            mode = s.get('mode', 'WAITING')
            t.update(mode=mode, modeLabel=MODE_LABELS.get(mode, mode),
                     egoKmh=float(s.get('ego', 0)) * .036, leadKmh=float(s.get('lead', 0)) * .036,
                     gapM=float(s.get('gap', 0)) / 100, ttcSeconds=float(s.get('ttc', -1)) / 1000 if s.get('ttc', -1) >= 0 else -1.,
                     accelMps2=float(s.get('a', 0)) / 100, simSeconds=float(s.get('ms', 0)) / 1000,
                     computeUs=int(s.get('us', 0)), gpu=int(s.get('gpu', 0)), frames=int(s.get('frames', 0)),
                     frameMaxMs=int(s.get('frame_max_ms', 0)), fresh=bool(s.get('fresh', False)),
                     present=mode != 'WAITING' and (self._state['scenario'] != 'cutin' or s.get('ms', 0) >= 3000))
            if t['collision']:
                t.update(mode='COLLISION', modeLabel='Çarpışma · deney sonlandı')
            self._state['telemetry'] = t
        elif app == 'Duello':
            s = response.get('state', {})
            self._state['duello'] = dict(gun=s.get('gun', '—'), action=s.get('action', '—'),
                                         ammo=s.get('ammo', 0), targetHp=s.get('target_hp', 0), walking=s.get('walking', False))
            if s.get('error'):
                self._state.update(statusMessage='Düello: ' + s['error'], statusTone='warning')
        if route:
            self._state['page'] = {'ADASLab': 'adas', 'Duello': 'duello', 'Smartwatch': 'firmware',
                                   'DeviceBoot': 'firmware'}.get(app, 'console')
            if app == 'ADASLab' and response.get('version', 0) >= 2:
                self._state['page'] = 'game'

    def _panel_response(self, response, *, allow_start=False):
        panel = response.get('state', {})
        if panel.get('error'):
            self._message('Kart paneli: ' + str(panel['error']), 'warning')
            return
        if 'gmode' not in panel:
            return
        self._game['devicePanel'] = True
        if not self._game['running']:
            self._game.update(mode=MODE_NAMES.get(panel['gmode'], 'active'), accEnabled=bool(panel.get('gacc')),
                              targetKmh=round(panel.get('gtarget', 2500) * .036), headwayMs=panel.get('gheadway', 1800))
        if allow_start and panel.get('grun') and self._driving_window_active() and not self._closing and self._state['page'] == 'game':
            QTimer.singleShot(0, self.startGame)

    def _apply_game_snapshot(self, snapshot):
        self._apply_response(snapshot['response'])
        self._game.update(snapshot['game'], status=snapshot['status'])
        self._game['running'] = self._active_operation == 'game'
        if self._write_live and time.monotonic() - self._last_live_write >= 1:
            self._last_live_write = time.monotonic()
            try:
                path = ROOT / 'build/game-live.json'
                path.parent.mkdir(exist_ok=True)
                path.write_text(json.dumps(dict(ui='QtQuick', backend='ARM_SIM' if self._arm_sim else 'STM32_UART',
                    game=self._game, firmware=snapshot['response']), ensure_ascii=False, indent=2) + '\n')
            except OSError:
                pass

    def _apply_snapshot(self, snapshot):
        self._apply_response(snapshot['response'])
        t = dict(self._state['telemetry'])
        t.update(simSeconds=float(snapshot['seconds']), cycle=snapshot['cycle'],
                 rttMs=round(snapshot['rtt_ms'], 2), overruns=snapshot['overruns'],
                 collision=bool(snapshot['collision']))
        if 'present' in snapshot:
            t['present'] = bool(snapshot['present'])
        if snapshot.get('data_pause'):
            t.update(mode='NO_DATA', modeLabel='Ölçüm akışı kesildi')
        if t['collision']:
            t.update(mode='COLLISION', modeLabel='Çarpışma · deney sonlandı')
        self._state['telemetry'] = t
        self._state['history'] = (self._state['history'] + [dict(gap=t['gapM'], ego=t['egoKmh'],
                                                               lead=t['leadKmh'], accel=t['accelMps2'])])[-200:]
        if self._write_live and time.monotonic() - self._last_live_write >= 1:
            self._last_live_write = time.monotonic()
            try:
                path = ROOT / 'build/adas-live.json'
                path.parent.mkdir(exist_ok=True)
                path.write_text(json.dumps(dict(ui='QtQuick', active=self._state['running'],
                    backend='ARM_SIM' if self._arm_sim else 'STM32_UART',
                    summary=f'{t["mode"]} · {t["simSeconds"]:.1f} s · tur {t["cycle"]}',
                    detail=f'RTT {t["rttMs"]:.1f} ms · GPU {t["gpu"]} · kare {t["frames"]}', sample=snapshot), ensure_ascii=False, indent=2) + '\n')
            except OSError:
                pass

    def _drop_device(self):
        if self._device:
            try:
                self._device.close()
            except Exception:
                pass
        self._device = None
        self._game_inputs.release()
        self._game.update(connected=False, ready=False, running=False, status='disconnected', warning=False, aeb=False)
        self._state.update(connected=False, app='', appVersion='', connectionText='Bağlantı yok',
                           appState='{}', telemetry=empty_telemetry(),
                           duello=dict(gun='—', action='—', ammo=0, targetHp=0, walking=False))

    @Slot(str)
    def navigate(self, page):
        if page != 'game' and self._game['running']:
            self.pauseGame()
        if page in ('game', 'adas', 'firmware', 'duello', 'console'):
            self._state['page'] = page
            self._publish()

    @Slot(int)
    def selectPort(self, index):
        if self._defer_if_heartbeat(lambda: self.selectPort(index)):
            return
        if self._idle() and not self._state['connected'] and 0 <= index < len(self._state['ports']):
            self._state['portIndex'] = index
            self._publish()

    @Slot()
    def refreshPorts(self):
        if self._defer_if_heartbeat(self.refreshPorts):
            return
        if not self._idle():
            return
        old = self._state['ports']
        selected = old[self._state['portIndex']]['device'] if 0 <= self._state['portIndex'] < len(old) else None
        ports = [dict(device=p.device, label=f'{p.device} · {p.description}')
                 for p in serial.tools.list_ports.comports()]
        index = next((i for i, p in enumerate(ports) if p['device'] == selected), -1)
        if index < 0:
            index = next((i for i, p in enumerate(ports) if 'STLINK' in p['label'].upper().replace('-', '')), 0 if ports else -1)
        self._state.update(ports=ports, portIndex=index)
        if old != ports:
            self.portsChanged.emit()
        self._publish()

    @Slot()
    def connectDevice(self):
        if self._defer_if_heartbeat(self.connectDevice):
            return
        if not self._idle():
            return
        index = self._state['portIndex']
        if not self._arm_sim and not 0 <= index < len(self._state['ports']):
            self._message('Seri port bulunamadı. USB bağlantısını kontrol edip Yenile’ye basın.', 'warning')
            return
        port = self._state['ports'][index]['device'] if index >= 0 else None

        def work():
            if self._device:
                self._device.close()
            if self._arm_sim:
                from .adas_arm import ArmDevice
                self._device = ArmDevice()
            else:
                self._device = self._factory(port)
            return self._device.detect()

        def connected(response):
            self._apply_response(response, route=True)
            self._state.update(statusMessage='Cihaz bağlantısı doğrulandı.', statusTone='success')
            self._log('Bağlandı: ' + response.get('app', 'cihaz'))
            if self._auto_adas and response.get('app') == 'ADASLab':
                QTimer.singleShot(200, self.startExperiment)

        self._state.update(connectionText='Cihaz aranıyor…', connected=False)
        self._job('connecting', work, connected)

    @Slot()
    def disconnectDevice(self):
        if self._defer_if_heartbeat(self.disconnectDevice):
            return
        if self._idle():
            self._drop_device()
            self._message('Bağlantı kesildi.')

    @Slot()
    def chooseFirmware(self):
        if self._defer_if_heartbeat(self.chooseFirmware):
            return
        if self._idle():
            path, _ = QFileDialog.getOpenFileName(None, 'Firmware paketi seç', str(ROOT / 'Firmware'), 'Device firmware (*.dfw)')
            if path:
                self.loadFirmware(path)

    @Slot(str)
    def loadFirmware(self, path):
        if self._defer_if_heartbeat(lambda: self.loadFirmware(path)):
            return
        if not self._idle():
            return
        self._firmware = None
        self._state.update(firmwareName='', firmwarePath='', firmwareSummary='Bir .dfw paketi seçin', progress=0.)
        try:
            self._firmware = Firmware.load(path)
            m = self._firmware.manifest
            self._state.update(firmwareName=m['name'], firmwarePath=str(path),
                               firmwareSummary=f'{m["name"]} v{m["version"]} · ID {m["id"]} · {m["size"]:,} bayt',
                               progressText='Paket doğrulandı · yüklemeye hazır', statusMessage='', statusTone='info')
            self._log('Paket doğrulandı: ' + Path(path).name)
        except Exception as exc:
            self._state.update(statusMessage=str(exc), statusTone='error', progressText='Paket doğrulanamadı')
            self._log('Paket hatası: ' + str(exc))
        self._publish()

    def _confirm(self, action, title, message, payload=None):
        self._pending = (action, payload)
        self._state['confirmation'] = dict(visible=True, title=title, message=message, action=action)
        self._publish()

    @Slot()
    def requestUpload(self):
        if self._defer_if_heartbeat(self.requestUpload):
            return
        if not self._require_device():
            return
        if self._arm_sim:
            self._message('Firmware yüklemek için fiziksel karta bağlanın.', 'warning')
            return
        if not self._firmware:
            self._message('Önce geçerli bir .dfw paketi seçin.', 'warning')
            return
        self._confirm('upload', 'Firmware yüklensin mi?',
                      f'{self._firmware.manifest["name"]} cihazdaki mevcut uygulamanın yerini alacak. Saat kayıtları korunacak.', self._firmware)

    @Slot()
    def requestInstallBootloader(self):
        if self._defer_if_heartbeat(self.requestInstallBootloader):
            return
        if not self._idle():
            return
        if self._arm_sim:
            self._message('Bootloader kurulumu için fiziksel kart gerekir.', 'warning')
            return
        path, _ = QFileDialog.getOpenFileName(None, 'DeviceBoot.bin seç', str(ROOT.parent / 'DeviceBoot/Firmware'), 'Bootloader (*.bin)')
        if path:
            self.loadBootloader(path)

    @Slot(str)
    def loadBootloader(self, path):
        if self._defer_if_heartbeat(lambda: self.loadBootloader(path)):
            return
        if not self._idle() or self._arm_sim:
            return
        try:
            data = Path(path).read_bytes()
            if not 0x7f20 <= len(data) <= 0x8000 or struct.unpack_from('<I', data, 0x7f00)[0] != 0x44425631:
                raise ProtocolError('Geçerli bir DeviceBoot binary’si seçin.')
            self._confirm('install', 'DeviceBoot kurulsun mu?',
                          'Önce tam 4 MiB Flash yedeği alınacak; ardından bootloader güncellenecek. Uyumlu uygulama yüklenene kadar kart kurtarma modunda kalabilir.', str(path))
        except Exception as exc:
            self._message(str(exc), 'error')

    @Slot(bool)
    def confirmAction(self, accepted):
        pending = self._pending
        self._pending = None
        self._state['confirmation'] = dict(visible=False, title='', message='', action='')
        self._publish()
        if not accepted or pending is None or not self._idle():
            return
        action, payload = pending
        if action == 'upload':
            if not self._require_device():
                return
            self._state.update(progress=0., progressText='Yükleme başlıyor…')
            def progress(percent, message):
                self._events.put(('progress', (percent, message), None))
            def done(response):
                self._apply_response(response, route=True)
                self._state.update(progress=100., progressText='Firmware doğrulandı · uygulama hazır',
                                   statusMessage='Firmware yüklendi ve uygulama başlatıldı.', statusTone='success')
                self._log('Firmware yüklendi: ' + response.get('app', ''))
            self._job('upload', lambda: self._device.upload(payload, progress, self._cancel), done)
        elif action == 'install':
            def work():
                if self._device:
                    self._device.close()
                    self._device = None
                return self._programmer.install(payload, ROOT / 'Backup',
                    log=lambda s: self._events.put(('log', s, None)))
            def done(result):
                self._drop_device()
                self._state.update(bootText=f'DeviceBoot v{result["version"]} kuruldu',
                                   statusMessage='Bootloader kuruldu. Bağlanıp uyumlu firmware yükleyin.', statusTone='success')
                self._log('Tam Flash yedeği: ' + result['backup'])
            self._job('install', work, done)

    @Slot()
    def inspectBootloader(self):
        if self._defer_if_heartbeat(self.inspectBootloader):
            return
        if not self._idle():
            return
        if self._arm_sim:
            self._message('ST-LINK kontrolü yalnız fiziksel kart için kullanılabilir.', 'warning')
            return
        def work():
            if self._device:
                self._device.close()
                self._device = None
            return self._programmer.inspect(log=lambda s: self._events.put(('log', s, None)))
        def done(result):
            self._drop_device()
            self._state['bootText'] = f'DeviceBoot v{result["version"]} Flash üzerinde bulundu' if result['installed'] else 'Tanınan DeviceBoot bulunamadı'
            self._state.update(statusMessage='ST-LINK kontrolü tamamlandı. Yeniden bağlanın; kart durmuşsa RESET ile başlatın.', statusTone='info')
        self._job('inspect', work, done)

    @Slot()
    def enterBootloader(self):
        if self._defer_if_heartbeat(self.enterBootloader):
            return
        if self._require_device():
            self._job('command', self._device.enter_boot, lambda r: self._apply_response(r, route=True))

    @Slot()
    def runApplication(self):
        if self._defer_if_heartbeat(self.runApplication):
            return
        if self._require_device():
            self._job('command', self._device.run, lambda r: self._apply_response(r, route=True))

    @Slot(str)
    def sendCommand(self, text):
        if self._defer_if_heartbeat(lambda: self.sendCommand(text)):
            return
        if not self._require_device(runtime=True):
            return
        text = text.strip()
        if not text or len(text) > 39 or any(ord(c) <= 32 or ord(c) > 126 for c in text):
            self._message('Komut boşluksuz 1–39 ASCII karakter içermeli.', 'warning')
            return
        if text == 'BOOT':
            self.enterBootloader()
        else:
            self._job('command', lambda: self._device.runtime(text), lambda r: self._log('Komut: ' + text))

    @Slot(str)
    def duelloCommand(self, command):
        if self._state['app'] == 'Duello' and command in ('DRAW', 'FIRE', 'HOLSTER', 'RELOAD', 'WALK', 'STOP', 'RESET'):
            self.sendCommand(command)

    @Slot(str, 'QVariant')
    def setOption(self, key, value):
        if self._defer_if_heartbeat(lambda: self.setOption(key, value)):
            return
        if not self._idle():
            return
        if hasattr(value, 'toVariant'):
            value = value.toVariant()
        try:
            if key == 'scenario':
                if value not in SCENARIOS:
                    raise ValueError('Geçerli bir senaryo seçin.')
            elif key in ('targetKmh', 'headwayMs'):
                if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
                    raise ValueError('Tam sayı girin.')
                value = int(value)
                lo, hi = (0, 200) if key == 'targetKmh' else (800, 4000)
                if not lo <= value <= hi:
                    raise ValueError(f'Değer {lo}–{hi} aralığında olmalı.')
            elif key in ('accEnabled', 'aebEnabled', 'noiseEnabled', 'repeatEnabled'):
                if not isinstance(value, bool):
                    raise ValueError('Açık veya kapalı seçin.')
            else:
                return
            self._state[key] = value
            self._publish()
        except (ValueError, TypeError) as exc:
            self._message(str(exc), 'warning')

    @Slot()
    def startExperiment(self):
        if self._defer_if_heartbeat(self.startExperiment):
            return
        if not self._require_device(runtime=True):
            return
        if self._state['app'] != 'ADASLab':
            self._message('Bu deney için ADASLab firmware’ini yükleyin.', 'warning')
            return
        config = Config(scenario=self._state['scenario'], target_kmh=self._state['targetKmh'],
                        headway_ms=self._state['headwayMs'], acc=self._state['accEnabled'],
                        aeb=self._state['aebEnabled'], noise=self._state['noiseEnabled'], repeat=self._state['repeatEnabled'])
        self._runner = Runner(self._device, config, self._cancel, self._emit_snapshot)
        self._state.update(history=[], telemetry=empty_telemetry(), statusMessage='', page='adas')
        def done(response):
            if self._state['telemetry']['collision']:
                self._state.update(statusMessage='Çarpışma oluştu. Deney sonlandırıldı; ayarları değiştirip yeniden deneyin.', statusTone='warning')
                self._log('ADASLab deneyi çarpışma nedeniyle sonlandırıldı.')
            else:
                self._state.update(statusMessage='Deney duraklatıldı. Ölçümleri CSV olarak kaydedebilirsiniz.', statusTone='info')
                self._log('ADASLab deneyi duraklatıldı.')
        self._job('adas', self._runner.run, done)

    @Slot()
    def stopOperation(self):
        if self._state['cancellable']:
            self._cancel.set()
            self._state.update(statusMessage='İşlem güvenli biçimde durduruluyor…', statusTone='info', cancellable=False)
            self._publish()

    @Slot()
    def exportCsv(self):
        if self._defer_if_heartbeat(self.exportCsv):
            return
        if not self._idle():
            return
        if not self._runner or not self._runner.rows:
            self._message('Kaydetmek için önce bir deney çalıştırın.')
            return
        path, _ = QFileDialog.getSaveFileName(None, 'ADASLab ölçümleri', str(ROOT / 'ADASLab.csv'), 'CSV (*.csv)')
        if not path:
            return
        try:
            rows = list(self._runner.rows)
            with open(path, 'w', newline='', encoding='utf-8') as target:
                writer = csv.DictWriter(target, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            self._message('Ölçümler kaydedildi: ' + Path(path).name, 'success')
        except OSError as exc:
            self._message(str(exc), 'error')

    @Slot()
    def clearLogs(self):
        self._state['logs'] = []
        self._publish()

    @Slot()
    def _heartbeat(self):
        if self._idle() and self._state['connected'] and self._state['app'] != 'DeviceBoot':
            panel = self._state['page'] == 'game' and self._game['ready']
            self._job('heartbeat', lambda: self._device.runtime('J' if panel else 'STATUS'),
                      (lambda r: self._panel_response(r, allow_start=True)) if panel else None)

    def _game_config(self):
        return GameConfig(mode=self._game['mode'], acc=self._game['accEnabled'], target_kmh=self._game['targetKmh'],
                          headway_ms=self._game['headwayMs'], seed=self._game['seed'])

    @Slot(str, 'QVariant')
    def setGameOption(self, key, value):
        if self._defer_if_heartbeat(lambda: self.setGameOption(key, value)):
            return
        if not self._idle() or self._game['running']:
            return
        if hasattr(value, 'toVariant'):
            value = value.toVariant()
        try:
            if key == 'mode' and value in MODES:
                pass
            elif key == 'accEnabled' and isinstance(value, bool):
                pass
            elif key in ('targetKmh', 'headwayMs', 'seed') and type(value) in (int, float) and int(value) == value:
                low, high = {'targetKmh': (0, 200), 'headwayMs': (800, 4000), 'seed': (1, 999999)}[key]
                if not low <= value <= high:
                    raise ValueError('Oyun ayarı izin verilen sınırların dışında.')
                value = int(value)
            else:
                raise ValueError('Geçersiz oyun ayarı.')
            if self._game[key] != value:
                self._game[key] = value
                self._game_world = None
                self._game['status'] = 'ready'
            self._publish()
            if self._state['connected'] and self._game['ready']:
                command = self._game_config().command()
                self._job('heartbeat', lambda: self._device.runtime(command), self._panel_response)
        except (ValueError, TypeError) as exc:
            self._message(str(exc), 'warning')

    @Slot()
    def startGame(self):
        # Recheck when a queued click/card request is finally executed: focus
        # or page may have changed while the heartbeat owned the UART.
        if not self._driving_window_active() or self._state['page'] != 'game' or self._closing:
            return
        if self._defer_if_heartbeat(self.startGame):
            return
        if not self._require_device(runtime=True):
            return
        if not self._game['ready']:
            self._message('Oyun için ADASLab v2 firmware’ini yükleyin.', 'warning')
            return
        config = self._game_config()
        if self._game_world and (self._game_world.finished or self._game_world.config != config):
            self._game_world = None
        self._game_inputs.release()
        self._game_runner = GameRunner(self._device, config, self._game_inputs, self._cancel, self._emit_snapshot, self._game_world)
        self._game_world = self._game_runner.world
        self._game.update(self._game_world.snapshot({}), running=True, status='running')
        self._state.update(page='game', statusMessage='')
        def done(response):
            world = self._game_world
            self._game.update(running=False, warning=False, aeb=False,
                              status='collision' if world.collision else 'finished' if world.finished else 'paused')
            if world.finished:
                result = dict(mode=config.mode, seed=config.seed, distance=round(world.distance), score=world.score,
                              collisions=int(world.collision), nearMisses=len(world.near_misses), interventions=world.interventions)
                self._game['results'] = (self._game['results'] + [result])[-9:]
            self._log('Trafik oyunu: ' + self._game['status'])
        self._job('game', self._game_runner.run, done)

    @Slot()
    def pauseGame(self):
        self._game_inputs.release()
        if self._active_operation == 'game':
            self.stopOperation()

    @Slot()
    def restartGame(self):
        if self._defer_if_heartbeat(self.restartGame):
            return
        if self._idle():
            self._game_world = None
            self.startGame()

    @Slot(str, bool, bool)
    def gameKey(self, key, pressed, auto_repeat=False):
        if self._game['running'] and self._state['page'] == 'game':
            self._game_inputs.key(key, pressed, auto_repeat)

    @Slot()
    def releaseGameKeys(self):
        self._game_inputs.release()

    @Slot()
    def focusLost(self):
        # The external renderer owns driving focus while its authenticated
        # heartbeat is fresh. Qt becoming inactive must not pause that window.
        if not self._external_driving_active():
            self.releaseGameKeys()
            self.pauseGame()

    @Slot(bool)
    def setWindowActive(self, active):
        self._window_active = active
        if not active:
            self.focusLost()

    def _external_driving_active(self):
        bridge = self._game3d_bridge
        return bool(bridge and bridge.connected and self._game3d_active and
                    time.monotonic() - bridge._heartbeat_at <= bridge.heartbeat_timeout)

    def _driving_window_active(self):
        return self._window_active or self._external_driving_active()

    @Slot()
    def openStandaloneGame(self):
        if self._defer_if_heartbeat(self.openStandaloneGame):
            return
        if not self._idle():
            self._message('Önce mevcut işlemi duraklatın.', 'info')
            return
        from .standalone import launch
        try:
            self.closeGame3D()
            self._drop_device()
            launch()
            self._message('ADASLab Drive bağımsız açıldı; USB bağlantısı oyuna bırakıldı.', 'info')
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            self._message(str(exc), 'error')

    @Slot()
    def openGame3D(self):
        if self._closing:
            return
        if self._game3d_process is not None and self._game3d_process.poll() is None:
            self._message('3B sürüş penceresi zaten açık.', 'info')
            return
        self.closeGame3D()
        executable = find_godot(ROOT)
        project = ROOT / 'godot/adas_drive/project.godot'
        self._game['renderer3dAvailable'] = executable is not None
        if executable is None:
            self._game['renderer3dMessage'] = 'Godot bulunamadı; GODOT_BIN yolunu ayarlayın.'
            self._message(self._game['renderer3dMessage'], 'warning')
            return
        if not project.is_file():
            self._game['renderer3dMessage'] = 'Godot sürüş projesi bulunamadı.'
            self._message(self._game['renderer3dMessage'], 'error')
            return
        self.pauseGame()
        try:
            self._game3d_bridge = GodotBridge()
            (ROOT / 'build').mkdir(exist_ok=True)
            self._game3d_log = (ROOT / 'build/godot-drive.log').open('ab')
            self._game3d_executable = executable
            self._game3d_phase = 'importing'
            # A cold clone contains GLB/FBX source assets, not .godot cache.
            # Import asynchronously; never occupy the serial worker or GUI.
            self._game3d_process = subprocess.Popen(
                [str(executable), '--headless', '--editor', '--path', str(project.parent), '--import', '--quit'],
                cwd=ROOT, stdout=self._game3d_log, stderr=subprocess.STDOUT)
            self._game['renderer3dMessage'] = '3B modeller hazırlanıyor…'
            self._state['page'] = 'game'
            self._publish()
        except (OSError, ValueError) as exc:
            self.closeGame3D()
            self._message('3B sürüş açılamadı: ' + str(exc), 'error')

    def _launch_game3d_runtime(self):
        bridge = self._game3d_bridge
        self._game3d_process = subprocess.Popen(
            [str(self._game3d_executable), '--path', str(ROOT / 'godot/adas_drive'), '--',
             '--bridge-port', str(bridge.port), '--bridge-token', bridge.token],
            cwd=ROOT, stdout=self._game3d_log, stderr=subprocess.STDOUT)
        self._game3d_phase = 'running'
        self._game['renderer3dMessage'] = '3B sürüş penceresi açılıyor…'
        self._publish()

    @Slot()
    def closeGame3D(self):
        if self._game3d_bridge is not None:
            self.pauseGame()
            self._game3d_bridge.close()
            self._game3d_bridge = None
        process, self._game3d_process = self._game3d_process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=.2)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=.2)
                except subprocess.TimeoutExpired:
                    pass
        self._game3d_phase = 'closed'
        self._game3d_executable = None
        if self._game3d_log is not None:
            self._game3d_log.close()
            self._game3d_log = None
        self._game3d_active = False
        self._game['renderer3dConnected'] = False
        self._game['renderer3dMessage'] = '3B sürüş penceresi kapalı'
        self._publish()

    def _start_game3d_request(self, restart=False):
        # Preserve the source of a deferred renderer request: switching back
        # to an active Studio window must not revive an old Godot START.
        if not self._external_driving_active() or self._closing or self._state['page'] != 'game':
            return
        if self._defer_if_heartbeat(lambda: self._start_game3d_request(restart)):
            return
        if restart:
            self.restartGame()
        else:
            self.startGame()

    def _poll_game_3d(self):
        bridge = self._game3d_bridge
        if bridge is None:
            return
        process = self._game3d_process
        if process is not None and process.poll() is not None:
            if self._game3d_phase == 'importing' and process.returncode == 0:
                try:
                    self._launch_game3d_runtime()
                except OSError as exc:
                    self.closeGame3D()
                    self._message('3B sürüş açılamadı: ' + str(exc), 'error')
            else:
                importing = self._game3d_phase == 'importing'
                self.closeGame3D()
                self._message('3B modeller hazırlanamadı; build/godot-drive.log dosyasını kontrol edin.' if importing
                              else '3B sürüş penceresi kapandı; sürüş duraklatıldı.', 'error' if importing else 'info')
            return
        changed = False
        for message in bridge.poll():
            kind = message['type']
            if kind == 'connected':
                self._game3d_active = False
                self._game.update(renderer3dConnected=True, renderer3dMessage='3B sürüş bağlı')
                changed = True
            elif kind == 'disconnected':
                self._game3d_active = False
                self.pauseGame()
                self._game.update(renderer3dConnected=False, renderer3dMessage='3B bağlantısı kesildi; sürüş duraklatıldı.')
                changed = True
            elif kind == 'heartbeat' or (kind == 'action' and message.get('name') == 'focus'):
                self._game3d_active = message['active']
                if not message['active']:
                    # Release even if Qt has just gained focus. A held Godot
                    # pedal must never migrate to the Qt driving viewport.
                    self.releaseGameKeys()
                    self.pauseGame()
            elif kind == 'input':
                if self._external_driving_active():
                    self.gameKey(message['key'], message['pressed'], message.get('repeat', False))
            elif kind == 'action':
                action = message['name']
                if action == 'pause':
                    self.pauseGame()
                elif self._external_driving_active():
                    if action == 'start':
                        self._start_game3d_request()
                    elif action == 'restart':
                        self._start_game3d_request(restart=True)
            elif kind == 'setting':
                self.setGameOption(message['key'], message['value'])
        now = time.monotonic()
        if bridge.connected and now - self._game3d_last_send >= .05:
            self._game3d_last_send = now
            bridge.send_state(self.gameState, connected=self._state['connected'],
                              backend='ARM_SIM' if self._arm_sim else 'STM32_UART')
        if changed:
            self._publish()

    @Slot(result=bool)
    def requestClose(self):
        self._closing = True
        self._deferred.clear()
        self._pending = None
        self._heartbeat_timer.stop()
        self.closeGame3D()
        if self._worker is not None:
            self._cancel.set()
            self._state.update(statusMessage='İşlem tamamlanınca pencere kapanacak…', statusTone='info', cancellable=False)
            self._publish()
            return False
        self._drop_device()
        self._drain_timer.stop()
        return True

    def _finish_close(self):
        self._drop_device()
        self._drain_timer.stop()
        self.shutdownReady.emit()

    @Slot()
    def shutdown(self):
        self._heartbeat_timer.stop()
        self.closeGame3D()
        self._cancel.set()
        if self._worker is None:
            self._drop_device()
            self._drain_timer.stop()
