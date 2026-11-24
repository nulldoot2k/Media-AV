import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
if os.name == "nt":
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MediaAV"
else:
    DATA_DIR = Path.home() / ".mediaav"
DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORY = DATA_DIR / "history.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
YT = str(BUNDLE_DIR / "yt-dlp.exe") if (BUNDLE_DIR / "yt-dlp.exe").exists() else shutil.which("yt-dlp") or "yt-dlp"
FFMPEG = BUNDLE_DIR / "ffmpeg.exe"


def parse_formats(text):
    result = []
    for line in text.splitlines():
        clean = line.replace("│", " ").replace("|", " ")
        p = clean.split()
        if len(p) >= 8 and re.fullmatch(r"[\w+.-]+", p[0]) and re.fullmatch(r"\d+x\d+", p[2]):
            item = {"id": p[0], "ext": p[1], "resolution": p[2], "vcodec": p[6], "acodec": p[7], "size": p[3] if p[3] != "~" else "Chưa có dữ liệu"}
            if not any(x["id"] == item["id"] for x in result):
                result.append(item)
    return result


def _format_size(item):
    value = item.get("filesize")
    approximate = False
    if value is None:
        value = item.get("filesize_approx")
        approximate = value is not None
    if value is None:
        return "Chưa có dữ liệu"
    try:
        value = float(value)
        units = ["B", "KiB", "MiB", "GiB", "TiB"]
        unit = 0
        while value >= 1024 and unit < len(units) - 1:
            value /= 1024
            unit += 1
        shown = f"{value:.2f} {units[unit]}"
        return f"~{shown}" if approximate else shown
    except (TypeError, ValueError):
        return str(value)


def parse_json_formats(text):
    try:
        data = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    result = []
    raw_formats = data.get("formats") or []
    if not isinstance(raw_formats, list):
        return []
    for item in raw_formats:
        if not isinstance(item, dict):
            continue
        format_id = str(item.get("format_id") or "best")
        resolution = item.get("resolution") or "unknown"
        if resolution == "audio only":
            resolution = "audio only"
        result.append({
            "id": format_id,
            "ext": item.get("ext") or "unknown",
            "resolution": resolution,
            "vcodec": item.get("vcodec") or "Chưa có dữ liệu",
            "acodec": item.get("acodec") or "Chưa có dữ liệu",
            "size": _format_size(item),
        })
    return result


class MediaDownloader(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MediaAV")
        self.geometry("1050x720")
        self.minsize(850, 600)
        self.jobs = queue.Queue()
        self.downloads = {}
        self.download_lock = threading.Lock()
        self.next_job_id = 1
        self.log_window = None
        self.log_text = None
        self.task_window = None
        self.task_list = None
        self.formats = []
        self._build_ui()
        self._load_history()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind_all("<Button-1>", self._clear_task_selection_on_click, add="+")
        self.after(150, self._drain_queue)
        self.after(5000, self._network_check)

    def _save_history(self):
        with self.download_lock:
            records = []
            for job_id, job in self.downloads.items():
                records.append({
                    "id": job_id,
                    "output": str(job.get("output", "")),
                    "args": list(job.get("args", [])),
                    "logs": list(job.get("logs", []))[-3000:],
                    "status": job.get("status", "Đã cancel"),
                    "progress": job.get("progress", "0%"),
                    "name": job.get("name", "video"),
                    "folder": job.get("folder", ""),
                    "url": job.get("url", ""),
                    "referer": job.get("referer", ""),
                    "source_type": job.get("source_type", ""),
                    "format_id": job.get("format_id", "best"),
                    "connections": job.get("connections", "4"),
                })
        temporary = HISTORY.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(HISTORY)
        except OSError:
            pass

    def _load_history(self):
        try:
            records = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []
        except (OSError, ValueError, json.JSONDecodeError):
            records = []
        if not isinstance(records, list):
            return
        for record in records:
            if not isinstance(record, dict) or not record.get("args"):
                continue
            job_id = str(record.get("id") or self.next_job_id)
            try:
                self.next_job_id = max(self.next_job_id, int(job_id) + 1)
            except ValueError:
                pass
            output = Path(record.get("output") or "video.mp4")
            name = str(record.get("name") or output.stem)
            status = str(record.get("status") or "Đã cancel")
            if status == "Đang tải":
                status = "Chưa hoàn tất"
            job = {
                "process": None, "stop_requested": False, "output": output,
                "folder": record.get("folder", str(output.parent)), "name": name,
                "logs": list(record.get("logs") or [])[-3000:], "args": list(record.get("args") or []),
                "status": status, "progress": str(record.get("progress") or "0%"),
                "url": record.get("url", ""), "referer": record.get("referer", ""),
                "source_type": record.get("source_type", ""), "format_id": record.get("format_id", "best"),
                "connections": record.get("connections", "4"),
            }
            self.downloads[job_id] = job
            self.tasks.insert("", "end", iid=job_id, values=(name, status, job["progress"], job["folder"]))

    def _set_job_state(self, job_id, status=None, progress=None):
        changed = False
        with self.download_lock:
            job = self.downloads.get(job_id)
            if not job:
                return
            if status is not None:
                changed = changed or job.get("status") != status
                job["status"] = status
            if progress is not None:
                changed = changed or job.get("progress") != progress
                job["progress"] = progress
        if changed:
            self._save_history()

    def _has_completed_output(self, job_id):
        with self.download_lock:
            job = self.downloads.get(job_id)
            if not job:
                return False
            output = Path(job.get("output", ""))
            folder = Path(job.get("folder") or output.parent)
            name = job.get("name") or output.stem
        if output.is_file() and output.stat().st_size > 0:
            return True
        for candidate in folder.glob(name + ".*"):
            if candidate.is_file() and candidate.stat().st_size > 0 and not candidate.name.endswith((".part", ".ytdl")) and ".part-Frag" not in candidate.name:
                return True
        return False

    def _build_ui(self):
        pad = {"padx": 10, "pady": 5}
        top = ttk.Frame(self); top.pack(fill="x", padx=12, pady=10)
        ttk.Label(top, text="MediaAV", font=("Segoe UI", 18, "bold")).pack(anchor="w")

        form = ttk.LabelFrame(self, text="Nguồn media")
        form.pack(fill="x", padx=12, pady=5)
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Media URL").grid(row=0, column=0, sticky="w", **pad)
        self.url = ttk.Entry(form); self.url.grid(row=0, column=1, columnspan=3, sticky="ew", **pad)
        ttk.Label(form, text="Referer").grid(row=1, column=0, sticky="w", **pad)
        self.referer = ttk.Entry(form); self.referer.grid(row=1, column=1, columnspan=3, sticky="ew", **pad)
        ttk.Label(form, text="Loại nguồn").grid(row=2, column=0, sticky="w", **pad)
        self.media_type = ttk.Combobox(form, values=["HLS / m3u8 / manifest", "DASH / mpd", "MP4 / WebM trực tiếp"], state="readonly")
        self.media_type.current(0); self.media_type.grid(row=2, column=1, sticky="w", **pad)
        ttk.Button(form, text="Scan", command=self.probe).grid(row=2, column=2, sticky="e", **pad)
        self.network = ttk.Label(form, text="Mạng: đang kiểm tra...", foreground="#1769e0")
        self.network.grid(row=2, column=3, sticky="e", **pad)

        formats_box = ttk.LabelFrame(self, text="Format / độ phân giải")
        formats_box.pack(fill="x", padx=12, pady=5)
        cols = ("id", "ext", "resolution", "size")
        self.table = ttk.Treeview(formats_box, columns=cols, show="headings", height=7)
        for col, title, width in zip(cols, ["ID", "Dạng", "Độ phân giải", "Size"], [110, 90, 180, 160]):
            self.table.heading(col, text=title); self.table.column(col, width=width, anchor="w")
        self.table.pack(fill="both", expand=True, padx=8, pady=8)

        opts = ttk.LabelFrame(self, text="Lưu và tải")
        opts.pack(fill="x", padx=12, pady=5)
        opts.columnconfigure(1, weight=1)
        ttk.Label(opts, text="Thư mục lưu").grid(row=0, column=0, sticky="w", **pad)
        self.output_dir = ttk.Entry(opts); self.output_dir.insert(0, str(Path.home() / "Downloads")); self.output_dir.grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(opts, text="Chọn thư mục", command=self.choose_folder).grid(row=0, column=2, **pad)
        ttk.Label(opts, text="Tên file").grid(row=1, column=0, sticky="w", **pad)
        self.filename = ttk.Entry(opts); self.filename.insert(0, "video"); self.filename.grid(row=1, column=1, sticky="ew", **pad)
        ttk.Label(opts, text="Số kết nối").grid(row=1, column=2, sticky="e", **pad)
        self.connections = ttk.Combobox(opts, values=["1", "2", "4", "6", "8", "12", "16"], state="readonly", width=8); self.connections.set("4"); self.connections.grid(row=1, column=3, **pad)

        tasks_box = ttk.LabelFrame(self, text="Tác vụ tải")
        tasks_box.pack(fill="x", padx=12, pady=5)
        self.tasks = ttk.Treeview(tasks_box, columns=("name", "status", "progress", "output"), show="headings", height=4)
        for col, title, width in (("name", "Tên file", 230), ("status", "Trạng thái", 140), ("progress", "Tiến độ", 100), ("output", "Thư mục lưu", 460)):
            self.tasks.heading(col, text=title); self.tasks.column(col, width=width, anchor="w")
        self.tasks.pack(side="left", fill="x", expand=True, padx=(8, 0), pady=8)
        task_scroll = ttk.Scrollbar(tasks_box, orient="vertical", command=self.tasks.yview)
        task_scroll.pack(side="right", fill="y", padx=(0, 8), pady=8)
        self.tasks.configure(yscrollcommand=task_scroll.set)
        self.tasks.bind("<<TreeviewSelect>>", self._on_task_selected)

        buttons = ttk.Frame(self); buttons.pack(fill="x", padx=12, pady=5)
        self.start_btn = ttk.Button(buttons, text="Bắt đầu tải", command=self.start_download); self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(buttons, text="Dừng / Cancel", command=self.stop_download, state="disabled"); self.stop_btn.pack(side="left", padx=8)
        self.remove_btn = ttk.Button(buttons, text="Hủy bỏ", command=self.remove_task, state="disabled"); self.remove_btn.pack(side="left")
        self.resume_btn = ttk.Button(buttons, text="Tiếp tục", command=self.resume_task, state="disabled"); self.resume_btn.pack(side="left", padx=8)
        self.start_all_btn = ttk.Button(buttons, text="Bắt đầu tất cả", command=self.start_all); self.start_all_btn.pack(side="left", padx=8)
        self.resume_all_btn = ttk.Button(buttons, text="Tiếp tục tất cả", command=self.resume_all); self.resume_all_btn.pack(side="left", padx=8)
        self.remove_all_btn = ttk.Button(buttons, text="Hủy bỏ tất cả", command=self.remove_all); self.remove_all_btn.pack(side="left")
        self.task_list_btn = ttk.Button(buttons, text="Danh sách tác vụ", command=self.show_task_list); self.task_list_btn.pack(side="left", padx=8)
        self.status = ttk.Label(buttons, text="Sẵn sàng"); self.status.pack(side="right")

    def _base(self):
        args = [YT, "--force-ipv4", "--no-playlist", "--newline", "--user-agent", UA, "--add-header", "Accept: */*"]
        if self.referer.get().strip(): args += ["--referer", self.referer.get().strip()]
        return args

    @staticmethod
    def _hidden_process_kwargs():
        if os.name != "nt":
            return {}
        return {"creationflags": subprocess.CREATE_NO_WINDOW}

    def probe(self):
        url = self.url.get().strip()
        if not url: return messagebox.showwarning("Thiếu URL", "Hãy nhập Media URL.")
        self.status.config(text="Đang scan Size & Độ phân giải..."); self.start_btn.config(state="disabled")
        threading.Thread(target=self._probe_worker, args=(url,), daemon=True).start()

    def _probe_worker(self, url):
        try:
            original_url = url
            variant_url = re.sub(r"-[0-9]+\.m3u8(?:\?.*)?$", "-playlist.m3u8", url, flags=re.I)
            probe_url = variant_url if variant_url != url else url
            # -F is nhanh hơn -J và đã có đủ ID, resolution, codec, size ước tính.
            p = subprocess.run(self._base() + ["--no-warnings", "-F", probe_url], capture_output=True, text=True, timeout=60, **self._hidden_process_kwargs())
            text = (p.stdout or "") + (p.stderr or "")
            formats = parse_formats(text)
            if not formats and probe_url != original_url:
                probe_url = original_url
                p = subprocess.run(self._base() + ["--no-warnings", "-F", probe_url], capture_output=True, text=True, timeout=60, **self._hidden_process_kwargs())
                text = (p.stdout or "") + (p.stderr or "")
                formats = parse_formats(text)
            # Một số extractor chỉ trả JSON; chỉ gọi -J khi bảng -F không đọc được.
            if not formats:
                p = subprocess.run(self._base() + ["--no-warnings", "-J", probe_url], capture_output=True, text=True, timeout=60, **self._hidden_process_kwargs())
                text = (p.stdout or "") + (p.stderr or "")
                formats = parse_json_formats(p.stdout or "")
            if not formats and "#EXTM3U" in text:
                formats = [{"id": "best", "ext": "m3u8", "resolution": "current", "vcodec": "stream", "acodec": "stream", "size": "Chưa có dữ liệu"}]
            self.jobs.put(("formats", probe_url, formats, text[-3000:]))
        except Exception as exc: self.jobs.put(("error", str(exc)))

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Chọn thư mục lưu video", initialdir=self.output_dir.get())
        if folder: self.output_dir.delete(0, "end"); self.output_dir.insert(0, folder)

    def _clear_input_area(self):
        self.url.delete(0, "end")
        self.referer.delete(0, "end")
        self.media_type.current(0)
        for item in self.table.get_children():
            self.table.delete(item)
        self.formats = []
        self.filename.delete(0, "end")
        self.filename.insert(0, "video")

    def _on_task_selected(self, _event=None):
        self._refresh_stop_button()
        if self.tasks.selection():
            self.show_log_window()
        elif self.log_window and self.log_window.winfo_exists():
            self.log_window.destroy()
            self.log_window = None
            self.log_text = None
        self._refresh_task_list_window()

    def show_task_list(self):
        if self.task_window and self.task_window.winfo_exists():
            self.task_window.lift()
            self._refresh_task_list_window()
            return
        self.task_window = tk.Toplevel(self)
        self.task_window.title("Danh sách tác vụ tải")
        self.task_window.geometry("900x420")
        self.task_window.minsize(650, 280)
        self.task_window.protocol("WM_DELETE_WINDOW", self.task_window.destroy)
        frame = ttk.Frame(self.task_window, padding=8)
        frame.pack(fill="both", expand=True)
        self.task_list = ttk.Treeview(frame, columns=("name", "status", "progress", "output"), show="headings")
        for col, title, width in (("name", "Tên file", 220), ("status", "Trạng thái", 140), ("progress", "Tiến độ", 100), ("output", "Thư mục lưu", 400)):
            self.task_list.heading(col, text=title); self.task_list.column(col, width=width, anchor="w")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.task_list.yview)
        self.task_list.configure(yscrollcommand=scroll.set)
        self.task_list.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        frame.rowconfigure(0, weight=1); frame.columnconfigure(0, weight=1)
        self.task_list.bind("<<TreeviewSelect>>", self._on_task_list_selected)
        self._refresh_task_list_window()

    def _refresh_task_list_window(self):
        if not self.task_list or not self.task_window or not self.task_window.winfo_exists():
            return
        main_ids = set(self.tasks.get_children())
        for job_id in self.task_list.get_children():
            if job_id not in main_ids:
                self.task_list.delete(job_id)
        for job_id in self.tasks.get_children():
            values = self.tasks.item(job_id, "values")
            if self.task_list.exists(job_id):
                self.task_list.item(job_id, values=values)
            else:
                self.task_list.insert("", "end", iid=job_id, values=values)

    def _on_task_list_selected(self, _event=None):
        selected = self.task_list.selection() if self.task_list else ()
        if selected and self.tasks.exists(selected[0]):
            self.tasks.selection_set(selected[0])
            self.tasks.focus(selected[0])
            self._on_task_selected()
            self._render_log_window()

    def _clear_task_selection_on_click(self, event):
        widget = event.widget
        protected = (self.tasks, self.task_list, self.stop_btn, self.remove_btn, self.resume_btn, self.start_all_btn, self.remove_all_btn, self.task_list_btn, self.log_window)
        for parent in protected:
            current = widget
            while current is not None:
                if current == parent:
                    return
                current = getattr(current, "master", None)
        selected = self.tasks.selection()
        if selected:
            for task_id in selected:
                self.tasks.selection_remove(task_id)
            self._on_task_selected()

    def show_log_window(self):
        selected = self.tasks.selection()
        if not selected:
            return
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.lift()
            self._render_log_window()
            return
        self.log_window = tk.Toplevel(self)
        self.log_window.title("Nhật ký tác vụ")
        self.log_window.geometry("820x480")
        self.log_window.minsize(600, 300)
        self.log_window.protocol("WM_DELETE_WINDOW", self.log_window.destroy)
        frame = ttk.Frame(self.log_window, padding=8)
        frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(frame, wrap="none", state="disabled", background="#111827", foreground="#d1fae5")
        scroll_y = ttk.Scrollbar(frame, orient="vertical", command=self.log_text.yview)
        scroll_x = ttk.Scrollbar(frame, orient="horizontal", command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1); frame.columnconfigure(0, weight=1)
        self._render_log_window()

    def _render_log_window(self):
        if not self.log_text or not self.log_window or not self.log_window.winfo_exists():
            return
        selected = self.tasks.selection()
        lines = []
        title = "Nhật ký tác vụ"
        if selected:
            with self.download_lock:
                job = self.downloads.get(selected[0], {})
                lines = list(job.get("logs", []))
                title = f"Nhật ký - {self.tasks.item(selected[0], 'values')[0]}"
        self.log_window.title(title)
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("end", "\n".join(lines))
        if lines:
            self.log_text.insert("end", "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def remove_task(self):
        selected = self.tasks.selection()
        if not selected:
            self.status.config(text="Chọn tác vụ để hủy bỏ")
            return
        job_id = selected[0]
        with self.download_lock:
            job = self.downloads.get(job_id)
            if not job:
                return
            process = job.get("process")
            if process and process.poll() is None:
                job["stop_requested"] = True
            output = Path(job["output"])
            stem = output.stem
            folder = output.parent
        threading.Thread(target=self._delete_task_files, args=(process, folder, stem), daemon=True).start()
        with self.download_lock:
            self.downloads.pop(job_id, None)
        if self.tasks.exists(job_id):
            self.tasks.delete(job_id)
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.destroy()
        self.log_window = None
        self.log_text = None
        self._on_task_selected()
        self._refresh_task_list_window()
        self._save_history()
        self.status.config(text="Đã hủy bỏ tác vụ")

    @staticmethod
    def _delete_task_files(process, folder, stem):
        if process and process.poll() is None:
            if os.name == "nt":
                subprocess.Popen(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                try:
                    os.killpg(process.pid, 15)
                except ProcessLookupError:
                    pass
        for _ in range(50):
            remaining = []
            for candidate in folder.glob(stem + ".mp4*"):
                try:
                    candidate.unlink()
                except OSError:
                    remaining.append(candidate)
            if not remaining:
                return
            time.sleep(0.1)

    def resume_task(self):
        selected = self.tasks.selection()
        if not selected:
            self.status.config(text="Chọn tác vụ đã cancel để tiếp tục")
            return
        if not self._resume_job(selected[0]):
            self.status.config(text="Tác vụ này không thể tiếp tục")

    def _download_args(self, url, referer, source_type, fmt, out, name, connections):
        """Tạo lại command từ metadata, tránh phụ thuộc đường dẫn args cũ."""
        args = [YT, "--force-ipv4", "--no-playlist", "--newline", "--user-agent", UA, "--add-header", "Accept: */*"]
        if referer:
            args += ["--referer", referer]
        lower_url = url.lower().split("?", 1)[0]
        if lower_url.endswith((".mpd", ".m4s")):
            source_type = "DASH / mpd"
        elif lower_url.endswith((".mp4", ".webm", ".mkv", ".mov", ".avi")):
            source_type = "MP4 / WebM trực tiếp"
        elif lower_url.endswith((".m3u8", ".m3u")):
            source_type = "HLS / m3u8 / manifest"
        args += ["--continue", "--retries", "infinite", "--fragment-retries", "infinite", "--file-access-retries", "20", "--socket-timeout", "30", "--retry-sleep", "fragment:exp=1:20", "--merge-output-format", "mp4"]
        if source_type.startswith("HLS"):
            if fmt != "best": args += ["--format", fmt]
            args += ["--hls-prefer-native", "--concurrent-fragments", str(connections or "4")]
        elif source_type.startswith("DASH"):
            args += ["--format", fmt if fmt != "best" else "bestvideo+bestaudio/best"]
        else:
            args += ["--format", "best", "--http-chunk-size", "10M"]
        if FFMPEG.exists():
            args += ["--ffmpeg-location", str(BUNDLE_DIR)]
        args += ["--output", str(Path(out) / (name + ".%(ext)s")), url]
        return args

    def _resume_job(self, job_id):
        with self.download_lock:
            job = self.downloads.get(job_id)
            if not job or not job.get("args"):
                return False
            if job.get("process") and job["process"].poll() is None:
                return False
            job["stop_requested"] = False
            args = self._download_args(
                job.get("url", ""), job.get("referer", ""), job.get("source_type", ""),
                job.get("format_id", "best"), job.get("folder", Path(job["output"]).parent),
                job.get("name", Path(job["output"]).stem), job.get("connections", "4"),
            ) if job.get("url") else list(job["args"])
            job["args"] = list(args)
        values = list(self.tasks.item(job_id, "values"))
        values[1] = "Đang khởi động"
        self.tasks.item(job_id, values=values)
        self.status.config(text=f"Đang tiếp tục: {values[0]}")
        self._refresh_stop_button()
        threading.Thread(target=self._download_worker, args=(job_id, args), daemon=True).start()
        return True

    def start_all(self):
        if not self.tasks.get_children():
            self.status.config(text="Không có tác vụ nào để bắt đầu")
            return
        resumed = 0
        for job_id in self.tasks.get_children():
            values = self.tasks.item(job_id, "values")
            if values and values[1] in ("Đã cancel", "Lỗi", "Chưa hoàn tất") and self._resume_job(job_id):
                resumed += 1
        if resumed:
            self.status.config(text=f"Đã bắt đầu lại {resumed} tác vụ")
        else:
            self.status.config(text="Không có tác vụ nào để bắt đầu")

    def resume_all(self):
        if not self.tasks.get_children():
            self.status.config(text="Không có tác vụ nào để tiếp tục")
            return
        resumed = 0
        for job_id in self.tasks.get_children():
            values = self.tasks.item(job_id, "values")
            if values and values[1] in ("Đã cancel", "Lỗi", "Chưa hoàn tất") and self._resume_job(job_id):
                resumed += 1
        if resumed:
            self.status.config(text=f"Đã tiếp tục {resumed} tác vụ")
        else:
            self.status.config(text="Không có tác vụ nào để tiếp tục")

    def remove_all(self):
        job_items = list(self.tasks.get_children())
        if not job_items:
            self.status.config(text="Không có tác vụ để hủy bỏ")
            return
        jobs = []
        with self.download_lock:
            for job_id in job_items:
                job = self.downloads.get(job_id)
                if job:
                    if job.get("process") and job["process"].poll() is None:
                        job["stop_requested"] = True
                    output = Path(job["output"])
                    jobs.append((job.get("process"), output.parent, output.stem))
            self.downloads.clear()
        for process, folder, stem in jobs:
            threading.Thread(target=self._delete_task_files, args=(process, folder, stem), daemon=True).start()
        for job_id in job_items:
            if self.tasks.exists(job_id):
                self.tasks.delete(job_id)
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.destroy()
        self.log_window = None
        self.log_text = None
        self._on_task_selected()
        self._save_history()
        self.status.config(text=f"Đã hủy bỏ {len(jobs)} tác vụ")

    def _on_close(self):
        with self.download_lock:
            running = [job["process"] for job in self.downloads.values() if job.get("process") and job["process"].poll() is None]
            for job in self.downloads.values():
                job["stop_requested"] = True
                if job.get("status") not in ("Hoàn tất", "Lỗi"):
                    job["status"] = "Đã cancel"
        self._save_history()
        for process in running:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                try:
                    os.killpg(process.pid, 15)
                except ProcessLookupError:
                    pass
        self.destroy()

    def start_download(self):
        url = self.url.get().strip()
        if not url:
            selected = self.tasks.selection()
            if selected:
                return self.resume_task()
            return messagebox.showwarning("Thiếu URL", "Hãy nhập Media URL.")
        selected = self.table.selection()
        fmt = self.table.item(selected[0], "values")[0] if selected else "best"
        name = Path(self.filename.get().strip() or "video").stem
        out = Path(self.output_dir.get().strip() or Path.home() / "Downloads")
        out.mkdir(parents=True, exist_ok=True)
        output_path = (out / (name + ".mp4")).resolve()
        with self.download_lock:
            duplicate_task = any(Path(job.get("output")).resolve() == output_path for job in self.downloads.values() if job.get("output"))
        existing_media = list(out.glob(name + ".*"))
        if output_path.exists() or existing_media or duplicate_task:
            return messagebox.showwarning("Tên file bị trùng", f"File '{name}.mp4' đã tồn tại hoặc đang được tải. Hãy nhập tên khác.")
        source_type = self.media_type.get()
        lower_url = url.lower().split("?", 1)[0]
        if lower_url.endswith((".mpd", ".m4s")):
            source_type = "DASH / mpd"
        elif lower_url.endswith((".mp4", ".webm", ".mkv", ".mov", ".avi")):
            source_type = "MP4 / WebM trực tiếp"
        elif lower_url.endswith((".m3u8", ".m3u")):
            source_type = "HLS / m3u8 / manifest"
        connections = self.connections.get() or "4"
        args = self._download_args(url, self.referer.get().strip(), source_type, fmt, out, name, connections)
        with self.download_lock:
            job_id = str(self.next_job_id)
            self.next_job_id += 1
            self.downloads[job_id] = {
                "process": None, "stop_requested": False, "output": out / (name + ".mp4"),
                "folder": str(out), "name": name, "logs": [], "args": list(args),
                "status": "Đang khởi động", "progress": "0%", "url": url,
                "referer": self.referer.get().strip(), "source_type": source_type,
                "format_id": fmt, "connections": connections,
            }
        for task_id in self.tasks.selection():
            self.tasks.selection_remove(task_id)
        self.tasks.insert("", "end", iid=job_id, values=(name, "Đang khởi động", "0%", str(out)))
        self._refresh_stop_button()
        self._refresh_task_list_window()
        self.status.config(text=f"Đang tải: {name}")
        self._clear_input_area()
        self._save_history()
        threading.Thread(target=self._download_worker, args=(job_id, args), daemon=True).start()

    def _download_worker(self, job_id, args):
        try:
            popen_kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "bufsize": 1,
            }
            if os.name == "nt":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            else:
                popen_kwargs["start_new_session"] = True
            process = subprocess.Popen(args, **popen_kwargs)
            with self.download_lock:
                self.downloads[job_id]["process"] = process
            self.jobs.put(("job_status", job_id, "Đang tải"))
            for line in process.stdout: self.jobs.put(("job_log", job_id, line.rstrip()))
            code = process.wait()
            with self.download_lock:
                stopped = self.downloads.get(job_id, {}).get("stop_requested", False)
            self.jobs.put(("job_stopped" if stopped else "job_done", job_id, code))
        except Exception as exc: self.jobs.put(("job_error", job_id, str(exc)))
        finally:
            with self.download_lock:
                if job_id in self.downloads:
                    self.downloads[job_id]["process"] = None

    @staticmethod
    def _terminate_process(process):
        try:
            if os.name == "nt":
                # Chạy ngoài luồng UI để nút Cancel phản hồi ngay cả khi
                # yt-dlp/ffmpeg đang bận hoặc còn nhiều fragment mở.
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                os.killpg(process.pid, 15)
        except Exception:
            pass

    def stop_download(self):
        selected = self.tasks.selection()
        if not selected:
            self.status.config(text="Chọn một tác vụ để dừng")
            return
        job_id = selected[0]
        with self.download_lock:
            job = self.downloads.get(job_id)
            process = job.get("process") if job else None
            if job:
                job["stop_requested"] = True
        if not process or process.poll() is not None:
            self.status.config(text="Tác vụ chưa có tiến trình")
            return
        self.status.config(text="Đang cancel...")
        self.stop_btn.config(state="disabled")
        threading.Thread(target=self._terminate_process, args=(process,), daemon=True).start()

    def _refresh_stop_button(self):
        selected = self.tasks.selection()
        enabled = False
        removable = bool(selected)
        resumable = False
        if selected:
            with self.download_lock:
                job = self.downloads.get(selected[0])
                enabled = bool(job and job.get("process") and job["process"].poll() is None and not job.get("stop_requested"))
            values = self.tasks.item(selected[0], "values")
            resumable = bool(values and values[1] in ("Đã cancel", "Lỗi", "Chưa hoàn tất")) and not enabled
        self.stop_btn.config(state="normal" if enabled else "disabled")
        self.remove_btn.config(state="normal" if removable else "disabled")
        self.resume_btn.config(state="normal" if resumable else "disabled")

    def _network_check(self):
        threading.Thread(target=self._network_worker, daemon=True).start()
        self.after(5000, self._network_check)

    def _network_worker(self):
        started = time.perf_counter()
        try:
            request = urllib.request.Request("https://www.google.com/generate_204", method="HEAD", headers={"User-Agent": UA})
            with urllib.request.urlopen(request, timeout=4):
                pass
            rtt = round((time.perf_counter() - started) * 1000)
            self.jobs.put(("network", f"Mạng: online · RTT {rtt} ms"))
        except Exception:
            self.jobs.put(("network", "Mạng: chưa kết nối"))

    def _drain_queue(self):
        processed = 0
        try:
            # Giới hạn số dòng xử lý mỗi nhịp để cửa sổ vẫn mượt khi có
            # nhiều download cùng lúc và yt-dlp ghi log liên tục.
            while processed < 250:
                item = self.jobs.get_nowait()
                processed += 1
                if item[0] == "formats":
                    _, url, formats, raw = item; self.url.delete(0, "end"); self.url.insert(0, url); self.formats = formats
                    for x in self.table.get_children(): self.table.delete(x)
                    for f in formats: self.table.insert("", "end", values=(f["id"], f["ext"], f["resolution"], f["size"]))
                    self.status.config(text=f"Đã scan {len(formats)} lựa chọn"); self.start_btn.config(state="normal")
                elif item[0] == "log": self.status.config(text=item[1])
                elif item[0] == "network": self.network.config(text=item[1])
                elif item[0] == "job_log":
                    _, job_id, line = item
                    with self.download_lock:
                        if job_id in self.downloads:
                            logs = self.downloads[job_id].setdefault("logs", [])
                            logs.append(line)
                            if len(logs) > 3000:
                                del logs[:-3000]
                    progress = re.search(r"(?:^|\s)(\d+(?:\.\d+)?)%", line)
                    if progress and self.tasks.exists(job_id):
                        percent = f"{progress.group(1)}%"
                        values = list(self.tasks.item(job_id, "values")); values[2] = percent; self.tasks.item(job_id, values=values)
                        self._set_job_state(job_id, progress=percent)
                    speed = re.search(r"at\s+([^\s]+/s)", line)
                    if speed and self.tasks.exists(job_id):
                        values = list(self.tasks.item(job_id, "values"))
                        eta = re.search(r"ETA\s+([^\s]+)", line)
                        detail = f"Đang tải · {speed.group(1)}"
                        if eta:
                            detail += f" · còn {eta.group(1)}"
                        values[1] = detail
                        self.tasks.item(job_id, values=values)
                elif item[0] == "job_status":
                    _, job_id, status = item
                    if self.tasks.exists(job_id):
                        values = list(self.tasks.item(job_id, "values")); values[1] = status; self.tasks.item(job_id, values=values)
                    self._set_job_state(job_id, status=status)
                    self._refresh_stop_button()
                elif item[0] == "job_done":
                    _, job_id, code = item
                    completed = code == 0 and self._has_completed_output(job_id)
                    if self.tasks.exists(job_id):
                        values = list(self.tasks.item(job_id, "values")); values[1] = "Hoàn tất" if completed else "Tải lỗi"; values[2] = "100%" if completed else values[2]; self.tasks.item(job_id, values=values)
                    self._set_job_state(job_id, "Hoàn tất" if completed else "Tải lỗi", "100%" if completed else None)
                    self._refresh_stop_button()
                elif item[0] == "job_stopped":
                    _, job_id, _code = item
                    if self.tasks.exists(job_id):
                        values = list(self.tasks.item(job_id, "values")); values[1] = "Đã cancel"; self.tasks.item(job_id, values=values)
                    self._set_job_state(job_id, "Đã cancel")
                    self._refresh_stop_button()
                elif item[0] == "job_error":
                    _, job_id, error = item
                    with self.download_lock:
                        if job_id in self.downloads:
                            self.downloads[job_id].setdefault("logs", []).append(f"Lỗi: {error}")
                    if self.tasks.exists(job_id):
                        values = list(self.tasks.item(job_id, "values")); values[1] = "Lỗi"; self.tasks.item(job_id, values=values)
                    self._set_job_state(job_id, "Lỗi")
                    self._refresh_stop_button()
                    if self.tasks.selection() == (job_id,) and self.log_window and self.log_window.winfo_exists():
                        self._render_log_window()
                elif item[0] == "error": self.status.config(text="Lỗi"); self.start_btn.config(state="normal"); messagebox.showerror("Lỗi", item[1])
        except queue.Empty: pass
        if self.tasks.selection() and self.log_window and self.log_window.winfo_exists():
            self._render_log_window()
        self._refresh_task_list_window()
        self.after(150, self._drain_queue)


if __name__ == "__main__":
    MediaDownloader().mainloop()
