import sys
import os
import subprocess
import threading
import queue
import tkinter as tk
from tkinter import messagebox
from tkinter.scrolledtext import ScrolledText
import requests

try:
    from config import MAGENTO as CFG_MAGENTO, MEDUSA as CFG_MEDUSA
except Exception:
    CFG_MAGENTO = {}
    CFG_MEDUSA = {}


class MigrationGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Magento -> Medusa Migration")
        self.geometry("920x640")

        self._proc = None
        self._q = queue.Queue()
        self._reader_thread = None

        self._build_ui()
        self.after(80, self._drain_queue)

    def _build_ui(self):
        top = tk.Frame(self)
        top.pack(fill="x", padx=12, pady=10)

        entities_box = tk.LabelFrame(top, text="Chọn dữ liệu cần sync")
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
        tk.Button(btns, text="Chọn tất cả", command=self._select_all).pack(side="left")
        tk.Button(btns, text="Bỏ chọn tất cả", command=self._select_none).pack(side="left", padx=(8, 0))

        opts_box = tk.LabelFrame(top, text="Tuỳ chọn")
        opts_box.pack(side="left", fill="x")

        tk.Label(opts_box, text="Limit (0 = không giới hạn):").grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))
        self.var_limit = tk.StringVar(value="0")
        tk.Entry(opts_box, textvariable=self.var_limit, width=12).grid(row=0, column=1, sticky="w", padx=10, pady=(8, 4))

        self.var_dry_run = tk.BooleanVar(value=False)
        tk.Checkbutton(opts_box, text="Dry-run (chỉ in payload)", variable=self.var_dry_run).grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 10))
        self.var_finalize_orders = tk.BooleanVar(value=False)
        tk.Checkbutton(opts_box, text="Finalize orders (Draft -> Order nếu Medusa hỗ trợ)", variable=self.var_finalize_orders).grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))

        cfg = tk.Frame(self)
        cfg.pack(fill="x", padx=12, pady=(0, 6))

        mag_box = tk.LabelFrame(cfg, text="Cấu hình Magento (mặc định lấy từ config.py)")
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
        tk.Entry(mag_box, textvariable=self.var_magento_pass, width=40, show="*").grid(row=2, column=1, sticky="w", padx=10, pady=4)
        tk.Checkbutton(mag_box, text="Verify SSL", variable=self.var_magento_verify).grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 10))
        tk.Button(mag_box, text="Test Magento", command=self._test_magento).grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))

        med_box = tk.LabelFrame(cfg, text="Cấu hình Medusa (mặc định lấy từ config.py)")
        med_box.pack(side="left", fill="x", expand=True)

        self.var_medusa_base_url = tk.StringVar(value=str(CFG_MEDUSA.get("BASE_URL", "")))
        self.var_medusa_email = tk.StringVar(value=str(CFG_MEDUSA.get("EMAIL", "")))
        self.var_medusa_pass = tk.StringVar(value=str(CFG_MEDUSA.get("PASSWORD", "")))

        tk.Label(med_box, text="Base URL").grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))
        tk.Entry(med_box, textvariable=self.var_medusa_base_url, width=40).grid(row=0, column=1, sticky="w", padx=10, pady=(8, 4))
        tk.Label(med_box, text="Email").grid(row=1, column=0, sticky="w", padx=10, pady=4)
        tk.Entry(med_box, textvariable=self.var_medusa_email, width=40).grid(row=1, column=1, sticky="w", padx=10, pady=4)
        tk.Label(med_box, text="Password").grid(row=2, column=0, sticky="w", padx=10, pady=4)
        tk.Entry(med_box, textvariable=self.var_medusa_pass, width=40, show="*").grid(row=2, column=1, sticky="w", padx=10, pady=4)
        tk.Button(med_box, text="Test Medusa", command=self._test_medusa).grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))

        actions = tk.Frame(self)
        actions.pack(fill="x", padx=12)
        self.btn_run = tk.Button(actions, text="Run", width=14, command=self._run)
        self.btn_run.pack(side="left")
        self.btn_stop = tk.Button(actions, text="Stop", width=14, state="disabled", command=self._stop)
        self.btn_stop.pack(side="left", padx=(10, 0))
        tk.Button(actions, text="Clear log", width=14, command=self._clear_log).pack(side="left", padx=(10, 0))

        log_box = tk.LabelFrame(self, text="Log")
        log_box.pack(fill="both", expand=True, padx=12, pady=12)
        self.txt = ScrolledText(log_box, wrap="word")
        self.txt.pack(fill="both", expand=True, padx=10, pady=10)
        self._log("Sẵn sàng. Nhấn Run để bắt đầu.\n")

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

    def _log(self, s: str):
        self.txt.insert("end", s)
        self.txt.see("end")

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

    def _test_magento(self):
        base_url = (self.var_magento_base_url.get() or "").strip().rstrip("/")
        if not base_url:
            messagebox.showerror("Thiếu base_url", "Magento Base URL đang trống.")
            return
        verify = bool(self.var_magento_verify.get())
        try:
            # Chỉ test kết nối TCP/HTTP cơ bản (không cần token)
            r = requests.get(base_url, timeout=6, verify=verify, allow_redirects=True)
            messagebox.showinfo("Magento", f"Kết nối OK.\nURL: {base_url}\nHTTP {r.status_code}")
        except Exception as e:
            messagebox.showerror("Magento", f"Không kết nối được.\nURL: {base_url}\nLỗi: {e}")

    def _test_medusa(self):
        base_url = (self.var_medusa_base_url.get() or "").strip().rstrip("/")
        if not base_url:
            messagebox.showerror("Thiếu base_url", "Medusa Base URL đang trống.")
            return
        try:
            # /health thường có, nếu không có thì fallback GET /
            try:
                r = requests.get(base_url + "/health", timeout=6)
            except Exception:
                r = requests.get(base_url, timeout=6, allow_redirects=True)
            messagebox.showinfo("Medusa", f"Kết nối OK.\nURL: {base_url}\nHTTP {r.status_code}")
        except Exception as e:
            messagebox.showerror("Medusa", f"Không kết nối được.\nURL: {base_url}\nLỗi: {e}")

    def _run(self):
        if self._proc and self._proc.poll() is None:
            messagebox.showwarning("Đang chạy", "Migration đang chạy. Hãy Stop trước khi chạy lại.")
            return

        entities = self._get_entities()
        if not entities:
            messagebox.showerror("Thiếu lựa chọn", "Bạn cần chọn ít nhất 1 entity để sync.")
            return

        try:
            limit = int((self.var_limit.get() or "0").strip())
            if limit < 0:
                raise ValueError()
        except Exception:
            messagebox.showerror("Sai limit", "Limit phải là số nguyên >= 0.")
            return

        cmd = [sys.executable, "-u", "main.py", "--entities", ",".join(entities)]
        if limit > 0:
            cmd += ["--limit", str(limit)]
        if self.var_dry_run.get():
            cmd += ["--dry-run"]
        if self.var_finalize_orders.get():
            cmd += ["--finalize-orders"]

        self._clear_log()
        self._log("Command:\n  " + " ".join(cmd) + "\n")
        self._log("(Credentials được truyền qua ENV từ GUI, không hiện trên command line)\n\n")

        try:
            env = os.environ.copy()
            env["MAGENTO_BASE_URL"] = (self.var_magento_base_url.get() or "").strip()
            env["MAGENTO_ADMIN_USERNAME"] = (self.var_magento_user.get() or "").strip()
            env["MAGENTO_ADMIN_PASSWORD"] = (self.var_magento_pass.get() or "").strip()
            env["MAGENTO_VERIFY_SSL"] = "1" if self.var_magento_verify.get() else "0"

            env["MEDUSA_BASE_URL"] = (self.var_medusa_base_url.get() or "").strip()
            env["MEDUSA_EMAIL"] = (self.var_medusa_email.get() or "").strip()
            env["MEDUSA_PASSWORD"] = (self.var_medusa_pass.get() or "").strip()

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
        except FileNotFoundError:
            messagebox.showerror("Không tìm thấy Python", "Không tìm thấy Python để chạy. Hãy chạy bằng đúng môi trường Python.")
            return

        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")

        self._reader_thread = threading.Thread(target=self._reader, daemon=True)
        self._reader_thread.start()

    def _reader(self):
        try:
            for line in self._proc.stdout:
                self._q.put(line)
        except Exception as e:
            self._q.put(f"\n[LỖI] Không đọc được stdout: {e}\n")
        finally:
            self._q.put(None)  # sentinel

    def _stop(self):
        if not self._proc or self._proc.poll() is not None:
            return
        self._log("\n[STOP] Đang dừng process...\n")
        try:
            self._proc.terminate()
        except Exception:
            pass

    def _drain_queue(self):
        try:
            while True:
                item = self._q.get_nowait()
                if item is None:
                    code = self._proc.poll() if self._proc else None
                    self._log(f"\n[FINISHED] exit code = {code}\n")
                    self.btn_run.config(state="normal")
                    self.btn_stop.config(state="disabled")
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
        print("Không thể mở GUI (Tkinter). Lỗi:", e)
        print("Bạn có thể chạy bằng CLI: python main.py --entities products,categories,customers,orders")


if __name__ == "__main__":
    main()


