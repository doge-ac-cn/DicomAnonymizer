import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import threading

import pydicom
from pydicom import dcmread
from pydicom.dataset import Dataset


class DicomAnonymizerApp:
    def __init__(self, root):
        self.root = root
        root.title("DICOM 匿名化工具 - 每个标签可单独设置替换值")
        root.geometry("1200x750")

        # 数据存储
        self.input_dir = ""
        self.output_dir = ""
        self.all_dicom_files = []
        self.sample_ds = None
        self.modify_tags = {}          # key: (group, elem) -> value: 替换值字符串

        self._create_widgets()

    def _create_widgets(self):
        # ========== 顶部框架：目录设置和开始按钮 ==========
        top_frame = ttk.LabelFrame(self.root, text="目录设置", padding=5)
        top_frame.pack(fill=tk.X, padx=5, pady=5)

        # 第0行：输入文件夹
        ttk.Label(top_frame, text="输入文件夹:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.input_var = tk.StringVar()
        ttk.Entry(top_frame, textvariable=self.input_var, width=60).grid(row=0, column=1, padx=5)
        ttk.Button(top_frame, text="浏览", command=self.select_input_dir).grid(row=0, column=2, padx=5)

        # 第1行：输出文件夹 + 开始按钮（放在右侧）
        ttk.Label(top_frame, text="输出文件夹:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.output_var = tk.StringVar()
        ttk.Entry(top_frame, textvariable=self.output_var, width=60).grid(row=1, column=1, padx=5)
        ttk.Button(top_frame, text="浏览", command=self.select_output_dir).grid(row=1, column=2, padx=5)
        # 开始按钮放在第1行的第3列
        self.start_button = ttk.Button(top_frame, text="开始匿名化", command=self.start_anonymization)
        self.start_button.grid(row=1, column=3, padx=10)

        # 第2行：加载样本按钮
        self.load_button = ttk.Button(top_frame, text="加载当前文件夹第一个 DICOM 作为标签样本", command=self.load_sample)
        self.load_button.grid(row=2, column=0, columnspan=3, pady=5, sticky=tk.W)

        # 第3行：状态信息（待修改标签数 + 处理状态 + 进度条）
        status_frame = ttk.Frame(top_frame)
        status_frame.grid(row=3, column=0, columnspan=4, sticky=tk.W+tk.E, pady=5)
        self.tag_count_label = ttk.Label(status_frame, text="待修改标签数: 0", foreground="blue")
        self.tag_count_label.pack(side=tk.LEFT, padx=10)

        self.process_status_label = ttk.Label(status_frame, text="就绪", foreground="green")
        self.process_status_label.pack(side=tk.LEFT, padx=10)

        # 进度条（放在状态文字右侧）
        self.progress = ttk.Progressbar(status_frame, mode='determinate', length=300)
        self.progress.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        self.percent_label = ttk.Label(status_frame, text="0%", foreground="darkgreen")
        self.percent_label.pack(side=tk.LEFT, padx=5)

        # ========== 中间区域：左右两个表格 ==========
        left_frame = ttk.LabelFrame(self.root, text="DICOM 标签列表 (选中后点击添加)", padding=5)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        scroll_y_left = ttk.Scrollbar(left_frame, orient=tk.VERTICAL)
        scroll_x_left = ttk.Scrollbar(left_frame, orient=tk.HORIZONTAL)

        self.tag_tree = ttk.Treeview(left_frame, columns=("tag", "name", "vr", "value"),
                                     show="headings", yscrollcommand=scroll_y_left.set, xscrollcommand=scroll_x_left.set)
        scroll_y_left.config(command=self.tag_tree.yview)
        scroll_x_left.config(command=self.tag_tree.xview)

        self.tag_tree.heading("tag", text="Tag")
        self.tag_tree.heading("name", text="Keyword / Name")
        self.tag_tree.heading("vr", text="VR")
        self.tag_tree.heading("value", text="Value")
        self.tag_tree.column("tag", width=100)
        self.tag_tree.column("name", width=200)
        self.tag_tree.column("vr", width=50)
        self.tag_tree.column("value", width=400)

        self.tag_tree.grid(row=0, column=0, sticky="nsew")
        scroll_y_left.grid(row=0, column=1, sticky="ns")
        scroll_x_left.grid(row=1, column=0, sticky="ew")
        left_frame.grid_rowconfigure(0, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        # 中间按钮区
        mid_frame = ttk.Frame(self.root, padding=5)
        mid_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        ttk.Button(mid_frame, text="→ 添加选中标签", command=self.add_selected_tags).pack(pady=10)
        ttk.Button(mid_frame, text="删除选中标签 ←", command=self.remove_selected_tags).pack(pady=10)

        # 右侧待修改标签列表（可编辑替换值）
        right_frame = ttk.LabelFrame(self.root, text="待修改标签列表 (双击「替换值」列进行编辑)", padding=5)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        scroll_y_right = ttk.Scrollbar(right_frame, orient=tk.VERTICAL)
        scroll_x_right = ttk.Scrollbar(right_frame, orient=tk.HORIZONTAL)

        self.modify_tree = ttk.Treeview(right_frame, columns=("tag", "keyword", "replace_value"),
                                        show="headings", yscrollcommand=scroll_y_right.set, xscrollcommand=scroll_x_right.set)
        scroll_y_right.config(command=self.modify_tree.yview)
        scroll_x_right.config(command=self.modify_tree.xview)

        self.modify_tree.heading("tag", text="Tag")
        self.modify_tree.heading("keyword", text="Keyword")
        self.modify_tree.heading("replace_value", text="替换值 (双击编辑)")
        self.modify_tree.column("tag", width=120)
        self.modify_tree.column("keyword", width=200)
        self.modify_tree.column("replace_value", width=200)

        self.modify_tree.grid(row=0, column=0, sticky="nsew")
        scroll_y_right.grid(row=0, column=1, sticky="ns")
        scroll_x_right.grid(row=1, column=0, sticky="ew")
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        # 绑定双击编辑事件
        self.modify_tree.bind("<Double-1>", self.edit_replace_value)

        # ========== 底部框架：仅用于占位（不再放置控件） ==========
        bottom_frame = ttk.Frame(self.root, padding=2)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=2)
        # 什么都不放，或者放一个空白标签，避免布局塌陷
        ttk.Label(bottom_frame, text="").pack()

    def select_input_dir(self):
        dir_path = filedialog.askdirectory(title="选择包含 DICOM 文件的文件夹")
        if dir_path:
            self.input_var.set(dir_path)
            self.input_dir = dir_path
            self._scan_dicom_files()

    def select_output_dir(self):
        dir_path = filedialog.askdirectory(title="选择匿名化后保存的文件夹")
        if dir_path:
            self.output_var.set(dir_path)
            self.output_dir = dir_path

    def _scan_dicom_files(self):
        if not self.input_dir:
            return
        self.all_dicom_files = []
        for root, dirs, files in os.walk(self.input_dir):
            for f in files:
                if f.lower().endswith('.dcm'):
                    full_path = os.path.join(root, f)
                    self.all_dicom_files.append(full_path)
        self.process_status_label.config(text=f"找到 {len(self.all_dicom_files)} 个 .dcm 文件")

    def load_sample(self):
        if not self.all_dicom_files:
            messagebox.showwarning("警告", "请先选择含有 .dcm 文件的输入文件夹！")
            return
        sample_path = self.all_dicom_files[0]
        try:
            ds = dcmread(sample_path)
            self.sample_ds = ds
            self._populate_tag_tree(ds)
            self.process_status_label.config(text=f"已加载样本文件: {os.path.basename(sample_path)}")
        except Exception as e:
            messagebox.showerror("错误", f"读取 DICOM 文件失败:\n{e}")

    def _populate_tag_tree(self, ds: Dataset):
        for item in self.tag_tree.get_children():
            self.tag_tree.delete(item)

        for elem in ds:
            tag_str = f"({elem.tag.group:04X},{elem.tag.element:04X})"
            name = elem.name
            vr = elem.VR
            if elem.value is None:
                value_str = ""
            elif isinstance(elem.value, bytes):
                try:
                    value_str = elem.value.decode('utf-8', errors='replace')
                except:
                    value_str = str(elem.value)
            else:
                value_str = str(elem.value)
                if len(value_str) > 200:
                    value_str = value_str[:200] + "..."
            self.tag_tree.insert("", tk.END, values=(tag_str, name, vr, value_str))

    def update_tag_count_display(self):
        count = len(self.modify_tags)
        self.tag_count_label.config(text=f"待修改标签数: {count}")

    def add_selected_tags(self):
        selected = self.tag_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先在左侧标签列表中选中要修改的标签")
            return
        for item in selected:
            values = self.tag_tree.item(item, "values")
            tag_str = values[0]
            keyword = values[1]
            try:
                clean = tag_str.strip('()')
                g_str, e_str = clean.split(',')
                group = int(g_str, 16)
                elem = int(e_str, 16)
                tag_key = (group, elem)
            except:
                continue

            if tag_key not in self.modify_tags:
                self.modify_tags[tag_key] = ""
                self.modify_tree.insert("", tk.END, values=(tag_str, keyword, ""), tags=(tag_key,))
        self.update_tag_count_display()

    def remove_selected_tags(self):
        selected = self.modify_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先在右侧列表中选中要移除的标签")
            return
        for item in selected:
            tag_str = self.modify_tree.item(item, "values")[0]
            try:
                clean = tag_str.strip('()')
                g_str, e_str = clean.split(',')
                group = int(g_str, 16)
                elem = int(e_str, 16)
                tag_key = (group, elem)
                if tag_key in self.modify_tags:
                    del self.modify_tags[tag_key]
            except:
                pass
            self.modify_tree.delete(item)
        self.update_tag_count_display()

    def edit_replace_value(self, event):
        region = self.modify_tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        column = self.modify_tree.identify_column(event.x)
        if column != "#3":
            return
        item = self.modify_tree.identify_row(event.y)
        if not item:
            return
        current_value = self.modify_tree.item(item, "values")[2]
        new_value = simpledialog.askstring("编辑替换值", "请输入新的替换值（留空表示清空标签）:",
                                           initialvalue=current_value)
        if new_value is not None:
            tag_str = self.modify_tree.item(item, "values")[0]
            try:
                clean = tag_str.strip('()')
                g_str, e_str = clean.split(',')
                group = int(g_str, 16)
                elem = int(e_str, 16)
                tag_key = (group, elem)
                self.modify_tags[tag_key] = new_value
            except:
                pass
            values = list(self.modify_tree.item(item, "values"))
            values[2] = new_value
            self.modify_tree.item(item, values=values)
            self.update_tag_count_display()

    def start_anonymization(self):
        if not self.input_dir:
            messagebox.showwarning("警告", "请先选择输入文件夹")
            return
        if not self.output_dir:
            messagebox.showwarning("警告", "请先选择输出文件夹")
            return
        if not self.all_dicom_files:
            self._scan_dicom_files()
            if not self.all_dicom_files:
                messagebox.showwarning("警告", "输入文件夹中没有找到 .dcm 文件")
                return
        if not self.modify_tags:
            messagebox.showwarning("警告", "请先添加需要修改的标签")
            return

        self.progress['maximum'] = len(self.all_dicom_files)
        self.progress['value'] = 0
        self.percent_label.config(text="0%")
        self.start_button.config(state=tk.DISABLED)
        self.load_button.config(state=tk.DISABLED)
        self.process_status_label.config(text="正在匿名化...")

        thread = threading.Thread(target=self._anonymize_worker, daemon=True)
        thread.start()

    def _anonymize_worker(self):
        total = len(self.all_dicom_files)
        failed_tags = {}
        try:
            for idx, src_path in enumerate(self.all_dicom_files):
                rel_path = os.path.relpath(src_path, self.input_dir)
                dst_path = os.path.join(self.output_dir, rel_path)
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)

                ds = dcmread(src_path)
                for (group, elem), replace_value in self.modify_tags.items():
                    tag = (group, elem)
                    if tag in ds:
                        try:
                            ds[tag].value = replace_value
                        except Exception as e:
                            tag_str = f"({group:04X},{elem:04X})"
                            failed_tags[tag_str] = str(e)
                            try:
                                ds[tag].value = ''
                            except:
                                pass
                ds.save_as(dst_path)

                self.root.after(0, self._update_progress, idx+1, total, os.path.basename(src_path))

            if failed_tags:
                warn_msg = "以下标签赋值失败（可能 VR 类型不匹配），已尝试保留原值或设为空：\n"
                for tag, err in list(failed_tags.items())[:10]:
                    warn_msg += f"{tag}: {err}\n"
                if len(failed_tags) > 10:
                    warn_msg += f"... 共 {len(failed_tags)} 个标签\n"
                self.root.after(0, lambda: messagebox.showwarning("警告", warn_msg))
            self.root.after(0, self._anonymization_finished, True, "")
        except Exception as e:
            self.root.after(0, self._anonymization_finished, False, str(e))

    def _update_progress(self, current, total, filename):
        self.progress['value'] = current
        percent = int(current / total * 100) if total else 0
        self.percent_label.config(text=f"{percent}%")
        self.process_status_label.config(text=f"处理中: {filename} ({current}/{total})")

    def _anonymization_finished(self, success, error_msg):
        self.start_button.config(state=tk.NORMAL)
        self.load_button.config(state=tk.NORMAL)
        if success:
            messagebox.showinfo("完成", f"匿名化完成！\n共处理 {len(self.all_dicom_files)} 个文件\n保存位置: {self.output_dir}")
            self.process_status_label.config(text="就绪")
        else:
            messagebox.showerror("错误", f"匿名化过程中出现错误:\n{error_msg}")
            self.process_status_label.config(text="处理出错")
        self.progress['value'] = 0
        self.percent_label.config(text="0%")


if __name__ == "__main__":
    root = tk.Tk()
    app = DicomAnonymizerApp(root)
    root.mainloop()
