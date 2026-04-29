"""
模型文件格式转换器
支持常见的深度学习模型格式转换
"""

import os
import base64
import traceback
from typing import Tuple, Dict, Any, Optional
import logging
import warnings

# 抑制各种警告
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # 抑制 TensorFlow 日志
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'  # 抑制 OneDNN 优化信息

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModelConverter:
    """模型文件格式转换器类"""
    
    # 支持的输入格式
    INPUT_FORMATS = {
        'pt', 'pth', 'pkl',  # PyTorch
        'h5', 'keras',  # Keras/TensorFlow
        'onnx',  # ONNX
        'pb',  # TensorFlow SavedModel
        'tflite',  # TensorFlow Lite
        'mar'  # TorchServe
    }
    
    # 支持的输出格式
    OUTPUT_FORMATS = {
        'pt', 'pth', 'pkl',  # PyTorch
        'h5', 'keras',  # Keras/TensorFlow
        'onnx',  # ONNX
        'tflite',  # TensorFlow Lite
    }
    
    # 支持的转换路径
    CONVERSION_PATHS = {
        ('pt', 'onnx'): 'PyTorch转ONNX',
        ('pth', 'onnx'): 'PyTorch转ONNX',
        ('pkl', 'onnx'): 'PyTorch转ONNX',
        ('pt', 'pth'): 'PyTorch格式转换',
        ('pth', 'pt'): 'PyTorch格式转换',
        ('pt', 'pkl'): 'PyTorch格式转换',
        ('pkl', 'pt'): 'PyTorch格式转换',
        ('pth', 'pkl'): 'PyTorch格式转换',
        ('pkl', 'pth'): 'PyTorch格式转换',
        ('onnx', 'tflite'): 'ONNX转TFLite',
        ('h5', 'tflite'): 'Keras转TFLite',
        ('keras', 'tflite'): 'Keras转TFLite',
        ('pb', 'tflite'): 'TensorFlow转TFLite',
        ('onnx', 'pt'): 'ONNX转PyTorch',
        ('onnx', 'pth'): 'ONNX转PyTorch',
        ('pt', 'tflite'): 'PyTorch转TFLite (Ultralytics原生)',
        ('pth', 'tflite'): 'PyTorch转TFLite (Ultralytics原生)',
        ('pkl', 'tflite'): 'PyTorch转TFLite (Ultralytics原生)',
    }
    
    def __init__(self, upload_folder: str, download_folder: str):
        """
        初始化转换器
        
        Args:
            upload_folder: 上传文件目录
            download_folder: 下载文件目录
        """
        self.upload_folder = upload_folder
        self.download_folder = download_folder
        self._check_dependencies()
    
    def _check_dependencies(self) -> None:
        """检查可用的依赖库"""
        self.available_libs = {
            'torch': False,
            'onnx': False,
            'tensorflow': False,
            'keras': False,
            'ultralytics': False,
            'yolov6': False,
        }
        
        try:
            import torch
            self.available_libs['torch'] = True
            logger.info("✓ PyTorch 可用")
        except ImportError:
            logger.warning("✗ PyTorch 未安装")
        except Exception as e:
            logger.warning(f"✗ PyTorch 导入失败: {e}")
        
        try:
            import ultralytics
            self.available_libs['ultralytics'] = True
            logger.info("✓ Ultralytics 可用 (支持 YOLOv5/YOLOv8 模型)")
        except ImportError:
            logger.warning("✗ Ultralytics 未安装")
            logger.warning("  如需直接转换 YOLO 模型，请运行: pip install ultralytics")
        except Exception as e:
            logger.warning(f"✗ Ultralytics 导入失败: {e}")
        
        try:
            import yolov6
            self.available_libs['yolov6'] = True
            logger.info("✓ YOLOv6 可用")
        except ImportError:
            logger.warning("✗ YOLOv6 未安装")
            logger.warning("  如需转换 YOLOv6 模型，请使用 YOLOv6 官方导出工具")
            logger.warning("  官方仓库: https://github.com/meituan/YOLOv6")
        
        try:
            import onnx
            self.available_libs['onnx'] = True
            logger.info("✓ ONNX 可用")
        except ImportError:
            logger.warning("✗ ONNX 未安装")
        except Exception as e:
            logger.warning(f"✗ ONNX 导入失败（可能是因为protobuf版本问题）: {str(e)[:100]}")
            logger.warning("  如需使用ONNX功能，请运行: pip install 'protobuf<4' onnx")
            logger.warning("  详细信息请参考 MODEL_INSTALL.md")
        
        try:
            import tensorflow
            self.available_libs['tensorflow'] = True
            logger.info("✓ TensorFlow 可用")
        except ImportError:
            logger.warning("✗ TensorFlow 未安装")
        except Exception as e:
            logger.warning(f"✗ TensorFlow 导入失败: {e}")
        
        try:
            import keras
            self.available_libs['keras'] = True
            logger.info("✓ Keras 可用")
        except ImportError:
            logger.warning("✗ Keras 未安装")
        except Exception as e:
            logger.warning(f"✗ Keras 导入失败: {e}")
    
    def allowed_file(self, filename: str) -> bool:
        """
        检查文件格式是否支持
        
        Args:
            filename: 文件名
            
        Returns:
            是否支持
        """
        return '.' in filename and \
            filename.rsplit('.', 1)[1].lower() in self.INPUT_FORMATS
    
    def get_file_format(self, filename: str) -> str:
        """
        获取文件格式
        
        Args:
            filename: 文件名
            
        Returns:
            文件扩展名（小写）
        """
        return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    def get_conversion_info(self, input_format: str, output_format: str) -> Dict[str, Any]:
        """
        获取转换信息
        
        Args:
            input_format: 输入格式
            output_format: 输出格式
            
        Returns:
            转换信息字典
        """
        key = (input_format.lower(), output_format.lower())
        conversion_name = self.CONVERSION_PATHS.get(key)
        
        return {
            'can_convert': conversion_name is not None,
            'conversion_name': conversion_name,
            'input_format': input_format,
            'output_format': output_format,
            'available_libs': self.available_libs
        }
    
    def convert_model(self, file_path: str, output_format: str,
                     input_shape: Optional[list] = None,
                     opset_version: int = 12,
                     **kwargs) -> Tuple[bytes, Dict[str, Any]]:
        """
        转换模型文件

        Args:
            file_path: 输入文件路径
            output_format: 输出格式
            input_shape: 输入形状（对于需要示例输入的转换）
            opset_version: ONNX opset版本
            **kwargs: 其他转换参数

        Returns:
            (转换后的文件数据, 模型信息字典)
        """
        input_format = self.get_file_format(file_path)
        output_format = output_format.lower()

        logger.info(f"开始转换: {input_format} -> {output_format}")
        logger.info(f"输入文件: {file_path}")

        # 验证转换是否支持
        conversion_info = self.get_conversion_info(input_format, output_format)

        # 如果不支持直接转换，尝试通过中间格式转换
        if not conversion_info['can_convert']:
            logger.info(f"不支持直接转换 {input_format} -> {output_format}，尝试间接转换...")
            return self._convert_via_intermediate(file_path, input_format, output_format, input_shape, opset_version, **kwargs)

        # 根据转换路径执行相应的转换
        conversion_key = (input_format, output_format)

        try:
            # PyTorch 同格式互转（pt/pth/pkl 之间直接保存即可）
            pytorch_formats = {'pt', 'pth', 'pkl'}
            if input_format in pytorch_formats and output_format in pytorch_formats:
                return self._convert_pytorch_same_format(file_path, output_format)
            elif conversion_key in [('pt', 'onnx'), ('pth', 'onnx'), ('pkl', 'onnx')]:
                return self._convert_pytorch_to_onnx(file_path, output_format, input_shape, opset_version)
            elif conversion_key == ('onnx', 'tflite'):
                return self._convert_onnx_to_tflite(file_path, output_format)
            elif conversion_key in [('h5', 'tflite'), ('keras', 'tflite')]:
                return self._convert_keras_to_tflite(file_path, output_format)
            elif conversion_key == ('pb', 'tflite'):
                return self._convert_tf_to_tflite(file_path, output_format, **kwargs)
            elif conversion_key in [('onnx', 'pt'), ('onnx', 'pth')]:
                return self._convert_onnx_to_pytorch(file_path, output_format)
            elif conversion_key in [('pt', 'tflite'), ('pth', 'tflite'), ('pkl', 'tflite')]:
                return self._convert_pytorch_to_tflite_direct(file_path, output_format, input_shape, **kwargs)
            else:
                raise ValueError(f"未实现的转换路径: {conversion_key}")

        except Exception as e:
            error_msg = f"模型转换失败: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            raise Exception(error_msg)

    def _convert_via_intermediate(self, file_path: str, input_format: str, output_format: str,
                                  input_shape: Optional[list] = None, opset_version: int = 12,
                                  **kwargs) -> Tuple[bytes, Dict[str, Any]]:
        """
        通过中间格式转换模型

        支持的间接转换路径：
        - PyTorch (pt/pth/pkl) -> ONNX -> PyTorch (pt/pth)
        """
        import tempfile
        import shutil

        # 定义支持间接转换的路径
        indirect_paths = {
            # PyTorch -> ONNX -> PyTorch (通过 ONNX 重新导出)
            ('pt', 'pt'): ['onnx'],
            ('pth', 'pth'): ['onnx'],
        }

        conversion_key = (input_format, output_format)
        if conversion_key not in indirect_paths:
            # 生成去重后的支持路径列表（input -> output）
            supported_pairs = sorted({f"{src}->{dst}" for (src, dst) in self.CONVERSION_PATHS.keys()})
            raise ValueError(
                f"不支持的转换路径: {input_format} -> {output_format}. "
                f"支持路径: {supported_pairs}\n"
                f"不支持间接转换。"
            )

        intermediate_format = indirect_paths[conversion_key][0]
        logger.info(f"使用间接转换路径: {input_format} -> {intermediate_format} -> {output_format}")

        try:
            # 创建临时文件
            temp_dir = tempfile.mkdtemp(prefix='model_conversion_')
            temp_intermediate_path = os.path.join(temp_dir, f'temp.{intermediate_format}')

            # 第一步：转换为中间格式
            logger.info(f"步骤 1/2: 转换 {input_format} -> {intermediate_format}")
            if intermediate_format == 'onnx':
                converted_data, _ = self._convert_pytorch_to_onnx(
                    file_path, intermediate_format, input_shape, opset_version
                )
                # 保存中间文件
                with open(temp_intermediate_path, 'wb') as f:
                    f.write(converted_data)
                logger.info(f"中间文件已保存: {temp_intermediate_path}")
            else:
                raise ValueError(f"不支持的中间格式: {intermediate_format}")

            # 第二步：从中间格式转换到目标格式
            logger.info(f"步骤 2/2: 转换 {intermediate_format} -> {output_format}")
            if output_format == 'tflite' and intermediate_format == 'onnx':
                final_data, final_info = self._convert_onnx_to_tflite(temp_intermediate_path, output_format)
            elif output_format in ['pt', 'pth'] and intermediate_format == 'onnx':
                final_data, final_info = self._convert_onnx_to_pytorch(temp_intermediate_path, output_format)
            else:
                raise ValueError(f"不支持的间接转换路径: {input_format} -> {intermediate_format} -> {output_format}")

            # 清理临时文件
            if os.path.exists(temp_intermediate_path):
                os.remove(temp_intermediate_path)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

            # 更新转换信息
            final_info['conversion_path'] = f"{input_format} -> {intermediate_format} -> {output_format}"
            final_info['original_format'] = input_format
            final_info['target_format'] = output_format

            logger.info(f"间接转换完成: {input_format} -> {intermediate_format} -> {output_format}")
            return final_data, final_info

        except Exception as e:
            # 清理临时文件
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            if 'temp_intermediate_path' in locals() and os.path.exists(temp_intermediate_path):
                os.remove(temp_intermediate_path)

            error_msg = f"间接转换失败 ({input_format} -> {intermediate_format} -> {output_format}): {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            raise Exception(error_msg)
    
    def _convert_pytorch_to_onnx(self, file_path: str, output_format: str,
                                input_shape: Optional[list] = None,
                                opset_version: int = 12) -> Tuple[bytes, Dict[str, Any]]:
        """PyTorch模型转ONNX"""
        if not self.available_libs['torch']:
            raise ImportError(
                "PyTorch未安装，无法进行PyTorch->ONNX转换。\n"
                "请运行: pip install torch\n"
                "详细安装指南请参考 MODEL_INSTALL.md"
            )
        
        try:
            import torch
        except ImportError as e:
            raise ImportError(
                f"PyTorch导入失败: {e}\n"
                "请检查PyTorch是否正确安装。\n"
                "详细安装指南请参考 MODEL_INSTALL.md"
            )
        
        # 尝试多种加载模型的方式
        model = None
        load_method = None
        is_yolov6 = 'yolov6' in os.path.basename(file_path).lower()
        
        # 方法0: YOLOv6 专用加载（优先于 Ultralytics）
        if is_yolov6:
            logger.info("检测到 YOLOv6 模型，尝试专用加载方式...")
            try:
                # 方法0a: 尝试使用 YOLOv6 官方仓库
                try:
                    from yolov6.utils.config import get_config
                    from yolov6.core.inferer import Inferer
                    
                    # YOLOv6 模型结构
                    class YOLOv6Model(torch.nn.Module):
                        def __init__(self, weights_path):
                            super().__init__()
                            checkpoint = torch.load(weights_path, map_location='cpu')
                            if 'model' in checkpoint:
                                self.model = checkpoint['model'].float()
                            elif 'state_dict' in checkpoint:
                                # 构建模型结构
                                state_dict = checkpoint['state_dict']
                                # YOLOv6 通常是 DetBenchModel 或类似结构
                                self.model = torch.nn.Module()
                            else:
                                # 直接使用 checkpoint 中的模型
                                self.model = checkpoint.get('ema', checkpoint.get('model', checkpoint))
                            
                        def forward(self, x):
                            return self.model(x)
                    
                    model = YOLOv6Model(file_path)
                    load_method = 'yolov6_official'
                    logger.info("使用 YOLOv6 官方方式加载成功")
                except ImportError:
                    logger.warning("YOLOv6 模块未安装，尝试其他方式...")
                    # 方法0b: 尝试直接加载 state_dict
                    try:
                        checkpoint = torch.load(file_path, map_location='cpu', weights_only=False)
                        if isinstance(checkpoint, dict):
                            if 'model' in checkpoint:
                                model_state = checkpoint['model']
                                if hasattr(model_state, 'float'):
                                    model = model_state.float()
                                    load_method = 'yolov6_checkpoint'
                                    logger.info("从 checkpoint 加载 YOLOv6 模型")
                            elif 'state_dict' in checkpoint:
                                # 尝试构建 YOLOv6 结构
                                model_state = checkpoint['state_dict']
                                # 检查是否是 YOLOv6 的 state_dict
                                if any('yolov6' in str(k).lower() for k in list(model_state.keys())[:5]):
                                    load_method = 'yolov6_state_dict'
                                    logger.info("检测到 YOLOv6 state_dict，尝试适配...")
                                    # 创建一个简单的 wrapper 模型
                                    class YOLOv6Wrapper(torch.nn.Module):
                                        def __init__(self, state_dict):
                                            super().__init__()
                                            self.state_dict = state_dict
                                        def forward(self, x):
                                            # YOLOv6 的前向传播
                                            return x  # 占位符，实际需要模型结构
                                    model = YOLOv6Wrapper(model_state)
                    except Exception as e:
                        logger.warning(f"YOLOv6 checkpoint 加载失败: {e}")
            except Exception as e:
                logger.warning(f"YOLOv6 专用加载失败: {e}")
        
        # 方法1: 使用 Ultralytics 加载 YOLO 模型（非 YOLOv6）
        if model is None and not is_yolov6 and self.available_libs['ultralytics']:
            try:
                from ultralytics import YOLO
                model = YOLO(file_path)
                load_method = 'ultralytics'
                logger.info("使用 Ultralytics 加载 YOLO 模型")
            except Exception as e:
                logger.info(f"Ultralytics 加载失败 (可能不是 YOLO 模型): {e}")
        
        # 方法1: 直接加载（用于 state_dict / checkpoint）
        if model is None:
            try:
                # PyTorch 2.6+ 默认 weights_only=True，旧 checkpoint 需显式关闭
                try:
                    model = torch.load(file_path, map_location="cpu", weights_only=False)
                except TypeError:
                    model = torch.load(file_path, map_location="cpu")
                load_method = 'direct_load'
            except Exception as e:
                logger.warning(f"直接加载失败: {e}")
        
        # 方法2: 检查是否是包含 model 键的字典（非 ultralytics 模型）
        if model is not None and load_method != 'ultralytics' and isinstance(model, dict):
            if 'model' in model:
                model = model['model']
                load_method = 'dict_with_model'
            elif 'state_dict' in model:
                model = model['state_dict']
                load_method = 'dict_with_state_dict'
            else:
                # 尝试使用 torch.hub.load
                try:
                    model = torch.hub.load('ultralytics/yolov5', 'custom', path=file_path, source='github')
                    load_method = 'yolov5_hub'
                    logger.info("使用 torch.hub 加载 YOLOv5 模型")
                except Exception as hub_error:
                    logger.warning(f"torch.hub 加载失败: {hub_error}")
                    raise Exception(
                        f"无法加载模型。错误：{hub_error}\n"
                        f"\n提示：\n"
                        f"- 如果是 YOLOv5/ULTRALYTICS 模型，请安装 ultralytics: pip install ultralytics\n"
                        f"- 如果是自定义模型，请确保模型文件完整\n"
                        f"- 如果是预训练模型，请尝试从官方源重新导出"
                    )
        
        # 方法3: 尝试从 hub 加载（适用于某些模型）
        if model is None or (load_method != 'ultralytics' and not hasattr(model, 'eval')):
            try:
                # 尝试常见的模型仓库
                for repo in ['ultralytics/yolov5', 'pytorch/vision']:
                    try:
                        model = torch.hub.load(repo, 'custom', path=file_path, source='github')
                        load_method = f'hub_{repo}'
                        logger.info(f"使用 torch.hub 加载模型: {repo}")
                        break
                    except:
                        continue
            except Exception as e:
                logger.warning(f"torch.hub 加载失败: {e}")
        
        # 检查模型是否成功加载
        if model is None:
            yolov6_hint = ""
            if is_yolov6:
                yolov6_hint = (
                    "\n\n【YOLOv6 专用提示】\n"
                    "检测到你上传的是 YOLOv6 模型。YOLOv6 需要专用的加载方式。\n"
                    "推荐方案：\n"
                    "1. 使用 YOLOv6 官方导出工具（推荐）:\n"
                    "   - 下载 YOLOv6 仓库: git clone https://github.com/meituan/YOLOv6.git\n"
                    "   - 进入目录: cd YOLOv6\n"
                    "   - 安装依赖: pip install -r requirements.txt\n"
                    "   - 导出 ONNX: python tools/export.py --weights 你的模型.pt --img 640 --batch 1\n\n"
                    "2. 或者安装 YOLOv6 Python 包:\n"
                    "   pip install yolov6\n"
                )
            raise Exception(
                f"模型加载失败。可能的原因：\n"
                f"1. 模型需要特定的加载方式（如 YOLOv6 需要 yolov6.models 模块）\n"
                f"2. 模型文件不完整或损坏\n"
                f"3. 模型依赖外部代码库\n\n"
                f"建议：\n"
                f"- 如果是 YOLOv6 模型，请使用 YOLOv6 官方导出工具\n"
                f"- 如果是 YOLOv5/YOLOv8 模型，请安装 ultralytics: pip install ultralytics\n"
                f"- 如果是 YOLOv5 模型，请使用 export.py 脚本直接导出 ONNX\n"
                f"- 查看模型仓库的官方导出工具"
                f"{yolov6_hint}"
            )
        
        # 如果模型不是 nn.Module 且不是 ultralytics/yolov6 模型，尝试构建
        if load_method not in ['ultralytics', 'yolov6_official', 'yolov6_checkpoint', 'yolov6_state_dict'] and not hasattr(model, 'eval'):
            raise Exception(
                "加载的对象不是有效的 PyTorch 模型。\n"
                f"加载方式: {load_method}\n"
                "请确保上传的是完整的 PyTorch 模型文件（.pt 或 .pth）。"
            )
        
        # 设置为评估模式（仅对非 ultralytics/yolov6 模型）
        if load_method not in ['ultralytics', 'yolov6_state_dict']:
            try:
                model.eval()
            except:
                logger.warning(f"无法将模型设置为 eval 模式 (加载方式: {load_method})")
        
        # YOLOv6 state_dict 需要特殊处理
        if load_method == 'yolov6_state_dict':
            raise Exception(
                "YOLOv6 模型需要完整的模型结构才能导出为 ONNX。\n"
                "请使用 YOLOv6 官方导出工具：\n"
                "1. git clone https://github.com/meituan/YOLOv6.git\n"
                "2. cd YOLOv6\n"
                "3. pip install -r requirements.txt\n"
                "4. python tools/export.py --weights 你的模型.pt --img 640 --batch 1\n"
            )
        
        # 确定输入形状
        if input_shape is None:
            # 尝试从模型获取输入形状（不总是可行）
            try:
                if load_method == 'ultralytics':
                    # Ultralytics 模型默认使用 640x640
                    input_shape = [1, 3, 640, 640]
                    logger.info(f"使用 Ultralytics 默认输入形状: {input_shape}")
                elif is_yolov6 or load_method in ['yolov6_official', 'yolov6_checkpoint']:
                    # YOLOv6 默认使用 640x640
                    input_shape = [1, 3, 640, 640]
                    logger.info(f"YOLOv6 模型使用默认输入形状: {input_shape}")
                elif hasattr(model, 'model'):
                    first_layer = list(model.model.parameters())[0] if list(model.model.parameters()) else None
                    if first_layer is not None:
                        input_shape = [1] + list(first_layer.shape)[1:]
                        logger.info(f"自动检测到输入形状: {input_shape}")
                else:
                    first_layer = list(model.parameters())[0] if list(model.parameters()) else None
                    if first_layer is not None:
                        input_shape = [1] + list(first_layer.shape)[1:]
                        logger.info(f"自动检测到输入形状: {input_shape}")
            except:
                pass
            
            # 默认形状 (1, 3, 224, 224) - 常见的图像分类输入
            if input_shape is None:
                input_shape = [1, 3, 224, 224]
                logger.info(f"使用默认输入形状: {input_shape}")
        
        # 生成输出文件名
        output_filename = os.path.basename(file_path).rsplit('.', 1)[0] + '.onnx'
        output_path = os.path.join(self.download_folder, output_filename)
        
        # 转换为ONNX
        try:
            if load_method == 'ultralytics':
                # 使用 Ultralytics 的 export 方法
                logger.info(f"使用 Ultralytics.export() 导出 ONNX...")
                model.export(format='onnx', simplify=True, opset=opset_version)
                
                # Ultralytics 会将 ONNX 文件保存在原文件同一目录，文件名不变但扩展名改为 .onnx
                # 我们需要找到它并移动到下载目录
                generated_onnx_path = os.path.splitext(file_path)[0] + '.onnx'
                if os.path.exists(generated_onnx_path):
                    import shutil
                    shutil.move(generated_onnx_path, output_path)
                    logger.info(f"移动 ONNX 文件到: {output_path}")
                else:
                    # 尝试查找可能的 ONNX 文件
                    base_name = os.path.basename(file_path).rsplit('.', 1)[0]
                    for ext in ['.onnx', '_onnx.onnx']:
                        possible_path = os.path.join(os.path.dirname(file_path), base_name + ext)
                        if os.path.exists(possible_path):
                            import shutil
                            shutil.move(possible_path, output_path)
                            logger.info(f"移动 ONNX 文件到: {output_path}")
                            break
                    else:
                        raise Exception("Ultralytics 导出后未找到生成的 ONNX 文件")
            elif load_method in ['yolov6_official', 'yolov6_checkpoint']:
                # YOLOv6 使用标准 PyTorch 导出
                logger.info(f"使用标准 PyTorch 导出 YOLOv6 模型为 ONNX...")
                dummy_input = torch.randn(*input_shape)
                
                torch.onnx.export(
                    model,
                    dummy_input,
                    output_path,
                    export_params=True,
                    opset_version=opset_version,
                    do_constant_folding=True,
                    input_names=['images'],
                    output_names=['output'],
                    dynamic_axes={
                        'images': {0: 'batch_size'},
                        'output': {0: 'batch_size'}
                    },
                )
            else:
                # 使用标准 PyTorch 导出
                # 创建示例输入
                dummy_input = torch.randn(*input_shape)
                
                torch.onnx.export(
                    model,
                    dummy_input,
                    output_path,
                    export_params=True,
                    opset_version=opset_version,
                    do_constant_folding=True,
                    input_names=['input'],
                    output_names=['output'],
                    dynamic_axes={
                        'input': {0: 'batch_size'},
                        'output': {0: 'batch_size'}
                    } if input_shape[0] == 1 else None,
                    verbose=False
                )
        except Exception as e:
            # 提供更有用的错误信息
            raise Exception(
                f"ONNX 导出失败: {e}\n"
                f"\n尝试的输入形状: {input_shape}\n"
                f"加载方式: {load_method}\n"
                f"\n建议：\n"
                f"- 检查模型是否支持导出到 ONNX\n"
                f"- 尝试不同的输入形状\n"
                f"- 如果是 YOLO 模型，确保安装了 ultralytics: pip install ultralytics\n"
                f"- 查看模型文档了解正确的导出方法"
            )
        
        # 读取转换后的文件
        with open(output_path, 'rb') as f:
            converted_data = f.read()

        graph_in, graph_out = [], []
        try:
            import onnx

            onnx_model = onnx.load(output_path)
            graph_in = [i.name for i in onnx_model.graph.input]
            graph_out = [o.name for o in onnx_model.graph.output]
        except Exception as ex:
            logger.warning("解析 ONNX 元数据失败（不影响导出文件）: %s", ex)

        model_info = {
            'original_format': 'pytorch',
            'target_format': 'onnx',
            'input_shape': input_shape,
            'opset_version': opset_version,
            'model_size_bytes': len(converted_data),
            'graph_input_names': graph_in,
            'graph_output_names': graph_out,
            'conversion_method': 'PyTorch转ONNX'
        }
        
        # 清理临时文件
        if os.path.exists(output_path):
            os.remove(output_path)
        
        return converted_data, model_info

    def _convert_pytorch_same_format(self, file_path: str, output_format: str) -> Tuple[bytes, Dict[str, Any]]:
        """PyTorch 同格式互转（pt/pth/pkl），直接加载后重新保存"""
        if not self.available_libs['torch']:
            raise ImportError("PyTorch 未安装，无法转换 PyTorch 格式。请运行: pip install torch")

        import torch
        logger.info(f"PyTorch 同格式转换: 保存为 .{output_format}")

        try:
            checkpoint = torch.load(file_path, map_location='cpu', weights_only=False)
        except TypeError:
            checkpoint = torch.load(file_path, map_location='cpu')

        import io
        buf = io.BytesIO()
        torch.save(checkpoint, buf)
        converted_data = buf.getvalue()

        model_info = {
            'original_format': self.get_file_format(file_path),
            'target_format': output_format,
            'model_size_bytes': len(converted_data),
            'conversion_method': f'PyTorch格式重保存(.{output_format})'
        }
        return converted_data, model_info

    def _convert_pytorch_to_tflite_direct(self, file_path: str, output_format: str,
                                         input_shape: Optional[list] = None,
                                         opset_version: int = 12,
                                         **kwargs) -> Tuple[bytes, Dict[str, Any]]:
        """使用 Ultralytics 原生导出 PyTorch模型转TFLite，失败则回退到间接转换"""

        # 抑制 TensorFlow 警告
        warnings.filterwarnings('ignore', category=UserWarning)
        warnings.filterwarnings('ignore', category=FutureWarning)

        try:
            import tensorflow as tf
            tf.get_logger().setLevel('ERROR')
        except ImportError:
            pass

        # 尝试使用 Ultralytics 直接导出
        if self.available_libs['ultralytics'] and self.available_libs['tensorflow']:
            try:
                from ultralytics import YOLO

                # 加载 YOLO 模型
                model = YOLO(file_path)
                logger.info("使用 Ultralytics 加载 YOLO 模型")

                # 生成输出文件名
                base_name = os.path.basename(file_path).rsplit('.', 1)[0]
                dir_path = os.path.dirname(file_path)
                saved_model_dir = os.path.join(dir_path, base_name + '_saved_model')

                # 使用 Ultralytics 的 export 方法直接导出 TFLite
                logger.info(f"使用 Ultralytics.export() 直接导出 TFLite...")
                model.export(format='tflite', simplify=True)

                # 查找生成的 TFLite 文件
                tflite_file = None

                # 优先查找在 _saved_model 目录下的文件
                if os.path.exists(saved_model_dir):
                    # 查找 _float32.tflite 文件
                    possible_path = os.path.join(saved_model_dir, base_name + '_float32.tflite')
                    if os.path.exists(possible_path):
                        tflite_file = possible_path
                        logger.info(f"找到 TFLite 文件: {tflite_file}")
                    else:
                        # 列出 _saved_model 目录中的所有文件
                        dir_files = os.listdir(saved_model_dir)
                        logger.info(f"_saved_model 目录内容: {dir_files}")
                        # 尝试找到任何 .tflite 文件
                        for f in dir_files:
                            if f.endswith('.tflite'):
                                tflite_file = os.path.join(saved_model_dir, f)
                                logger.info(f"找到 TFLite 文件: {tflite_file}")
                                break

                # 如果在 _saved_model 目录中没找到，尝试在原目录中查找（兼容旧版本）
                if tflite_file is None:
                    for ext in ['.tflite', '_float32.tflite']:
                        possible_path = os.path.join(dir_path, base_name + ext)
                        if os.path.exists(possible_path):
                            tflite_file = possible_path
                            logger.info(f"找到 TFLite 文件: {tflite_file}")
                            break

                if tflite_file is None:
                    # 列出目录中所有可能的文件和目录
                    dir_files = os.listdir(dir_path)
                    logger.error(f"目录内容: {dir_files}")
                    if os.path.exists(saved_model_dir):
                        saved_model_files = os.listdir(saved_model_dir)
                        logger.error(f"_saved_model 目录内容: {saved_model_files}")
                    raise Exception("Ultralytics 导出后未找到生成的 TFLite 文件")

                # 读取 TFLite 文件
                with open(tflite_file, 'rb') as f:
                    tflite_data = f.read()

                # 移动到下载目录（如果原文件不在下载目录）
                tflite_filename = os.path.basename(tflite_file)
                target_path = os.path.join(self.download_folder, tflite_filename)

                if os.path.dirname(tflite_file) != self.download_folder:
                    import shutil
                    shutil.move(tflite_file, target_path)
                    logger.info(f"移动 TFLite 文件到: {target_path}")

                # 清理 _saved_model 目录
                if os.path.exists(saved_model_dir):
                    import shutil
                    shutil.rmtree(saved_model_dir)
                    logger.info(f"清理临时目录: {saved_model_dir}")

                # 获取输入形状信息
                if input_shape is None:
                    input_shape = [1, 3, 640, 640]
                    logger.info(f"使用默认输入形状: {input_shape}")

                model_info = {
                    'original_format': 'pytorch',
                    'target_format': 'tflite',
                    'input_shape': input_shape,
                    'model_size_bytes': len(tflite_data),
                    'conversion_method': 'PyTorch转TFLite (Ultralytics原生)'
                }

                return tflite_data, model_info

            except Exception as e:
                # Ultralytics 加载或导出失败，回退到间接转换
                logger.warning(f"Ultralytics 原生转换失败: {e}")
                logger.info("回退到间接转换: PT -> ONNX -> TFLite")
        else:
            logger.info("Ultralytics 或 TensorFlow 不可用，使用间接转换")

        # 回退到间接转换：PT -> ONNX -> TFLite
        logger.info("使用间接转换路径: PT -> ONNX -> TFLite")
        import tempfile
        import shutil

        try:
            # 创建临时文件
            temp_dir = tempfile.mkdtemp(prefix='model_conversion_')
            temp_onnx_path = os.path.join(temp_dir, 'temp.onnx')

            # 第一步：转换为 ONNX
            logger.info(f"步骤 1/2: 转换 PT -> ONNX")
            onnx_data, _ = self._convert_pytorch_to_onnx(
                file_path, 'onnx', input_shape, opset_version
            )
            with open(temp_onnx_path, 'wb') as f:
                f.write(onnx_data)
            logger.info(f"中间文件已保存: {temp_onnx_path}")

            # 第二步：从 ONNX 转换到 TFLite
            logger.info(f"步骤 2/2: 转换 ONNX -> TFLite")
            final_data, final_info = self._convert_onnx_to_tflite(temp_onnx_path, 'tflite')

            # 清理临时文件
            if os.path.exists(temp_onnx_path):
                os.remove(temp_onnx_path)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

            # 更新转换信息
            final_info['conversion_path'] = 'PT -> ONNX -> TFLite'
            final_info['original_format'] = 'pt'
            final_info['target_format'] = 'tflite'

            logger.info(f"间接转换完成: PT -> ONNX -> TFLite")
            return final_data, final_info

        except Exception as e:
            # 清理临时文件
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            if 'temp_onnx_path' in locals() and os.path.exists(temp_onnx_path):
                os.remove(temp_onnx_path)

            error_msg = f"间接转换失败 (PT -> ONNX -> TFLite): {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            raise Exception(error_msg)

    def _convert_onnx_to_tflite(self, file_path: str, output_format: str) -> Tuple[bytes, Dict[str, Any]]:
        """ONNX模型转TFLite"""
        # 抑制警告
        warnings.filterwarnings('ignore', category=UserWarning)
        warnings.filterwarnings('ignore', category=FutureWarning)

        # 设置 TensorFlow 和 absl 日志级别
        import logging
        tf_logger = logging.getLogger('tensorflow')
        tf_logger.setLevel(logging.ERROR)
        absl_logger = logging.getLogger('absl')
        absl_logger.setLevel(logging.ERROR)

        try:
            import onnx
        except ImportError:
            raise ImportError("ONNX未安装，无法进行ONNX->TFLite转换")

        # 尝试使用onnx-tf进行转换
        try:
            import onnx_tf
        except ImportError:
            raise ImportError("onnx-tf未安装。请运行: pip install onnx-tf")

        try:
            import tensorflow as tf
            # 进一步抑制 TensorFlow 的日志输出
            tf.get_logger().setLevel('ERROR')
        except ImportError:
            raise ImportError("TensorFlow未安装，无法转换到TFLite")

        # 加载ONNX模型
        onnx_model = onnx.load(file_path)

        # 转换为TensorFlow模型
        tf_rep = onnx_tf.backend.prepare(onnx_model)

        # 导出为SavedModel
        output_filename = os.path.basename(file_path).rsplit('.', 1)[0]
        saved_model_path = os.path.join(self.download_folder, f'{output_filename}_temp_tf')
        tf_rep.export_graph(saved_model_path)

        # 转换为TFLite
        converter = tf.lite.TFLiteConverter.from_saved_model(saved_model_path)
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        tflite_model = converter.convert()

        # 清理临时目录
        import shutil
        if os.path.exists(saved_model_path):
            shutil.rmtree(saved_model_path)

        model_info = {
            'original_format': 'onnx',
            'target_format': 'tflite',
            'model_size_bytes': len(tflite_model),
            'conversion_method': 'ONNX转TFLite'
        }

        return tflite_model, model_info
    
    def _convert_keras_to_tflite(self, file_path: str, output_format: str) -> Tuple[bytes, Dict[str, Any]]:
        """Keras模型转TFLite"""
        try:
            import tensorflow as tf
        except ImportError:
            raise ImportError("TensorFlow未安装，无法进行Keras->TFLite转换")
        
        # 加载Keras模型
        model = tf.keras.models.load_model(file_path)
        
        # 转换为TFLite
        converter = tf.lite.TFLiteConverter.from_keras_model(model)
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        tflite_model = converter.convert()
        
        model_info = {
            'original_format': 'keras',
            'target_format': 'tflite',
            'model_size_bytes': len(tflite_model),
            'conversion_method': 'Keras转TFLite'
        }
        
        return tflite_model, model_info
    
    def _convert_tf_to_tflite(self, file_path: str, output_format: str, 
                            **kwargs) -> Tuple[bytes, Dict[str, Any]]:
        """TensorFlow SavedModel转TFLite"""
        try:
            import tensorflow as tf
        except ImportError:
            raise ImportError("TensorFlow未安装，无法进行TF->TFLite转换")
        
        # 转换为TFLite
        converter = tf.lite.TFLiteConverter.from_saved_model(file_path)
        
        # 设置优化
        if kwargs.get('optimize', True):
            converter.optimizations = [tf.lite.Optimize.DEFAULT]
        
        tflite_model = converter.convert()
        
        model_info = {
            'original_format': 'tensorflow',
            'target_format': 'tflite',
            'model_size_bytes': len(tflite_model),
            'conversion_method': 'TensorFlow转TFLite'
        }
        
        return tflite_model, model_info
    
    def _convert_onnx_to_pytorch(self, file_path: str, output_format: str) -> Tuple[bytes, Dict[str, Any]]:
        """ONNX模型转PyTorch"""
        try:
            import onnx
        except ImportError:
            raise ImportError("ONNX未安装，无法进行ONNX->PyTorch转换")
        
        try:
            import torch
        except ImportError:
            raise ImportError("PyTorch未安装，无法进行ONNX->PyTorch转换")
        
        # 加载ONNX模型
        onnx_model = onnx.load(file_path)
        
        # 使用onnx2pytorch进行转换
        try:
            import onnx2pytorch
        except ImportError:
            raise ImportError("onnx2pytorch未安装。请运行: pip install onnx2pytorch")
        
        pytorch_model = onnx2pytorch.ConvertModel(onnx_model)
        
        # 保存模型
        output_filename = os.path.basename(file_path).rsplit('.', 1)[0] + '.pt'
        output_path = os.path.join(self.download_folder, output_filename)
        torch.save(pytorch_model, output_path)
        
        # 读取转换后的文件
        with open(output_path, 'rb') as f:
            converted_data = f.read()
        
        model_info = {
            'original_format': 'onnx',
            'target_format': 'pytorch',
            'model_size_bytes': len(converted_data),
            'conversion_method': 'ONNX转PyTorch'
        }
        
        # 清理临时文件
        if os.path.exists(output_path):
            os.remove(output_path)
        
        return converted_data, model_info
    
    def get_supported_conversions(self) -> Dict[str, list]:
        """
        获取支持的所有转换路径

        Returns:
            支持的转换路径字典
        """
        return {
            'pytorch_to_onnx': ['pt', 'pth', 'pkl'],
            'pytorch_to_tflite': ['pt', 'pth', 'pkl'],  # 使用 Ultralytics 原生导出
            'onnx_to_tflite': ['onnx'],
            'keras_to_tflite': ['h5', 'keras'],
            'tensorflow_to_tflite': ['pb'],
            'onnx_to_pytorch': ['onnx'],
        }
