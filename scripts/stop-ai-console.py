"""Send a graceful interrupt only to an explicitly approved Windows console."""
from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from ctypes import wintypes


def interrupt(pid: int, approved: dict[int, str]) -> None:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handles = []

    def verify(process_id: int) -> None:
        handle = kernel.OpenProcess(0x1000, False, process_id)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        handles.append(handle)
        path = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(path))
        if not kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        if os.path.normcase(path.value) != os.path.normcase(approved[process_id]):
            raise RuntimeError("Process executable changed; interrupt refused")

    try:
        verify(pid)
        kernel.FreeConsole()
        if not kernel.AttachConsole(pid):
            raise ctypes.WinError(ctypes.get_last_error())
        members = (wintypes.DWORD * 1024)()
        count = kernel.GetConsoleProcessList(members, len(members))
        if not count or count > len(members):
            raise RuntimeError("Cannot validate console membership")
        others = set(members[:count]) - {os.getpid()}
        if pid not in others or not others.issubset(approved):
            raise RuntimeError("Console contains an unrelated process; interrupt refused")
        for member in others - {pid}:
            verify(member)
        if not kernel.SetConsoleCtrlHandler(None, True):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.GenerateConsoleCtrlEvent(0, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        time.sleep(0.2)
    finally:
        kernel.FreeConsole()
        for handle in handles:
            kernel.CloseHandle(handle)


if __name__ == "__main__":
    with open(sys.argv[2], encoding="utf-8-sig") as source:
        approved_paths = {int(p["pid"]): p["path"] for p in json.load(source)}
    interrupt(int(sys.argv[1]), approved_paths)
