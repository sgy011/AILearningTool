import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    UPLOAD_FOLDER = 'uploads'
    DOWNLOAD_FOLDER = 'downloads'
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB max file size for all types
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp', 'ico'}
    OUTPUT_FORMATS = {'png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif'}
    
    # 模型文件配置
    MODEL_ALLOWED_EXTENSIONS = {'pt', 'pth', 'pkl', 'h5', 'keras', 'onnx', 'pb', 'tflite', 'mar'}
    MODEL_OUTPUT_FORMATS = {'pt', 'pth', 'onnx', 'tflite'}
    MAX_MODEL_FILE_SIZE = 500 * 1024 * 1024  # 500MB for model files
    
    # 确保上传和下载目录存在
    @staticmethod
    def init_app(app):
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)