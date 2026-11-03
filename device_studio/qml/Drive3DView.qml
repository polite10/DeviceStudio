pragma ComponentBehavior: Bound
import QtCore
import QtQuick
import QtQuick.Layouts
import QtQuick3D
import QtQuick3D.Helpers
import QtQuick3D.Particles3D
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
    readonly property bool busy: studio ? Boolean(studio.state.busy) : false
    property bool hoodCamera: false
    property bool soundOn: true
    // What the firmware reports beside and behind the car.
    readonly property int assistBits: playing ? Number(game.assistBits || 0) : 0
    readonly property int blindLeft: playing ? Number(game.blindLeft || 0) : 0
    readonly property int blindRight: playing ? Number(game.blindRight || 0) : 0
    readonly property int rearThreat: playing ? Number(game.rearThreat || 0) : 0
    readonly property bool sideAlert: blindLeft > 1 || blindRight > 1 || rearThreat > 1
    // The most pressing thing the side and rear systems are doing; empty when nothing.
    readonly property var aroundNote: {
        const bits = drive.assistBits
        if (bits & 16) return ["ŞERİTTEN KAÇIŞ", "· arkadan gelen araç için", "#63dec2"]
        if (bits & 4) return ["KAÇIŞ GAZI", "· arkadan veya yandan gelen araç için", "#63dec2"]
        if (bits & 2) return ["YÖN DÜZELTME", "· yanda araç var", "#ff8a5c"]
        if (bits & 8) return ["YANDAN ARAÇ GİRİYOR", "· fren", "#ff8a5c"]
        if (bits & 1) return ["ŞERİT TAKİP", "· sinyal ver veya direksiyonu zorla", "#63dec2"]
        if (drive.rearThreat > 1) return ["ARKADAN HIZLI ARAÇ", "", "#ff8a5c"]
        if (drive.blindLeft > 1) return ["KÖR NOKTA · SOL", "· o tarafa geçme", "#ff4a58"]
        if (drive.blindRight > 1) return ["KÖR NOKTA · SAĞ", "· o tarafa geçme", "#ff4a58"]
        if (bits & 32) return ["SÜRÜCÜ DEVRALDI", "· şerit takip bekliyor", "#ffc35c"]
        if (bits & 64) return ["ŞERİT UYARISI", "", "#ffc35c"]
        if (drive.playing && Boolean(drive.game.scraping)) return ["BARİYERE SÜRTÜNÜYOR", "", "#ff8a5c"]
        return null
    }
    // Per-frame updates run while driving, briefly after any change, and for
    // the showroom orbit only while Studio is the active application.
    readonly property bool showroom: !playing && game.status !== "paused" && !hoodCamera
    // The ego car is picked between drives and remembered across sessions.
    readonly property bool choosing: !playing && game.status !== "paused"
    // Body roll and dive in degrees per m/s²: a soft 1980s sedan rolls ~7°/g,
    // the Model 3 ~3.5°/g, the fan-held Roadster barely moves.
    readonly property var cars: [
        {id: "sahin", name: "Tofaş Şahin", note: "1980'ler · klasik sedan", variant: 5, paint: "#b5221f", metallic: 0.15, roll: 0.7, dive: 0.34},
        {id: "model3", name: "Tesla Model 3", note: "Elektrikli · cam tavan", variant: 6, paint: "#f2f4f5", metallic: 0.08, roll: 0.36, dive: 0.19},
        {id: "roadster", name: "Tesla Taklacı Güvercin Serisi", note: "Uçar · ters rampadan", variant: 7, paint: "#eef0f1", metallic: 0.05, roll: 0.15, dive: 0.1, flight: true}]
    readonly property var egoCar: cars.find(car => car.id === garage.car) || cars[0]
    // The Taklacı Güvercin (2028 Roadster design) flies: three layers on R/F, takla lane changes, and its
    // drive starts upside down on the ceiling of the reveal's J-shaped launch ramp.
    readonly property bool flying: Boolean(egoCar.flight)
    // A new drive of the flier opens with it driving up the ramp while the plant waits.
    readonly property bool launching: playing && flying && Boolean(game.launching)
    readonly property real climbTime: Math.max(1, Number(game.launchSeconds || 4.6) - 0.6)
    property real launchKmh: 0
    // Read the car itself: the flying binding may not have re-evaluated yet.
    onEgoCarChanged: { drive.settle(); if (studio) studio.setVehicle(egoCar.id) }
    readonly property real introTime: 2.2
    // The launch is filmed from beside the road, far enough to show the whole J.
    readonly property var spectator: ({x: 28, y: 3.6, z: -10, fov: 50})
    // The reveal's launch ramp, along our lane: a quarter pipe rising from the
    // road behind the car, a straight wall, then a curl into a flat ceiling
    // where the car stops upside down, pulled up by its fans. Ramp space: z back
    // from the road tangent, y up, metres; the car's centre hangs at rampHang.
    // Before a drive it waits rampRun metres down the road, facing the ramp.
    readonly property real rampRun: 24
    readonly property real rampCeiling: 9.0
    readonly property real rampHang: -1.3
    readonly property real rampWidth: 4.4
    readonly property var rampProfile: {
        const points = [], low = 3.5, wall = 2.5, high = 3.0, flat = 3.6
        for (let i = 0; i <= 16; ++i) {
            const a = Math.PI / 2 * i / 16
            points.push([low * Math.sin(a), low - low * Math.cos(a)])
        }
        for (let i = 1; i <= 3; ++i)
            points.push([low, low + wall * i / 3])
        for (let i = 1; i <= 16; ++i) {
            const a = Math.PI / 2 * i / 16
            points.push([low - high + high * Math.cos(a), low + wall + high * Math.sin(a)])
        }
        for (let i = 1; i <= 3; ++i)
            points.push([low - high - flat * i / 3, low + wall + high])
        return points
    }
    // Deck slabs [z, y, pitch, length] centred half their thickness behind the
    // driving surface, and the surface line's [z, y] midpoints for its markings.
    readonly property var rampSegments: {
        const points = drive.rampProfile, segments = []
        for (let i = 1; i < points.length; ++i) {
            const [z0, y0] = points[i - 1], [z1, y1] = points[i]
            const length = Math.hypot(z1 - z0, y1 - y0), tz = (z1 - z0) / length, ty = (y1 - y0) / length
            segments.push([(z0 + z1) / 2 + ty * 0.09, (y0 + y1) / 2 - tz * 0.09, -Math.atan2(y1 - y0, z1 - z0) * 57.2958,
                           length + 0.03, (z0 + z1) / 2 - ty * 0.012, (y0 + y1) / 2 + tz * 0.012, i])
        }
        return segments
    }
    // The car's way up: [distance, z, y] from where it waits, along the ramp's surface.
    readonly property var rampTrack: {
        const points = [[drive.rampHang - drive.rampRun, 0]].concat(drive.rampProfile), track = []
        let distance = 0
        for (let i = 0; i < points.length; ++i) {
            if (i)
                distance += Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1])
            track.push([distance, points[i][0], points[i][1]])
        }
        return track
    }
    function rampPoint(distance) {
        const track = drive.rampTrack
        if (distance <= 0)
            return [track[0][1] + distance, 0]
        let i = 1
        while (i < track.length - 1 && track[i][0] < distance)
            ++i
        const a = track[i - 1], b = track[i], u = (distance - a[0]) / (b[0] - a[0])
        return [a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u]
    }
    // Pose climbing, with both axles on the surface, so it follows the curve as a
    // rigid car does. Eases from rest to a stop with the car's centre at rampHang.
    function climbPose(time) {
        const last = drive.rampTrack[drive.rampTrack.length - 1]
        const stop = last[0] - (drive.rampHang - last[1])
        const u = drive.clamp(time / drive.climbTime, 0, 1), axle = ego.length * 0.31
        const distance = stop * u * u * (3 - 2 * u)
        const rear = drive.rampPoint(distance - axle), front = drive.rampPoint(distance + axle)
        return {distance: distance, kmh: stop * 6 * u * (1 - u) / drive.climbTime * 3.6,
                y: (rear[1] + front[1]) / 2, z: (rear[0] + front[0]) / 2 - drive.rampHang,
                pitch: -Math.atan2(front[1] - rear[1], front[0] - rear[0]) * 57.2958}
    }
    Settings {
        id: garage
        category: "drive"
        property string car: "sahin"
        // The ADAS drawings the driver wants; remembered like the car.
        property bool corridor: true
        property bool bracket: true
        property bool sensors: true
        property bool blindSpot: true
    }
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
        distance: 0, speed: 0, accel: 0, lane: 1, laneRate: 0, x: 0, lateral: 0, latAccel: 0, yaw: 0, wheel: 0,
        pitch: 0, pitchRate: 0, roll: 0, rollRate: 0, flip: 0, lift: 0, jet: 0, retro: 0, side: 0,
        camX: 0, camBack: 9.2, orbit: 0, idle: 0, shake: 0, blink: false, lastBlink: false, lead: -1, slots: [],
        alt: 0, renderAlt: 0, intro: -1, rampAt: 0, wing: 0, climb: 0, launchClock: 0, spectatorAt: [28, 3.6, -10, 36]
    })
    readonly property var paints: [["#e8eaeb", 0.15], ["#f3f2ee", 0.05], ["#b4b9bd", 0.8], ["#6b7178", 0.7], ["#202326", 0.55],
        ["#1d3352", 0.65], ["#8e1c22", 0.6], ["#2d4b3e", 0.55], ["#c9bfa6", 0.35], ["#4a5560", 0.7], ["#5c1a26", 0.6], ["#d8dadb", 0.2]]

    function number(value, digits) { return Number(value || 0).toFixed(digits) }
    function clamp(value, low, high) { return Math.max(low, Math.min(high, value)) }
    function focusDriving() { if (playing && visible) viewport.forceActiveFocus() }
    function keyName(key) {
        return ({[Qt.Key_W]:"w", [Qt.Key_Up]:"up", [Qt.Key_S]:"s", [Qt.Key_Down]:"down",
                 [Qt.Key_Space]:"space", [Qt.Key_A]:"a", [Qt.Key_Left]:"left", [Qt.Key_D]:"d",
                 [Qt.Key_Right]:"right", [Qt.Key_R]:"r", [Qt.Key_F]:"f", [Qt.Key_Q]:"q", [Qt.Key_E]:"e",
                 [Qt.Key_Z]:"z", [Qt.Key_X]:"x"})[key] || ""
    }
    // Plant vehicle classes to their models; sizes match the plant's footprints.
    readonly property var kinds: ({sedan: 0, suv: 1, hatch: 2, taxi: 3, van: 4, sahin: 5, model3: 6})
    function look(id, kind) {
        const hash = Math.imul(id + 1, 2654435761) >>> 0
        const variant = kind in drive.kinds ? drive.kinds[kind] : 0
        const paint = kind === "taxi" ? ["#f2c12e", 0.25] : drive.paints[(hash >>> 8) % drive.paints.length]
        return {variant: variant, paint: paint[0], metallic: paint[1]}
    }
    function sample() {
        const g = drive.game, k = drive.kin
        const entry = {t: Number(g.elapsed || 0), d: Number(g.distance || 0), v: Number(g.egoKmh || 0) / 3.6,
                       a: Number(g.accelMps2 || 0), lane: Number(g.egoLane === undefined ? 1 : g.egoLane),
                       target: Number(g.targetLane === undefined ? 1 : g.targetLane), h: Number(g.altitude || 0),
                       vy: Number(g.egoLaneRate || 0), ay: Number(g.egoLatAccel || 0), signal: Number(g.egoSignal || 0),
                       braking: Boolean(g.egoBraking), roll: Number(g.roll || 0), lift: Number(g.lift || 0),
                       boost: Number(g.boost || 0), retro: Number(g.retro || 0), side: Number(g.side || 0),
                       wheel: Number(g.wheel || 0), cars: {}}
        for (const car of (g.traffic || []))
            entry.cars[car.id] = {z: entry.d + Number(car.relativeZ), v: Number(car.speedKmh) / 3.6,
                                  lane: Number(car.lane), vy: Number(car.laneRate || 0), braking: Boolean(car.braking),
                                  signal: Number(car.signal || 0), a: Number(car.accel || 0), kind: String(car.kind || "sedan")}
        const last = k.buffer.length ? k.buffer[k.buffer.length - 1] : null
        if (!last || entry.t < last.t - 0.001 || entry.d < last.d - 25) {
            // First sample or a new drive: start over instead of sliding backwards.
            k.buffer = [entry]
            k.renderT = entry.t - drive.renderDelay
            k.leadAverage = drive.renderDelay
            k.distance = entry.d; k.lane = entry.lane; k.x = (entry.lane - 1) * 3.6; k.camX = k.x
            k.rampAt = entry.d
            for (const slot of k.slots) slot.id = -1
        } else if (entry.t > last.t + 0.001) {
            k.buffer.push(entry)
            if (k.buffer.length > 16)
                k.buffer.shift()
        } else {
            k.buffer[k.buffer.length - 1] = entry  // same plant step, e.g. a status refresh
        }
        k.target = entry.target
        // Delegates stay bound to plant car ids, so re-sorting never swaps cars.
        for (const slot of k.slots) slot.seen = false
        for (const key in entry.cars) {
            const id = Number(key)
            let slot = k.slots.find(s => s.id === id)
            if (!slot) {
                slot = k.slots.find(s => s.id < 0)
                if (!slot)
                    continue
                const style = drive.look(id, entry.cars[key].kind)
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
        const live = drive.playing && !drive.launching
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
            // The plant's quintic lane path, through its sampled lateral rates.
            k.lane = drive.hermite(s0.lane, s0.vy, s1.lane, s1.vy, h, u)
            k.laneRate = s0.vy + (s1.vy - s0.vy) * u
            k.latAccel = s0.ay + (s1.ay - s0.ay) * u
            k.wheel = s0.wheel + (s1.wheel - s0.wheel) * u
            k.alt = s0.h + (s1.h - s0.h) * u
            accel = s0.a + (s1.a - s0.a) * u
            // Rolls wrap at a full turn: never spin back from 360° to 0°.
            let roll1 = s1.roll
            while (roll1 - s0.roll > 180) roll1 -= 360
            while (roll1 - s0.roll < -180) roll1 += 360
            k.flip = s0.roll + (roll1 - s0.roll) * u
            k.lift = s0.lift + (s1.lift - s0.lift) * u
            k.jet = s0.boost + (s1.boost - s0.boost) * u
            k.retro = s0.retro + (s1.retro - s0.retro) * u
            k.side = s0.side + (s1.side - s0.side) * u
        } else {
            // Buffer underrun: coast briefly on the last acknowledged step.
            const ahead = live ? drive.clamp(k.renderT - s0.t, 0, 0.25) : 0
            k.distance = s0.d + s0.v * ahead
            k.speed = s0.v
            k.lane = s0.lane + s0.vy * ahead
            k.laneRate = s0.vy; k.latAccel = s0.ay; k.wheel = s0.wheel
            k.alt = s0.h
            k.flip = s0.roll; k.lift = s0.lift; k.jet = s0.boost; k.retro = s0.retro; k.side = s0.side
        }
        const near = s1 && u >= 0.5 ? s1 : s0
        k.accel += ((live ? accel : 0) - k.accel) * Math.min(1, dt * 10)
        k.blink = (k.clock % 0.7) < 0.38

        k.x = (k.lane - 1) * 3.6
        k.lateral = k.laneRate * 3.6
        // Heading follows the path; the flier's thrusters slide it sideways when slow.
        const yawTarget = -Math.atan2(k.lateral, Math.max(k.speed, drive.flying ? 12 : 1)) * 57.2958
        k.yaw += (drive.clamp(yawTarget, -25, 25) - k.yaw) * Math.min(1, dt * 10)
        // Suspension: nose dives under braking, squats on throttle, leans out of lane changes.
        const car = drive.egoCar
        let state = drive.spring(k.pitch, k.pitchRate, drive.clamp(-k.accel * car.dive, -3, 3.5), 85, 13, dt)
        k.pitch = state[0]; k.pitchRate = state[1]
        state = drive.spring(k.roll, k.rollRate, drive.clamp((live ? k.latAccel : 0) * car.roll, -4, 4), 70, 12, dt)
        k.roll = state[0]; k.rollRate = state[1]

        const signal = live ? near.signal : 0
        ego.x = k.x
        ego.eulerRotation = Qt.vector3d(0, 180 + k.yaw, 0)
        ego.bodyPitch = k.pitch
        ego.bodyRoll = k.roll
        ego.wheelAngle = -k.distance * 200
        ego.steerAngle = live ? -drive.clamp(k.wheel, -1, 1) * 26 : 0
        cockpit.wheel = live ? k.wheel : 0
        chaseWheel.angle = live ? k.wheel * 95 : 0
        ego.braking = live && near.braking
        ego.indicator = signal
        ego.blinkOn = k.blink
        drive.updateFlight(dt)
        highway.distance = k.distance
        // The far carriageway keeps flowing while the plant waits for the launch.
        highway.drivingTime = k.renderT + k.launchClock
        cluster.indicator = signal
        cluster.blinkOn = k.blink
        cockpit.indicator = signal
        cockpit.blinkOn = k.blink
        if (signal !== 0 && k.blink && !k.lastBlink)
            sounds.tick()
        k.lastBlink = k.blink

        drive.updateTraffic(dt, span, live)
        drive.updateCamera(dt)
        drive.updateLandingCamera()
        drive.updateOverlays()
        sounds.road(drive.launching ? drive.launchKmh / 3.6 : live ? k.speed : 0)
    }
    // Roadster pose: waiting before the ramp, up it to a stop on the ceiling, the
    // drop-and-roll, then the plant's flight: takla rolls and hops, nozzles and wing.
    function updateFlight(dt) {
        const k = drive.kin
        let alt = k.alt, flip = 0, thrust = 0, y = 0, z = 0
        if (!drive.flying) {
            k.intro = -1
        } else if (drive.choosing || drive.launching) {
            if (drive.launching) {
                k.climb += dt
                k.launchClock += dt
            } else {
                k.climb = 0
                k.intro = -1
            }
            const pose = drive.climbPose(k.climb)
            alt = 0
            y = pose.y
            z = pose.z
            ego.eulerRotation = Qt.vector3d(pose.pitch, 0, 0)
            ego.wheelAngle = -pose.distance * 200
            drive.launchKmh = pose.kmh
            k.rampAt = k.distance
        } else if (k.intro >= 0) {
            k.intro += dt
            const f = drive.clamp(k.intro / drive.introTime, 0, 1)
            const start = drive.rampCeiling - ego.height
            alt = start * (1 - f * f) + 0.9 * Math.sin(Math.PI * f) * (1 - f)
            flip = 180 + 540 * f * f * (3 - 2 * f)
            thrust = 1 - 0.4 * f
            // The plant is already at speed: drift back with the road at first, so
            // the car gathers way from rest, and be back in place on landing.
            z = k.speed * drive.introTime * f * (1 - f) * (1 - f)
            if (f >= 1)
                k.intro = -1
        } else {
            // The plant flies the car: takla roll, hop and nozzle thrust come sampled.
            flip = k.flip
            thrust = k.lift
        }
        const touchdown = drive.flying && !drive.choosing && k.renderAlt > 0.25 && alt <= 0.05
        k.renderAlt = alt
        k.wing += ((drive.flying && (alt > 0.3 || k.accel < -4) ? 1 : 0) - k.wing) * Math.min(1, dt * 4)
        ego.y = y
        ego.z = z
        ego.altitude = alt
        ego.flip = flip
        ego.thrust = thrust
        ego.boost = drive.flying && drive.playing ? k.jet : 0
        ego.retro = drive.flying && drive.playing ? k.retro : 0
        ego.side = drive.flying && drive.playing ? k.side : 0
        ego.wing = k.wing
        ramp.z = k.distance - k.rampAt - drive.rampHang
        drive.updateJets(touchdown)
    }
    // Compressed-air jets leave each firing nozzle along its axis. The scene
    // follows the car, so the air streams backwards at its speed: jets bend
    // back and trail behind, and lift jets fan out where they meet the road.
    function updateJets(touchdown) {
        const k = drive.kin, item = ego.loaded
        const nozzles = drive.flying && item && item.nozzles ? item.nozzles : null
        const live = drive.playing || k.intro >= 0
        const air = Qt.vector3d(0, 0, drive.playing ? k.speed : 0)
        const reach = ego.altitude + 0.4
        for (let i = 0; i < 4; ++i) {
            const jet = liftJets.objectAt(i), splash = splashJets.objectAt(i), rear = boostJets.objectAt(i)
            if (!jet || !splash || !rear)
                continue
            if (!nozzles) {
                jet.emitRate = splash.emitRate = rear.emitRate = 0
                continue
            }
            const n = nozzles.lift[i], b = nozzles.boost[i]
            const p = item.mapPositionToScene(Qt.vector3d(n[0], n[1], n[2]))
            const down = item.mapDirectionToScene(Qt.vector3d(0, -1, 0)).normalized()
            const lift = live ? ego.thrust : 0
            jet.position = p
            jet.velocity.direction = down.times(18).plus(air)
            jet.lifeSpan = drive.clamp(reach / 18 * 1000, 60, 420)
            jet.emitRate = lift > 0.03 ? 260 * lift : 0
            const ground = down.y < -0.5 ? drive.clamp(1.15 - ego.altitude / 10, 0, 1) : 0
            splash.position = Qt.vector3d(p.x + down.x * reach, 0.08, p.z + down.z * reach)
            splash.velocity.direction = air.plus(Qt.vector3d(0, 0.4, 0))
            splash.emitRate = lift > 0.03 ? 120 * lift * ground : 0
            if (touchdown)
                splash.burst(26, 140, splash.position)
            rear.position = item.mapPositionToScene(Qt.vector3d(b[0], b[1], b[2]))
            rear.velocity.direction = item.mapDirectionToScene(Qt.vector3d(0, 0, -1)).normalized().times(34).plus(air)
            rear.emitRate = live && ego.boost > 0.03 ? 80 * ego.boost : 0
        }
        // Nose pair: the one facing away from the push fires; both fire forward to brake.
        for (let i = 0; i < 2; ++i) {
            const jet = noseJets.objectAt(i)
            if (!jet)
                continue
            const n = nozzles ? nozzles.yaw[i] : null
            const out = n ? Math.sign(n[0]) : 0
            const push = live ? Math.max(0, out * ego.side) : 0, brake = live ? ego.retro : 0
            jet.emitRate = n && Math.max(push, brake) > 0.03 ? 70 * Math.max(push, brake) : 0
            if (!n)
                continue
            jet.position = item.mapPositionToScene(Qt.vector3d(n[0], n[1], n[2]))
            const local = Qt.vector3d(out * push, 0, brake).normalized()
            jet.velocity.direction = item.mapDirectionToScene(local).normalized().times(24).plus(air)
        }
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
            let signal, accel
            if (c0 && c1) {
                slot.z = drive.hermite(c0.z, c0.v, c1.z, c1.v, h, u)
                slot.speed = c0.v + (c1.v - c0.v) * u
                slot.braking = u < 0.5 ? c0.braking : c1.braking
                slot.lane = drive.hermite(c0.lane, c0.vy, c1.lane, c1.vy, h, u)
                slot.vx = (c0.vy + (c1.vy - c0.vy) * u) * 3.6
                signal = u < 0.5 ? c0.signal : c1.signal
                accel = c0.a + (c1.a - c0.a) * u
            } else {
                const c = c0 || c1
                const ahead = c0 && live ? drive.clamp(k.renderT - s0.t, 0, 0.25) : 0
                slot.z = c.z + c.v * ahead
                slot.speed = c.v
                slot.braking = c.braking
                slot.lane = c.lane + c.vy * ahead
                slot.vx = c.vy * 3.6
                signal = c.signal
                accel = c.a
            }
            slot.x = (slot.lane - 1) * 3.6
            if (!slot.styled) {
                car.variant = slot.variant; car.paint = slot.paint; car.metallic = slot.metallic
                slot.styled = true
            }
            const ahead = slot.z - k.distance
            car.visible = true
            car.x = slot.x
            car.z = -ahead
            car.eulerRotation = Qt.vector3d(0, 180 - drive.clamp(Math.atan2(slot.vx, Math.max(slot.speed, 1)) * 57.2958, -25, 25), 0)
            car.wheelAngle = -slot.z * 200
            car.bodyPitch = live ? drive.clamp(-accel * 0.3, -2.5, 3) : 0
            car.braking = slot.braking
            // Drivers signal before they steer and cancel as they settle in the lane.
            car.indicator = live ? signal : 0
            car.blinkOn = k.blink
            const inPath = Math.abs(slot.lane - k.lane) < 0.6 || (Math.abs(k.target - k.lane) > 0.05 && Math.abs(slot.lane - k.target) < 0.6)
            if (ahead > 2.0 && inPath && ahead < leadAhead) { lead = i; leadAhead = ahead }
            const g = drive.game
            radarCars.push({lane: slot.lane, ahead: ahead, lead: false, braking: slot.braking,
                            watched: live && (slot.id === g.sensorLeft && drive.blindLeft > 0 || slot.id === g.sensorRight && drive.blindRight > 0
                                              || slot.id === g.sensorRear && drive.rearThreat > 0)})
        }
        if (lead >= 0)
            radarCars[lead].lead = true
        k.lead = lead
        radar.egoLane = k.lane
        radar.place(radarCars)
    }
    function updateCamera(dt) {
        const k = drive.kin
        if (drive.flying && (drive.choosing || drive.launching)) {
            if (drive.choosing) {
                // Idle: redrawn at ~30 Hz, like the showroom orbit below.
                k.idle += dt
                if (k.idle < 1 / 30)
                    return
                k.orbit += k.idle * 7
                k.idle = 0
            }
            drive.spectate()
            k.camX = k.x; k.camBack = 9.2
            return
        }
        const fast = drive.clamp(k.speed / 55, 0, 1)
        const t = k.clock
        k.shake += ((drive.emergency && drive.playing ? 1 : 0) - k.shake) * Math.min(1, dt * (drive.emergency ? 10 : 2.5))
        // No continuous road vibration: high-frequency camera noise reads as a
        // shaking screen. Only emergency braking adds a short, low nudge.
        const nudge = drive.playing ? 0.025 * k.shake : 0
        const sx = Math.sin(t * 7.3) * nudge
        const sy = Math.sin(t * 9.1 + 0.7) * nudge
        const lift = drive.flying && !drive.choosing && k.intro < 0 ? k.renderAlt : 0
        const look = drive.flying && k.intro >= 0 ? k.renderAlt * 0.75 : lift * 0.9
        if (drive.hoodCamera) {
            const yaw = k.yaw * Math.PI / 180
            driveCamera.position = Qt.vector3d(k.x - Math.sin(yaw) * 0.8 + sx * 0.4, 1.3 + lift + sy * 0.5 - k.pitch * 0.006, -Math.cos(yaw) * 0.8)
            driveCamera.eulerRotation = Qt.vector3d(-3 - k.pitch * 0.35, k.yaw, -k.roll * 0.3)
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
            const radius = 8.4, height = 2.9, aim = 1.5
            driveCamera.position = Qt.vector3d(k.x + Math.sin(a) * radius, height, Math.cos(a) * radius)
            const dx = k.x - driveCamera.position.x, dz = -driveCamera.position.z, dy = aim - height
            driveCamera.eulerRotation = Qt.vector3d(Math.atan2(dy, Math.hypot(dx, dz)) * 57.2958, Math.atan2(-dx, -dz) * 57.2958, 0)
            driveCamera.fieldOfView = 52
            k.camX = k.x; k.camBack = 9.2
            return
        }
        k.orbit = 0
        k.camX += (k.x - k.camX) * Math.min(1, dt * 3.4)
        const back = 9.2 + fast * 1.4 + drive.clamp(k.accel * 0.11, -0.9, 0.35)
        k.camBack += (back - k.camBack) * Math.min(1, dt * 2.5)
        const height = 3.25 + fast * 0.35 + lift * 0.85
        const px = k.camX + sx, py = height + sy, pz = k.camBack
        const lookX = k.x * 0.7 + k.camX * 0.3, lookY = 0.3 + look, lookZ = -12
        driveCamera.position = Qt.vector3d(px, py, pz)
        driveCamera.eulerRotation = Qt.vector3d(Math.atan2(lookY - py, Math.hypot(lookX - px, lookZ - pz)) * 57.2958,
                                           Math.atan2(-(lookX - px), -(lookZ - pz)) * 57.2958,
                                           drive.clamp(-k.lateral * 0.05, -0.5, 0.5))
        driveCamera.fieldOfView = 54 + fast * 8
    }
    function aimCamera(x, y, z, aimX, aimY, aimZ, roll, fov) {
        const dx = aimX - x, dy = aimY - y, dz = aimZ - z
        driveCamera.position = Qt.vector3d(x, y, z)
        driveCamera.eulerRotation = Qt.vector3d(Math.atan2(dy, Math.hypot(dx, dz)) * 57.2958, Math.atan2(-dx, -dz) * 57.2958, roll)
        driveCamera.fieldOfView = fov
    }
    // The roadside camera: wide, on the ramp as well as the car while they are apart;
    // zoomed in on the car alone by the time it reaches the ramp.
    function spectate() {
        const k = drive.kin, s = drive.spectator
        const x = s.x, y = s.y + 0.4 * Math.sin(k.orbit * 0.03), z = s.z + 1.5 * Math.sin(k.orbit * 0.02)
        const u = drive.clamp(-ego.z / drive.rampRun, 0, 1), apart = u * u * (3 - 2 * u)
        const ramp = 0.38 * apart, fov = s.fov - 14 * (1 - apart)
        k.spectatorAt = [x, y, z, fov]
        // Aimed high enough to keep the waiting car below the start card.
        drive.aimCamera(x, y, z, k.x, ego.y + (10 - ego.y) * ramp, ego.z + (2 - ego.z) * ramp, 0, fov)
    }
    // After the release: from the roadside to the normal view, which it reaches
    // exactly as the car lands, keeping the falling car in frame on the way.
    function updateLandingCamera() {
        const k = drive.kin
        if (!drive.flying || k.intro < 0)
            return
        const f = drive.clamp(k.intro / drive.introTime, 0, 1), w = f * f * (3 - 2 * f)
        const blend = (from, to) => from + (to - from) * w
        // The aim leaves the car last, so it stays in frame while the camera swings round.
        const look = (from, to) => from + (to - from) * w * w * w
        const p = driveCamera.position, e = driveCamera.eulerRotation, from = k.spectatorAt
        const pitch = e.x * Math.PI / 180, yaw = e.y * Math.PI / 180, reach = 25
        // It comes in from the side last, rather than close past the falling car.
        drive.aimCamera(from[0] + (p.x - from[0]) * w * w, blend(from[1], p.y), blend(from[2], p.z),
                        look(k.x, p.x - Math.sin(yaw) * Math.cos(pitch) * reach),
                        look(ego.altitude + ego.height / 2, p.y + Math.sin(pitch) * reach),
                        look(ego.z, p.z - Math.cos(yaw) * Math.cos(pitch) * reach),
                        e.z * w, blend(from[3], driveCamera.fieldOfView))
    }
    function updateOverlays() {
        const k = drive.kin
        const show = drive.playing && !drive.launching && drive.mode !== "off" && !(drive.flying && k.renderAlt > 1)
        const leadCar = k.lead >= 0 ? traffic.objectAt(k.lead) : null
        const leadSlot = k.lead >= 0 ? k.slots[k.lead] : null
        const gap = leadSlot ? Math.max(0, leadSlot.z - k.distance - (leadCar.length + ego.length) / 2) : 1e9
        const want = Math.max(6, k.speed * Number(drive.game.headwayMs || 1800) / 1000)
        const span = Math.max(1.5, Math.min(want, gap, 90))
        corridor.visible = show && garage.corridor
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
        // The blind zones beside the car, from the mirror to 3 m past the bumper:
        // barely there while empty, amber with a car in them, red if steering at it.
        const levels = [drive.blindLeft, drive.blindRight], flash = pulse.lit
        for (let i = 0; i < 2; ++i) {
            const zone = blindZones.objectAt(i)
            if (!zone)
                continue
            const side = i ? 1 : -1
            zone.visible = show && garage.blindSpot && !drive.hoodCamera && (i ? k.lane < 1.6 : k.lane > 0.4)
            zone.x = k.x + side * (ego.halfWidth + 0.5 + 1.25)
            zone.z = (ego.length / 2 + 3 - 0.6) / 2
            zone.scale = Qt.vector3d(0.025, (ego.length / 2 + 3 + 0.6) / 100, 1)
            const level = levels[i], material = zone.materials[0]
            material.tint = level > 1 ? Qt.vector3d(1.0, 0.16, 0.2) : level > 0 ? Qt.vector3d(1.0, 0.62, 0.12) : Qt.vector3d(0.55, 0.75, 0.8)
            material.strength = level > 1 ? (flash ? 1.5 : 0.8) : level > 0 ? 1.1 : 0.22
        }
        const closing = leadSlot ? Math.round((k.speed - leadSlot.speed) * 3.6) : 0
        radar.relativeText = !leadSlot ? "—" : closing === 0 ? "0 km/sa" : (closing > 0 ? "−" : "+") + Math.abs(closing) + " km/sa"

        if (!show || !garage.bracket || !leadCar || gap > 140) {
            target.visible = false
            return
        }
        const half = [leadCar.halfWidth, 0.0, leadCar.length / 2]
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
        if (playing && drive.flying && !Boolean(game.launching) && Number(game.elapsed || 0) < 0.3)
            drive.kin.intro = 0
        if (playing) Qt.callLater(focusDriving)
        else if (studio) studio.releaseGameKeys()
    }
    onVisibleChanged: {
        drive.settle()
        if (!visible && studio) studio.releaseGameKeys()
    }
    onHoodCameraChanged: drive.settle()
    onSideAlertChanged: if (sideAlert) sounds.alert()
    // It lets go of the ceiling as the plant starts, with the usual render delay.
    onLaunchingChanged: {
        const k = drive.kin
        if (!launching && Boolean(game.running) && k.buffer.length) {
            k.intro = 0
            k.renderT = k.buffer[k.buffer.length - 1].t - drive.renderDelay
            k.leadAverage = drive.renderDelay
        }
    }
    Timer { id: settleTimer; interval: 2500; running: true; onTriggered: drive.settling = false }
    Component.onCompleted: {
        const slots = []
        for (let i = 0; i < 16; ++i)
            slots.push({id: -1})
        drive.kin.slots = slots
        drive.sample()
        if (studio) studio.setVehicle(drive.egoCar.id)
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
    component CarTile: Rectangle {
        id: tile
        required property var car
        readonly property bool chosen: drive.egoCar.id === tile.car.id
        objectName: "car_" + tile.car.id
        implicitHeight: 62
        radius: 10
        color: tile.chosen ? "#183634" : tileArea.containsMouse ? "#18303d" : "#112330"
        border.width: tile.chosen ? 2 : 1
        border.color: tile.chosen ? "#63dec2" : tileArea.containsMouse ? "#3c5c6c" : "#284250"
        Behavior on color { ColorAnimation { duration: 120 } }
        Accessible.role: Accessible.RadioButton
        Accessible.name: tile.car.name
        Accessible.checked: tile.chosen
        Rectangle {
            id: swatch
            anchors.left: parent.left; anchors.leftMargin: 11; anchors.verticalCenter: parent.verticalCenter
            width: 14; height: 14; radius: 7
            color: tile.car.paint; border.width: 1; border.color: "#55ffffff"
        }
        Column {
            anchors.left: swatch.right; anchors.leftMargin: 10
            anchors.right: parent.right; anchors.rightMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            spacing: 3
            Copy {
                width: parent.width; text: tile.car.name; font.pixelSize: 13; font.weight: Font.DemiBold
                wrapMode: Text.WordWrap; maximumLineCount: 2; lineHeight: 0.95
                color: tile.chosen ? "#f1f7f9" : "#c6d5de"
            }
            Copy { width: parent.width; text: tile.car.note; font.pixelSize: 11; color: tile.chosen ? "#8fc9bb" : "#7891a1" }
        }
        MouseArea {
            id: tileArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: garage.car = tile.car.id
        }
    }
    // Clickable like the car tiles: a MouseArea takes no keyboard focus, so
    // pressing these while driving never pulls focus off the road and pauses.
    component RunButton: Rectangle {
        id: run
        property string caption
        property color ink: "#63dec2"
        property bool pause: false
        property bool restart: false
        signal activated()
        implicitWidth: runRow.implicitWidth + 28; implicitHeight: 34
        radius: 8
        color: !run.enabled ? "#18232e" : runArea.containsMouse ? Qt.lighter(run.ink, 1.12) : run.ink
        Behavior on color { ColorAnimation { duration: 100 } }
        Accessible.role: Accessible.Button
        Accessible.name: run.caption
        Accessible.onPressAction: run.activated()
        Row {
            id: runRow
            anchors.centerIn: parent; spacing: 8
            Item {
                width: 11; height: 12; anchors.verticalCenter: parent.verticalCenter
                Rectangle { visible: run.pause; width: 4; height: 12; radius: 1; color: runText.color }
                Rectangle { visible: run.pause; x: 7; width: 4; height: 12; radius: 1; color: runText.color }
                Text { visible: !run.pause; anchors.centerIn: parent; text: run.restart ? "↺" : "▶︎"; color: runText.color; font.pixelSize: run.restart ? 14 : 11 }
            }
            Copy { id: runText; text: run.caption; color: run.enabled ? "#10251f" : "#637684"; font.weight: Font.Bold; font.letterSpacing: 0.8 }
        }
        MouseArea {
            id: runArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: run.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: run.activated()
        }
    }
    component IndicatorSwitch: Rectangle {
        id: toggle
        property string caption
        property string detail
        property bool checked: false
        signal toggled()
        implicitWidth: toggleRow.implicitWidth + 22; implicitHeight: 28
        radius: 8
        color: toggleArea.containsMouse ? "#18303d" : "#142430"
        border.color: toggle.checked ? "#3a7f72" : "#27404f"
        Accessible.role: Accessible.CheckBox
        Accessible.name: toggle.caption
        Accessible.description: toggle.detail
        Accessible.checkable: true
        Accessible.checked: toggle.checked
        Accessible.onToggleAction: toggle.toggled()
        Row {
            id: toggleRow
            anchors.centerIn: parent; spacing: 8
            Rectangle {
                width: 22; height: 12; radius: 6; anchors.verticalCenter: parent.verticalCenter
                color: toggle.checked ? "#3fbfa6" : "#2a3d4b"
                Rectangle {
                    x: toggle.checked ? 12 : 2; y: 2; width: 8; height: 8; radius: 4
                    color: toggle.checked ? "#eafff9" : "#8aa2b1"
                    Behavior on x { NumberAnimation { duration: 90 } }
                }
            }
            Copy { text: toggle.caption; color: toggle.checked ? "#e5edf3" : "#8aa5b6"; font.pixelSize: 11; font.weight: Font.DemiBold; anchors.verticalCenter: parent.verticalCenter }
        }
        MouseArea {
            id: toggleArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: toggle.toggled()
        }
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
            Chip {
                objectName: "flightLayer"
                visible: drive.flying
                caption: "UÇUŞ " + (["YOL", "4 m", "9 m"][Number(drive.game.layer || 0)] || "YOL")
                ink: "#86c8ff"; lit: Number(drive.game.layer || 0) > 0
            }
            Rectangle {
                // Thruster air: 600 L at 700 bar, spent at thrust / exhaust velocity, refilled on the road.
                id: airGauge
                objectName: "airGauge"
                visible: drive.flying
                readonly property real level: Number(drive.game.airFull) > 0 ? drive.clamp(Number(drive.game.air) / Number(drive.game.airFull), 0, 1) : 1
                readonly property color ink: airGauge.level < 0.25 ? "#ff8a5c" : airGauge.level < 0.45 ? "#ffc35c" : "#86c8ff"
                implicitWidth: airRow.implicitWidth + 26; implicitHeight: 31
                radius: 8; color: "#142430"; border.color: "#27404f"
                Row {
                    id: airRow
                    anchors.centerIn: parent; spacing: 8
                    Copy { text: "HAVA"; color: airGauge.ink; font.pixelSize: 11; font.weight: Font.DemiBold; font.letterSpacing: 0.6 }
                    Rectangle {
                        width: 58; height: 6; radius: 3; color: "#26ffffff"; anchors.verticalCenter: parent.verticalCenter
                        Rectangle { width: parent.width * airGauge.level; height: parent.height; radius: 3; color: airGauge.ink }
                    }
                    Copy {
                        text: Math.round(Number(drive.game.air || 0)) + " kg"; color: "#c6d6e0"; font.pixelSize: 11
                        font.features: { "tnum": 1 }
                    }
                }
            }
            Item { Layout.fillWidth: true }
            // The flying car's two gauges fill a narrow row; a wider one would widen the whole page.
            Copy { visible: !(viewport.compact && drive.flying); text: "AYARLAR SAATTEN"; color: "#748f9e"; font.pixelSize: 10; font.letterSpacing: 1 }
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
                else if (event.key === Qt.Key_Escape) {
                    if (!event.isAutoRepeat) drive.studio.pauseGame()
                    event.accepted = true
                } else if (event.key === Qt.Key_C) {
                    if (!event.isAutoRepeat) drive.hoodCamera = !drive.hoodCamera
                    event.accepted = true
                } else if (event.key === Qt.Key_V) {
                    if (!event.isAutoRepeat) garage.corridor = garage.bracket = garage.blindSpot = !(garage.corridor || garage.bracket || garage.blindSpot)
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
                    skyBoxCubeMap: CubeMapTexture { id: skyMap; source: "assets/sky/sky_%p.jpg" }
                    lightProbe: Texture { id: skyProbe; source: "assets/sky/probe.hdr" }
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
                        enabled: true; color: "#d4dbeb"
                        depthEnabled: true; depthNear: 70; depthFar: 720; depthCurve: 0.85; density: 0.92
                    }
                }
                PerspectiveCamera {
                    id: driveCamera
                    objectName: "driveCamera"
                    position: Qt.vector3d(0, 3.1, 8.6)
                    eulerRotation.x: -11
                    clipNear: 0.25; clipFar: 1600; fieldOfView: 56
                }
                DirectionalLight {
                    eulerRotation: Qt.vector3d(-48, -32, 0)
                    color: "#fff2df"; brightness: 1.55
                    ambientColor: "#1a2128"
                    castsShadow: true
                    // The mirrors render the scene and its shadows again: lighter from the seat.
                    shadowMapQuality: viewport.pilot ? Light.ShadowMapQualityHigh : Light.ShadowMapQualityVeryHigh
                    shadowMapFar: viewport.pilot ? 140 : 240
                    csmNumSplits: viewport.pilot ? 0 : 2; csmSplit1: 0.12; csmSplit2: 0.4; csmBlendRatio: 0.08
                    lockShadowmapTexels: true
                    shadowFactor: 72; shadowBias: 0.012
                    softShadowQuality: Light.PCF16; pcfFactor: 1.6
                }
                Highway3D { id: highway }
                Vehicle3D {
                    id: ego
                    objectName: "egoVehicle3D"
                    variant: drive.egoCar.variant; paint: drive.egoCar.paint; metallic: drive.egoCar.metallic
                    lamps: 0.45
                }
                Repeater3D {
                    id: traffic
                    model: 16
                    delegate: Vehicle3D { visible: false; lamps: 0.4 }
                }
                Node {
                    // The J launch ramp of the reveal on our lane, left behind at the start.
                    id: ramp
                    objectName: "launchRamp"
                    visible: drive.flying && z < 90
                    PrincipledMaterial { id: rampMaterial; baseColor: "#8f9498"; roughness: 0.82 }
                    PrincipledMaterial {
                        id: rampEdgeMaterial
                        baseColor: "#ff3b3b"; roughness: 0.4
                        emissiveFactor: Qt.vector3d(1.6, 0.12, 0.1)
                    }
                    PrincipledMaterial { id: rampLineMaterial; baseColor: "#f2f2ee"; roughness: 0.5 }
                    PrincipledMaterial { id: rampMarkMaterial; baseColor: "#202326"; roughness: 0.9 }
                    PrincipledMaterial { id: trussMaterial; baseColor: "#a7adb3"; metalness: 0.85; roughness: 0.35 }
                    Repeater3D {
                        model: drive.rampSegments
                        delegate: Model {
                            required property var modelData
                            source: "#Cube"
                            position: Qt.vector3d(0, modelData[1], modelData[0])
                            eulerRotation.x: modelData[2]
                            scale: Qt.vector3d(drive.rampWidth / 100, 0.0018, modelData[3] / 100)
                            materials: rampMaterial
                        }
                    }
                    Repeater3D {
                        // Red edge lines on both sides of the deck.
                        model: drive.rampSegments.length * 2
                        delegate: Model {
                            required property int index
                            readonly property var segment: drive.rampSegments[index >> 1]
                            source: "#Cube"
                            castsShadows: false
                            position: Qt.vector3d((index & 1 ? 1 : -1) * (drive.rampWidth / 2 - 0.14), segment[5], segment[4])
                            eulerRotation.x: segment[2]
                            scale: Qt.vector3d(0.0012, 0.0002, segment[3] / 100)
                            materials: rampEdgeMaterial
                        }
                    }
                    Repeater3D {
                        // Dashed white centre line.
                        model: drive.rampSegments.filter(segment => segment[6] % 3 !== 0)
                        delegate: Model {
                            required property var modelData
                            source: "#Cube"
                            castsShadows: false
                            position: Qt.vector3d(0, modelData[5], modelData[4])
                            eulerRotation.x: modelData[2]
                            scale: Qt.vector3d(0.0012, 0.0002, modelData[3] / 100)
                            materials: rampLineMaterial
                        }
                    }
                    Repeater3D {
                        // Tyre marks on the ceiling where the car drove up and stopped.
                        model: [-0.86, 0.86]
                        delegate: Model {
                            required property real modelData
                            source: "#Cube"
                            position: Qt.vector3d(modelData, drive.rampCeiling - 0.004, -1.55)
                            scale: Qt.vector3d(0.0028, 0.0001, 0.031)
                            castsShadows: false
                            materials: rampMarkMaterial
                        }
                    }
                    // Steel scaffold beside the deck: three column pairs, rails every
                    // 1.6 m, X braces behind the wall and beams over the ceiling.
                    Repeater3D {
                        model: [[-2.6, -3.0], [2.6, -3.0], [-2.6, 0.5], [2.6, 0.5], [-2.6, 4.3], [2.6, 4.3]]
                        delegate: Model {
                            required property var modelData
                            source: "#Cube"
                            position: Qt.vector3d(modelData[0], 4.8, modelData[1])
                            scale: Qt.vector3d(0.0022, 0.096, 0.0022)
                            materials: trussMaterial
                        }
                    }
                    Repeater3D {
                        model: 12
                        delegate: Model {
                            required property int index
                            source: "#Cube"
                            position: Qt.vector3d(index % 2 ? 2.6 : -2.6, 1.6 + 1.6 * (index >> 1), 0.65)
                            scale: Qt.vector3d(0.0014, 0.0014, 0.073)
                            materials: trussMaterial
                        }
                    }
                    Repeater3D {
                        model: 24
                        delegate: Model {
                            required property int index
                            readonly property int bay: index >> 2
                            source: "#Cube"
                            position: Qt.vector3d(index & 1 ? 2.6 : -2.6, 0.8 + 1.6 * bay, 2.4)
                            eulerRotation.x: (index & 2 ? 1 : -1) * 22.8
                            scale: Qt.vector3d(0.0011, 0.0011, 0.0413)
                            materials: trussMaterial
                        }
                    }
                    Repeater3D {
                        model: [-3.0, 0.5, 4.3]
                        delegate: Model {
                            required property real modelData
                            source: "#Cube"
                            position: Qt.vector3d(0, 9.55, modelData)
                            scale: Qt.vector3d(0.054, 0.0022, 0.0022)
                            materials: trussMaterial
                        }
                    }
                }
                ParticleSystem3D {
                    // The Taklacı Güvercin's compressed-air jets (driven by updateJets):
                    // condensing moisture shows as quick white billows that thin out.
                    id: jets
                    objectName: "airJets"
                    visible: drive.flying
                    running: drive.flying && drive.visible
                    SpriteParticle3D {
                        id: jetPuff
                        sprite: Texture { source: "assets/fx/jet_puff.png" }
                        colorTable: Texture { source: "assets/fx/jet_life.png" }
                        particleScale: 1
                        maxAmount: 1600
                        billboard: true
                        sortMode: Particle3D.SortDistance
                        colorVariation: Qt.vector4d(0.02, 0.02, 0.02, 0.2)
                    }
                    SpriteParticle3D {
                        id: roadPuff
                        sprite: Texture { source: "assets/fx/jet_puff.png" }
                        colorTable: Texture { source: "assets/fx/jet_life.png" }
                        particleScale: 1
                        maxAmount: 900
                        billboard: true
                        sortMode: Particle3D.SortDistance
                        color: "#c4eef1f3"
                    }
                    Repeater3D {
                        id: liftJets
                        model: 4
                        delegate: ParticleEmitter3D {
                            system: jets
                            particle: jetPuff
                            emitRate: 0
                            lifeSpan: 160; lifeSpanVariation: 40
                            particleScale: 0.22; particleEndScale: 1.25
                            particleScaleVariation: 0.06; particleEndScaleVariation: 0.35
                            particleRotationVariation: Qt.vector3d(0, 0, 180)
                            particleRotationVelocityVariation: Qt.vector3d(0, 0, 120)
                            velocity: VectorDirection3D { directionVariation: Qt.vector3d(2.5, 2.5, 2.5) }
                        }
                    }
                    Repeater3D {
                        id: splashJets
                        model: 4
                        delegate: ParticleEmitter3D {
                            system: jets
                            particle: roadPuff
                            emitRate: 0
                            lifeSpan: 900; lifeSpanVariation: 250
                            particleScale: 0.5; particleEndScale: 2.6; particleEndScaleVariation: 0.8
                            particleRotationVariation: Qt.vector3d(0, 0, 180)
                            particleRotationVelocityVariation: Qt.vector3d(0, 0, 40)
                            shape: ParticleShape3D { type: ParticleShape3D.Sphere; extents: Qt.vector3d(0.25, 0.02, 0.25) }
                            velocity: VectorDirection3D { directionVariation: Qt.vector3d(6, 0.35, 6) }
                        }
                    }
                    Repeater3D {
                        id: noseJets
                        model: 2
                        delegate: ParticleEmitter3D {
                            system: jets
                            particle: jetPuff
                            emitRate: 0
                            lifeSpan: 220; lifeSpanVariation: 50
                            particleScale: 0.1; particleEndScale: 0.6; particleEndScaleVariation: 0.15
                            particleRotationVariation: Qt.vector3d(0, 0, 180)
                            velocity: VectorDirection3D { directionVariation: Qt.vector3d(2, 2, 2) }
                        }
                    }
                    Repeater3D {
                        id: boostJets
                        model: 4
                        delegate: ParticleEmitter3D {
                            system: jets
                            particle: jetPuff
                            emitRate: 0
                            lifeSpan: 320; lifeSpanVariation: 60
                            particleScale: 0.12; particleEndScale: 0.95; particleEndScaleVariation: 0.25
                            particleRotationVariation: Qt.vector3d(0, 0, 180)
                            particleRotationVelocityVariation: Qt.vector3d(0, 0, 90)
                            velocity: VectorDirection3D { directionVariation: Qt.vector3d(2.5, 2.5, 2.5) }
                        }
                    }
                }
                Repeater3D {
                    id: blindZones
                    model: 2
                    delegate: Model {
                        required property int index
                        objectName: index ? "blindZoneRight" : "blindZoneLeft"
                        source: "#Rectangle"
                        visible: false
                        y: 0.032
                        eulerRotation.x: -90
                        castsShadows: false; receivesShadows: false
                        materials: CustomMaterial {
                            shadingMode: CustomMaterial.Unshaded
                            vertexShader: "shaders/corridor.vert"
                            fragmentShader: "shaders/zone.frag"
                            sourceBlend: CustomMaterial.SrcAlpha
                            destinationBlend: CustomMaterial.OneMinusSrcAlpha
                            property real strength: 0.2
                            property vector3d tint: Qt.vector3d(0.55, 0.75, 0.8)
                        }
                    }
                }
                Node {
                    id: corridor
                    objectName: "followCorridor"
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

            // The pilot camera's seat: dashboard, steering wheel and wing mirrors.
            readonly property bool pilot: drive.hoodCamera && (drive.playing || drive.game.status === "paused") && !drive.launching
            DriveCockpit {
                id: cockpit
                anchors.fill: parent
                visible: viewport.pilot
                ink: (drive.assistBits & 3) || (drive.assistBits & 16) ? "#63dec2" : (drive.assistBits & 32) ? "#ffc35c" : "#c8d4dc"
            }
            DriveMirror {
                id: leftMirror
                side: -1
                world: scene.scene; sky: skyMap; probe: skyProbe
                visible: viewport.pilot
                anchors.left: parent.left; anchors.leftMargin: 16; y: 62
                width: 262 * viewport.ui; height: 124 * viewport.ui
                level: drive.blindLeft; flash: pulse.lit
                carX: ego.x; carHalfWidth: ego.halfWidth; carYaw: ego.eulerRotation.y - 180
            }
            DriveMirror {
                id: rightMirror
                side: 1
                world: scene.scene; sky: skyMap; probe: skyProbe
                visible: viewport.pilot
                anchors.right: parent.right; anchors.rightMargin: 16; y: viewport.compact ? 62 : 88
                width: 262 * viewport.ui; height: 124 * viewport.ui
                level: drive.blindRight; flash: pulse.lit
                carX: ego.x; carHalfWidth: ego.halfWidth; carYaw: ego.eulerRotation.y - 180
            }
            // Beside the follow camera's road drawings: the wheel and the lamps at a glance.
            Item {
                objectName: "chaseSteering"
                visible: drive.playing && !viewport.pilot && !drive.launching && garage.blindSpot && drive.mode !== "off"
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom; anchors.bottomMargin: 14
                width: 210; height: 62
                scale: viewport.ui; transformOrigin: Item.Bottom
                Repeater {
                    model: [-1, 1]
                    delegate: Rectangle {
                        required property int modelData
                        readonly property int level: modelData < 0 ? drive.blindLeft : drive.blindRight
                        x: modelData < 0 ? 0 : parent.width - width
                        anchors.verticalCenter: parent.verticalCenter
                        width: 62; height: 26; radius: 7
                        color: level > 1 ? (pulse.lit ? "#ff4a58" : "#7a2730") : level > 0 ? "#ffb52e" : "#a80a1219"
                        border.width: 1; border.color: level > 0 ? "transparent" : "#22ffffff"
                        Text {
                            anchors.centerIn: parent
                            text: modelData < 0 ? "◀ SOL" : "SAĞ ▶"
                            color: parent.level > 0 ? "#1b1006" : "#6f8796"
                            font.pixelSize: 10; font.weight: Font.Bold
                        }
                    }
                }
                DriveSteering {
                    id: chaseWheel
                    anchors.centerIn: parent
                    width: 62; height: 62
                    ink: (drive.assistBits & 3) || (drive.assistBits & 16) ? "#63dec2" : "#d6e1e8"
                    rimColor: "#d90a1219"; spokeColor: "#e60a1219"
                }
            }

            // Edge glow for collision warnings and emergency braking.
            Item {
                id: edgeGlow
                anchors.fill: parent
                visible: opacity > 0.01
                opacity: drive.playing && drive.emergency ? (pulse.lit ? 0.8 : 0.35) : drive.playing && drive.warning ? (pulse.lit ? 0.45 : 0.2) : 0
                Behavior on opacity { NumberAnimation { duration: 120 } }
                readonly property color ink: drive.emergency ? "#ff2e45" : "#ffae2e"
                Timer { id: pulse; property bool lit: true; interval: drive.emergency ? 160 : drive.sideAlert ? 220 : 380; repeat: true; running: drive.playing && (drive.emergency || drive.warning || drive.sideAlert); onTriggered: lit = !lit }
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

            // Lane keeping, blind spot and rear systems at work.
            Rectangle {
                objectName: "aroundBanner"
                visible: drive.aroundNote !== null && !drive.launching
                anchors.top: parent.top; anchors.horizontalCenter: parent.horizontalCenter
                anchors.topMargin: drive.emergency || drive.warning ? 122 : 66
                width: aroundRow.implicitWidth + 36; height: 38; radius: 10
                color: "#dc0a1219"; border.width: 2
                border.color: drive.aroundNote ? drive.aroundNote[2] : "transparent"
                scale: viewport.ui
                Row {
                    id: aroundRow; anchors.centerIn: parent; spacing: 8
                    Copy {
                        objectName: "aroundText"
                        text: drive.aroundNote ? drive.aroundNote[0] : ""
                        color: drive.aroundNote ? drive.aroundNote[2] : "transparent"
                        font.weight: Font.Bold; font.pixelSize: 14; font.letterSpacing: 0.8; anchors.verticalCenter: parent.verticalCenter
                    }
                    Copy { text: drive.aroundNote ? drive.aroundNote[1] : ""; color: "#b8c8d2"; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                }
            }

            // A refused landing: the lane below is taken.
            Rectangle {
                objectName: "landingBlocked"
                visible: drive.playing && Boolean(drive.game.landingBlocked) && !(drive.emergency || drive.warning)
                anchors.top: parent.top; anchors.horizontalCenter: parent.horizontalCenter; anchors.topMargin: 66
                width: landingRow.implicitWidth + 40; height: 44; radius: 12
                color: "#e63a2a08"; border.width: 2; border.color: "#ffc35c"
                scale: viewport.ui
                Row {
                    id: landingRow; anchors.centerIn: parent; spacing: 10
                    Copy { text: "İNİŞ ŞERİDİ DOLU"; color: "#ffc35c"; font.weight: Font.Bold; font.pixelSize: 16; font.letterSpacing: 1; anchors.verticalCenter: parent.verticalCenter }
                    Copy { text: "· şerit değiştir veya bekle"; color: "#d9c39a"; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                }
            }

            // Thruster air: a refused climb, or the reserve flying the car down.
            Rectangle {
                objectName: "airBanner"
                visible: drive.playing && drive.flying && (Boolean(drive.game.autoLand) || Boolean(drive.game.airLow))
                         && !Boolean(drive.game.landingBlocked) && !(drive.emergency || drive.warning)
                anchors.top: parent.top; anchors.horizontalCenter: parent.horizontalCenter; anchors.topMargin: 66
                width: airBannerRow.implicitWidth + 40; height: 44; radius: 12
                color: "#e63a2a08"; border.width: 2; border.color: "#ffc35c"
                scale: viewport.ui
                Row {
                    id: airBannerRow; anchors.centerIn: parent; spacing: 10
                    Copy {
                        text: drive.game.autoLand ? "HAVA AZALDI · OTOMATİK İNİŞ" : "HAVA TÜPÜ AZ"
                        color: "#ffc35c"; font.weight: Font.Bold; font.pixelSize: 16; font.letterSpacing: 1; anchors.verticalCenter: parent.verticalCenter
                    }
                    Copy {
                        text: drive.game.autoLand ? "· yedek hava inişe ayrıldı" : "· yolda sürerken dolar"
                        color: "#d9c39a"; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }

            DriveCluster {
                id: cluster
                anchors.left: parent.left; anchors.bottom: parent.bottom; anchors.margins: 14
                transformOrigin: Item.BottomLeft
                scale: viewport.ui
                speedKmh: drive.launching ? drive.launchKmh : Number(drive.game.egoKmh || 0)
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
                // The plant has not started on the ramp: nothing true to show yet.
                visible: garage.sensors && !drive.launching && !(viewport.pilot && viewport.compact)
                blindLeft: drive.blindLeft; blindRight: drive.blindRight; rearThreat: drive.rearThreat
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
                // Level with the status pill, clear of the showroom car below.
                anchors.top: parent.top; anchors.topMargin: viewport.compact ? 64 * viewport.ui : 16
                transformOrigin: Item.Top
                width: Math.min(560, parent.width - 64); height: card.implicitHeight + 46
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
                    Column {
                        objectName: "carPicker"
                        visible: drive.choosing
                        width: parent.width; spacing: 8
                        Copy { text: "ARACINI SEÇ"; color: "#7590a1"; font.pixelSize: 10; font.weight: Font.DemiBold; font.letterSpacing: 1.2 }
                        Row {
                            width: parent.width; spacing: 10
                            Repeater {
                                model: drive.cars
                                delegate: CarTile {
                                    required property var modelData
                                    car: modelData
                                    width: (parent.width - 20) / 3
                                }
                            }
                        }
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
                        text: !drive.available ? "Üstteki Bağlan düğmesiyle ADASLab yüklü saati bağla. Ardından BAŞLAT’a burada veya saatte dokun."
                              : drive.flying && drive.choosing ? "Taklacı Güvercin, tanıtımdaki J rampanın önünde bekliyor. BAŞLAT’a burada veya saatte dokun; rampaya tırmanır, tavanda durur ve iticileriyle takla atarak yola iner."
                              : "Modu ve ACC ayarını saatten seç. BAŞLAT’a burada veya saatte dokun."
                    }
                    Row {
                        spacing: 10
                        RunButton {
                            objectName: "driveStartButton"
                            visible: drive.available
                            enabled: !drive.busy
                            caption: drive.game.status === "paused" ? "DEVAM ET" : drive.finished ? "YENİ SÜRÜŞ" : "BAŞLAT"
                            onActivated: if (enabled) drive.studio.requestGameStart()
                        }
                        // The paused road can be left for the car picker without having to crash.
                        RunButton {
                            objectName: "driveChooseCarButton"
                            visible: drive.game.status === "paused"
                            enabled: !drive.busy
                            caption: "YENİDEN BAŞLAT · ARAÇ SEÇ"
                            ink: "#b6c9d5"
                            restart: true
                            onActivated: if (enabled) drive.studio.chooseNewCar()
                        }
                    }
                    Flow {
                        width: parent.width; spacing: 14
                        Keycap { keys: "W ↑"; label: "Gaz" }
                        Keycap { keys: "S ↓ ␣"; label: "Fren" }
                        Keycap { keys: "A D"; label: "Direksiyon" }
                        Keycap { keys: "Q E"; label: "Sinyal" }
                        Keycap { keys: "Z X"; label: "Takla"; visible: drive.flying }
                        Keycap { keys: "R F"; label: "Yüksel / alçal"; visible: drive.flying }
                        Keycap { keys: "C"; label: drive.hoodCamera ? "Pilot kamerası" : "Takip kamerası" }
                        Keycap { keys: "Esc"; label: "Duraklat" }
                    }
                }
            }
        }
        RowLayout {
            objectName: "indicatorSwitches"
            Layout.fillWidth: true; spacing: 8
            Copy { text: "GÖSTERGELER"; color: "#748f9e"; font.pixelSize: 10; font.letterSpacing: 1; Layout.rightMargin: 4 }
            IndicatorSwitch {
                objectName: "indicatorCorridor"
                caption: "Koridor"; detail: "Yoldaki takip mesafesi şeridi"
                checked: garage.corridor
                onToggled: garage.corridor = !garage.corridor
            }
            IndicatorSwitch {
                objectName: "indicatorBracket"
                caption: "Çerçeve"; detail: "Öndeki aracın çerçevesi, mesafesi ve TTC"
                checked: garage.bracket
                onToggled: garage.bracket = !garage.bracket
            }
            IndicatorSwitch {
                objectName: "indicatorBlindSpot"
                caption: "Kör nokta"; detail: "Aracın iki yanında yola çizilen kör nokta bölgeleri"
                checked: garage.blindSpot
                onToggled: garage.blindSpot = !garage.blindSpot
            }
            IndicatorSwitch {
                objectName: "indicatorSensors"
                caption: "Sensör"; detail: "Sağ alttaki kuşbakışı araç haritası"
                checked: garage.sensors
                onToggled: garage.sensors = !garage.sensors
            }
            // Otherwise the first two switches look broken: ADAS off draws neither.
            Copy { Layout.fillWidth: true; Layout.leftMargin: 4; text: drive.mode === "off" ? "ADAS kapalıyken yol çizimleri görünmez" : ""; color: "#6d8b9d"; font.pixelSize: 11 }
            // As tall as the switches, so the 3D view keeps its size when this hides.
            RunButton {
                objectName: "drivePauseButton"
                visible: drive.playing
                caption: "DURAKLAT"; pause: true; ink: "#ffc35c"
                implicitHeight: 28
                onActivated: drive.studio.pauseGame()
            }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 16
            Keycap { keys: "WASD"; label: "Sür" }
            Keycap { keys: "Q E"; label: "Sinyal"; active: Number(drive.game.egoSignal || 0) !== 0 }
            Keycap { keys: "␣"; label: "Fren" }
            Keycap { keys: "Esc"; label: "Duraklat" }
            Keycap { keys: "C"; label: "Kamera"; active: drive.hoodCamera }
            Keycap { keys: "V"; label: "Yol çizimleri"; active: garage.corridor || garage.bracket || garage.blindSpot }
            Keycap { keys: "M"; label: drive.soundOn ? "Ses açık" : "Ses kapalı"; active: drive.soundOn }
            Keycap { keys: "R F"; label: "Uçuş katmanı"; visible: drive.flying; active: Number(drive.game.layer || 0) > 0 }
            Keycap { keys: "Z X"; label: "Takla"; visible: drive.flying }
            Item { Layout.fillWidth: true }
        }
    }

    // Warning chimes, relay ticks and a speed-dependent tyre/wind bed.
    MediaDevices { id: mediaDevices }
    Item {
        id: sounds
        readonly property bool available: mediaDevices.audioOutputs.length > 0
        readonly property bool audible: drive.soundOn && drive.visible && available
        function tick() { if (sounds.audible) tickSound.play() }
        function alert() { if (sounds.audible) blindSound.play() }
        function road(speed) {
            const level = sounds.audible && drive.playing ? 0.05 + 0.4 * Math.pow(drive.clamp(speed / 55, 0, 1), 1.4) : 0
            bedSound.volume = level
            if (level > 0 && !bedSound.playing) bedSound.play()
            else if (level === 0 && bedSound.playing) bedSound.stop()
        }
        SoundEffect { id: fcwSound; source: sounds.available ? "assets/sounds/fcw.wav" : ""; volume: 0.5 }
        SoundEffect { id: aebSound; source: sounds.available ? "assets/sounds/aeb.wav" : ""; volume: 0.6 }
        SoundEffect { id: tickSound; source: sounds.available ? "assets/sounds/indicator.wav" : ""; volume: 0.3 }
        SoundEffect { id: blindSound; source: sounds.available ? "assets/sounds/fcw.wav" : ""; volume: 0.3 }
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
