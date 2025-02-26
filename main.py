import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from threading import Thread, Event
from queue import Queue, Empty
import platform
import subprocess


def convert_size(size_bytes):
    """Конвертирует размер в байтах в удобочитаемый формат."""
    if size_bytes == 0:
        return "0 B"
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    idx = 0
    while size_bytes >= 1024 and idx < len(units) - 1:
        size_bytes /= 1024
        idx += 1
    return f"{size_bytes:.2f} {units[idx]}"


class ModernStyle(ttk.Style):
    def __init__(self):
        super().__init__()
        self.theme_use('clam')
        self.configure('TFrame', background='#f0f0f0')
        self.configure('TLabel', background='#f0f0f0', font=('Segoe UI', 9))
        self.configure('TButton', font=('Segoe UI', 9), relief='flat')
        self.configure('Treeview', rowheight=25, font=('Segoe UI', 9))
        self.configure('Treeview.Heading', font=('Segoe UI', 9, 'bold'))
        self.map('TButton', background=[('active', '#e1e1e1')])


class SizeAnalyzerApp:
    def __init__(self, root, initial_path=None, recursive=True):
        self.root = root
        self.style = ModernStyle()
        self.recursive = recursive
        self.initial_path = initial_path

        # Управление потоками
        self.stop_event = Event()
        self.scan_thread = None
        self.queue = Queue()
        self.data = []
        self.processed_paths = set()

        # Переменные для сортировки
        self.sort_column = 'name'
        self.sort_reverse = False
        self.column_names = {
            'type': 'Тип',
            'name': 'Имя',
            'size': 'Размер'
        }

        self.setup_ui()
        self.check_queue()

        if self.initial_path:
            self.start_scan_thread(self.initial_path)

    def setup_ui(self):
        self.root.geometry("900x600")
        self.root.configure(bg='#f0f0f0')

        # Header
        header_frame = ttk.Frame(self.root)
        header_frame.pack(padx=15, pady=10, fill=tk.X)

        self.path_entry = ttk.Entry(header_frame, width=60, font=('Segoe UI', 10))
        self.path_entry.pack(side=tk.LEFT, padx=5)

        ttk.Button(header_frame, text="Обзор", command=self.browse_folder,
                   style='Accent.TButton').pack(side=tk.LEFT, padx=5)

        # Mode Selector
        mode_frame = ttk.Frame(self.root)
        mode_frame.pack(padx=15, pady=5, fill=tk.X)

        self.mode_var = tk.BooleanVar(value=self.recursive)
        ttk.Radiobutton(mode_frame, text="Рекурсивный поиск", variable=self.mode_var,
                        value=True, command=self.mode_changed).pack(side=tk.LEFT)
        ttk.Radiobutton(mode_frame, text="Только текущая папка", variable=self.mode_var,
                        value=False, command=self.mode_changed).pack(side=tk.LEFT, padx=15)

        # Treeview
        self.tree = ttk.Treeview(self.root, columns=('type', 'name', 'size'), show='headings')
        self.tree.heading('type', text='Тип', anchor=tk.W, command=lambda: self.sort('type'))
        self.tree.heading('name', text='Имя', anchor=tk.W, command=lambda: self.sort('name'))
        self.tree.heading('size', text='Размер', anchor=tk.W, command=lambda: self.sort('size'))
        self.tree.column('type', width=100, anchor=tk.W)
        self.tree.column('name', width=400, anchor=tk.W)
        self.tree.column('size', width=150, anchor=tk.W)

        vsb = ttk.Scrollbar(self.root, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self.root, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=15, pady=5)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Button-3>", self.on_right_click)

        # Status Bar
        self.status = ttk.Label(self.root, text="Готово", relief=tk.SUNKEN)
        self.status.pack(side=tk.BOTTOM, fill=tk.X, padx=1, pady=1)

        # Custom Style
        self.style.configure('Accent.TButton', background='#0078d4', foreground='white')
        self.style.map('Accent.TButton',
                       background=[('active', '#006cbd'), ('pressed', '#005a9e')])

    def sort(self, column):
        """Обработчик сортировки с индикацией направления"""
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False

        # Обновляем заголовки с индикацией
        for col in ['type', 'name', 'size']:
            text = self.column_names[col]
            if col == self.sort_column:
                arrow = ' ▼' if self.sort_reverse else ' ▲'
                text += arrow
            self.tree.heading(col, text=text)

        # Сортировка данных
        self.update_sort()
        self.update_treeview()

    def update_sort(self):
        """Обновление порядка данных"""
        if self.sort_column == 'type':
            self.data.sort(key=lambda x: (x[0], x[1].lower()), reverse=self.sort_reverse)
        elif self.sort_column == 'name':
            self.data.sort(key=lambda x: x[1].lower(), reverse=self.sort_reverse)
        else:
            self.data.sort(key=lambda x: x[2], reverse=self.sort_reverse)

    def update_treeview(self):
        """Обновление отображения данных"""
        self.tree.delete(*self.tree.get_children())
        for item in self.data:
            self.tree.insert('', tk.END,
                             values=(item[0], item[1], convert_size(item[2])),
                             tags=(item[3],))

    def mode_changed(self):
        self.recursive = self.mode_var.get()
        if self.path_entry.get():
            self.start_scan_thread(self.path_entry.get())

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.start_scan_thread(folder)
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, folder)

    def start_scan_thread(self, folder):
        # Полная очистка предыдущего состояния
        self.stop_scanning()
        self.reset_scan_state()

        # Запуск нового сканирования
        self.scan_thread = Thread(
            target=self.scan_folder,
            args=(folder, self.stop_event),
            daemon=True
        )
        self.scan_thread.start()

    def stop_scanning(self):
        """Остановка текущего сканирования"""
        if self.scan_thread and self.scan_thread.is_alive():
            self.stop_event.set()
            self.scan_thread.join(timeout=0.5)
            self.scan_thread = None

    def reset_scan_state(self):
        """Сброс всего состояния перед новым сканированием"""
        self.stop_event.clear()
        with self.queue.mutex:
            self.queue.queue.clear()
        self.processed_paths.clear()
        self.data.clear()
        self.tree.delete(*self.tree.get_children())
        self.status.config(text="Сканирование...")

    def scan_folder(self, folder, stop_event):
        try:
            if self.recursive:
                self.scan_recursive(folder, stop_event)
            else:
                self.scan_current(folder, stop_event)

            if not stop_event.is_set():
                self.queue.put(('status', "Готово"))
        except Exception as e:
            self.queue.put(('error', str(e)))

    def scan_recursive(self, folder, stop_event):
        for root, dirs, files in os.walk(folder):
            if stop_event.is_set():
                return

            for name in files:
                if stop_event.is_set():
                    return
                self.process_item(os.path.join(root, name), False, stop_event)

            for name in dirs:
                if stop_event.is_set():
                    return
                self.process_item(os.path.join(root, name), True, stop_event)

    def scan_current(self, folder, stop_event):
        try:
            for entry in os.scandir(folder):
                if stop_event.is_set():
                    return
                self.process_item(entry.path, entry.is_dir(), stop_event)
        except Exception as e:
            pass

    def process_item(self, path, is_dir, stop_event):
        if stop_event.is_set() or path in self.processed_paths:
            return

        try:
            self.processed_paths.add(path)
            size = self.get_folder_size(path, stop_event) if is_dir else os.path.getsize(path)
            item_type = '📁 Папка' if is_dir else '📄 Файл'
            rel_path = os.path.basename(path) if not self.recursive else os.path.relpath(path, self.path_entry.get())

            self.queue.put(('item', (item_type, rel_path, size, path)))
        except Exception as e:
            pass

    def get_folder_size(self, path, stop_event):
        total = 0
        try:
            for entry in os.scandir(path):
                if stop_event.is_set():
                    return total
                if entry.is_file():
                    total += entry.stat().st_size
                elif entry.is_dir():
                    total += self.get_folder_size(entry.path, stop_event)
        except:
            pass
        return total

    def on_double_click(self, event):
        item = self.tree.selection()
        if not item:
            return
        path = self.tree.item(item[0], 'tags')[0]
        if os.path.isdir(path) and not self.recursive:
            self.open_new_window(path)

    def on_right_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            path = self.tree.item(item, 'tags')[0]
            menu = tk.Menu(self.root, tearoff=0)
            menu.add_command(label="Открыть в проводнике", command=lambda: self.open_in_explorer(path))
            menu.post(event.x_root, event.y_root)

    def open_new_window(self, path):
        new_window = tk.Toplevel(self.root)
        SizeAnalyzerApp(new_window, initial_path=path, recursive=False)

    def open_in_explorer(self, path):
        if not os.path.exists(path):
            return

        if platform.system() == "Windows":
            if os.path.isdir(path):
                os.startfile(path)
            else:
                subprocess.Popen(f'explorer /select,"{path}"')
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])

    def check_queue(self):
        try:
            while True:
                task = self.queue.get_nowait()
                if task[0] == 'item':
                    self.data.append(task[1])
                elif task[0] == 'status':
                    self.status.config(text=task[1])
                    self.update_sort()
                    self.update_treeview()
                elif task[0] == 'error':
                    messagebox.showerror("Ошибка", task[1])
        except Empty:
            pass

        self.root.after(100, self.check_queue)


if __name__ == "__main__":
    root = tk.Tk()
    app = SizeAnalyzerApp(root, recursive=True)
    root.mainloop()
