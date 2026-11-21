"""
disk_scanner.py - SchijfOpschoner
Scant harde schijf op:
- Geïnstalleerde apps (laatst gebruikt via Prefetch + Register)
- Grote bestanden
- Temp / Junk bestanden
Alleen-lezen: verwijdert nooit iets zelf.
"""
import os
import sys
import struct
import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable

# ---------- Helpers ----------

def format_size(bytes_size: int) -> str:
    if bytes_size < 1024:
        return f"{bytes_size} B"
    for unit in ["KB", "MB", "GB", "TB"]:
        bytes_size /= 1024
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
    return f"{bytes_size:.1f} PB"

def days_ago(dt: Optional[datetime.datetime]) -> Optional[int]:
    if dt is None:
        return None
    delta = datetime.datetime.now() - dt
    return delta.days

def filetime_to_datetime(ft: int) -> Optional[datetime.datetime]:
    if ft == 0:
        return None
    try:
        # FILETIME is 100-nanosecond intervals since 1601-01-01
        epoch = datetime.datetime(1601, 1, 1)
        return epoch + datetime.timedelta(microseconds=ft // 10)
    except Exception:
        return None

# ---------- Data classes ----------

@dataclass
class InstalledApp:
    name: str
    publisher: str = ""
    install_location: str = ""
    install_date: Optional[datetime.datetime] = None
    size_bytes: int = 0
    uninstall_string: str = ""
    exe_path: str = ""
    last_used: Optional[datetime.datetime] = None
    days_since_use: Optional[int] = None
    source: str = ""  # registry key

    def to_dict(self):
        return {
            "name": self.name,
            "publisher": self.publisher,
            "install_location": self.install_location,
            "install_date": self.install_date.isoformat() if self.install_date else "",
            "size": format_size(self.size_bytes),
            "size_bytes": self.size_bytes,
            "last_used": self.last_used.isoformat() if self.last_used else "Onbekend",
            "days_since_use": self.days_since_use if self.days_since_use is not None else -1,
            "uninstall_string": self.uninstall_string,
        }

@dataclass
class LargeFile:
    path: str
    size_bytes: int
    modified: Optional[datetime.datetime] = None
    extension: str = ""

    @property
    def size_str(self):
        return format_size(self.size_bytes)

@dataclass
class JunkFile:
    path: str
    size_bytes: int
    category: str  # bv. "Temp", "Prullenbak", "Browser cache"
    modified: Optional[datetime.datetime] = None

    @property
    def size_str(self):
        return format_size(self.size_bytes)

@dataclass
class ScanResult:
    apps: List[InstalledApp] = field(default_factory=list)
    large_files: List[LargeFile] = field(default_factory=list)
    junk_files: List[JunkFile] = field(default_factory=list)
    total_junk_bytes: int = 0
    total_large_bytes: int = 0
    scanned_files: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def total_reclaimable(self):
        return self.total_junk_bytes + self.total_large_bytes

# ---------- 1. Geïnstalleerde apps ----------

def _parse_prefetch_last_run(prefetch_dir: Path) -> Dict[str, datetime.datetime]:
    """Lees Prefetch .pf bestanden -> {exe-naam-lower: laatste starttijd}"""
    result = {}
    if not prefetch_dir.exists():
        return result
    try:
        for pf in prefetch_dir.glob("*.pf"):
            try:
                data = pf.read_bytes()
                if len(data) < 136:
                    continue
                # Exe naam: offset 16, 60 bytes UTF-16LE
                exe_name = data[16:76].decode("utf-16le", errors="ignore").strip("\x00").strip()
                if not exe_name:
                    continue
                # Laatste runtijd: offset 128, 8 bytes FILETIME (Windows 10/11)
                ft = struct.unpack("<Q", data[128:136])[0]
                dt = filetime_to_datetime(ft)
                if dt:
                    key = exe_name.lower()
                    if key not in result or dt > result[key]:
                        result[key] = dt
            except Exception:
                continue
    except Exception:
        pass
    return result

def _parse_install_date(value: str) -> Optional[datetime.datetime]:
    """Parse InstallDate uit registry (meestal YYYYMMDD)"""
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(value, fmt)
        except Exception:
            continue
    return None

def get_installed_apps(progress: Optional[Callable[[str, int], None]] = None) -> List[InstalledApp]:
    """
    Haalt geïnstalleerde programma's op uit het Register.
    Werkt alleen op Windows (winreg). Op Linux/Mac geeft lege lijst + fallback via /usr/share/applications.
    """
    apps: List[InstalledApp] = []
    prefetch_map = _parse_prefetch_last_run(Path(r"C:\Windows\Prefetch"))

    if sys.platform == "win32":
        try:
            import winreg
        except ImportError:
            return apps

        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]

        for hive, subkey in reg_paths:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    i = 0
                    while True:
                        try:
                            sub = winreg.EnumKey(key, i)
                        except OSError:
                            break
                        i += 1
                        try:
                            with winreg.OpenKey(key, sub) as sk:
                                def get_val(name, default=""):
                                    try:
                                        v, _ = winreg.QueryValueEx(sk, name)
                                        return v
                                    except OSError:
                                        return default

                                name = get_val("DisplayName", "").strip()
                                if not name:
                                    continue
                                # Sla Windows-updates en componenten over (geen echte apps)
                                if get_val("SystemComponent") == 1:
                                    continue
                                if get_val("ParentKeyName"):
                                    continue

                                publisher = str(get_val("Publisher", "")).strip()
                                location = str(get_val("InstallLocation", "")).strip()
                                uninstall = str(get_val("UninstallString", "")).strip()
                                install_date_raw = str(get_val("InstallDate", "")).strip()
                                install_date = _parse_install_date(install_date_raw)

                                size_kb = get_val("EstimatedSize", 0)
                                try:
                                    size_bytes = int(size_kb) * 1024
                                except Exception:
                                    size_bytes = 0

                                # Schat grootte via map als EstimatedSize ontbreekt
                                if size_bytes == 0 and location and os.path.isdir(location):
                                    try:
                                        total = 0
                                        for root, _, files in os.walk(location):
                                            for f in files:
                                                try:
                                                    total += os.path.getsize(os.path.join(root, f))
                                                except OSError:
                                                    pass
                                            if total > 5 * 1024 * 1024 * 1024:  # stop bij >5GB voor snelheid
                                                break
                                        size_bytes = total
                                    except Exception:
                                        pass

                                # Laatst gebruikt: via Prefetch match op exe-naam
                                last_used = None
                                exe_path = ""
                                if location:
                                    # Zoek hoofd-exe in installatiemap
                                    try:
                                        for f in Path(location).glob("*.exe"):
                                            exe_path = str(f)
                                            key_name = f.name.lower()
                                            if key_name in prefetch_map:
                                                last_used = prefetch_map[key_name]
                                                break
                                    except Exception:
                                        pass
                                    # Fallback: LastAccessTime van map/exe
                                    if last_used is None and exe_path and os.path.exists(exe_path):
                                        try:
                                            ts = os.path.getatime(exe_path)
                                            last_used = datetime.datetime.fromtimestamp(ts)
                                        except Exception:
                                            pass

                                apps.append(InstalledApp(
                                    name=name,
                                    publisher=publisher,
                                    install_location=location,
                                    install_date=install_date,
                                    size_bytes=size_bytes,
                                    uninstall_string=uninstall,
                                    exe_path=exe_path,
                                    last_used=last_used,
                                    days_since_use=days_ago(last_used),
                                    source=f"{subkey}\\{sub}",
                                ))
                        except Exception:
                            continue
            except Exception:
                continue

        # Sorteer: langst ongebruikt eerst, onbekend onderaan
        apps.sort(key=lambda a: (a.days_since_use is None, -(a.days_since_use or 0)))
        if progress:
            progress("Apps opgehaald", 100)
        return apps

    else:
        # Fallback voor testen op Linux: lees .desktop bestanden
        app_dir = Path("/usr/share/applications")
        if app_dir.exists():
            for desktop in app_dir.glob("*.desktop"):
                try:
                    text = desktop.read_text(errors="ignore")
                    name = ""
                    for line in text.splitlines():
                        if line.startswith("Name="):
                            name = line.split("=", 1)[1].strip()
                            break
                    if name:
                        st = desktop.stat()
                        apps.append(InstalledApp(
                            name=name,
                            install_location=str(desktop),
                            last_used=datetime.datetime.fromtimestamp(st.st_atime),
                            days_since_use=days_ago(datetime.datetime.fromtimestamp(st.st_atime)),
                        ))
                except Exception:
                    continue
        return apps

# ---------- 2. Grote bestanden ----------

SKIP_DIRS = {
    "$recycle.bin", "system volume information", "windows", "program files",
    "program files (x86)", "programdata", "recovery", "perflogs",
}

def scan_large_files(
    roots: List[str],
    min_size_mb: int = 500,
    progress: Optional[Callable[[str, int], None]] = None,
    max_files: int = 5000,
) -> List[LargeFile]:
    """Scant mappen op bestanden groter dan min_size_mb."""
    results: List[LargeFile] = []
    min_bytes = min_size_mb * 1024 * 1024
    scanned = 0

    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root_path, topdown=True, onerror=lambda e: None):
            # Sla systeem-mappen over voor snelheid
            dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS and not d.startswith(".")]
            for fname in filenames:
                scanned += 1
                fpath = Path(dirpath) / fname
                try:
                    size = fpath.stat().st_size
                    if size >= min_bytes:
                        try:
                            mod = datetime.datetime.fromtimestamp(fpath.stat().st_mtime)
                        except Exception:
                            mod = None
                        results.append(LargeFile(
                            path=str(fpath),
                            size_bytes=size,
                            modified=mod,
                            extension=fpath.suffix.lower(),
                        ))
                        if len(results) >= max_files:
                            break
                except (OSError, PermissionError):
                    continue
            if progress and scanned % 500 == 0:
                progress(f"Grote bestanden scannen... {scanned} bestanden", min(99, scanned // 100))
            if len(results) >= max_files:
                break
        if len(results) >= max_files:
            break

    results.sort(key=lambda x: x.size_bytes, reverse=True)
    if progress:
        progress("Grote bestanden klaar", 100)
    return results

def default_large_file_roots() -> List[str]:
    """Standaard mappen voor grote-bestanden-scan (gebruikersmappen)."""
    roots = []
    user = Path.home()
    for folder in ["Documents", "Downloads", "Desktop", "Pictures", "Videos", "Music"]:
        p = user / folder
        if p.exists():
            roots.append(str(p))
    # Extra schijven (D:, E: ...) - alleen gebruikersmappen, geen Windows-map
    if sys.platform == "win32":
        import string
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            try:
                if os.path.exists(drive):
                    # Voeg alleen toe als het geen systeemschijf is (C:)
                    if letter != "C":
                        roots.append(drive)
            except Exception:
                pass
    return roots

# ---------- 3. Temp / Junk ----------

def _collect_dir_junk(path: Path, category: str, min_age_days: int = 0) -> List[JunkFile]:
    out = []
    if not path.exists():
        return out
    cutoff = datetime.datetime.now() - datetime.timedelta(days=min_age_days) if min_age_days else None
    for dirpath, _, filenames in os.walk(path, topdown=True, onerror=lambda e: None):
        for fname in filenames:
            fpath = Path(dirpath) / fname
            try:
                st = fpath.stat()
                if cutoff and datetime.datetime.fromtimestamp(st.st_mtime) > cutoff:
                    continue
                out.append(JunkFile(
                    path=str(fpath),
                    size_bytes=st.st_size,
                    category=category,
                    modified=datetime.datetime.fromtimestamp(st.st_mtime),
                ))
            except (OSError, PermissionError):
                continue
    return out

def scan_junk_files(progress: Optional[Callable[[str, int], None]] = None) -> List[JunkFile]:
    """Scant bekende temp/junk-locaties. Verwijdert niets."""
    results: List[JunkFile] = []

    def add(path_str: str, category: str, min_age: int = 0):
        if progress:
            progress(f"Junk scannen: {category}...", 0)
        p = Path(os.path.expandvars(path_str))
        results.extend(_collect_dir_junk(p, category, min_age_days=min_age))

    # Gebruikers-temp (veilig, alles)
    add(os.environ.get("TEMP", ""), "Temp (gebruiker)")
    add(os.environ.get("TMP", ""), "Temp (gebruiker)")
    add(str(Path.home() / "AppData" / "Local" / "Temp"), "Temp (gebruiker)")

    # Windows Temp (alleen >7 dagen oud voor veiligheid)
    add(r"C:\Windows\Temp", "Windows Temp (>7 dagen)", min_age=7)

    # Prullenbak
    add(r"C:\$Recycle.Bin", "Prullenbak")
    # Per-user recycle bins
    if sys.platform == "win32":
        try:
            import string
            for letter in string.ascii_uppercase:
                p = Path(f"{letter}:\\$Recycle.Bin")
                if p.exists():
                    results.extend(_collect_dir_junk(p, "Prullenbak"))
        except Exception:
            pass

    # Windows Update download-cache (>30 dagen)
    add(r"C:\Windows\SoftwareDistribution\Download", "Windows Update cache", min_age=30)

    # Delivery Optimization
    add(r"C:\Windows\SoftwareDistribution\DeliveryOptimization", "Delivery Optimization", min_age=7)

    # Prefetch oud (>30 dagen) - kleine winst, maar veilig
    add(r"C:\Windows\Prefetch", "Prefetch (>30 dagen)", min_age=30)

    # Thumbnail cache
    add(str(Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Explorer"), "Miniaturen-cache")

    # Browser caches
    local = Path.home() / "AppData" / "Local"
    add(str(local / "Google" / "Chrome" / "User Data" / "Default" / "Cache"), "Chrome cache")
    add(str(local / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache"), "Edge cache")
    add(str(local / "Mozilla" / "Firefox" / "Profiles"), "Firefox cache")

    # Crash dumps en logs
    add(str(local / "CrashDumps"), "Crash-dumps")
    add(r"C:\Windows\Minidump", "Minidump")
    add(r"C:\Windows\Memory.dmp", "Geheugendump")  # bestand, geen map - _collect_dir_junk pakt map; hier apart:
    # Logbestanden ouder dan 30 dagen in Windows\Logs
    add(r"C:\Windows\Logs", "Windows-logs (>30 dagen)", min_age=30)

    # Sorteer op grootte
    results.sort(key=lambda x: x.size_bytes, reverse=True)
    if progress:
        progress("Junk-scan klaar", 100)
    return results

def get_drive_info() -> List[Dict]:
    """Geeft schijfinformatie terug (Windows: via ctypes, anders via shutil)."""
    drives = []
    if sys.platform == "win32":
        import ctypes
        drives_mask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            if drives_mask & (1 << i):
                letter = chr(ord("A") + i)
                path = f"{letter}:\\"
                try:
                    free = ctypes.c_ulonglong(0)
                    total = ctypes.c_ulonglong(0)
                    ctypes.windll.kernel32.GetDiskFreeSpaceExW(path, None, ctypes.byref(total), ctypes.byref(free))
                    drives.append({
                        "letter": letter,
                        "path": path,
                        "total": total.value,
                        "free": free.value,
                        "used": total.value - free.value,
                        "pct_used": round((total.value - free.value) / total.value * 100, 1) if total.value else 0,
                    })
                except Exception:
                    continue
    else:
        import shutil
        total, used, free = shutil.disk_usage("/")
        drives.append({
            "letter": "/", "path": "/", "total": total, "free": free,
            "used": used, "pct_used": round(used / total * 100, 1) if total else 0,
        })
    return drives
