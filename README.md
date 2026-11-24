# Tools Media AV

Ứng dụng desktop Windows để tải nội dung media mà bạn có quyền lưu trữ.

## Chạy bản test

Mở:

```text
dist\media-msi.exe
```

## Tạo bản ZIP cho client

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

Kết quả:

```text
dist\media-msi.exe
release\media-msi.exe
release\Tools-Media-AV-Windows.zip
```

Client chỉ cần giải nén ZIP và chạy `media-msi.exe`. Không cần Python, WSL2, yt-dlp hoặc FFmpeg.

Nếu máy build có Inno Setup, script cũng tạo `release\Tools-Media-AV-Setup.exe`.

Hướng dẫn cài nhanh cho client nằm trong `client-install.txt` và được đóng gói cùng ZIP.

## Tạo GitHub Release

Workflow nằm tại `.github/workflows/release-windows.yml`. Sau khi push source lên GitHub, tạo tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

GitHub Actions sẽ tự build trên Windows, đóng gói `Tools-Media-AV-Windows.zip` và tạo Release để client tải.

## Cấu trúc Git

```text
media-downloader-project/
├── desktop_app.py
├── build-full-windows.ps1
├── Tools-Media-AV.iss
├── client-install.txt
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
