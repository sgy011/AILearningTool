# 多媒体格式转换器

支持图片格式转换、音频文件修复和模型文件格式转换的Web应用。

## 🚀 快速开始

### ⚡ 一键安装（推荐）

```bash
complete_install.bat
```

该脚本会引导您完成所有安装步骤，并解决依赖冲突问题。

### 📦 基础安装（图片+音频功能）

```bash
pip install -r requirements.txt
copy .env.example .env
# 编辑 .env，至少配置 MODELSCOPE_TOKEN（若使用 AI / 每日必读资讯）
python run.py
```

浏览器访问 **http://127.0.0.1:5000**（本地默认仅本机；未设置 `FLASK_DEBUG` 时默认开启调试与热重载）。

## ⚠️ 重要提示：依赖冲突

**问题**：TensorFlow 和 ONNX 对 protobuf 有冲突的版本要求

**解决方案**：
1. **使用虚拟环境** - 最推荐，创建独立环境避免冲突
2. **选择安装** - 只安装您需要的功能
3. **版本降级** - 使用兼容的旧版本

详细说明请查看 `INSTALL_GUIDE.md`

## 🚀 本地启动应用

### Windows（可选）

双击或在项目根目录执行：

```bat
start_local.bat
```

### 手动启动

```bash
# 激活虚拟环境（如有）
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Linux / macOS

python run.py
# 或与 run.py 等价：
python app.py
```

默认 **127.0.0.1:5000**、**调试模式开启**。局域网访问请在 `.env` 设置 `FLASK_HOST=0.0.0.0`；生产部署请使用 gunicorn（见 `wsgi.py`），并设置 `FLASK_DEBUG=0`。

## ⚠️ 常见问题

### 1. YOLO 模型转换

**好消息！** 现在可以直接转换 YOLO 模型了！

#### 方法 1：直接转换（推荐）⭐

如果已安装 `ultralytics`，可以直接上传 YOLO 模型进行转换：

```bash
# 安装 YOLO 支持
install_yolo_support.bat

# 或手动安装
pip install ultralytics 'protobuf<4' 'onnx>=1.14.0' torch
```

**支持的模型**：
- YOLOv5 (.pt, .pth)
- YOLOv8 (.pt, .pth)
- YOLO-SEG (.pt)
- 其他 Ultralytics 模型

#### 方法 2：使用官方导出工具（备选）

如果方法 1 失败，可以使用官方导出工具：

```bash
export_yolo.bat
```

该脚本会：
1. 自动下载 YOLOv5 仓库
2. 安装依赖
3. 导出模型为 ONNX
4. 批量导出支持

#### 详细指南
- 查看 `export_yolo_guide.md` - 完整的 YOLO 导出指南
- 包含所有 YOLO 版本的导出方法

#### 工作流程
```
YOLO 模型 → 直接转换（方法1）→ ONNX → 其他格式
或
YOLO 模型 → export_yolo.bat → ONNX → 本应用 → 其他格式
```

### 2. TensorFlow 和 ONNX 依赖冲突

**错误**：`tensorflow requires protobuf>=5.28.0, but you have protobuf 3.20.3`

**解决方法**：
- 运行 `complete_install.bat` 选择只安装其中一个
- 或使用不同的虚拟环境
- 参考 `INSTALL_GUIDE.md` 获取详细方案

### 3. ONNX 导入错误

**错误**：
```
TypeError: Descriptors cannot be created directly.
```

**原因**：protobuf 版本过高（>= 4.0），与 ONNX 不兼容

**解决方法**：
```bash
# 快速修复（仅使用 ONNX 时）
fix_protobuf.bat

# 或在虚拟环境中按顺序安装
pip install 'protobuf<4'
pip install 'onnx>=1.14.0'
```

### 3. 应用启动时提示依赖未安装

**说明**：这是正常的！模型转换功能是可选的。即使某些依赖未安装，图片和音频转换功能仍可正常使用。

## 📦 功能特性

### 图片转换
- 支持格式：PNG, JPG, GIF, BMP, TIFF, WEBP
- 批量转换
- 自定义质量
- 实时进度显示

### 音频修复
- 支持格式：MP3, WAV, M4A, FLAC, OGG
- 单音道修复
- 立体声增强
- 格式转换

### 模型转换（可选）
- PyTorch → ONNX
- PyTorch → TFLite (通过 ONNX 间接转换)
- **YOLOv5/YOLOv8 → ONNX** ⭐（推荐安装 ultralytics）
- **YOLOv5/YOLOv8 → TFLite** ⭐（通过 ONNX 间接转换）
- ONNX → TFLite
- ONNX → PyTorch
- Keras/TensorFlow → TFLite
- 批量转换
- 自定义输入形状

## 📁 项目结构

```
transvsverter/
├── app.py                      # Flask应用主文件
├── run.py                      # 启动脚本
├── config.py                   # 配置文件
├── requirements.txt            # 依赖清单
├── fix_protobuf.bat        # protobuf修复脚本
├── MODEL_INSTALL.md        # 模型转换安装指南
├── QUICK_START.md         # 快速开始指南
├── README.md              # 本文件
├── utils/                     # 工具模块
│   ├── image_converter.py      # 图片转换器
│   ├── audio_repair.py        # 音频修复器
│   └── model_converter.py     # 模型转换器
├── templates/                 # HTML模板
│   └── index.html            # 主页面
├── static/                   # 静态资源
│   └── js/
│       └── main.js          # 前端JavaScript
├── uploads/                  # 上传文件目录
└── downloads/                # 下载文件目录
```

## 🔧 环境要求

- Python 3.8 或更高版本
- Windows / Linux / macOS

## 📖 详细文档

- `MODEL_INSTALL.md` - 模型转换功能详细安装指南
- `QUICK_START.md` - 快速开始指南

## 📝 许可证

本项目仅供学习和个人使用。

## 🤝 贡献

欢迎提交问题和改进建议！
