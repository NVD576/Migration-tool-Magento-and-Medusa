# Migration-tool-Magento-and-Medusa

## Mô tả
Công cụ này hỗ trợ di chuyển dữ liệu giữa Magento và Medusa (mô tả ngắn — điều chỉnh theo dự án).

## Yêu cầu trước
- Node.js >= 16 (nếu dự án dùng Node)
- Python 3.8+ (nếu có thành phần Python)
- Git

## Cài đặt

1. Clone repo:

```powershell
git clone https://github.com/NVD576/Migration-tool-Magento-and-Medusa.git
cd Migration-tool-Magento-and-Medusa
```

2. Cài thư viện
pip install requests 


3. Chạy ứng dụng

- Python:

```powershell
python main.py   #Chạy mà không cần giao diện

python app_gui.py #giao diện chính
```


## Ghi chú
Cài magento và medusa trước, cài bằng docker (cd vào từng thư mục Magento và Medusa)
- Mở terminal chạy lệnh docker compose up -d --build


## License

