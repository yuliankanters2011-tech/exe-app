"""
safe_cleaner.py - SchijfOpschoner
Veilig verwijderen: standaard naar Prullenbak, nooit definitief zonder bevestiging.
"""
import os
import sys
import shutil
import datetime
from pathlib import Path
from typing import List, Tuple

# Mappen die NOOIT automatisch verwijderd mogen worden
PROTECTED_PREFIXES = [
    r"C:\Windows\System32",
    r"C:\Windows\SysWOW64",
    r"C:\Windows\WinSxS",
    r"C:\Windows\Installer",
    r"C:\Program Files",
    r"C:\Program Files (x86)",
]

def is_protected(path: str) -> bool:
    p = str(path).lower()
    for prefix in PROTECTED_PREFIXES:
        if p.startswith(prefix.lower()):
            return True
    return False

def move_to_recycle_bin(paths: List[str]) -> Tuple[List[str], List[str]]:
    """
    Verplaatst bestanden/mappen naar de Prullenbak (Windows).
    Geeft (gelukt, mislukt_met_redenen) terug.
    Op Linux/Mac: gebruikt trash via gio of verplaatst naar ~/.local/share/Trash.
    """
    succeeded = []
    failed = []

    if sys.platform == "win32":
        # Windows: SHFileOperationW met FOF_ALLOWUNDO
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", ctypes.c_uint),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", ctypes.c_ushort),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        FO_DELETE = 3
        FOF_ALLOWUNDO = 0x0040
        FOF_NOCONFIRMMKDIR = 0x0200
        FOF_SILENT = 0x0004

        for path in paths:
            if is_protected(path):
                failed.append(f"{path} (beschermd systeem-bestand, overgeslagen)")
                continue
            if not os.path.exists(path):
                failed.append(f"{path} (bestaat niet meer)")
                continue
            try:
                # Dubbele null-terminated string
                p_from = str(path) + "\x00\x00"
                op = SHFILEOPSTRUCTW(
                    None, FO_DELETE, p_from, None,
                    FOF_ALLOWUNDO | FOF_NOCONFIRMMKDIR | FOF_SILENT,
                    False, None, None,
                )
                result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
                if result == 0 and not op.fAnyOperationsAborted:
                    succeeded.append(path)
                else:
                    failed.append(f"{path} (foutcode {result})")
            except Exception as e:
                failed.append(f"{path} ({e})")
        return succeeded, failed

    else:
        # Linux/Mac fallback: probeer gio trash, anders ~/.local/share/Trash/files
        trash_dir = Path.home() / ".local" / "share" / "Trash" / "files"
        info_dir = Path.home() / ".local" / "share" / "Trash" / "info"
        try:
            trash_dir.mkdir(parents=True, exist_ok=True)
            info_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        for path in paths:
            try:
                src = Path(path)
                if not src.exists():
                    failed.append(f"{path} (bestaat niet meer)")
                    continue
                dest = trash_dir / src.name
                counter = 1
                while dest.exists():
                    dest = trash_dir / f"{src.stem}_{counter}{src.suffix}"
                    counter += 1
                shutil.move(str(src), str(dest))
                # .trashinfo bestand
                try:
                    info = info_dir / (dest.name + ".trashinfo")
                    info.write_text(f"[Trash Info]\nPath={src.resolve()}\nDeletionDate={datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n")
                except Exception:
                    pass
                succeeded.append(path)
            except Exception as e:
                failed.append(f"{path} ({e})")
        return succeeded, failed

def permanent_delete(paths: List[str]) -> Tuple[List[str], List[str]]:
    """Definitief verwijderen (alleen na expliciete bevestiging in UI)."""
    succeeded, failed = [], []
    for path in paths:
        if is_protected(path):
            failed.append(f"{path} (beschermd, overgeslagen)")
            continue
        try:
            p = Path(path)
            if p.is_dir():
                shutil.rmtree(p)
            elif p.exists():
                p.unlink()
            succeeded.append(path)
        except Exception as e:
            failed.append(f"{path} ({e})")
    return succeeded, failed

def uninstall_app(uninstall_string: str) -> bool:
    """
    Start de officiële uninstaller van een app.
    Geeft True als gestart, False als mislukt.
    LET OP: dit opent de Windows-uninstaller - gebruiker bevestigt daar zelf.
    """
    if not uninstall_string:
        return False
    try:
        if sys.platform == "win32":
            # UninstallString kan args bevatten, bv. "C:\\...\\uninstall.exe" /S
            # Gebruik shell=True via os.startfile waar mogelijk
            if uninstall_string.lower().startswith("msiexec"):
                os.system(uninstall_string)
            else:
                # Haal exe-pad tussen quotes of tot eerste spatie
                exe = uninstall_string.strip().strip('"')
                if exe.startswith('"'):
                    exe = exe.split('"')[1]
                elif " " in exe and not exe.endswith(".exe"):
                    exe = exe.split(" ")[0]
                if os.path.exists(exe):
                    os.startfile(exe)  # type: ignore
                else:
                    os.system(uninstall_string)
            return True
        return False
    except Exception:
        return False

def estimate_size(paths: List[str]) -> int:
    total = 0
    for path in paths:
        try:
            p = Path(path)
            if p.is_file():
                total += p.stat().st_size
            elif p.is_dir():
                for root, _, files in os.walk(p):
                    for f in files:
                        try:
                            total += os.path.getsize(os.path.join(root, f))
                        except OSError:
                            pass
        except Exception:
            continue
    return total
