import sys
import os
import subprocess
import threading
import queue
import tkinter as tk
from tkinter import messagebox
from tkinter.scrolledtext import ScrolledText
import requests
import urllib3
import warnings
import logging

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from config import MAGENTO as CFG_MAGENTO, MEDUSA as CFG_MEDUSA
except Exception:
    CFG_MAGENTO = {}
    CFG_MEDUSA = {}

from services.magento_auth import get_magento_token
from services.medusa_auth import get_medusa_token
from migrators.utils import clean_stop_signal



class SelectionDialog(tk.Toplevel):
    def __init__(self, parent, title, items, initial_selection=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("600x500")
        self.items = items
        self.selected_ids = set(initial_selection or [])
        self.vars = {}
        
        self.result = None
        
        self._build_ui()
        self._populate()

    def _build_ui(self):
        top = tk.Frame(self)
        top.pack(fill="x", padx=10, pady=10)
        tk.Label(top, text="Search:").pack(side="left")
        self.var_search = tk.StringVar()
        self.var_search.trace("w", self._on_search)
        tk.Entry(top, textvariable=self.var_search).pack(side="left", fill="x", expand=True, padx=5)

        tk.Entry(top, textvariable=self.var_search).pack(side="left", fill="x", expand=True, padx=5)
        btn_frame = tk.Frame(self)
        btn_frame.pack(side="bottom", fill="x", padx=10, pady=10)
        tk.Button(btn_frame, text="OK", width=10, command=self._on_ok).pack(side="right", padx=5)
        tk.Button(btn_frame, text="Cancel", width=10, command=self.destroy).pack(side="right", padx=5)
        
        tk.Button(btn_frame, text="Cancel", width=10, command=self.destroy).pack(side="right", padx=5)
        sel_frame = tk.Frame(self)
        sel_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 5))
        tk.Button(sel_frame, text="Select All", command=self._select_all).pack(side="left")
        tk.Button(sel_frame, text="Deselect All", command=self._deselect_all).pack(side="left", padx=5)
        self.canvas = tk.Canvas(self)
        self.scrollbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True, padx=10)
        self.scrollbar.pack(side="right", fill="y")
        
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))
        
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except:
            pass
        self.destroy()

    def _on_mousewheel(self, event):
        try:
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        except:
            pass

    def _populate(self, filter_text=None):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        self.vars = {}
        row = 0
        
        filter_text = filter_text.lower() if filter_text else None

        
        count = 0
        for item in self.items:
            label = item.get('label', '')
            if filter_text and filter_text not in label.lower():
                continue
            
            count += 1
            if count > 300:
                tk.Label(self.scrollable_frame, text="... (Use search to filter more) ...", fg="gray").grid(row=row, column=0, sticky="w", padx=5)
                break
                
            iid = str(item['id'])
            var = tk.BooleanVar(value=(iid in self.selected_ids))
            self.vars[iid] = var
            
            self.vars[iid] = var
            cb = tk.Checkbutton(self.scrollable_frame, text=label, variable=var,
                                command=lambda i=iid, v=var: self._toggle(i, v))
            cb.grid(row=row, column=0, sticky="w", padx=5, pady=2)
            row += 1

    def _toggle(self, iid, var):
        if var.get():
            self.selected_ids.add(iid)
        else:
            self.selected_ids.discard(iid)

    def _on_search(self, *args):
        self._populate(self.var_search.get())
    
    def _select_all(self):
        for iid in self.vars:
            self.vars[iid].set(True)
            self.selected_ids.add(iid)
            
    def _deselect_all(self):
        for iid in self.vars:
            self.vars[iid].set(False)
            self.selected_ids.discard(iid)

    def _on_ok(self):
        self.result = list(self.selected_ids)
        self._on_close()


class MigrationGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Magento -> Medusa Migration")
        self.geometry("920x640")

        self._proc = None
        self._q = queue.Queue()
        self._reader_thread = None

        self.cached_magento_token = None
        self.cached_medusa_token = None
        
        self.cached_products = None
        self.cached_categories = None
        self.cached_customers = None
        self.cached_orders = None
        
        self.init_done = False 

        self._build_ui()
        self._setup_logging()
        self.after(80, self._drain_queue)
    
    def _setup_logging(self):
        def warning_handler(message, category, filename, lineno, file=None, line=None):
            warning_msg = f"Warning: {category.__name__}: {message}\n"
            self._log(warning_msg)
        
        warnings.showwarning = warning_handler

    def _build_ui(self):
        top = tk.Frame(self)
        top.pack(fill="x", padx=12, pady=10)

        entities_box = tk.LabelFrame(top, text="Select Data to Sync")
        entities_box.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.var_products = tk.BooleanVar(value=True)
        self.var_categories = tk.BooleanVar(value=True)
        self.var_customers = tk.BooleanVar(value=True)
        self.var_orders = tk.BooleanVar(value=True)

        tk.Checkbutton(entities_box, text="Products", variable=self.var_products).grid(row=0, column=0, sticky="w", padx=10, pady=6)
        tk.Checkbutton(entities_box, text="Categories", variable=self.var_categories).grid(row=0, column=1, sticky="w", padx=10, pady=6)
        tk.Checkbutton(entities_box, text="Customers", variable=self.var_customers).grid(row=1, column=0, sticky="w", padx=10, pady=6)
        tk.Checkbutton(entities_box, text="Orders", variable=self.var_orders).grid(row=1, column=1, sticky="w", padx=10, pady=6)

        btns = tk.Frame(entities_box)
        btns.grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 10))
        tk.Button(btns, text="Select All", command=self._select_all).pack(side="left")
        tk.Button(btns, text="Select None", command=self._select_none).pack(side="left", padx=(8, 0))

        filter_box = tk.LabelFrame(top, text="Filter by ID (comma separated)")
        filter_box.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        tk.Label(filter_box, text="Product IDs:").grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))
        self.var_product_ids = tk.StringVar()
        tk.Entry(filter_box, textvariable=self.var_product_ids, width=20).grid(row=0, column=1, sticky="w", padx=10, pady=(8, 4))
        tk.Button(filter_box, text="Select...", command=self._open_product_selector).grid(row=0, column=2, padx=5)
        
        tk.Label(filter_box, text="Category IDs:").grid(row=1, column=0, sticky="w", padx=10, pady=4)
        self.var_category_ids = tk.StringVar()
        tk.Entry(filter_box, textvariable=self.var_category_ids, width=20).grid(row=1, column=1, sticky="w", padx=10, pady=4)
        tk.Button(filter_box, text="Select...", command=self._open_category_selector).grid(row=1, column=2, padx=5)
        
        tk.Label(filter_box, text="Customer IDs:").grid(row=2, column=0, sticky="w", padx=10, pady=4)
        self.var_customer_ids = tk.StringVar()
        tk.Entry(filter_box, textvariable=self.var_customer_ids, width=20).grid(row=2, column=1, sticky="w", padx=10, pady=4)
        tk.Button(filter_box, text="Select...", command=self._open_customer_selector).grid(row=2, column=2, padx=5)
        
        tk.Label(filter_box, text="Order IDs:").grid(row=3, column=0, sticky="w", padx=10, pady=4)
        self.var_order_ids = tk.StringVar()
        tk.Entry(filter_box, textvariable=self.var_order_ids, width=20).grid(row=3, column=1, sticky="w", padx=10, pady=(4, 10))
        tk.Button(filter_box, text="Select...", command=self._open_order_selector).grid(row=3, column=2, padx=5, pady=(0, 5))

        opts_box = tk.LabelFrame(top, text="Options")
        opts_box.pack(side="left", fill="x")

        tk.Label(opts_box, text="Limit (0 = unlimited):").grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))
        self.var_limit = tk.StringVar(value="0")
        tk.Entry(opts_box, textvariable=self.var_limit, width=12).grid(row=0, column=1, sticky="w", padx=10, pady=(8, 4))

        self.var_dry_run = tk.BooleanVar(value=False)
        self.var_dry_run_file = tk.BooleanVar(value=False)
        
        dr_frame = tk.Frame(opts_box)
        dr_frame.grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 5))
        
        tk.Checkbutton(dr_frame, text="Dry-run (payload only)", variable=self.var_dry_run).pack(side="left")
        self.cb_dry_run_file = tk.Checkbutton(dr_frame, text="Export to file", variable=self.var_dry_run_file)
        self.cb_dry_run_file.pack(side="left", padx=(10, 0))

        self.var_finalize_orders = tk.BooleanVar(value=True)
        tk.Checkbutton(opts_box, text="Finalize orders (Draft -> Order)", variable=self.var_finalize_orders).grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))

        tk.Checkbutton(opts_box, text="Finalize orders (Draft -> Order)", variable=self.var_finalize_orders).grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))
        cfg_container = tk.Frame(self)
        cfg_container.pack(fill="x", padx=12, pady=(0, 6))
        
        self.cfg_visible = tk.BooleanVar(value=False)
        cfg_toggle_btn = tk.Button(cfg_container, text="▼ Show Configuration", command=self._toggle_config)
        cfg_toggle_btn.pack(anchor="w")
        
        self.cfg_frame = tk.Frame(cfg_container)
        self.cfg_frame = tk.Frame(cfg_container)
        
        cfg = self.cfg_frame

        mag_box = tk.LabelFrame(cfg, text="Magento Configuration (defaults from config.py)")
        mag_box.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.var_magento_base_url = tk.StringVar(value=str(CFG_MAGENTO.get("BASE_URL", "")))
        self.var_magento_user = tk.StringVar(value=str(CFG_MAGENTO.get("ADMIN_USERNAME", "")))
        self.var_magento_pass = tk.StringVar(value=str(CFG_MAGENTO.get("ADMIN_PASSWORD", "")))
        self.var_magento_verify = tk.BooleanVar(value=bool(CFG_MAGENTO.get("VERIFY_SSL", False)))

        tk.Label(mag_box, text="Base URL").grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))
        tk.Entry(mag_box, textvariable=self.var_magento_base_url, width=40).grid(row=0, column=1, sticky="w", padx=10, pady=(8, 4))
        tk.Label(mag_box, text="Admin username").grid(row=1, column=0, sticky="w", padx=10, pady=4)
        tk.Entry(mag_box, textvariable=self.var_magento_user, width=40).grid(row=1, column=1, sticky="w", padx=10, pady=4)
        tk.Label(mag_box, text="Admin password").grid(row=2, column=0, sticky="w", padx=10, pady=4)
        pass_frame_mag = tk.Frame(mag_box)
        pass_frame_mag.grid(row=2, column=1, sticky="w", padx=10, pady=4)
        self.ent_magento_pass = tk.Entry(pass_frame_mag, textvariable=self.var_magento_pass, width=32, show="*")
        self.ent_magento_pass.pack(side="left")
        tk.Button(pass_frame_mag, text="👁", width=2, command=lambda: self._toggle_pass(self.ent_magento_pass)).pack(side="left", padx=2)
        tk.Checkbutton(mag_box, text="Verify SSL", variable=self.var_magento_verify).grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 10))
        tk.Button(mag_box, text="Test Magento", command=self._test_magento).grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))

        med_box = tk.LabelFrame(cfg, text="Medusa Configuration (defaults from config.py)")
        med_box.pack(side="left", fill="x", expand=True)

        self.var_medusa_base_url = tk.StringVar(value=str(CFG_MEDUSA.get("BASE_URL", "")))
        self.var_medusa_email = tk.StringVar(value=str(CFG_MEDUSA.get("EMAIL", "")))
        self.var_medusa_pass = tk.StringVar(value=str(CFG_MEDUSA.get("PASSWORD", "")))

        tk.Label(med_box, text="Base URL").grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))
        tk.Entry(med_box, textvariable=self.var_medusa_base_url, width=40).grid(row=0, column=1, sticky="w", padx=10, pady=(8, 4))
        tk.Label(med_box, text="Email").grid(row=1, column=0, sticky="w", padx=10, pady=4)
        tk.Entry(med_box, textvariable=self.var_medusa_email, width=40).grid(row=1, column=1, sticky="w", padx=10, pady=4)
        tk.Label(med_box, text="Password").grid(row=2, column=0, sticky="w", padx=10, pady=4)
        pass_frame_med = tk.Frame(med_box)
        pass_frame_med.grid(row=2, column=1, sticky="w", padx=10, pady=4)
        self.ent_medusa_pass = tk.Entry(pass_frame_med, textvariable=self.var_medusa_pass, width=32, show="*")
        self.ent_medusa_pass.pack(side="left")
        tk.Button(pass_frame_med, text="👁", width=2, command=lambda: self._toggle_pass(self.ent_medusa_pass)).pack(side="left", padx=2)
        tk.Button(med_box, text="Test Medusa", command=self._test_medusa).grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))

        actions = tk.Frame(self)
        actions.pack(fill="x", padx=12)
        self.btn_run = tk.Button(actions, text="Run", width=14, command=self._run)
        self.btn_run.pack(side="left")
        self.btn_stop = tk.Button(actions, text="Stop", width=14, state="disabled", command=self._stop)
        self.btn_stop.pack(side="left", padx=(10, 0))
        
        # Pause/Resume Button
        self.pause_btn = ttk.Button(
            actions, # Corrected parent frame to 'actions'
            text="Pause",
            command=self._pause_resume,
            state=tk.DISABLED
        )
        self.pause_btn.pack(side="left", padx=(10, 0)) # Adjusted padx for consistency
        
        tk.Button(actions, text="Clear log", width=14, command=self._clear_log).pack(side="left", padx=(10, 0))

        log_box = tk.LabelFrame(self, text="Log")
        log_box.pack(fill="both", expand=True, padx=12, pady=12)
        self.txt = ScrolledText(log_box, wrap="word")
        self.txt.pack(fill="both", expand=True, padx=10, pady=10)
        self._log("Ready. Press Run to start.\n")

    def _select_all(self):
        self.var_products.set(True)
        self.var_categories.set(True)
        self.var_customers.set(True)
        self.var_orders.set(True)

    def _select_none(self):
        self.var_products.set(False)
        self.var_categories.set(False)
        self.var_customers.set(False)
        self.var_orders.set(False)

    def _clear_log(self):
        self.txt.delete("1.0", "end")
        self.init_done = False

    def _log(self, s: str):
        if threading.current_thread() is threading.main_thread():
            self.txt.insert("end", s)
            self.txt.see("end")
        else:
            self.after(0, lambda: self._log(s))

    def _save_to_config_py(self):
        magento_base = self.var_magento_base_url.get().strip().rstrip("/")
        magento_user = self.var_magento_user.get().strip()
        magento_pass = self.var_magento_pass.get().strip()
        magento_verify = self.var_magento_verify.get()

        medusa_base = self.var_medusa_base_url.get().strip().rstrip("/")
        medusa_email = self.var_medusa_email.get().strip()
        medusa_pass = self.var_medusa_pass.get().strip()
        
        current_medusa = dict(CFG_MEDUSA)
        
        content = f'''MAGENTO = {{
    "BASE_URL": "{magento_base}",
    "ADMIN_USERNAME": "{magento_user}",
    "ADMIN_PASSWORD": "{magento_pass}",
    "VERIFY_SSL": {magento_verify},
}}

MEDUSA = {{
    "BASE_URL": "{medusa_base}",
    "EMAIL": "{medusa_email}",
    "PASSWORD": "{medusa_pass}",
    "SALES_CHANNEL": "{current_medusa.get('SALES_CHANNEL', 'Default Sales Channel')}",
}}
'''
        try:
            with open("config.py", "w", encoding="utf-8") as f:
                f.write(content)
            self._log("Configuration saved into config.py\n")
        except Exception as e:
            self._log(f"Could not save config.py: {e}\n")

    def _get_entities(self):
        entities = []
        if self.var_products.get():
            entities.append("products")
        if self.var_categories.get():
            entities.append("categories")
        if self.var_customers.get():
            entities.append("customers")
        if self.var_orders.get():
            entities.append("orders")
        return entities

    def _toggle_config(self):
        if self.cfg_visible.get():
            self.cfg_frame.pack_forget()
            self.cfg_visible.set(False)
            for widget in self.cfg_frame.master.winfo_children():
                if isinstance(widget, tk.Button):
                    widget.config(text="▼ Show Configuration")
                    break
        else:
            self.cfg_frame.pack(fill="x", pady=5)
            self.cfg_visible.set(True)
            for widget in self.cfg_frame.master.winfo_children():
                if isinstance(widget, tk.Button):
                    widget.config(text="▲ Hide Configuration")
                    break

    def _get_magento_client(self):
        base_url = (self.var_magento_base_url.get() or "").strip().rstrip("/")
        user = (self.var_magento_user.get() or "").strip()
        pwd = (self.var_magento_pass.get() or "").strip()
        verify = bool(self.var_magento_verify.get())
        
        if not base_url or not user:
            messagebox.showerror("Error", "Please enter Magento configuration first.")
            return None

        from connectors.magento_connector import MagentoConnector
        
        token = self.cached_magento_token
        if not token:
            try:
                token = get_magento_token(base_url, user, pwd, verify, logger=self._log)
                self.cached_magento_token = token
            except Exception as e:
                error_msg = f"Lỗi Login Magento: {str(e)}\n"
                self._log(error_msg)
                messagebox.showerror("Lỗi Login Magento", str(e))
                return None
        
        return MagentoConnector(base_url, token, verify)

    def _toggle_pass(self, entry_widget):
        if entry_widget.cget("show") == "*":
            entry_widget.config(show="")
        else:
            entry_widget.config(show="*")

    def _open_product_selector(self):
        if self.cached_products:
            initial = [x.strip() for x in self.var_product_ids.get().split(",") if x.strip()]
            dlg = SelectionDialog(self, "Select Products", self.cached_products, initial_selection=initial)
            self.wait_window(dlg)
            if dlg.result is not None:
                self.var_product_ids.set(", ".join(dlg.result))
            return
        
        # Loading popup
        loading = tk.Toplevel(self)
        loading.title("Loading...")
        loading.geometry("300x120")
        tk.Label(loading, text="Loading product list from Magento...\n(This might take a few seconds)", padx=20, pady=20).pack()
        loading.transient(self)
        loading.grab_set()
        
        result_queue = queue.Queue()

        def worker():
            try:
                # Get client inside the thread to avoid blocking UI on first login
                client = self._get_magento_client()
                if not client:
                    raise Exception("Failed to get Magento client. Check credentials.")

                page = 1
                items = []
                while True:
                    res = client.get_products(page=page, page_size=100, fields="items[id,name,sku]")
                    chunk = res.get('items', [])
                    if not chunk: break
                    
                    for p in chunk:
                        items.append({
                            'id': p.get('id'),
                            'label': f"[{p.get('id')}] {p.get('sku')} - {p.get('name')}"
                        })
                    
                    page += 1
                    if page > 20: break
                result_queue.put(items)
            except Exception as e:
                result_queue.put(e)

        threading.Thread(target=worker, daemon=True).start()

        def check_result():
            try:
                res = result_queue.get_nowait()
                loading.destroy()
                
                if isinstance(res, Exception):
                    error_msg = f"Failed to fetch products: {res}\n"
                    self._log(error_msg)
                else:
                    self.cached_products = res
                    initial = [x.strip() for x in self.var_product_ids.get().split(",") if x.strip()]
                    dlg = SelectionDialog(self, "Select Products", res, initial_selection=initial)
                    self.wait_window(dlg)
                    
                    if dlg.result is not None:
                        self.var_product_ids.set(", ".join(dlg.result))
            except queue.Empty:
                self.after(100, check_result)

        check_result()


    def _open_category_selector(self):
        if self.cached_categories:
            initial = [x.strip() for x in self.var_category_ids.get().split(",") if x.strip()]
            dlg = SelectionDialog(self, "Select Categories", self.cached_categories, initial_selection=initial)
            self.wait_window(dlg)
            if dlg.result is not None:
                self.var_category_ids.set(", ".join(dlg.result))
            return
            
        # Loading popup
        loading = tk.Toplevel(self)
        loading.title("Loading...")
        loading.geometry("300x120")
        tk.Label(loading, text="Loading category list from Magento...\n(This might take a few seconds)", padx=20, pady=20).pack()
        loading.transient(self)
        loading.grab_set()
        
        result_queue = queue.Queue()

        def worker():
            try:
                # Get client inside the thread
                client = self._get_magento_client()
                if not client:
                    raise Exception("Failed to get Magento client. Check credentials.")

                res = client.get_categories(page=1, page_size=1000, fields="items[id,name,level,parent_id]")
                chunk = res.get('items', [])
                
                items = []
                for c in chunk:
                    cid = c.get('id')
                    level = int(c.get('level') or 0)
                    
                    if cid == 1 or cid == "1" or level == 0:
                        continue
                        
                    indent = "--" * max(0, level - 1)
                    items.append({
                        'id': cid,
                        'label': f"{indent} [{cid}] {c.get('name')}"
                    })
                result_queue.put(items)
            except Exception as e:
                result_queue.put(e)

        threading.Thread(target=worker, daemon=True).start()

        def check_result():
            try:
                res = result_queue.get_nowait()
                loading.destroy()
                
                if isinstance(res, Exception):
                    error_msg = f"Failed to fetch categories: {res}\n"
                    self._log(error_msg)
                else:
                    self.cached_categories = res
                    initial = [x.strip() for x in self.var_category_ids.get().split(",") if x.strip()]
                    dlg = SelectionDialog(self, "Select Categories", res, initial_selection=initial)
                    self.wait_window(dlg)
                    
                    if dlg.result is not None:
                        self.var_category_ids.set(", ".join(dlg.result))
            except queue.Empty:
                self.after(100, check_result)

        check_result()

    def _open_customer_selector(self):
        if self.cached_customers:
            initial = [x.strip() for x in self.var_customer_ids.get().split(",") if x.strip()]
            dlg = SelectionDialog(self, "Select Customers", self.cached_customers, initial_selection=initial)
            self.wait_window(dlg)
            if dlg.result is not None:
                self.var_customer_ids.set(", ".join(dlg.result))
            return
            
        # Loading popup
        loading = tk.Toplevel(self)
        loading.title("Loading...")
        loading.geometry("300x120")
        tk.Label(loading, text="Loading customer list from Magento...\n(This might take a few seconds)", padx=20, pady=20).pack()
        loading.transient(self)
        loading.grab_set()
        
        result_queue = queue.Queue()

        def worker():
            try:
                # Get client inside the thread
                client = self._get_magento_client()
                if not client:
                    raise Exception("Failed to get Magento client. Check credentials.")

                page = 1
                items = []
                while True:
                    res = client.get_customers(page=page, page_size=100)
                    chunk = res.get('items', [])
                    if not chunk: break
                    
                    for c in chunk:
                        cid = c.get('id')
                        email = c.get('email')
                        fname = c.get('firstname') or ''
                        lname = c.get('lastname') or ''
                        items.append({
                            'id': cid,
                            'label': f"[{cid}] {fname} {lname} - {email}"
                        })
                    
                    page += 1
                    if page > 10: break
                result_queue.put(items)
            except Exception as e:
                result_queue.put(e)

        threading.Thread(target=worker, daemon=True).start()

        def check_result():
            try:
                res = result_queue.get_nowait()
                loading.destroy()
                
                if isinstance(res, Exception):
                    error_msg = f"Failed to fetch customers: {res}\n"
                    self._log(error_msg)
                else:
                    self.cached_customers = res
                    initial = [x.strip() for x in self.var_customer_ids.get().split(",") if x.strip()]
                    dlg = SelectionDialog(self, "Select Customers", res, initial_selection=initial)
                    self.wait_window(dlg)
                    
                    if dlg.result is not None:
                        self.var_customer_ids.set(", ".join(dlg.result))
            except queue.Empty:
                self.after(100, check_result)

        check_result()
        
    def _open_order_selector(self):
        if self.cached_orders:
            initial = [x.strip() for x in self.var_order_ids.get().split(",") if x.strip()]
            dlg = SelectionDialog(self, "Select Orders", self.cached_orders, initial_selection=initial)
            self.wait_window(dlg)
            if dlg.result is not None:
                self.var_order_ids.set(", ".join(dlg.result))
            return
            
        # Loading popup
        loading = tk.Toplevel(self)
        loading.title("Loading...")
        loading.geometry("300x120")
        tk.Label(loading, text="Loading order list from Magento...\n(This might take a few seconds)", padx=20, pady=20).pack()
        loading.transient(self)
        loading.grab_set()
        
        result_queue = queue.Queue()

        def worker():
            try:
                # Get client inside the thread
                client = self._get_magento_client()
                if not client:
                    raise Exception("Failed to get Magento client. Check credentials.")

                page = 1
                items = []
                while True:
                    res = client.get_orders(page=page, page_size=50)
                    chunk = res.get('items', [])
                    if not chunk: break
                    
                    for o in chunk:
                        oid = o.get('entity_id')
                        inc = o.get('increment_id')
                        total = o.get('grand_total')
                        items.append({
                            'id': oid,
                            'label': f"[{oid}] Order #{inc} - ${total:.2f}" if total else f"[{oid}] Order #{inc}"
                        })
                    
                    page += 1
                    if page > 10: break
                result_queue.put(items)
            except Exception as e:
                result_queue.put(e)

        threading.Thread(target=worker, daemon=True).start()

        def check_result():
            try:
                res = result_queue.get_nowait()
                loading.destroy()
                
                if isinstance(res, Exception):
                    error_msg = f"Failed to fetch orders: {res}\n"
                    self._log(error_msg)
                else:
                    self.cached_orders = res
                    initial = [x.strip() for x in self.var_order_ids.get().split(",") if x.strip()]
                    dlg = SelectionDialog(self, "Select Orders", res, initial_selection=initial)
                    self.wait_window(dlg)
                    
                    if dlg.result is not None:
                        self.var_order_ids.set(", ".join(dlg.result))
            except queue.Empty:
                self.after(100, check_result)

        check_result()


    def _test_magento(self):
        base_url = (self.var_magento_base_url.get() or "").strip().rstrip("/")
        user = (self.var_magento_user.get() or "").strip()
        pwd = (self.var_magento_pass.get() or "").strip()
        verify = bool(self.var_magento_verify.get())

        if not base_url:
            messagebox.showerror("Missing base_url", "Magento Base URL is empty.")
            return

        # Show loading indicator
        loading = tk.Toplevel(self)
        loading.title("Testing...")
        loading.geometry("300x120")
        tk.Label(loading, text="Testing Magento connection...", padx=20, pady=20).pack()
        loading.transient(self)
        loading.grab_set()

        result_queue = queue.Queue()

        def worker():
            try:
                token = get_magento_token(base_url, user, pwd, verify, logger=self._log)
                result_queue.put(token)
            except Exception as e:
                result_queue.put(e)

        threading.Thread(target=worker, daemon=True).start()

        def check_result():
            try:
                res = result_queue.get_nowait()
                loading.destroy()

                if isinstance(res, Exception):
                    self.cached_magento_token = None
                    error_msg = f"Magento Login failed: {res}\n"
                    self._log(error_msg)
                    messagebox.showerror("Magento", f"Login failed.\nError: {res}")
                else:
                    self.cached_magento_token = res
                    self.init_done = False
                    self._log("Magento Login OK! Token cached for this session.\n")
                    messagebox.showinfo("Magento", "Login OK!\nToken cached for this session.")
            
            except queue.Empty:
                self.after(100, check_result)

        check_result()


    def _test_medusa(self):
        base_url = (self.var_medusa_base_url.get() or "").strip().rstrip("/")
        email = (self.var_medusa_email.get() or "").strip()
        pwd = (self.var_medusa_pass.get() or "").strip()

        if not base_url:
            messagebox.showerror("Missing base_url", "Medusa Base URL is empty.")
            return

        # Show loading indicator
        loading = tk.Toplevel(self)
        loading.title("Testing...")
        loading.geometry("300x120")
        tk.Label(loading, text="Testing Medusa connection...", padx=20, pady=20).pack()
        loading.transient(self)
        loading.grab_set()

        result_queue = queue.Queue()

        def worker():
            try:
                token = get_medusa_token(base_url, email, pwd, logger=self._log)
                result_queue.put(token)
            except Exception as e:
                result_queue.put(e)

        threading.Thread(target=worker, daemon=True).start()

        def check_result():
            try:
                res = result_queue.get_nowait()
                loading.destroy()

                if isinstance(res, Exception):
                    self.cached_medusa_token = None
                    error_msg = f"Medusa Login failed: {res}\n"
                    self._log(error_msg)
                    messagebox.showerror("Medusa", f"Login failed.\nError: {res}")
                else:
                    self.cached_medusa_token = res
                    self.init_done = False
                    self._log("✅ Medusa Login OK! Token cached for this session.\n")
                    messagebox.showinfo("Medusa", "Login OK!\nToken cached for this session.")
            
            except queue.Empty:
                self.after(100, check_result)

        check_result()


    def _run(self):
        if self._proc and self._proc.poll() is None:
            messagebox.showwarning("Running", "Migration is already running. Please Stop before running again.")
            return

        entities = self._get_entities()
        if not entities:
            messagebox.showerror("Missing Selection", "You must select at least 1 entity to sync.")
            return

        try:
            limit_val = (self.var_limit.get() or "0").strip()
            limit = int(limit_val)
            if limit < 0: raise ValueError()
        except:
            messagebox.showerror("Invalid Limit", "Limit must be an integer >= 0.")
            return

        # Disable run button immediately
        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.pause_btn.config(state="normal", text="Pause") # Enable pause button and set text to "Pause"
        
        # Ensure clean state
        clean_stop_signal()
        toggle_pause_signal(active=False) # Ensure pause is cleared before starting
        
        threading.Thread(target=self._run_background, args=(entities, limit), daemon=True).start()

    def _run_background(self, entities, limit):
        try:
            import datetime
            run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

            cmd = [sys.executable, "-u", "main.py", "--entities", ",".join(entities), "--run-id", run_id]
            if self.init_done:
                cmd += ["--skip-init-log"]
            if limit > 0:
                cmd += ["--limit", str(limit)]
            if self.var_dry_run.get():
                cmd += ["--dry-run"]
            if self.var_dry_run_file.get():
                cmd += ["--dry-run-file"]
            if self.var_finalize_orders.get():
                cmd += ["--finalize-orders"]
                
            self._save_to_config_py()

            p_ids = self.var_product_ids.get().strip()
            if p_ids: cmd += ["--product-ids", p_ids]
            c_ids = self.var_category_ids.get().strip()
            if c_ids: cmd += ["--category-ids", c_ids]
            cust_ids = self.var_customer_ids.get().strip()
            if cust_ids: cmd += ["--customer-ids", cust_ids]
            ord_ids = self.var_order_ids.get().strip()
            if ord_ids: cmd += ["--order-ids", ord_ids]

            if self.cached_magento_token:
                self._log("✅ [PRE-FLIGHT] Magento: Using cached login session.\n")
            else:
                base_url = (self.var_magento_base_url.get() or "").strip().rstrip("/")
                user = (self.var_magento_user.get() or "").strip()
                pwd = (self.var_magento_pass.get() or "").strip()
                verify = bool(self.var_magento_verify.get())
                try:
                    self.cached_magento_token = get_magento_token(base_url, user, pwd, verify, logger=self._log)
                except Exception as e:
                    self._log(f"❌ [FAIL] Magento connection failed.\n")
                    self.after(0, lambda: messagebox.showerror("Magento Error", f"Magento login failed: {e}"))
                    self.after(0, lambda: self.btn_run.config(state="normal"))
                    self.after(0, lambda: self.btn_stop.config(state="disabled"))
                    self.after(0, lambda: self.pause_btn.config(state="disabled")) # Disable pause button on error
                    return
            
            if self.cached_medusa_token:
                self._log("✅ [PRE-FLIGHT] Medusa: Using cached login session.\n")
            else:
                base_url = (self.var_medusa_base_url.get() or "").strip().rstrip("/")
                email = (self.var_medusa_email.get() or "").strip()
                pwd = (self.var_medusa_pass.get() or "").strip()
                try:
                    self.cached_medusa_token = get_medusa_token(base_url, email, pwd, logger=self._log)
                except Exception as e:
                    self._log(f"❌ [FAIL] Medusa connection failed.\n")
                    self.after(0, lambda: messagebox.showerror("Medusa Error", f"Medusa login failed: {e}"))
                    self.after(0, lambda: self.btn_run.config(state="normal"))
                    self.after(0, lambda: self.btn_stop.config(state="disabled"))
                    self.after(0, lambda: self.pause_btn.config(state="disabled")) # Disable pause button on error
                    return
 
            self._log(f"\n--- 🚀 STARTING MIGRATION SESSION: {run_id} ---\n")
            
            env = os.environ.copy()
            env["MAGENTO_BASE_URL"] = (self.var_magento_base_url.get() or "").strip()
            env["MAGENTO_ADMIN_USERNAME"] = (self.var_magento_user.get() or "").strip()
            env["MAGENTO_ADMIN_PASSWORD"] = (self.var_magento_pass.get() or "").strip()
            env["MAGENTO_VERIFY_SSL"] = "1" if self.var_magento_verify.get() else "0"
            env["MEDUSA_BASE_URL"] = (self.var_medusa_base_url.get() or "").strip()
            env["MEDUSA_EMAIL"] = (self.var_medusa_email.get() or "").strip()
            env["MEDUSA_PASSWORD"] = (self.var_medusa_pass.get() or "").strip()

            if self.cached_magento_token: env["MAGENTO_TOKEN"] = self.cached_magento_token
            if self.cached_medusa_token: env["MEDUSA_TOKEN"] = self.cached_medusa_token

            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                bufsize=1,
            )

            self._reader_thread = threading.Thread(target=self._reader, daemon=True)
            self._reader_thread.start()

        except Exception as ex:
            self._log(f"❌ Error starting background thread: {ex}\n")
            self.after(0, lambda: self.btn_run.config(state="normal"))
            self.after(0, lambda: self.btn_stop.config(state="disabled"))
            self.after(0, lambda: self.pause_btn.config(state="disabled")) # Disable pause button on error

    def _reader(self):
        assert self._proc is not None
        assert self._proc.stdout is not None

        try:
            for line in self._proc.stdout:
                self._q.put(line)
        except Exception as e:
            self._q.put(f"\n[ERROR] Could not read stdout: {e}\n")
        finally:
            self._q.put(None)

    def _stop(self):
        if not self._proc or self._proc.poll() is not None:
            return
        self._log("\n[STOP] Stopping process (creating signal)...\n")
        
        # Create stop signal file
        try:
            with open(".stop_signal", "w") as f:
                f.write("stop")
        except Exception as e:
            self._log(f"Warning: Could not create stop signal file: {e}\n")

        try:
            self._proc.terminate()
        except Exception:
            pass
        
        toggle_pause_signal(active=False) # Ensure pause is cleared on stop
        self.pause_btn.config(text="Pause", state=tk.DISABLED)

    def _pause_resume(self):
        """Toggle pause state."""
        current_text = self.pause_btn.cget("text")
        if current_text == "Pause":
            # Enable pause
            toggle_pause_signal(active=True)
            self.pause_btn.config(text="Resume")
            self._log("\n[PAUSE] Pausing migration process...\n")
        else:
            # Resume
            toggle_pause_signal(active=False)
            self.pause_btn.config(text="Pause")
            self._log("\n[RESUME] Resuming migration process...\n")

    def _drain_queue(self):
        try:
            while True:
                item = self._q.get_nowait()
                if item is None:
                    code = self._proc.poll() if self._proc else None
                    self._log(f"\n[FINISHED] exit code = {code}\n")
                    if code == 0:
                        self.init_done = True
                    self.btn_run.config(state="normal")
                    self.btn_stop.config(state="disabled")
                    self.pause_btn.config(state="disabled") # Disable pause button when process finishes
                    self._proc = None # Clear _proc reference
                    break
                self._log(item)
        except queue.Empty:
            pass
        finally:
            self.after(80, self._drain_queue)


def main():
    try:
        app = MigrationGUI()
        app.mainloop()
    except tk.TclError as e:
        print("Could not open GUI (Tkinter). Error:", e)
        print("You can run using CLI: python main.py --entities products,categories,customers,orders")


if __name__ == "__main__":
    main()

