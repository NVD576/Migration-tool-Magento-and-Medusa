# Magento to Medusa Data Migration Tool

Công cụ hỗ trợ di chuyển dữ liệu (Products, Categories, Customers, Orders) từ Magento 2 sang MedusaJS. Ứng dụng cung cấp cả giao diện đồ họa (GUI) và giao diện dòng lệnh (CLI) để thuận tiện cho việc sử dụng.

## Tính năng

- **Giao diện đồ họa (GUI):** Giao diện trực quan để dễ dàng cấu hình và thực thi di chuyển dữ liệu.
- **Giao diện dòng lệnh (CLI):** Hỗ trợ chạy tự động và tích hợp vào các script.
- **Di chuyển các thực thể:**
  - Products (Sản phẩm)
  - Categories (Danh mục)
  - Customers (Khách hàng)
  - Orders (Đơn hàng)
- **Cấu hình linh hoạt:** Cấu hình thông tin kết nối qua tệp `config.py`, biến môi trường hoặc trực tiếp trên GUI.
- **Test kết nối:** Chức năng kiểm tra kết nối tới Magento và Medusa trước khi chạy.
- **Lựa chọn dữ liệu:** Hỗ trợ di chuyển toàn bộ hoặc chỉ chọn các ID cụ thể.
- **Dry-run:** Chế độ chạy thử để xem trước payload dữ liệu mà không ghi vào Medusa.
- **Ghi log thời gian thực:** Theo dõi tiến trình di chuyển trực tiếp trên GUI.

## Yêu cầu

- **Python 3.8+**
- **Git**
- **Tkinter** (Thường đi kèm với Python. Nếu không, cài đặt bằng lệnh: `sudo apt-get install python3-tk` trên Debian/Ubuntu)

## Cài đặt

1.  **Clone kho mã nguồn:**

    ```sh
    git clone https://github.com/NVD576/Migration-tool-Magento-and-Medusa.git
    cd Migration-tool-Magento-and-Medusa
    ```

2.  **Tạo và kích hoạt môi trường ảo (khuyến nghị):**

    ```sh
    python -m venv venv
    # Trên Windows
    .\venv\Scripts\activate
    # Trên macOS/Linux
    source venv/bin/activate
    ```

3.  **Cài đặt các thư viện cần thiết:**
    ```sh
    pip install -r requirements.txt
    ```

## Cấu hình

Bạn có thể cấu hình thông tin kết nối tới Magento và Medusa theo một trong các cách sau:

1.  **Tệp `config.py` (Mặc định):**
    Chỉnh sửa tệp `config.py` để cung cấp thông tin mặc định.

    ```python
    # config.py
    MAGENTO = {
        "BASE_URL": "https://your-magento.store",
        "ADMIN_USERNAME": "admin",
            "ADMIN_PASSWORD": "your_admin_password",
            "VERIFY_SSL": False,
        }

        MEDUSA = {
            "BASE_URL": "http://localhost:9000",
            "EMAIL": "your_admin_email@example.com",
            "PASSWORD": "your_medusa_password",
            "SALES_CHANNEL": "Default Sales Channel",
    }
    ```

2.  **Giao diện đồ họa (GUI):**
    Chạy `app_gui.py` và bấm vào nút **"▼ Hiện cấu hình"** để nhập thông tin trực tiếp. Thông tin này sẽ ghi đè lên cấu hình từ `config.py`.

3.  **Biến môi trường (cho CLI):**
    Khi chạy `main.py`, các biến môi trường sau sẽ được ưu tiên:
    - `MAGENTO_BASE_URL`, `MAGENTO_ADMIN_USERNAME`, `MAGENTO_ADMIN_PASSWORD`, `MAGENTO_VERIFY_SSL`
    - `MEDUSA_BASE_URL`, `MEDUSA_EMAIL`, `MEDUSA_PASSWORD`

## Hướng dẫn sử dụng

### 1. Chế độ Giao diện đồ họa (GUI)

Đây là cách sử dụng đơn giản và được khuyến nghị.

```sh
python app_gui.py
```

- **Chọn dữ liệu:** Tích vào các ô `Products`, `Categories`, v.v. để chọn loại dữ liệu cần di chuyển.
- **Lọc theo ID (Tùy chọn):** Nhập danh sách các ID (cách nhau bởi dấu phẩy) hoặc dùng nút **"Chọn..."** để lấy và chọn từ danh sách.
- **Cấu hình:** Mở rộng mục cấu hình để nhập hoặc xác nhận thông tin đăng nhập. Dùng nút **"Test..."** để đảm bảo kết nối thành công.
- **Chạy:** Nhấn nút **"Run"** để bắt đầu. Theo dõi tiến trình trong cửa sổ log.

### 2. Chế độ Dòng lệnh (CLI)

Sử dụng `main.py` cho các tác vụ tự động.

```sh
python main.py [OPTIONS]
```

**Các tùy chọn (OPTIONS) chính:**

- `--entities`: Các loại dữ liệu cần di chuyển, cách nhau bởi dấu phẩy (vd: `products,customers`). Mặc định là tất cả.
- `--limit <số>`: Giới hạn số lượng đối tượng cho mỗi loại. `0` là không giới hạn.
- `--product-ids <id1,id2>`: Chỉ di chuyển các sản phẩm có ID này.
- `--category-ids <id1,id2>`: Chỉ di chuyển các danh mục có ID này.
- `--customer-ids <id1,id2>`: Chỉ di chuyển các khách hàng có ID này.
- `--order-ids <id1,id2>`: Chỉ di chuyển các đơn hàng có ID này.
- `--dry-run`: Chạy thử, chỉ in ra payload mà không thực sự tạo dữ liệu trên Medusa.

**Ví dụ:**

- Di chuyển 10 sản phẩm và tất cả danh mục:
  ```sh
  python main.py --entities products,categories --limit 10
  ```
- Chỉ di chuyển sản phẩm có ID là 123 và 456:
  ```sh
  python main.py --entities products --product-ids 123,456
  ```

## Cấu trúc dự án

```
├── connectors/   # Module giao tiếp API với Magento và Medusa
├── extractors/   # Module trích xuất dữ liệu từ Magento
├── transformers/ # Module chuyển đổi dữ liệu từ định dạng Magento sang Medusa
├── migrators/    # Module điều phối quá trình di chuyển (extract-transform-load)
├── services/     # Module xác thực, lấy token
├── config/       # Chứa các file cấu hình mẫu
├── app_gui.py    # Entry point cho ứng dụng GUI
├── main.py       # Entry point cho ứng dụng CLI
├── config.py     # File cấu hình chính
└── README.md     # Tài liệu hướng dẫn
```

