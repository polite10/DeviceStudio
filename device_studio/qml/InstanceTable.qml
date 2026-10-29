import QtQuick
import QtQuick3D

// Static instancing table built once from plain rows:
// {p: [x, y, z], s: [sx, sy, sz], r: [rx, ry, rz], c: [r, g, b]} in metres/degrees.
InstanceList {
    id: table
    property var rows: []
    property Component entry: Component { InstanceListEntry {} }

    function rebuild() {
        const old = Array.from(table.instances)
        const entries = []
        for (const row of table.rows) {
            const s = row.s || [1, 1, 1], r = row.r || [0, 0, 0], c = row.c || [1, 1, 1]
            entries.push(table.entry.createObject(table, {
                position: Qt.vector3d(row.p[0], row.p[1], row.p[2]),
                scale: Qt.vector3d(s[0], s[1], s[2]),
                eulerRotation: Qt.vector3d(r[0], r[1], r[2]),
                color: Qt.rgba(c[0], c[1], c[2], 1)
            }))
        }
        table.instances = entries
        for (const entry of old)
            entry.destroy()
    }
    onRowsChanged: rebuild()
    Component.onCompleted: rebuild()
}
