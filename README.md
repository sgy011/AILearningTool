# AILearningTool

一个多功能的 AI 学习工具集，支持多媒体格式转换、模型格式转换、AI 助手等多种功能。

## ✨ 功能特性

### 🖼️ 图片处理
- 图片格式转换（PNG, JPG, GIF, BMP, TIFF, WEBP）
- 批量转换
- 图片增强与数据清洗

### 🎵 音频处理
- 音频文件修复（单音道/立体声增强）
- 音频格式转换（MP3, WAV, M4A, FLAC, OGG）

### 🤖 模型转换
- **YOLOv5/YOLOv8 → ONNX**（推荐安装 ultralytics）
- PyTorch ↔ ONNX
- ONNX → TFLite / Keras
- PyTorch → TFLite（通过 ONNX 间接转换）
- 批量转换、自定义输入形状

### 📚 AI 学习助手
- AI 导师（问答辅导）
- 知识库管理（文档向量化、检索）
- 资讯聚合与摘要

### 🛠️ 实用工具
- Word/Excel 文档处理
- 数据集管理
- 爬虫工具

## 🚀 快速开始

### 环境要求
- Python 3.8+
- Windows / Linux / macOS

### 安装

```bash
# 克隆仓库
git clone https://github.com/sgy011/AILearningTool.git
cd AILearningTool

# 创建虚拟环境
python -m venv .venv
source .venv/Scripts/activate  # Windows
# source .venv/bin/activate    # Linux/macOS

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
copy .env.example .env
# 编辑 .env 文件，配置必要的 API Token

# 启动应用
python app.py
```

访问 **http://127.0.0.1:5000**

## ⚠️ 注意事项

- `ffmpeg.exe` 和 `ffprobe.exe` 因体积过大未上传，可从 [FFmpeg 官网](https://ffmpeg.org/) 下载并放置在项目根目录
- 部分功能（如 AI 导师、模型转换）需要额外的依赖或 API Token

## 📁 项目结构

```
.
├── app.py              # Flask 应用主文件
├── config.py           # 配置文件
├── requirements.txt    # 依赖清单
├── utils/              # 工具模块
│   ├── image_converter.py
│   ├── audio_repair.py
│   ├── model_converter.py
│   └── ...
├── frontend/           # 前端源码（Vue.js）
├── templates/          # HTML 模板
├── static/            # 静态资源
├── uploads/            # 上传文件目录
└── downloads/          # 下载文件目录
```

## 📝 许可证

MIT License
