"""
SchijfOpschoner - Windows schijf opschonen
Scant op ongebruikte apps, grote bestanden en temp/junk.
Vraagt ALTIJD om bevestiging voordat iets wordt verwijderd.

Starten:  python app.py
Bouwen naar .exe:  build.bat
"""
import os
import sys
import json
import threading
import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

# Zorg dat imports werken als .exe (PyInstaller)
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from disk_scanner import (
    get_installed_apps, scan_large_files, scan_junk_files,
    default_large_file_roots, get_drive_info, format_size, ScanResult
)
from safe_cleaner import move_to_recycle_bin, permanent_delete, uninstall_app, estimate_size

APP_NAME = "SchijfOpschoner"
APP_VERSION = "1.0.0"
CONFIG_FILE = BASE_DIR / "schijfopschoner_config.json"

# ---------- Config ----------

def load_config():
    defaults = {"min_large_mb": 500, "include_drives": True, "last_scan": None}
    try:
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text())
            defaults.update(data)
    except Exception:
        pass
    return defaults

def save_config(cfg):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass

# ---------- GUI ----------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION} — Schijf opschonen")
        self.geometry("1100x700")
        self.minsize(900, 600)
        self.config(bg="#f0f0f0")

        self.cfg = load_config()
        self.result: ScanResult = ScanResult()
        self.checked_apps = set()   # indices
        self.checked_large = set()
        self.checked_junk = set()
        self.scanning = False

        self._build_ui()
        self._refresh_drives()

    # ----- UI opbouw -----
    def _build_ui(self):
        # Header
        header = ttk.Frame(self, padding=10)
        header.pack(fill="x")
        ttk.Label(header, text="🧹 SchijfOpschoner", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Label(header, text="Vind ongebruikte apps, grote bestanden & temp — verwijder veilig via Prullenbak",
                  font=("Segoe UI", 9), foreground="gray").pack(side="left", padx=20)

        # Schijf-overzicht
        self.drive_frame = ttk.LabelFrame(self, text="Schijven", padding=8)
        self.drive_frame.pack(fill="x", padx=10, pady=(0, 6))
        self.drive_labels = {}
        ttk.Label(self.drive_frame, text="Schijven laden...").pack()

        # Toolbar
        toolbar = ttk.Frame(self, padding=(10, 4))
        toolbar.pack(fill="x")
        self.scan_btn = ttk.Button(toolbar, text="🔍 Volledige scan starten", command=self.start_scan)
        self.scan_btn.pack(side="left")
        self.export_btn = ttk.Button(toolbar, text="📄 Exporteer rapport (CSV)", command=self.export_csv, state="disabled")
        self.export_btn.pack(side="left", padx=6)
        ttk.Label(toolbar, text="Grote bestanden vanaf (MB):").pack(side="left", padx=(16, 2))
        self.min_mb_var = tk.IntVar(value=self.cfg.get("min_large_mb", 500))
        ttk.Spinbox(toolbar, from_=50, to=5000, increment=50, width=7, textvariable=self.min_mb_var).pack(side="left")
        self.status_var = tk.StringVar(value="Klaar. Klik op 'Volledige scan starten'.")
        ttk.Label(toolbar, textvariable=self.status_var, foreground="gray").pack(side="right")

        # Voortgang
        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(fill="x", padx=10, pady=4)

        # Samenvatting
        self.summary_var = tk.StringVar(value="Nog niet gescand.")
        ttk.Label(self, textvariable=self.summary_var, font=("Segoe UI", 10, "bold"), padding=6).pack(fill="x", padx=10)

        # Tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.tab_apps = self._make_tab("📦 Apps (lang niet gebruikt)")
        self.tab_large = self._make_tab("📁 Grote bestanden")
        self.tab_junk = self._make_tab("🗑️ Temp & Junk")

        self._build_apps_tab()
        self._build_large_tab()
        self._build_junk_tab()

        # Footer met verwijder-knoppen
        footer = ttk.Frame(self, padding=10)
        footer.pack(fill="x")
        self.recycle_btn = ttk.Button(footer, text="🗑️ Geselecteerde naar Prullenbak", command=self.delete_selected_recycle)
        self.recycle_btn.pack(side="left")
        self.perm_btn = ttk.Button(footer, text="⚠️ Definitief verwijderen (geen Prullenbak)", command=self.delete_selected_permanent)
        self.perm_btn.pack(side="left", padx=6)
        self.uninstall_btn = ttk.Button(footer, text="🔧 Verwijder geselecteerde app (officiële uninstaller)", command=self.uninstall_selected)
        self.uninstall_btn.pack(side="left", padx=6)
        ttk.Label(footer, text="Er wordt nooit iets verwijderd zonder jouw bevestiging.", foreground="gray", font=("Segoe UI", 8)).pack(side="right")

    def _make_tab(self, title):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=title)
        return frame

    def _build_apps_tab(self):
        top = ttk.Frame(self.tab_apps)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text="Alles selecteren", command=lambda: self._select_all(self.apps_tree, self.checked_apps)).pack(side="left")
        ttk.Button(top, text="Niets selecteren", command=lambda: self._select_none(self.apps_tree, self.checked_apps)).pack(side="left", padx=4)
        ttk.Label(top, text="Sorteer op 'Dagen sinds gebruik' — hoog = lang niet gebruikt. 'Onbekend' = geen Prefetch-data (Windows registreert dit niet altijd).",
                  foreground="gray", font=("Segoe UI", 8)).pack(side="left", padx=10)

        cols = ("sel", "name", "publisher", "size", "last", "days", "location")
        self.apps_tree = ttk.Treeview(self.tab_apps, columns=cols, show="headings", selectmode="extended")
        headings = {"sel": "✓", "name": "App", "publisher": "Uitgever", "size": "Grootte",
                    "last": "Laatst gebruikt", "days": "Dagen geleden", "location": "Locatie"}
        widths = {"sel": 40, "name": 220, "publisher": 160, "size": 90, "last": 130, "days": 110, "location": 300}
        for c in cols:
            self.apps_tree.heading(c, text=headings[c])
            self.apps_tree.column(c, width=widths[c], anchor="center" if c in ("sel", "size", "days") else "w")
        self.apps_tree.pack(fill="both", expand=True, padx=6, pady=6)
        self.apps_tree.bind("<Button-1>", lambda e: self._toggle_check(e, self.apps_tree, self.checked_apps))

    def _build_large_tab(self):
        top = ttk.Frame(self.tab_large)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text="Alles selecteren", command=lambda: self._select_all(self.large_tree, self.checked_large)).pack(side="left")
        ttk.Button(top, text="Niets selecteren", command=lambda: self._select_none(self.large_tree, self.checked_large)).pack(side="left", padx=4)
        ttk.Label(top, text="Scant Documenten, Downloads, Desktop, Afbeeldingen, Video's, Muziek (+ andere schijven).",
                  foreground="gray", font=("Segoe UI", 8)).pack(side="left", padx=10)

        cols = ("sel", "size", "modified", "path")
        self.large_tree = ttk.Treeview(self.tab_large, columns=cols, show="headings", selectmode="extended")
        self.large_tree.heading("sel", text="✓")
        self.large_tree.heading("size", text="Grootte")
        self.large_tree.heading("modified", text="Gewijzigd")
        self.large_tree.heading("path", text="Bestand")
        self.large_tree.column("sel", width=40, anchor="center")
        self.large_tree.column("size", width=110, anchor="center")
        self.large_tree.column("modified", width=150, anchor="center")
        self.large_tree.column("path", width=700)
        self.large_tree.pack(fill="both", expand=True, padx=6, pady=6)
        self.large_tree.bind("<Button-1>", lambda e: self._toggle_check(e, self.large_tree, self.checked_large))

    def _build_junk_tab(self):
        top = ttk.Frame(self.tab_junk)
        top.pack(fill="x", padx=6, pady=6)
        ttk.Button(top, text="Alles selecteren", command=lambda: self._select_all(self.junk_tree, self.checked_junk)).pack(side="left")
        ttk.Button(top, text="Niets selecteren", command=lambda: self._select_none(self.junk_tree, self.checked_junk)).pack(side="left", padx=4)
        ttk.Label(top, text="Temp, Prullenbak, Windows Update-cache, browser-cache, dumps & logs. Systeem-mappen worden nooit aangeraakt.",
                  foreground="gray", font=("Segoe UI", 8)).pack(side="left", padx=10)

        cols = ("sel", "category", "size", "modified", "path")
        self.junk_tree = ttk.Treeview(self.tab_junk, columns=cols, show="headings", selectmode="extended")
        self.junk_tree.heading("sel", text="✓")
        self.junk_tree.heading("category", text="Categorie")
        self.junk_tree.heading("size", text="Grootte")
        self.junk_tree.heading("modified", text="Gewijzigd")
        self.junk_tree.heading("path", text="Bestand")
        self.junk_tree.column("sel", width=40, anchor="center")
        self.junk_tree.column("category", width=200)
        self.junk_tree.column("size", width=110, anchor="center")
        self.junk_tree.column("modified", width=150, anchor="center")
        self.junk_tree.column("path", width=550)
        self.junk_tree.pack(fill="both", expand=True, padx=6, pady=6)
        self.junk_tree.bind("<Button-1>", lambda e: self._toggle_check(e, self.junk_tree, self.checked_junk))

    # ----- Helpers -----
    def _toggle_check(self, event, tree, checked_set):
        region = tree.identify("region", event.x, event.y)
        if region == "tree" or tree.identify_column(event.x, event.y) == "#1":
            item = tree.identify_row(event.y)
            if item:
                idx = int(item)
                if idx in checked_set:
                    checked_set.remove(idx)
                    tree.set(item, "sel", "")
                else:
                    checked_set.add(idx)
                    tree.set(item, "sel", "☑")

    def _select_all(self, tree, checked_set):
        checked_set.clear()
        for item in tree.get_children():
            idx = int(item)
            checked_set.add(idx)
            tree.set(item, "sel", "☑")

    def _select_none(self, tree, checked_set):
        checked_set.clear()
        for item in tree.get_children():
            tree.set(item, "sel", "")

    def _refresh_drives(self):
        for w in self.drive_frame.winfo_children():
            w.destroy()
        drives = get_drive_info()
        if not drives:
            ttk.Label(self.drive_frame, text="Geen schijven gevonden.").pack()
            return
        for d in drives:
            pct = d["pct_used"]
            color = "red" if pct > 90 else ("orange" if pct > 75 else "green")
            text = f"{d['path']}  —  Vrij: {format_size(d['free'])} van {format_size(d['total'])}  ({pct}% gebruikt)"
            lbl = ttk.Label(self.drive_frame, text=text, foreground=color, font=("Segoe UI", 9))
            lbl.pack(anchor="w")

    def _set_status(self, msg):
        self.status_var.set(msg)
        self.update_idletasks()

    # ----- Scannen (in thread, UI blijft responsive) -----
    def start_scan(self):
        if self.scanning:
            return
        self.scanning = True
        self.scan_btn.config(state="disabled")
        self.progress.start(10)
        self._set_status("Scannen gestart...")
        self.cfg["min_large_mb"] = int(self.min_mb_var.get() or 500)
        save_config(self.cfg)

        def worker():
            try:
                self._set_status("Apps ophalen uit Register...")
                apps = get_installed_apps()
                self.after(0, lambda: self._show_apps(apps))

                self._set_status("Grote bestanden scannen...")
                roots = default_large_file_roots()
                large = scan_large_files(roots, min_size_mb=self.cfg["min_large_mb"])
                self.after(0, lambda: self._show_large(large))

                self._set_status("Temp & junk scannen...")
                junk = scan_junk_files()
                self.after(0, lambda: self._show_junk(junk))

                self.result.apps = apps
                self.result.large_files = large
                self.result.junk_files = junk
                self.result.total_large_bytes = sum(f.size_bytes for f in large)
                self.result.total_junk_bytes = sum(f.size_bytes for f in junk)
                self.result.scanned_files = len(large) + len(junk)
                self.cfg["last_scan"] = datetime.datetime.now().isoformat()
                save_config(self.cfg)

                total = self.result.total_reclaimable
                self.after(0, lambda: self._set_status(
                    f"Klaar! {len(apps)} apps, {len(large)} grote bestanden, {len(junk)} junk-bestanden gevonden. "
                    f"Potentieel vrij te maken: {format_size(total)}"))
                self.after(0, lambda: self.summary_var.set(
                    f"📊 {len(apps)} apps gevonden  •  {len(large)} grote bestanden ({format_size(self.result.total_large_bytes)})  •  "
                    f"{len(junk)} junk-bestanden ({format_size(self.result.total_junk_bytes)})  •  "
                    f"Totaal vrij te maken: {format_size(total)}"))
                self.after(0, lambda: self.export_btn.config(state="normal"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Scan-fout", f"Er ging iets mis tijdens het scannen:\n{e}"))
                self.after(0, lambda: self._set_status("Scan mislukt."))
            finally:
                self.after(0, lambda: (self.progress.stop(), self.scan_btn.config(state="normal")))
                self.scanning = False

        threading.Thread(target=worker, daemon=True).start()

    def _show_apps(self, apps):
        for item in self.apps_tree.get_children():
            self.apps_tree.delete(item)
        self.checked_apps.clear()
        for i, app in enumerate(apps):
            days = str(app.days_since_use) if app.days_since_use is not None else "Onbekend"
            last = app.last_used.strftime("%Y-%m-%d") if app.last_used else "Onbekend"
            self.apps_tree.insert("", "end", iid=str(i), values=(
                "", app.name, app.publisher, format_size(app.size_bytes),
                last, days, app.install_location or app.exe_path
            ))

    def _show_large(self, files):
        for item in self.large_tree.get_children():
            self.large_tree.delete(item)
        self.checked_large.clear()
        for i, f in enumerate(files):
            mod = f.modified.strftime("%Y-%m-%d") if f.modified else "-"
            self.large_tree.insert("", "end", iid=str(i), values=("", f.size_str, mod, f.path))

    def _show_junk(self, files):
        for item in self.junk_tree.get_children():
            self.junk_tree.delete(item)
        self.checked_junk.clear()
        for i, f in enumerate(files):
            mod = f.modified.strftime("%Y-%m-%d") if f.modified else "-"
            self.junk_tree.insert("", "end", iid=str(i), values=("", f.category, f.size_str, mod, f.path))

    # ----- Verwijderen -----
    def _selected_paths(self):
        paths = []
        for idx in self.checked_large:
            if idx < len(self.result.large_files):
                paths.append(self.result.large_files[idx].path)
        for idx in self.checked_junk:
            if idx < len(self.result.junk_files):
                paths.append(self.result.junk_files[idx].path)
        return paths

    def delete_selected_recycle(self):
        paths = self._selected_paths()
        if not paths:
            messagebox.showinfo("Niets geselecteerd", "Selecteer eerst bestanden in 'Grote bestanden' of 'Temp & Junk' (klik op ✓).")
            return
        size = estimate_size(paths)
        ok = messagebox.askyesno(
            "Bevestig: naar Prullenbak",
            f"Je gaat {len(paths)} bestanden ({format_size(size)}) naar de Prullenbak verplaatsen.\n\n"
            "Dit is veilig: je kunt ze later nog terugzetten uit de Prullenbak.\n\n"
            "Doorgaan?"
        )
        if not ok:
            return
        self._set_status("Verplaatsen naar Prullenbak...")
        succeeded, failed = move_to_recycle_bin(paths)
        self._report_delete("Prullenbak", succeeded, failed, size)

    def delete_selected_permanent(self):
        paths = self._selected_paths()
        if not paths:
            messagebox.showinfo("Niets geselecteerd", "Selecteer eerst bestanden (klik op ✓).")
            return
        size = estimate_size(paths)
        ok = messagebox.askyesno(
            "⚠️ DEFINITIEF verwijderen?",
            f"Je gaat {len(paths)} bestanden ({format_size(size)}) DEFINITIEF verwijderen.\n\n"
            "Deze actie kan NIET ongedaan worden en ze komen NIET in de Prullenbak.\n\n"
            "Weet je het zeker?"
        )
        if not ok:
            return
        succeeded, failed = permanent_delete(paths)
        self._report_delete("Definitief", succeeded, failed, size)

    def _report_delete(self, mode, succeeded, failed, size):
        msg = f"{mode}: {len(succeeded)} bestanden verplaatst/verwijderd ({format_size(size)})."
        if failed:
            msg += f"\n\n{len(failed)} mislukt (bijv. in gebruik of geen rechten):\n" + "\n".join(failed[:10])
            if len(failed) > 10:
                msg += f"\n... en {len(failed)-10} meer."
        messagebox.showinfo("Klaar", msg)
        self._set_status(msg.split("\n")[0])
        self._refresh_drives()
        # Opnieuw scannen om lijsten bij te werken
        self.start_scan()

    def uninstall_selected(self):
        if not self.checked_apps:
            messagebox.showinfo("Niets geselecteerd", "Selecteer een app in het tabblad 'Apps' (klik op ✓).")
            return
        for idx in list(self.checked_apps):
            if idx >= len(self.result.apps):
                continue
            app = self.result.apps[idx]
            if not app.uninstall_string:
                messagebox.showwarning("Geen uninstaller", f"'{app.name}' heeft geen uninstall-string. Verwijder via Instellingen > Apps.")
                continue
            ok = messagebox.askyesno(
                "App verwijderen?",
                f"De officiële uninstaller van '{app.name}' wordt gestart.\n"
                "Bevestig de verwijdering in het venster dat opent.\n\nDoorgaan?"
            )
            if ok:
                if uninstall_app(app.uninstall_string):
                    self._set_status(f"Uninstaller gestart voor: {app.name}")
                else:
                    messagebox.showerror("Mislukt", f"Kon uninstaller voor '{app.name}' niet starten.")

    # ----- Export -----
    def export_csv(self):
        if not self.result.apps and not self.result.large_files and not self.result.junk_files:
            messagebox.showinfo("Niets te exporteren", "Start eerst een scan.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile=f"schijfopschoner_rapport_{datetime.date.today().isoformat()}.csv",
        )
        if not path:
            return
        try:
            import csv
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["SchijfOpschoner rapport", datetime.datetime.now().isoformat()])
                w.writerow([])
                w.writerow(["=== APPS ==="])
                w.writerow(["Naam", "Uitgever", "Grootte", "Laatst gebruikt", "Dagen geleden", "Locatie"])
                for a in self.result.apps:
                    w.writerow([a.name, a.publisher, format_size(a.size_bytes),
                                a.last_used.strftime("%Y-%m-%d") if a.last_used else "Onbekend",
                                a.days_since_use if a.days_since_use is not None else "Onbekend",
                                a.install_location])
                w.writerow([])
                w.writerow(["=== GROTE BESTANDEN ==="])
                w.writerow(["Grootte (bytes)", "Grootte", "Gewijzigd", "Pad"])
                for lf in self.result.large_files:
                    w.writerow([lf.size_bytes, lf.size_str,
                                lf.modified.strftime("%Y-%m-%d") if lf.modified else "", lf.path])
                w.writerow([])
                w.writerow(["=== TEMP & JUNK ==="])
                w.writerow(["Categorie", "Grootte (bytes)", "Grootte", "Gewijzigd", "Pad"])
                for jf in self.result.junk_files:
                    w.writerow([jf.category, jf.size_bytes, jf.size_str,
                                jf.modified.strftime("%Y-%m-%d") if jf.modified else "", jf.path])
            messagebox.showinfo("Geëxporteerd", f"Rapport opgeslagen als:\n{path}")
        except Exception as e:
            messagebox.showerror("Export-fout", str(e))


def main():
    # Windows: schaal voor HiDPI
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
