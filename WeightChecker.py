import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from threading import Thread, Event
from queue import Queue, Empty
import platform
import subprocess
import shutil


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
        # Добавляем стиль для прогрессбара
        self.configure('green.Horizontal.TProgressbar',
                     background='#90EE90',
                     troughcolor='#e0e0e0',
                     bordercolor='#c0c0c0',
                     lightcolor='#c0ffc0',
                     darkcolor='#60a060')
        # Остальные стили...
        self.configure('TFrame', background='#f0f0f0')
        self.configure('TLabel', background='#f0f0f0', font=('Segoe UI', 9))
        self.configure('TButton', font=('Segoe UI', 9), relief='flat')
        self.configure('Treeview', rowheight=25, font=('Segoe UI', 9))
        self.configure('Treeview.Heading', font=('Segoe UI', 9, 'bold'))
        self.map('TButton', background=[('active', '#e1e1e1')])


class SizeAnalyzerApp:
    def __init__(self, root, initial_path=None, recursive=True):
        self.root = root
        self.root.title("WeightChecker")
        self.style = ModernStyle()
        self.recursive = recursive
        self.initial_path = initial_path

        # Управление потоками
        self.stop_event = Event()
        self.scan_thread = None
        self.queue = Queue()
        self.data = []
        self.processed_paths = set()
        self.total_items = 0
        self.processed_items = 0

        # Настройки фильтрации
        self.show_hidden = tk.BooleanVar(value=False)
        self.file_mask = tk.StringVar(value="*")

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

        # Поле пути
        self.path_entry = ttk.Entry(header_frame, width=110, font=('Segoe UI', 10))
        self.path_entry.pack(side=tk.LEFT, padx=5)

        # Кнопка обзора
        ttk.Button(header_frame, text="Обзор", command=self.browse_folder,
                   style='Accent.TButton').pack(side=tk.LEFT, padx=5)

        # Панель управления
        control_frame = ttk.Frame(self.root)
        control_frame.pack(padx=15, pady=5, fill=tk.X)

        # Mode Selector
        mode_frame = ttk.Frame(self.root)
        mode_frame.pack(padx=15, pady=5, fill=tk.X)

        self.mode_var = tk.BooleanVar(value=self.recursive)
        ttk.Radiobutton(mode_frame, text="Рекурсивный поиск", variable=self.mode_var,
                        value=True, command=self.mode_changed).pack(side=tk.LEFT, padx=15)
        ttk.Radiobutton(mode_frame, text="Только текущая папка", variable=self.mode_var,
                        value=False, command=self.mode_changed).pack(side=tk.LEFT)
        # Маска файлов
        mask_frame = ttk.Frame(mode_frame)
        mask_frame.pack(side=tk.RIGHT, padx=5)
        ttk.Label(mask_frame, text="Маска:").pack(side=tk.LEFT)
        ttk.Entry(mask_frame, textvariable=self.file_mask, width=15).pack(side=tk.LEFT)
        # Чекбокс скрытых файлов
        ttk.Checkbutton(mode_frame, text="Показывать скрытые",
                        variable=self.show_hidden).pack(side=tk.RIGHT, padx=10)

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

        # Строка состояния с прогрессбаром
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=1, pady=1)

        self.status = ttk.Label(status_frame, text="Готово", relief=tk.SUNKEN)
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.progress = ttk.Progressbar(
            status_frame,
            orient=tk.HORIZONTAL,
            mode='determinate',
            style='green.Horizontal.TProgressbar',
            length=500  # длина
        )
        self.progress.pack_forget()

        # Custom Style
        self.style.configure('Accent.TButton', background='#0078d4', foreground='white')
        self.style.map('Accent.TButton',
                       background=[('active', '#006cbd'), ('pressed', '#005a9e')])

    def is_hidden(self, path):
        """Проверка, является ли файл/папка скрытым"""
        try:
            if platform.system() == 'Windows':
                return bool(os.stat(path).st_file_attributes & 2)  # FILE_ATTRIBUTE_HIDDEN
            else:
                return os.path.basename(path).startswith('.')
        except:
            return False

    def matches_mask(self, filename):
        """Проверка соответствия маске файлов"""
        import fnmatch
        return fnmatch.fnmatch(filename, self.file_mask.get())

    def update_progress(self):
        """Обновление прогрессбара"""
        if self.total_items > 0:
            progress = (self.processed_items / self.total_items) * 100
            self.progress['value'] = progress
            self.root.update_idletasks()

    def count_total_items(self, folder):
        """Подсчет общего количества элементов для прогрессбара"""
        self.total_items = 0
        if self.recursive:
            for root, dirs, files in os.walk(folder):
                if self.stop_event.is_set():
                    return
                self.total_items += len(files) + len(dirs)
        else:
            self.total_items = len(os.listdir(folder))
        self.processed_items = 0

    def sort(self, column):
        """Обработчик сортировки с индикацией направления"""
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False

        for col in ['type', 'name', 'size']:
            text = self.column_names[col]
            if col == self.sort_column:
                arrow = ' ▼' if self.sort_reverse else ' ▲'
                text += arrow
            self.tree.heading(col, text=text)

        self.update_sort()
        self.update_treeview()

    def update_sort(self):
        if self.sort_column == 'type':
            self.data.sort(key=lambda x: (x[0], x[1].lower()), reverse=self.sort_reverse)
        elif self.sort_column == 'name':
            self.data.sort(key=lambda x: x[1].lower(), reverse=self.sort_reverse)
        else:
            self.data.sort(key=lambda x: x[2], reverse=self.sort_reverse)

    def update_treeview(self):
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
        self.stop_scanning()
        self.reset_scan_state()
        self.count_total_items(folder)
        self.progress['value'] = 0
        self.progress.pack(side=tk.RIGHT, fill=tk.X, expand=False)  # Показываем прогрессбар

        self.scan_thread = Thread(
            target=self.scan_folder,
            args=(folder, self.stop_event),
            daemon=True
        )
        self.scan_thread.start()

    def stop_scanning(self):
        if self.scan_thread and self.scan_thread.is_alive():
            self.stop_event.set()
            self.scan_thread.join(timeout=0.5)
            self.scan_thread = None

    def reset_scan_state(self):
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

            # Фильтрация скрытых папок
            if not self.show_hidden.get():
                dirs[:] = [d for d in dirs if not self.is_hidden(os.path.join(root, d))]

            for name in files:
                if stop_event.is_set():
                    return
                path = os.path.join(root, name)
                if self.should_process(path):
                    self.process_item(path, False, stop_event)

            for name in dirs:
                if stop_event.is_set():
                    return
                path = os.path.join(root, name)
                if self.should_process(path):
                    self.process_item(path, True, stop_event)

    def scan_current(self, folder, stop_event):
        try:
            for entry in os.scandir(folder):
                if stop_event.is_set():
                    return
                path = entry.path
                if self.should_process(path):
                    self.process_item(path, entry.is_dir(), stop_event)
        except Exception as e:
            pass

    def should_process(self, path):
        """Проверка всех условий фильтрации"""
        if not self.show_hidden.get() and self.is_hidden(path):
            return False
        if not self.matches_mask(os.path.basename(path)):
            return False
        return True

    def process_item(self, path, is_dir, stop_event):
        if stop_event.is_set() or path in self.processed_paths:
            return

        try:
            self.processed_paths.add(path)
            size = self.get_folder_size(path, stop_event) if is_dir else os.path.getsize(path)
            item_type = '📁 Папка' if is_dir else '📄 Файл'
            rel_path = os.path.basename(path) if not self.recursive else os.path.relpath(path, self.path_entry.get())

            self.queue.put(('item', (item_type, rel_path, size, path)))
            self.processed_items += 1
            self.queue.put(('progress', None))
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
            menu.add_command(label="Переименовать", command=lambda: self.rename_selected_item(item, path))
            menu.add_command(label="Удалить", command=lambda: self.delete_selected_item(item, path))
            menu.post(event.x_root, event.y_root)

    def delete_selected_item(self, item, path):
        if not messagebox.askyesno("Подтверждение", "Вы уверены, что хотите удалить этот элемент?"):
            return

        try:
            if os.path.isfile(path):
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)

            # Обновляем данные
            self.data = [x for x in self.data if x[3] != path]
            self.processed_paths.discard(path)

            # Обновляем отображение
            self.update_sort()
            self.update_treeview()
            messagebox.showinfo("Успех", "Элемент успешно удален")

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось удалить: {str(e)}")

    def rename_selected_item(self, item, old_path):
        new_name = simpledialog.askstring(
            "Переименование",
            "Введите новое имя:",
            initialvalue=os.path.basename(old_path)
        )

        if not new_name:
            return

        try:
            new_path = os.path.join(os.path.dirname(old_path), new_name)
            os.rename(old_path, new_path)

            # Обновляем данные
            for i, entry in enumerate(self.data):
                if entry[3] == old_path:
                    rel_path = os.path.relpath(new_path, self.path_entry.get()) if self.recursive else new_name
                    self.data[i] = (entry[0], rel_path, entry[2], new_path)

            self.processed_paths.discard(old_path)
            self.processed_paths.add(new_path)

            self.update_sort()
            self.update_treeview()
            messagebox.showinfo("Успех", "Элемент успешно переименован")

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось переименовать: {str(e)}")

    def open_new_window(self, path):
        new_window = tk.Toplevel(self.root)
        new_window.title("WeightChecker subwindow")
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
                    self.progress.pack_forget()  # Скрываем прогрессбар
                elif task[0] == 'error':
                    messagebox.showerror("Ошибка", task[1])
                    self.progress.pack_forget()
                elif task[0] == 'progress':
                    self.update_progress()
        except Empty:
            pass

        self.root.after(100, self.check_queue)


if __name__ == "__main__":
    root = tk.Tk()
    app = SizeAnalyzerApp(root, recursive=True)
    root.mainloop()
