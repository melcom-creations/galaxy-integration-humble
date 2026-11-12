import os
import logging
import difflib
import ctypes
from ctypes import wintypes
from functools import lru_cache
from pathlib import Path, PurePath
from typing import List, Union, Sequence, Optional
from typing import cast


class PathFinder:
    def __init__(self, is_windows: bool):
        self.is_windows = is_windows

    def find_executables(self, path: Union[str, os.PathLike]) -> List[str]:
        folder = Path(path)

        if not folder.exists():
            raise FileNotFoundError(f'Pathfinder: {path} does not exist')
        execs: List[str] = []
        for root, _, files in os.walk(folder):
            for path in files:
                whole_path = os.path.join(root, path)
                if self.is_exe(whole_path):
                    execs.append(whole_path)
            break
        return execs

    def is_exe(self, path: str) -> bool:
        if self.is_windows:
            return path.endswith('.exe')
        else:
            return os.access(path, os.X_OK)

    def executable_titles(self, path: Union[str, os.PathLike]) -> Sequence[str]:
        """Read Windows product titles without running the executable."""
        if not self.is_windows:
            return ()
        try:
            file = Path(path).resolve()
            info = file.stat()
            return self._windows_executable_titles(str(file), info.st_mtime_ns, info.st_size)
        except OSError:
            return ()

    @staticmethod
    @lru_cache(maxsize=512)
    def _windows_executable_titles(path: str, modified: int, file_size: int) -> Sequence[str]:
        # File timestamps and size invalidate cached titles as an archive is extracted.
        version = ctypes.WinDLL('version', use_last_error=True)
        size_of = version.GetFileVersionInfoSizeW
        size_of.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        size_of.restype = wintypes.DWORD
        read = version.GetFileVersionInfoW
        read.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        read.restype = wintypes.BOOL
        query = version.VerQueryValueW
        query.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR,
                          ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
        query.restype = wintypes.BOOL
        ignored = wintypes.DWORD()
        size = size_of(path, ctypes.byref(ignored))
        if not size or size > 1024 * 1024:
            return ()
        data = ctypes.create_string_buffer(size)
        if not read(path, 0, size, data):
            return ()
        pointer, length = ctypes.c_void_p(), wintypes.UINT()
        start, end = ctypes.addressof(data), ctypes.addressof(data) + size
        languages = []
        if query(data, r'\VarFileInfo\Translation', ctypes.byref(pointer), ctypes.byref(length)):
            if pointer.value and start <= pointer.value and pointer.value + length.value <= end:
                pairs = ctypes.cast(pointer, ctypes.POINTER(wintypes.WORD))
                languages = [(pairs[2 * i], pairs[2 * i + 1]) for i in range(min(length.value // 4, 32))]
        languages.extend([(0x0409, 0x04b0), (0x0409, 0x04e4)])
        titles = []
        for language, codepage in dict.fromkeys(languages):
            for field in ('ProductName', 'FileDescription'):
                key = f'\\StringFileInfo\\{language:04x}{codepage:04x}\\{field}'
                if not query(data, key, ctypes.byref(pointer), ctypes.byref(length)):
                    continue
                if not pointer.value or not start <= pointer.value or pointer.value + length.value * 2 > end:
                    continue
                value = ctypes.wstring_at(pointer, length.value).rstrip('\0').strip()
                if value and value not in titles:
                    titles.append(value)
        return tuple(titles)

    @staticmethod
    def choose_main_executable(pattern: str, executables: Sequence[str]) -> Optional[str]:
        if len(executables) == 1:
            return executables[0]

        execs = {PurePath(k).stem.lower(): k for k in executables}
        no_cutoff = 0

        matches_ = difflib.get_close_matches(pattern.lower(), execs.keys(), cutoff=no_cutoff)
        matches = cast(List[str], matches_)  # as str is Sequence[str] - mypy/issues/5090
        try:
            best_match = matches[0]
        except IndexError:
            logging.error(f'Empty list returns from get_close_matches {pattern}, {executables}')
            return None
        else:
            return execs[best_match]
