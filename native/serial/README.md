# Native USB transport

`NativeSerial` is a small Godot GDExtension, built with the official MIT-licensed `godot-cpp` SDK (`godot-4.5-stable`, compatible with the tested Godot 4.7.2 runtime). The checked macOS library is an Apple Silicon release build. It links only platform C/C++ libraries.

Godot owns the complete runtime. `native_host.gd` calls this API from one worker, never the rendering thread. The extension enumerates serial ports, opens 115200 8N1, writes bounded command bytes and reads with a bounded wait. macOS uses `TIOCEXCL`; a second process cannot open the active port. `native_host.gd` owns protocol framing, sequence validation and timeouts. It reads configuration from the watch instead of sending PC settings during normal play.

Build with `tools/build_standalone.py`; SCons profile enables the required RefCounted/OS bindings. Platform source branches for POSIX and Windows exist, but only macOS Apple Silicon has been built and exercised in this task. SDK and release-template caches stay under ignored `.tools/`; generated `.app` bundles stay under ignored `dist/`.
