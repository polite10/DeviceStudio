"""Bring an explicitly opened Studio window to the foreground on each desktop."""
import ctypes
import sys


def activate_window(window):
    window.raise_()
    if sys.platform == 'darwin':
        # QWindow.requestActivate does not activate a background Python app on
        # macOS. Explicit app launch and QA actions activate this process once;
        # background telemetry never calls this helper.
        objc = ctypes.CDLL('/usr/lib/libobjc.A.dylib')
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        pointer_call = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(('objc_msgSend', objc))
        bool_call = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool)(('objc_msgSend', objc))
        application = pointer_call(objc.objc_getClass(b'NSApplication'), objc.sel_registerName(b'sharedApplication'))
        bool_call(application, objc.sel_registerName(b'activateIgnoringOtherApps:'), True)
    window.requestActivate()
