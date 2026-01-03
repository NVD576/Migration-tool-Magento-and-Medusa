# Công Cụ Di Chuyển Dữ Liệu Magento 2 sang MedusaJS

Công cụ chuyên dụng để di chuyển dữ liệu (Sản phẩm, Danh mục, Khách hàng, Đơn hàng) từ Magento 2 sang MedusaJS. Phiên bản mới nhất hỗ trợ chạy trên nền tảng **Web**, đóng gói bằng **Docker**, giao diện thân thiện và log thời gian thực chi tiết.

## 🚀 Tính Năng Chính

*   **Web Interface (Mới):** Giao diện web hiện đại, dễ sử dụng, cho phép cấu hình và theo dõi log realtime.
*   **Dockerized:** Dễ dàng triển khai chỉ với 1 lệnh `docker-compose up`.
*   **Clean Logs:** Hệ thống log được tối ưu, loại bỏ icon rác và căn chỉnh thẳng hàng, dễ đọc.
*   **Hỗ trợ `localhost`:** Tự động xử lý kết nối tới `localhost` của máy chủ ngay cả khi chạy trong Docker container.
*   **Chọn lọc thực thể:** Di chuyển toàn bộ hoặc chọn cụ thể từng ID (Sản phẩm, Đơn hàng, Khách hàng...).
*   **Resume/Skip:** Tự động bỏ qua các bản ghi đã tồn tại hoặc bị lỗi, không làm gián đoạn quá trình.

## 🛠 Yêu Cầu

*   **Docker** và **Docker Compose** (Khuyên dùng)
*   Hoặc **Python 3.11+** nếu chạy trực tiếp (Manual).

## 📦 Cài Đặt & Chạy (Docker - Khuyên dùng)

Đây là cách nhanh nhất và ổn định nhất để chạy công cụ.

1.  **Clone dự án:**
    ```bash
    git clone https://github.com/NVD576/Migration-tool-Magento-and-Medusa.git
    cd Migration-tool-Magento-and-Medusa
    ```

2.  **Khởi chạy Docker:**
    ```bash
    docker-compose up --build
    ```

3.  **Truy cập Web Interface:**
    Mở trình duyệt và truy cập: [http://localhost:5000](http://localhost:5000)

4.  **Sử dụng `localhost`?**
    Nếu Medusa hoặc Magento của bạn chạy ở `localhost` (trên máy chủ), cứ điền URL là `http://localhost:9000` hoặc `http://127.0.0.1`. Hệ thống sẽ tự động chuyển đổi nó thành `host.docker.internal` để container có thể kết nối được.

## 💻 Cấu Hình Trên Web

Tại giao diện Web `http://localhost:5000`:

1.  **Cấu hình Magento:**
    *   **Base URL:** Ví dụ `https://magento.example.com`
    *   **Username/Password:** Tài khoản Admin.
    *   **SSL:** Tick chọn nếu site có HTTPS hợp lệ, hoặc bỏ chọn nếu là dev/self-signed.

2.  **Cấu hình Medusa:**
    *   **Base URL:** Ví dụ `http://localhost:9000` (sẽ được tự động fix nếu chạy Docker).
    *   **Email/Password:** Tài khoản Admin Medusa.

3.  **Chọn Dữ Liệu:**
    *   Tick chọn các mục muốn di chuyển (Products, Categories, Customers, Orders).
    *   Nhập ID cụ thể (ngăn cách bằng dấu phẩy) nếu chỉ muốn test một vài bản ghi.

4.  **Chạy:** Bấm **RUN MIGRATION** và xem log chạy trực tiếp ở cột bên phải.

## 🔧 Chạy Thủ Công (Cho Dev/Debug)

Nếu không muốn dùng Docker, bạn có thể chạy trực tiếp bằng Python:

1.  **Cài đặt thư viện:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Chạy Web Server:**
    ```bash
    python app_web.py
    ```
    Truy cập `http://localhost:5000`.

3.  **Hoặc chạy CLI (Command Line):**
    ```bash
    # Di chuyển 10 sản phẩm
    python main.py --entities products --limit 10

    # Di chuyển đơn hàng cụ thể
    python main.py --entities orders --order-ids 1001,1002
    ```

## 📂 Cấu Trúc Dự Án

*   `app_web.py`: Backend Flask cho giao diện Web.
*   `app_gui.py`: Giao diện Desktop (Legacy Tkinter).
*   `main.py`: Entry point cho CLI.
*   `templates/index.html`: Giao diện người dùng Web.
*   `migrators/`: Logic chính để di chuyển dữ liệu.
*   `transformers/`: Chuyển đổi dữ liệu từ cấu trúc Magento sang Medusa.
*   `services/`: Auth service (Login lấy token).
*   `config.py`: File cấu hình mặc định (được Web UI ghi đè khi chạy).


