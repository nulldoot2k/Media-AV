# MediaAV

Ứng dụng desktop Windows để tải nội dung media mà bạn có quyền lưu trữ.

## Chạy bản test

Mở:

```text
dist\mediaAV-msi\mediaAV-msi.exe
```

## Bản Windows cho client

Máy build cần có Python Windows và ba file trong `tools`:

```text
tools\yt-dlp.exe
tools\ffmpeg.exe
tools\ffprobe.exe
```

Chạy PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\build-full-windows.ps1
```

Kết quả build:

```text
dist\mediaAV-msi\mediaAV-msi.exe
release\Media-AV-Windows.zip
release\Media-AV-Windows.exe
```

### Cách dùng khuyến nghị

Client chỉ cần tải một file duy nhất là `Media-AV-Windows.exe` rồi chạy bằng quyền Administrator. Trình cài đặt sẽ tự quản lý toàn bộ file ứng dụng trong thư mục riêng:

```text
%ProgramFiles%\MediaAV\mediaAV-msi.exe
```

Sau đó tạo shortcut trong Start Menu và trên Desktop. Client chỉ cần mở shortcut `MediaAV`; không cần Python, WSL2, yt-dlp hoặc FFmpeg. Bản cài đặt dùng kiểu thư mục để mở nhanh hơn, không phải giải nén toàn bộ ứng dụng mỗi lần khởi động.

Thư mục `C:\Program Files\MediaAV` tương tự thư mục riêng của IDM. Client không cần tự mở, di chuyển hoặc xóa các file bên trong. Khi gỡ cài đặt từ Windows, toàn bộ thư mục ứng dụng sẽ được dọn.

### Bản portable

Nếu không muốn cài đặt, client tải `Media-AV-Windows.zip`. Sau khi giải nén, copy thư mục `MediaAV` vào `C:\Program Files\MediaAV`, rồi chạy `mediaAV-msi.exe` trong thư mục đó.

Hướng dẫn cài nhanh cho client nằm trong `client-install.txt` và được đóng gói cùng ZIP.

## Tạo GitHub Release

Workflow nằm tại `.github/workflows/release-windows.yml`. Sau khi push source lên GitHub, tạo tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

GitHub Actions sẽ tự build trên Windows, đóng gói cả installer `Media-AV-Windows.exe` và ZIP portable. Khi tag đã tồn tại, workflow cập nhật lại các asset của chính release đó.

## Cấu trúc Git

```text
media-downloader-project/
├── desktop_app.py
├── build-full-windows.ps1
├── Media-AV.iss
├── client-install.txt
├── LICENSE
├── README.md
├── tools/
│   └── README.txt
├── dist/                 # output local, không commit
└── release/              # file client, không commit
```

## Chức năng

- Scan ID, dạng file, độ phân giải và Size.
- Để trống format để dùng chất lượng tốt nhất.
- Nhiều tác vụ tải độc lập, có tiến độ riêng.
- Cancel, tiếp tục, hủy bỏ từng tác vụ hoặc tất cả.
- Danh sách tác vụ riêng và nhật ký riêng cho từng download.
- Không ghi đè file đã tồn tại.
- Chọn thư mục lưu bằng hộp thoại Windows.

Chỉ sử dụng với nội dung bạn có quyền tải và lưu trữ.

Mã nguồn được phát hành theo giấy phép MIT. Các thành phần bên thứ ba như yt-dlp và FFmpeg tuân theo giấy phép riêng của chúng.
