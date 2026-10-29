pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtQuick3D
import QtQuick3D.Helpers
import QtMultimedia

FocusScope {
    id: drive
    objectName: "drive3DView"
    required property var studio
    property var game: studio ? studio.gameState : ({})
    readonly property bool playing: Boolean(game.running)
    readonly property bool available: Boolean(game.connected && game.ready)
    readonly property bool emergency: Boolean(game.aeb)
    readonly property bool warning: Boolean(game.warning)
    readonly property string mode: String(game.mode || "active")
    readonly property bool finished: game.status === "finished" || game.status === "collision"
    readonly property color signalColor: emergency ? "#ff5a68" : warning ? "#ffc35c" : "#63dec2"
    // The firmware caps TTC at 60 s; anything at the cap is not a closing hazard.
    readonly property bool closingTtc: Number(game.ttc) >= 0 && Number(game.ttc) < 59.9
    property bool hoodCamera: false
    property bool overlays: true
    property bool soundOn: true
    // Per-frame updates run while driving, briefly after any change, and for
    // the showroom orbit only while Studio is the active application.
    readonly property bool showroom: !playing && game.status !== "paused" && !hoodCamera
    property bool settling: true
    function settle() { drive.settling = true; settleTimer.restart() }
    implicitHeight: 625
    implicitWidth: 1000

    // Render-side kinematics. The firmware acknowledges one 50 ms plant step
    // per sample (~20 Hz). Samples are buffered by simulation time and each
    // display frame is drawn slightly behind the newest one, interpolating
    // (Hermite, with the sampled speeds) between the two that bracket it, so
    // serial jitter never shows up as a speed change.
    readonly property real renderDelay: 0.1
    property var kin: ({
        clock: 0, renderT: 0, leadAverage: 0.1, buffer: [], target: 1,
        distance: 0, speed: 0, accel: 0, lane: 1, x: 0, lateral: 0, latAccel: 0, yaw: 0,
        pitch: 0, pitchRate: 0, roll: 0, rollRate: 0, signalSide: 0, signalUntil: 0,
        camX: 0, camBack: 9.2, orbit: 0, idle: 0, shake: 0, blink: false, lastBlink: false, lead: -1, slots: []
    })
    readonly property var paints: [["#e8eaeb", 0.15], ["#f3f2ee", 0.05], ["#b4b9bd", 0.8], ["#6b7178", 0.7], ["#202326", 0.55],
        ["#1d3352", 0.65], ["#8e1c22", 0.6], ["#2d4b3e", 0.55], ["#c9bfa6", 0.35], ["#4a5560", 0.7], ["#5c1a26", 0.6], ["#d8dadb", 0.2]]

    function number(value, digits) { return Number(value || 0).toFixed(digits) }
    function clamp(value, low, high) { return Math.max(low, Math.min(high, value)) }
    function focusDriving() { if (playing && visible) viewport.forceActiveFocus() }
    function keyName(key) {
        return ({[Qt.Key_W]:"w", [Qt.Key_Up]:"up", [Qt.Key_S]:"s", [Qt.Key_Down]:"down",
                 [Qt.Key_A]:"a", [Qt.Key_Left]:"left", [Qt.Key_D]:"d", [Qt.Key_Right]:"right"})[key] || ""
    }
    function look(id) {
        const hash = Math.imul(id + 1, 2654435761) >>> 0
        const pick = hash % 100
        const variant = pick < 40 ? 0 : pick < 66 ? 1 : pick < 78 ? 3 : pick < 89 ? 2 : 4
        const paint = variant === 3 ? ["#f2c12e", 0.25] : drive.paints[(hash >>> 8) % drive.paints.length]
        return {variant: variant, paint: paint[0], metallic: paint[1]}
    }
    function sample() {
        const g = drive.game, k = drive.kin
        const entry = {t: Number(g.elapsed || 0), d: Number(g.distance || 0), v: Number(g.egoKmh || 0) / 3.6,
                       a: Number(g.accelMps2 || 0), lane: Number(g.egoLane === undefined ? 1 : g.egoLane),
                       target: Number(g.targetLane === undefined ? 1 : g.targetLane), cars: {}}
        for (const car of (g.traffic || []))
            entry.cars[car.id] = {z: entry.d + Number(car.relativeZ), v: Number(car.speedKmh) / 3.6,
                                  lane: Number(car.lane), braking: Boolean(car.braking)}
        const last = k.buffer.length ? k.buffer[k.buffer.length - 1] : null
        if (!last || entry.t < last.t - 0.001 || entry.d < last.d - 25) {
            // First sample or a new drive: start over instead of sliding backwards.
            k.buffer = [entry]
            k.renderT = entry.t - drive.renderDelay
            k.leadAverage = drive.renderDelay
            k.distance = entry.d; k.lane = entry.lane; k.x = (entry.lane - 1) * 3.6; k.camX = k.x
            for (const slot of k.slots) slot.id = -1
        } else if (entry.t > last.t + 0.001) {
            k.buffer.push(entry)
            if (k.buffer.length > 16)
                k.buffer.shift()
        } else {
            k.buffer[k.buffer.length - 1] = entry  // same plant step, e.g. a status refresh
        }
        k.target = entry.target
        if (Math.abs(entry.target - entry.lane) > 0.05) {
            k.signalSide = entry.target > entry.lane ? 1 : -1
            k.signalUntil = k.clock + 0.9
        }
        // Delegates stay bound to plant car ids, so re-sorting never swaps cars.
        for (const slot of k.slots) slot.seen = false
        for (const key in entry.cars) {
            const id = Number(key)
            let slot = k.slots.find(s => s.id === id)
            if (!slot) {
                slot = k.slots.find(s => s.id < 0)
                if (!slot)
                    continue
                const style = drive.look(id)
                slot.id = id; slot.styled = false; slot.vx = 0; slot.lane = entry.cars[key].lane
                slot.variant = style.variant; slot.paint = style.paint; slot.metallic = style.metallic
            }
            slot.seen = true
        }
        for (const slot of k.slots)
            if (!slot.seen)
                slot.id = -1
    }
    function hermite(p0, v0, p1, v1, h, u) {
        const u2 = u * u, u3 = u2 * u
        return (2 * u3 - 3 * u2 + 1) * p0 + (u3 - 2 * u2 + u) * v0 * h + (3 * u2 - 2 * u3) * p1 + (u3 - u2) * v1 * h
    }
    // The buffered samples around simulation time t: [s0, s1 or null, u, h].
    function bracket(t) {
        const buffer = drive.kin.buffer
        let i = buffer.length - 1
        while (i > 0 && buffer[i].t > t)
            --i
        const s0 = buffer[i], s1 = buffer[i + 1] || null
        return s1 ? [s0, s1, drive.clamp((t - s0.t) / (s1.t - s0.t), 0, 1), s1.t - s0.t] : [s0, null, 0, 0]
    }
    function spring(value, rate, target, stiffness, damping, dt) {
        rate += ((target - value) * stiffness - rate * damping) * dt
        return [value + rate * dt, rate]
    }
    function advance(dt) {
        const k = drive.kin
        dt = drive.clamp(dt, 0, 0.05)
        if (dt <= 0 || !k.buffer.length)
            return
        k.clock += dt
        const live = drive.playing
        const newest = k.buffer[k.buffer.length - 1].t
        if (live) {
            // Stay about renderDelay behind the newest step. The plant may run a
            // little slower or faster than wall time, and the lead is a 20 Hz
            // sawtooth, so only its slow average steers the render clock rate.
            const lead = newest - k.renderT
            if (lead > 0.6 || lead < -0.3) {
                k.renderT = newest - drive.renderDelay
                k.leadAverage = drive.renderDelay
            }
            k.leadAverage += (lead - k.leadAverage) * Math.min(1, dt * 2)
            k.renderT += dt * drive.clamp(1 + (k.leadAverage - drive.renderDelay) * 3, 0.5, 1.5)
        } else {
            k.renderT += (newest - k.renderT) * Math.min(1, dt * 8)
        }
        const span = drive.bracket(k.renderT), s0 = span[0], s1 = span[1], u = span[2], h = span[3]
        let accel = s0.a
        if (s1) {
            k.distance = drive.hermite(s0.d, s0.v, s1.d, s1.v, h, u)
            k.speed = s0.v + (s1.v - s0.v) * u
            k.lane = s0.lane + (s1.lane - s0.lane) * u
            accel = s0.a + (s1.a - s0.a) * u
        } else {
            // Buffer underrun: coast briefly on the last acknowledged step.
            const ahead = live ? drive.clamp(k.renderT - s0.t, 0, 0.25) : 0
            k.distance = s0.d + s0.v * ahead
            k.speed = s0.v
            k.lane = s0.lane + drive.clamp(s0.target - s0.lane, -2.4 * ahead, 2.4 * ahead)
        }
        k.accel += ((live ? accel : 0) - k.accel) * Math.min(1, dt * 10)
        k.blink = (k.clock % 0.7) < 0.38

        const x = (k.lane - 1) * 3.6
        const previousLateral = k.lateral
        k.lateral += ((x - k.x) / dt - k.lateral) * Math.min(1, dt * 12)
        k.latAccel += ((k.lateral - previousLateral) / dt - k.latAccel) * Math.min(1, dt * 8)
        k.x = x
        const yawTarget = -Math.atan2(k.lateral, Math.max(k.speed, 6)) * 57.2958
        k.yaw += (drive.clamp(yawTarget, -11, 11) - k.yaw) * Math.min(1, dt * 10)
        // Suspension: nose dives under braking, squats on throttle, leans out of lane changes.
        let state = drive.spring(k.pitch, k.pitchRate, drive.clamp(-k.accel * 0.24, -1.2, 2.3), 85, 8.5, dt)
        k.pitch = state[0]; k.pitchRate = state[1]
        state = drive.spring(k.roll, k.rollRate, drive.clamp(k.latAccel * 0.09, -2.6, 2.6), 70, 7.5, dt)
        k.roll = state[0]; k.rollRate = state[1]

        const signal = live && k.clock < k.signalUntil ? k.signalSide : 0
        ego.x = k.x
        ego.eulerRotation = Qt.vector3d(0, 180 + k.yaw, 0)
        ego.bodyPitch = k.pitch
        ego.bodyRoll = k.roll
        ego.wheelAngle = -k.distance * 200
        ego.braking = k.accel < -1.0
        ego.indicator = signal
        ego.blinkOn = k.blink
        highway.distance = k.distance
        highway.drivingTime = k.renderT
        cluster.indicator = signal
        cluster.blinkOn = k.blink
        if (signal !== 0 && k.blink && !k.lastBlink)
            sounds.tick()
        k.lastBlink = k.blink

        drive.updateTraffic(dt, span, live)
        drive.updateCamera(dt)
        drive.updateOverlays()
        sounds.road(live ? k.speed : 0)
    }
    function updateTraffic(dt, span, live) {
        const k = drive.kin
        const s0 = span[0], s1 = span[1], u = span[2], h = span[3]
        const radarCars = []
        let lead = -1, leadAhead = 1e9
        for (let i = 0; i < k.slots.length; ++i) {
            const slot = k.slots[i], car = traffic.objectAt(i)
            if (!car)
                continue
            const c0 = slot.id >= 0 ? s0.cars[slot.id] : undefined
            const c1 = slot.id >= 0 && s1 ? s1.cars[slot.id] : undefined
            if (!c0 && !c1) {
                // Not yet (or no longer) at the rendered time.
                car.visible = false
                radarCars.push(null)
                continue
            }
            let lane
            if (c0 && c1) {
                slot.z = drive.hermite(c0.z, c0.v, c1.z, c1.v, h, u)
                slot.speed = c0.v + (c1.v - c0.v) * u
                slot.braking = u < 0.5 ? c0.braking : c1.braking
                lane = c0.lane + (c1.lane - c0.lane) * u
            } else {
                const c = c0 || c1
                slot.z = c.z + c.v * (c0 && live ? drive.clamp(k.renderT - s0.t, 0, 0.25) : 0)
                slot.speed = c.v
                slot.braking = c.braking
                lane = c.lane
            }
            const previousX = (slot.lane - 1) * 3.6
            slot.lane = lane
            slot.x = (lane - 1) * 3.6
            slot.vx += ((slot.x - previousX) / dt - slot.vx) * Math.min(1, dt * 8)
            if (!slot.styled) {
                car.variant = slot.variant; car.paint = slot.paint; car.metallic = slot.metallic
                slot.styled = true
            }
            const ahead = slot.z - k.distance
            car.visible = true
            car.x = slot.x
            car.z = -ahead
            car.eulerRotation = Qt.vector3d(0, 180 - drive.clamp(Math.atan2(slot.vx, Math.max(slot.speed, 6)) * 57.2958, -9, 9), 0)
            car.wheelAngle = -slot.z * 200
            car.braking = slot.braking
            car.indicator = Math.abs(slot.vx) > 0.3 ? (slot.vx > 0 ? 1 : -1) : 0
            car.blinkOn = k.blink
            const inPath = Math.abs(slot.lane - k.lane) < 0.6 || (Math.abs(k.target - k.lane) > 0.05 && Math.abs(slot.lane - k.target) < 0.6)
            if (ahead > 2.0 && inPath && ahead < leadAhead) { lead = i; leadAhead = ahead }
            radarCars.push({lane: slot.lane, ahead: ahead, lead: false, braking: slot.braking})
        }
        if (lead >= 0)
            radarCars[lead].lead = true
        k.lead = lead
        radar.egoLane = k.lane
        radar.place(radarCars)
    }
    function updateCamera(dt) {
        const k = drive.kin
        const fast = drive.clamp(k.speed / 55, 0, 1)
        const t = k.clock
        k.shake += ((drive.emergency && drive.playing ? 1 : 0) - k.shake) * Math.min(1, dt * (drive.emergency ? 10 : 2.5))
        // Road vibration only while driving, so a paused scene stops redrawing.
        const rumble = drive.playing ? 0.006 + 0.02 * fast * fast + 0.05 * k.shake : 0
        const sx = (Math.sin(t * 37.1) + Math.sin(t * 23.7 + 1.3) * 0.6) * rumble
        const sy = (Math.sin(t * 41.3 + 0.7) + Math.sin(t * 19.1) * 0.5) * rumble
        if (drive.hoodCamera) {
            const yaw = k.yaw * Math.PI / 180
            driveCamera.position = Qt.vector3d(k.x - Math.sin(yaw) * 0.55 + sx * 0.4, 1.22 + sy * 0.5 - k.pitch * 0.012, -Math.cos(yaw) * 0.55)
            driveCamera.eulerRotation = Qt.vector3d(-5.5 - k.pitch * 0.8, k.yaw, -k.roll * 0.7)
            driveCamera.fieldOfView = 60 + fast * 6
            return
        }
        if (!drive.playing && drive.game.status !== "paused") {
            // Showroom orbit before the first drive and after a finished one,
            // redrawn at ~30 Hz to keep an idle Studio light on the GPU.
            k.idle += dt
            if (k.idle < 1 / 30)
                return
            k.orbit += k.idle * 7
            k.idle = 0
            const a = (k.orbit + 205) * Math.PI / 180
            const radius = 8.4
            driveCamera.position = Qt.vector3d(k.x + Math.sin(a) * radius, 2.9, Math.cos(a) * radius)
            const dx = k.x - driveCamera.position.x, dz = -driveCamera.position.z, dy = 1.25 - 2.9
            driveCamera.eulerRotation = Qt.vector3d(Math.atan2(dy, Math.hypot(dx, dz)) * 57.2958, Math.atan2(-dx, -dz) * 57.2958, 0)
            driveCamera.fieldOfView = 52
            k.camX = k.x; k.camBack = 9.2
            return
        }
        k.orbit = 0
        k.camX += (k.x - k.camX) * Math.min(1, dt * 3.4)
        const back = 9.2 + fast * 1.4 + drive.clamp(k.accel * 0.11, -0.9, 0.35)
        k.camBack += (back - k.camBack) * Math.min(1, dt * 2.5)
        const height = 3.25 + fast * 0.35
        const px = k.camX + sx, py = height + sy, pz = k.camBack
        const lookX = k.x * 0.7 + k.camX * 0.3, lookY = 0.3, lookZ = -12
        driveCamera.position = Qt.vector3d(px, py, pz)
        driveCamera.eulerRotation = Qt.vector3d(Math.atan2(lookY - py, Math.hypot(lookX - px, lookZ - pz)) * 57.2958,
                                           Math.atan2(-(lookX - px), -(lookZ - pz)) * 57.2958,
                                           drive.clamp(-k.lateral * 0.12, -1.2, 1.2))
        driveCamera.fieldOfView = 54 + fast * 8 + k.shake * 2
    }
    function updateOverlays() {
        const k = drive.kin
        const show = drive.overlays && drive.playing && drive.mode !== "off"
        const leadCar = k.lead >= 0 ? traffic.objectAt(k.lead) : null
        const leadSlot = k.lead >= 0 ? k.slots[k.lead] : null
        const gap = leadSlot ? Math.max(0, leadSlot.z - k.distance - 4.6) : 1e9
        const want = Math.max(6, k.speed * Number(drive.game.headwayMs || 1800) / 1000)
        const span = Math.max(1.5, Math.min(want, gap, 90))
        corridor.visible = show
        corridor.x = k.x
        corridor.eulerRotation = Qt.vector3d(0, k.yaw, 0)
        corridorCarpet.z = -(2.35 + span / 2)
        corridorCarpet.scale = Qt.vector3d(0.026, span / 100, 1)
        corridorMaterial.span = span
        corridorMaterial.phase = k.distance % 3.2
        const close = gap < want
        const tint = drive.emergency ? [1.0, 0.16, 0.2] : close || drive.warning ? [1.0, 0.62, 0.12] : [0.18, 0.85, 0.7]
        corridorMaterial.tint = Qt.vector3d(tint[0], tint[1], tint[2])
        corridorMaterial.strength = drive.emergency ? 1.4 : 1.0
        const closing = leadSlot ? Math.round((k.speed - leadSlot.speed) * 3.6) : 0
        radar.relativeText = !leadSlot ? "—" : closing === 0 ? "0 km/sa" : (closing > 0 ? "−" : "+") + Math.abs(closing) + " km/sa"

        if (!show || !leadCar || gap > 140) {
            target.visible = false
            return
        }
        const half = [1.05, 0.0, 2.3]
        let left = 1e9, right = -1e9, top = 1e9, bottom = -1e9, valid = true
        for (const cx of [-1, 1]) for (const cy of [0, 1]) for (const cz of [-1, 1]) {
            const p = scene.mapFrom3DScene(Qt.vector3d(leadCar.x + cx * half[0], cy * (leadCar.height || 1.35), leadCar.z + cz * half[2]))
            if (!(p.z > 0)) valid = false
            left = Math.min(left, p.x); right = Math.max(right, p.x); top = Math.min(top, p.y); bottom = Math.max(bottom, p.y)
        }
        target.visible = valid && right - left > 6
        target.x = left - 6; target.y = top - 6
        target.width = right - left + 12; target.height = bottom - top + 12
        target.label = drive.number(gap, gap < 10 ? 1 : 0) + " m" + (drive.closingTtc ? "  ·  " + drive.number(drive.game.ttc, 1) + " s" : "")
    }

    onGameChanged: { drive.sample(); if (!playing) drive.settle() }
    onPlayingChanged: {
        drive.settle()
        if (playing) Qt.callLater(focusDriving)
        else if (studio) studio.releaseGameKeys()
    }
    onVisibleChanged: {
        drive.settle()
        if (!visible && studio) studio.releaseGameKeys()
    }
    onHoodCameraChanged: drive.settle()
    onOverlaysChanged: drive.settle()
    Timer { id: settleTimer; interval: 2500; running: true; onTriggered: drive.settling = false }
    Component.onCompleted: {
        const slots = []
        for (let i = 0; i < 12; ++i)
            slots.push({id: -1})
        drive.kin.slots = slots
        drive.sample()
    }

    component Copy: Text { color: "#e5edf3"; font.pixelSize: 12; elide: Text.ElideRight }
    component Chip: Rectangle {
        id: chip
        property string caption
        property color ink: "#b6c9d5"
        property bool lit: false
        implicitWidth: chipRow.implicitWidth + 26; implicitHeight: 31
        radius: 8; color: chip.lit ? Qt.rgba(chip.ink.r, chip.ink.g, chip.ink.b, 0.12) : "#142430"
        border.color: chip.lit ? Qt.rgba(chip.ink.r, chip.ink.g, chip.ink.b, 0.45) : "#27404f"
        Row {
            id: chipRow
            anchors.centerIn: parent; spacing: 8
            Rectangle { width: 6; height: 6; radius: 3; color: chip.ink; anchors.verticalCenter: parent.verticalCenter; visible: chip.lit }
            Copy { id: chipText; text: chip.caption; color: chip.ink; font.pixelSize: 11; font.weight: Font.DemiBold; font.letterSpacing: 0.6 }
        }
    }
    component Glass: Rectangle {
        radius: 14; color: "#c80a1219"
        border.width: 1; border.color: "#22ffffff"
    }
    component Keycap: Row {
        id: keycap
        property string keys
        property string label
        property bool active: false
        spacing: 7
        Rectangle {
            width: Math.max(24, keyText.implicitWidth + 12); height: 22; radius: 5
            color: keycap.active ? "#1d3f3b" : "#172633"; border.color: keycap.active ? "#4fb9a0" : "#2f4656"
            Text { id: keyText; anchors.centerIn: parent; text: keycap.keys; color: keycap.active ? "#9ff2dc" : "#c6d6e0"; font.pixelSize: 10; font.weight: Font.DemiBold }
        }
        Copy { text: keycap.label; color: "#8aa5b6"; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter }
    }

    ColumnLayout {
        anchors.fill: parent; spacing: 12
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            Chip {
                objectName: "watchMode"
                caption: drive.mode === "active" ? "ADAS ETKİN" : drive.mode === "warn" ? "YALNIZ UYARI" : "ADAS KAPALI"
                ink: drive.mode === "off" ? "#8ea3b1" : drive.signalColor; lit: drive.mode !== "off"
            }
            Chip { objectName: "watchAcc"; caption: "ACC " + (drive.game.accEnabled ? "AÇIK" : "KAPALI"); ink: drive.game.accEnabled ? "#63dec2" : "#b6c9d5"; lit: Boolean(drive.game.accEnabled) }
            Chip { objectName: "watchTarget"; caption: "Hedef " + drive.number(drive.game.targetKmh, 0) + " km/sa" }
            Chip { objectName: "watchHeadway"; caption: "Takip " + drive.number(Number(drive.game.headwayMs) / 1000, 1) + " s" }
            Item { Layout.fillWidth: true }
            Copy { text: "AYARLAR SAATTEN"; color: "#748f9e"; font.pixelSize: 10; font.letterSpacing: 1 }
        }
        Rectangle {
            id: viewport
            objectName: "driveViewport"
            Layout.fillWidth: true; Layout.fillHeight: true
            Layout.minimumHeight: 380
            radius: 12; clip: true; color: "#a9c4d3"
            focus: true
            border.width: viewport.activeFocus && drive.playing ? 2 : 1
            border.color: drive.playing ? drive.signalColor : "#314a5b"
            readonly property real ui: drive.clamp(width / 1100, 0.7, 1.0)
            readonly property bool compact: width < 900
            Keys.onPressed: function(event) {
                let key = drive.keyName(event.key)
                if (key) { drive.studio.gameKey(key, true, event.isAutoRepeat); event.accepted = true }
                else if (event.key === Qt.Key_Space || event.key === Qt.Key_Escape) {
                    if (!event.isAutoRepeat) drive.studio.pauseGame()
                    event.accepted = true
                } else if (event.key === Qt.Key_C) {
                    if (!event.isAutoRepeat) drive.hoodCamera = !drive.hoodCamera
                    event.accepted = true
                } else if (event.key === Qt.Key_V) {
                    if (!event.isAutoRepeat) drive.overlays = !drive.overlays
                    event.accepted = true
                } else if (event.key === Qt.Key_M) {
                    if (!event.isAutoRepeat) drive.soundOn = !drive.soundOn
                    event.accepted = true
                }
            }
            Keys.onReleased: function(event) {
                let key = drive.keyName(event.key)
                if (key) { drive.studio.gameKey(key, false, event.isAutoRepeat); event.accepted = true }
            }
            onActiveFocusChanged: if (!activeFocus && drive.playing) drive.studio.pauseGame()

            View3D {
                id: scene
                objectName: "embeddedDriveScene"
                anchors.fill: parent
                visible: drive.visible
                camera: driveCamera
                environment: ExtendedSceneEnvironment {
                    backgroundMode: SceneEnvironment.SkyBoxCubeMap
                    skyBoxCubeMap: CubeMapTexture { source: "assets/sky/sky_%p.jpg" }
                    lightProbe: Texture { source: "assets/sky/probe.jpg" }
                    probeExposure: 0.78
                    probeHorizon: 0.35
                    antialiasingMode: SceneEnvironment.MSAA
                    antialiasingQuality: SceneEnvironment.High
                    specularAAEnabled: true
                    tonemapMode: SceneEnvironment.TonemapModeAces
                    exposure: 1.0
                    aoEnabled: true
                    aoStrength: 55; aoDistance: 1.4; aoSoftness: 45; aoDither: true; aoSampleRate: 3
                    glowEnabled: true
                    glowQualityHigh: true
                    glowStrength: 0.9; glowIntensity: 0.55; glowBloom: 0
                    glowHDRMinimumValue: 1.2; glowHDRScale: 2.0
                    glowBlendMode: ExtendedSceneEnvironment.GlowBlendMode.Additive
                    glowLevel: ExtendedSceneEnvironment.GlowLevel.Two | ExtendedSceneEnvironment.GlowLevel.Three | ExtendedSceneEnvironment.GlowLevel.Four
                    // Strength/radius follow Qt's (u·v·strength)^radius falloff: corners only.
                    vignetteEnabled: true; vignetteStrength: 40; vignetteRadius: 0.12; vignetteColor: "#0a1016"
                    colorAdjustmentsEnabled: true
                    adjustmentContrast: 1.04; adjustmentSaturation: 1.1; adjustmentBrightness: 1.0
                    ditheringEnabled: true
                    fog: Fog {
                        enabled: true; color: "#b8cad3"
                        depthEnabled: true; depthNear: 70; depthFar: 720; depthCurve: 0.85; density: 0.92
                    }
                }
                PerspectiveCamera {
                    id: driveCamera
                    position: Qt.vector3d(0, 3.1, 8.6)
                    eulerRotation.x: -11
                    clipNear: 0.25; clipFar: 1600; fieldOfView: 56
                }
                DirectionalLight {
                    eulerRotation: Qt.vector3d(-38, -32, 0)
                    color: "#fff2df"; brightness: 1.55
                    ambientColor: "#1a2128"
                    castsShadow: true
                    shadowMapQuality: Light.ShadowMapQualityVeryHigh
                    shadowMapFar: 240
                    csmNumSplits: 2; csmSplit1: 0.12; csmSplit2: 0.4; csmBlendRatio: 0.08
                    lockShadowmapTexels: true
                    shadowFactor: 72; shadowBias: 0.012
                    softShadowQuality: Light.PCF16; pcfFactor: 1.6
                }
                Highway3D { id: highway }
                Vehicle3D {
                    id: ego
                    objectName: "egoVehicle3D"
                    variant: 0; paint: "#17867b"; metallic: 0.7
                    lamps: 0.45
                }
                Repeater3D {
                    id: traffic
                    model: 12
                    delegate: Vehicle3D { visible: false; lamps: 0.4 }
                }
                Node {
                    id: corridor
                    visible: false
                    Model {
                        id: corridorCarpet
                        source: "#Rectangle"
                        y: 0.03
                        eulerRotation.x: -90
                        castsShadows: false; receivesShadows: false
                        materials: CustomMaterial {
                            id: corridorMaterial
                            shadingMode: CustomMaterial.Unshaded
                            vertexShader: "shaders/corridor.vert"
                            fragmentShader: "shaders/corridor.frag"
                            sourceBlend: CustomMaterial.SrcAlpha
                            destinationBlend: CustomMaterial.OneMinusSrcAlpha
                            property real span: 10
                            property real phase: 0
                            property real strength: 1
                            property vector3d tint: Qt.vector3d(0.18, 0.85, 0.7)
                        }
                    }
                }
            }
            FrameAnimation {
                objectName: "driveClock"
                running: drive.visible && (drive.playing || drive.settling || drive.showroom && drive.Window.active)
                onTriggered: drive.advance(frameTime)
            }
            MouseArea {
                anchors.fill: parent
                onClicked: viewport.forceActiveFocus()
                cursorShape: drive.playing ? Qt.BlankCursor : Qt.ArrowCursor
            }

            // Edge glow for collision warnings and emergency braking.
            Item {
                id: edgeGlow
                anchors.fill: parent
                visible: opacity > 0.01
                opacity: drive.playing && drive.emergency ? (pulse.lit ? 0.8 : 0.35) : drive.playing && drive.warning ? (pulse.lit ? 0.45 : 0.2) : 0
                Behavior on opacity { NumberAnimation { duration: 120 } }
                readonly property color ink: drive.emergency ? "#ff2e45" : "#ffae2e"
                Timer { id: pulse; property bool lit: true; interval: drive.emergency ? 160 : 380; repeat: true; running: drive.playing && (drive.emergency || drive.warning); onTriggered: lit = !lit }
                Rectangle {
                    anchors { left: parent.left; right: parent.right; top: parent.top }
                    height: parent.height * 0.18
                    gradient: Gradient { GradientStop { position: 0; color: Qt.rgba(edgeGlow.ink.r, edgeGlow.ink.g, edgeGlow.ink.b, 0.38) } GradientStop { position: 1; color: "transparent" } }
                }
                Rectangle {
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                    height: parent.height * 0.18
                    gradient: Gradient { GradientStop { position: 0; color: "transparent" } GradientStop { position: 1; color: Qt.rgba(edgeGlow.ink.r, edgeGlow.ink.g, edgeGlow.ink.b, 0.4) } }
                }
                Rectangle {
                    anchors { top: parent.top; bottom: parent.bottom; left: parent.left }
                    width: parent.width * 0.09
                    gradient: Gradient { orientation: Gradient.Horizontal; GradientStop { position: 0; color: Qt.rgba(edgeGlow.ink.r, edgeGlow.ink.g, edgeGlow.ink.b, 0.34) } GradientStop { position: 1; color: "transparent" } }
                }
                Rectangle {
                    anchors { top: parent.top; bottom: parent.bottom; right: parent.right }
                    width: parent.width * 0.09
                    gradient: Gradient { orientation: Gradient.Horizontal; GradientStop { position: 0; color: "transparent" } GradientStop { position: 1; color: Qt.rgba(edgeGlow.ink.r, edgeGlow.ink.g, edgeGlow.ink.b, 0.34) } }
                }
            }

            // Projected lead-vehicle bracket, like an ADAS camera overlay.
            Item {
                id: target
                objectName: "leadTarget"
                property string label: ""
                visible: false
                readonly property color ink: drive.signalColor
                Repeater {
                    model: 4
                    delegate: Item {
                        id: corner
                        required property int index
                        readonly property bool atRight: index % 2 === 1
                        readonly property bool atBottom: index > 1
                        x: atRight ? target.width - 14 : 0
                        y: atBottom ? target.height - 14 : 0
                        width: 14; height: 14
                        Rectangle { x: corner.atRight ? 11 : 0; width: 3; height: 14; radius: 1; color: target.ink }
                        Rectangle { y: corner.atBottom ? 11 : 0; width: 14; height: 3; radius: 1; color: target.ink }
                    }
                }
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.top; anchors.bottomMargin: 6
                    width: targetLabel.implicitWidth + 16; height: 22; radius: 6
                    color: "#d80a1219"; border.color: Qt.rgba(target.ink.r, target.ink.g, target.ink.b, 0.6)
                    Copy { id: targetLabel; anchors.centerIn: parent; text: target.label; color: target.ink; font.pixelSize: 11; font.weight: Font.DemiBold; font.features: { "tnum": 1 } }
                }
            }

            // Status pill, top left.
            Glass {
                anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 16
                width: liveRow.implicitWidth + 28; height: 36; radius: 10
                Row {
                    id: liveRow; anchors.centerIn: parent; spacing: 12
                    Rectangle {
                        width: 8; height: 8; radius: 4; anchors.verticalCenter: parent.verticalCenter
                        color: drive.playing ? drive.signalColor : drive.available ? "#63dec2" : "#8b9eae"
                        SequentialAnimation on opacity {
                            running: drive.playing; loops: Animation.Infinite; alwaysRunToEnd: true
                            NumberAnimation { to: 0.35; duration: 600 } NumberAnimation { to: 1; duration: 600 }
                        }
                    }
                    Copy { text: drive.playing ? "CANLI SÜRÜŞ" : drive.available ? "SAAT BAĞLI" : "BAĞLANTI BEKLENİYOR"; color: "#e8f1f5"; font.pixelSize: 11; font.weight: Font.DemiBold; font.letterSpacing: 0.8 }
                    Copy { text: "STM32 · USB" + (drive.playing && Number(drive.game.rttMs) > 0 ? " · " + drive.number(drive.game.rttMs, 1) + " ms" : ""); color: "#8fa8b8"; font.pixelSize: 11; font.features: { "tnum": 1 } }
                }
            }

            // Session progress and score, top right.
            Glass {
                id: session
                objectName: "driveSession"
                visible: drive.available && !viewport.compact
                anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 16
                width: 236; height: 64; radius: 12
                readonly property real total: Number(drive.game.elapsed || 0) + Number(drive.game.remaining || 0)
                Column {
                    anchors.fill: parent; anchors.margins: 12; spacing: 7
                    Row {
                        width: parent.width
                        Copy { text: "SÜRÜŞ"; color: "#7e97a7"; font.pixelSize: 10; font.letterSpacing: 1; width: 60 }
                        Copy {
                            width: parent.width - 60; horizontalAlignment: Text.AlignRight
                            text: Math.floor(Number(drive.game.elapsed || 0) / 60) + ":" + String(Math.floor(Number(drive.game.elapsed || 0) % 60)).padStart(2, "0") + "  ·  " + drive.number(Number(drive.game.distance || 0) / 1000, 2) + " km  ·  " + Number(drive.game.score || 0) + " puan"
                            font.pixelSize: 11; font.features: { "tnum": 1 }
                        }
                    }
                    Rectangle {
                        width: parent.width; height: 4; radius: 2; color: "#1fffffff"
                        Rectangle {
                            height: parent.height; radius: 2; color: "#63dec2"
                            width: parent.width * drive.clamp(Number(drive.game.elapsed || 0) / Math.max(1, session.total), 0, 1)
                        }
                    }
                    Copy {
                        text: "Uyarı " + Number(drive.game.warnings || 0) + "  ·  AEB " + Number(drive.game.interventions || 0) + "  ·  Ramak kala " + Number(drive.game.nearMisses || 0)
                        color: "#8fa8b8"; font.pixelSize: 10
                    }
                }
            }

            // Collision warning / emergency braking banner.
            Rectangle {
                visible: drive.playing && (drive.emergency || drive.warning)
                anchors.top: parent.top; anchors.horizontalCenter: parent.horizontalCenter; anchors.topMargin: 66
                width: warningRow.implicitWidth + 44; height: 48; radius: 12
                color: drive.emergency ? "#e6400c16" : "#e63a2a08"
                border.width: 2; border.color: drive.signalColor
                scale: viewport.ui
                Row {
                    id: warningRow; anchors.centerIn: parent; spacing: 12
                    Rectangle {
                        width: 26; height: 26; radius: 13; color: drive.signalColor; anchors.verticalCenter: parent.verticalCenter
                        Text { anchors.centerIn: parent; text: "!"; color: "#1a0d10"; font.pixelSize: 17; font.weight: Font.Black }
                    }
                    Copy { id: warningLabel; objectName: "driveWarning"; color: drive.signalColor; text: drive.emergency ? "AEB · ACİL FREN" : "ÇARPIŞMA UYARISI"; font.weight: Font.Bold; font.pixelSize: 17; font.letterSpacing: 1; anchors.verticalCenter: parent.verticalCenter }
                }
            }

            DriveCluster {
                id: cluster
                anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 14
                transformOrigin: Item.BottomLeft
                scale: viewport.ui
                speedKmh: Number(drive.game.egoKmh || 0)
                targetKmh: Number(drive.game.targetKmh || 0)
                accEnabled: Boolean(drive.game.accEnabled)
                warning: drive.warning
                emergency: drive.emergency
                mode: drive.mode
                accel: Number(drive.game.accelMps2 || 0)
                headwayMs: Number(drive.game.headwayMs || 1800)
            }
            DriveRadar {
                id: radar
                anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 14
                transformOrigin: Item.BottomRight
                scale: viewport.compact ? 0.62 : viewport.ui
                signal: drive.signalColor
                gapText: Number(drive.game.gap) >= 0 ? drive.number(drive.game.gap, 1) + " m" : "—"
                ttcText: drive.closingTtc ? drive.number(drive.game.ttc, 1) + " s" : "—"
            }

            // Ready, paused and finished card.
            Rectangle {
                visible: !drive.playing
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: parent.top; anchors.topMargin: 64 * viewport.ui
                transformOrigin: Item.Top
                width: Math.min(470, parent.width - 64); height: card.implicitHeight + 46
                radius: 16; color: "#e60b1720"; border.color: "#3a5866"
                scale: viewport.ui
                Column {
                    id: card; anchors.centerIn: parent; width: parent.width - 46; spacing: 14
                    Copy {
                        width: parent.width
                        text: !drive.available ? "3B sürüş hazır" : drive.game.status === "collision" ? "Sürüş tamamlandı · Çarpışma" : drive.game.status === "finished" ? "Sürüş tamamlandı" : drive.game.status === "paused" ? "Sürüş duraklatıldı" : "Direksiyon sende"
                        font.pixelSize: 24; font.weight: Font.DemiBold
                        color: drive.game.status === "collision" ? "#ff8a95" : "#eef4f7"
                    }
                    Grid {
                        objectName: "driveResults"
                        visible: drive.available && (drive.finished || drive.game.status === "paused") && Number(drive.game.elapsed || 0) > 0
                        columns: 4; columnSpacing: 22; rowSpacing: 10
                        Repeater {
                            model: [
                                ["PUAN", String(Number(drive.game.score || 0))],
                                ["MESAFE", drive.number(Number(drive.game.distance || 0) / 1000, 2) + " km"],
                                ["UYARI", String(Number(drive.game.warnings || 0))],
                                ["AEB", String(Number(drive.game.interventions || 0))],
                                ["RAMAK KALA", String(Number(drive.game.nearMisses || 0))],
                                ["TEPKİ", Number(drive.game.reactionMs) >= 0 ? drive.number(Number(drive.game.reactionMs) / 1000, 2) + " s" : "—"],
                                ["SÜRE", drive.number(drive.game.elapsed, 0) + " s"],
                                ["ÇARPIŞMA", String(Number(drive.game.collisions || 0))]
                            ]
                            delegate: Column {
                                id: result
                                required property var modelData
                                spacing: 3
                                Copy { text: result.modelData[0]; color: "#6f8a9a"; font.pixelSize: 9; font.letterSpacing: 1 }
                                Copy { text: result.modelData[1]; color: "#e7f0f4"; font.pixelSize: 16; font.weight: Font.DemiBold; font.features: { "tnum": 1 } }
                            }
                        }
                    }
                    Text {
                        objectName: "watchStartHint"
                        width: parent.width; wrapMode: Text.WordWrap; color: "#c4d6e0"; font.pixelSize: 13; lineHeight: 1.4
                        text: !drive.available ? "Üstteki Bağlan düğmesiyle ADASLab yüklü saati bağla. Ardından saatte BASLAT’a dokun." : "Modu ve ACC ayarını saatten seç. Saat ekranındaki BASLAT’a dokun; oyun burada başlayacak."
                    }
                    Flow {
                        width: parent.width; spacing: 14
                        Keycap { keys: "W ↑"; label: "Gaz" }
                        Keycap { keys: "S ↓"; label: "Fren" }
                        Keycap { keys: "A D"; label: "Şerit" }
                        Keycap { keys: "C"; label: drive.hoodCamera ? "Kaput kamerası" : "Takip kamerası" }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 16
            Keycap { keys: "WASD"; label: "Sür" }
            Keycap { keys: "␣"; label: "Duraklat" }
            Keycap { keys: "C"; label: "Kamera"; active: drive.hoodCamera }
            Keycap { keys: "V"; label: "ADAS çizimi"; active: drive.overlays }
            Keycap { keys: "M"; label: drive.soundOn ? "Ses açık" : "Ses kapalı"; active: drive.soundOn }
            Item { Layout.fillWidth: true }
            Copy { text: "Başlat / Duraklat ve ADAS ayarları: saat"; color: "#6d8b9d"; font.pixelSize: 11 }
        }
    }

    // Warning chimes, relay ticks and a speed-dependent tyre/wind bed.
    MediaDevices { id: mediaDevices }
    Item {
        id: sounds
        readonly property bool available: mediaDevices.audioOutputs.length > 0
        readonly property bool audible: drive.soundOn && drive.visible && available
        function tick() { if (sounds.audible) tickSound.play() }
        function road(speed) {
            const level = sounds.audible && drive.playing ? 0.05 + 0.4 * Math.pow(drive.clamp(speed / 55, 0, 1), 1.4) : 0
            bedSound.volume = level
            if (level > 0 && !bedSound.playing) bedSound.play()
            else if (level === 0 && bedSound.playing) bedSound.stop()
        }
        SoundEffect { id: fcwSound; source: sounds.available ? "assets/sounds/fcw.wav" : ""; volume: 0.5 }
        SoundEffect { id: aebSound; source: sounds.available ? "assets/sounds/aeb.wav" : ""; volume: 0.6 }
        SoundEffect { id: tickSound; source: sounds.available ? "assets/sounds/indicator.wav" : ""; volume: 0.3 }
        SoundEffect { id: bedSound; source: sounds.available ? "assets/sounds/road.wav" : ""; loops: SoundEffect.Infinite; volume: 0 }
        Timer {
            interval: drive.emergency ? 300 : 650
            repeat: true
            triggeredOnStart: true
            running: sounds.audible && drive.playing && (drive.emergency || drive.warning)
            onTriggered: (drive.emergency ? aebSound : fcwSound).play()
        }
    }
}
