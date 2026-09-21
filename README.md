# Z755 – Phân hệ Quản lý & đánh giá KPI (Odoo 18)

Module Odoo 18 phục vụ giao KPI, thực hiện, tự đánh giá, thẩm định, Tổ KPI và phê duyệt. Giao diện hoàn toàn bằng tiếng Việt, bám theo bản thiết kế "Odoo Performance Hub" và hiển thị tốt trên máy tính, máy tính bảng, điện thoại ở mọi mức thu phóng.

## 1. Yêu cầu

| Thành phần | Phiên bản |
|---|---|
| Odoo | 18.0 (bản Community là đủ) |
| Python | 3.10 trở lên |
| PostgreSQL | 13 trở lên |
| Git | bản bất kỳ |

Module phụ thuộc các module có sẵn của Odoo: `base`, `mail`, `hr`.

## 2. Tải mã nguồn về máy

Thư mục module **bắt buộc phải tên là `z755_kpi`**, vì Odoo tìm module theo tên thư mục.

```bash
mkdir -p ~/odoo-addons
cd ~/odoo-addons
git clone https://github.com/hoanghochoi0509-art/z755.git z755_kpi
```

Trên Windows (PowerShell):

```powershell
mkdir $HOME\odoo-addons
cd $HOME\odoo-addons
git clone https://github.com/hoanghochoi0509-art/z755.git z755_kpi
```

Nếu repo để chế độ riêng tư, Git sẽ yêu cầu đăng nhập: nhập tên tài khoản GitHub và dùng **Personal Access Token** thay cho mật khẩu.

## 3. Cài Odoo 18 (nếu chưa có)

```bash
git clone --depth 1 --branch 18.0 https://github.com/odoo/odoo.git
cd odoo
python3 -m venv ../venv
source ../venv/bin/activate          # Windows: ..\venv\Scripts\activate
pip install -r requirements.txt
```

Tạo người dùng PostgreSQL (làm một lần, thay `mat_khau` bằng mật khẩu của bạn):

```bash
sudo -u postgres createuser -s odoo
sudo -u postgres psql -c "ALTER USER odoo WITH PASSWORD 'mat_khau';"
```

## 4. Khởi động lần đầu (tạo CSDL và cài module)

Chạy trong thư mục `odoo` vừa clone, đã kích hoạt môi trường ảo:

```bash
python -m odoo -d kpi_local \
  --addons-path=addons,odoo/addons,$HOME/odoo-addons \
  --db_user=odoo --db_password=mat_khau \
  -i z755_kpi --load-language=vi_VN \
  --http-port=8069
```

Trên Windows (PowerShell), viết trên một dòng:

```powershell
python -m odoo -d kpi_local --addons-path="addons,odoo\addons,$HOME\odoo-addons" --db_user=odoo --db_password=mat_khau -i z755_kpi --load-language=vi_VN --http-port=8069
```

Giải thích nhanh:
- `-d kpi_local`: tên CSDL, chưa có thì Odoo tự tạo.
- `--addons-path`: danh sách thư mục chứa module. Phải có thư mục **cha** của `z755_kpi` (ở đây là `odoo-addons`), không trỏ thẳng vào `z755_kpi`.
- `-i z755_kpi`: cài module KPI cùng các module phụ thuộc.
- `--load-language=vi_VN`: nạp ngôn ngữ tiếng Việt.

Lần đầu mất vài phút. Khi log hiện dòng `HTTP service (werkzeug) running on ...:8069` là đã sẵn sàng.

## 5. Đăng nhập

1. Mở trình duyệt, vào **http://localhost:8069**.
2. Đăng nhập: tài khoản `admin`, mật khẩu `admin` (mặc định khi Odoo tự tạo CSDL). **Hãy đổi mật khẩu ngay** ở Tùy chọn → Đổi mật khẩu.
3. Chọn ứng dụng **KPI** ở màn hình chính. Module tự gắn tài khoản admin vào nhóm quản trị KPI và đặt tiếng Việt cho người dùng nội bộ.

Bấm vào **Bảng điều khiển** để xem tổng quan; dữ liệu mẫu (đơn vị Ban CNTT, danh mục KPI, quy tắc chấm) được nạp sẵn.

## 6. Những lần khởi động sau

Chỉ cần chạy, không kèm `-i`:

```bash
python -m odoo -d kpi_local \
  --addons-path=addons,odoo/addons,$HOME/odoo-addons \
  --db_user=odoo --db_password=mat_khau \
  --http-port=8069
```

Dừng server bằng `Ctrl + C`.

## 7. Cập nhật khi có bản mới

```bash
cd ~/odoo-addons/z755_kpi
git pull
```

Sau đó chạy lại Odoo kèm `-u z755_kpi` để nâng cấp module:

```bash
python -m odoo -d kpi_local \
  --addons-path=addons,odoo/addons,$HOME/odoo-addons \
  --db_user=odoo --db_password=mat_khau \
  -u z755_kpi
```

Nếu vừa sửa giao diện mà thấy vẫn còn bản cũ, mở trang với `?debug=assets`, ví dụ `http://localhost:8069/odoo?debug=assets`, rồi tải lại trang.

## 8. Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| `Module z755_kpi not found` | Kiểm tra `--addons-path` trỏ tới thư mục **cha** và thư mục module tên đúng là `z755_kpi`. |
| `Address already in use` | Cổng 8069 đang bị chiếm. Đổi sang cổng khác, ví dụ `--http-port=8070`. |
| Lỗi kết nối PostgreSQL | Kiểm tra PostgreSQL đang chạy, đúng `--db_user` và `--db_password`. |
| Trang trắng hoặc mất giao diện | Mở `?debug=assets`, tải lại. Nếu vẫn lỗi, xem log server và console của trình duyệt (F12). |
| Vẫn còn chữ tiếng Anh | Vào Tùy chọn của người dùng, đặt ngôn ngữ là **Tiếng Việt / Vietnamese**. |

## 9. Cấu trúc thư mục

```
z755_kpi/
├── __manifest__.py        Khai báo module
├── models/                Mô hình dữ liệu và logic nghiệp vụ
├── views/                 Giao diện danh sách, biểu mẫu, menu
├── wizard/                Cửa sổ nhập lý do
├── report/                Mẫu in PDF
├── security/              Nhóm quyền và quy tắc truy cập
├── data/                  Dữ liệu mẫu, chuỗi số, lịch chạy tự động
└── static/src/            Giao diện: JS, XML, SCSS (thanh bên, bảng điều khiển)
```
