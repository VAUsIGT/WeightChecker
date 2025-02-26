import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from threading import Thread
from queue import Queue

def convert_size(size_bytes):
    """Конвертирует размер в байтах в удобочитаемый формат."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"

class SizeAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Анализатор размера папок")
        
        # Очередь для обновления GUI из фонового потока
        self.queue = Queue()
        
        # Переменные
        self.current_path = tk.StringVar()
        self.data = []
        
        # Создание элементов интерфейса
        self.create_widgets()
        
        # Проверка очереди сообщений
        self.check_queue()

    def create_widgets(self):
        # Фрейм для выбора папки
        top_frame = ttk.Frame(self.root)
        top_frame.pack(padx=10, pady=10, fill=tk.X)
        
        ttk.Label(top_frame, text="Выберите папку:").pack(side=tk.LEFT)
        ttk.Entry(top_frame, textvariable=self.current_path, width=50).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Обзор", command=self.browse_folder).pack(side=tk.LEFT)
        
        # Treeview для отображения результатов
        self.tree = ttk.Treeview(self.root, columns=('name', 'path', 'size'), show='headings')
        self.tree.heading('name', text='Имя', command=lambda: self.sort_column('name', False))
        self.tree.heading('path', text='Путь', command=lambda: self.sort_column('path', False))
        self.tree.heading('size', text='Размер', command=lambda: self.sort_column('size', False))
        self.tree.column('name', width=200)
        self.tree.column('path', width=300)
        self.tree.column('size', width=100)
        self.tree.pack(padx=10, pady=10, expand=True, fill=tk.BOTH)
        
        # Статус бар
        self.status = ttk.Label(self.root, text="Готово")
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.current_path.set(folder)
            self.start_scan_thread(folder)

    def start_scan_thread(self, folder):
        self.status.config(text="Сканирование...")
        self.data.clear()
        self.tree.delete(*self.tree.get_children())
        thread = Thread(target=self.scan_folder, args=(folder,), daemon=True)
        thread.start()

    def scan_folder(self, folder):
        try:
            for root, dirs, files in os.walk(folder):
                # Сначала обрабатываем файлы
                for name in files:
                    path = os.path.join(root, name)
                    if os.path.exists(path):
                        try:
                            size = os.path.getsize(path)
                            self.queue.put(('item', (name, path, size)))
                        except Exception as e:
                            continue
                
                # Затем обрабатываем папки
                for name in dirs:
                    path = os.path.join(root, name)
                    if os.path.exists(path):
                        try:
                            size = self.get_folder_size(path)
                            self.queue.put(('item', (name, path, size)))
                        except Exception as e:
                            continue
            
            self.queue.put(('status', "Готово"))
        except Exception as e:
            self.queue.put(('error', str(e)))

    def get_folder_size(self, path):
        total = 0
        for entry in os.scandir(path):
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += self.get_folder_size(entry.path)
        return total

    def check_queue(self):
        while not self.queue.empty():
            task = self.queue.get()
            if task[0] == 'item':
                name, path, size = task[1]
                self.data.append((name, path, size))
                self.tree.insert('', tk.END, values=(name, path, convert_size(size)))
            elif task[0] == 'status':
                self.status.config(text=task[1])
            elif task[0] == 'error':
                messagebox.showerror("Ошибка", task[1])
        self.root.after(100, self.check_queue)

    def sort_column(self, col, reverse):
        # Сортировка данных
        if col == 'size':
            self.data.sort(key=lambda x: x[2], reverse=reverse)
        else:
            self.data.sort(key=lambda x: x[0 if col == 'name' else 1], reverse=reverse)
        
        # Обновление Treeview
        self.tree.delete(*self.tree.get_children())
        for item in self.data:
            self.tree.insert('', tk.END, values=(item[0], item[1], convert_size(item[2])))
        
        # Изменение направления сортировки
        self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))

if __name__ == "__main__":
    root = tk.Tk()
    app = SizeAnalyzerApp(root)
    root.mainloop()
