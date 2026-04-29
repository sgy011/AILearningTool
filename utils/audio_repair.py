import os
import base64
import io
import subprocess
import sys
import logging
from pydub import AudioSegment
from pydub.effects import normalize
import tempfile

logger = logging.getLogger(__name__)

class AudioRepair:
    def __init__(self):
        self.supported_formats = ['mp3', 'wav', 'm4a', 'flac', 'ogg', 'aac']
        self.max_file_size = 50 * 1024 * 1024  # 50MB
        self._check_ffmpeg()
    
    def allowed_file(self, filename):
        """检查文件是否为支持的音频格式"""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in self.supported_formats
    
    def repair_audio(
        self,
        file_data,
        output_format='wav',
        quality=320,
        auto_detect_mono=True,
        enhance_stereo=True,
        mode='repair',
    ):
        """
        修复或转换音频。

        Args:
            file_data: 文件数据或文件路径
            output_format: 输出格式
            quality: 音频质量 (kbps)，有损格式使用
            auto_detect_mono: 是否自动检测单音道（仅 mode=repair）
            enhance_stereo: 是否增强立体声（仅 mode=repair）
            mode: repair=单声道修复、立体声增强与标准化；convert=仅按目标格式转码，不做修复

        Returns:
            str: base64 编码的音频数据
            dict: 音频信息
        """
        if not self.ffmpeg_available:
            raise Exception('ffmpeg未安装，无法处理音频文件。请安装ffmpeg后重试。')
        
        try:
            # 如果是文件路径，读取文件
            if isinstance(file_data, str) and os.path.exists(file_data):
                with open(file_data, 'rb') as f:
                    file_bytes = f.read()
            else:
                file_bytes = file_data
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as temp_input:
                temp_input.write(file_bytes)
                temp_input_path = temp_input.name
            
            try:
                # 加载音频文件
                audio = AudioSegment.from_file(temp_input_path)
                
                # 获取原始音频信息
                original_info = {
                    'channels': audio.channels,
                    'sample_rate': audio.frame_rate,
                    'duration_seconds': len(audio) / 1000.0,
                    'sample_width': audio.sample_width,
                    'max_dBFS': audio.max_dBFS
                }
                
                # 检测是否为单音道
                is_mono = audio.channels == 1

                # 仅格式转换：不重算波形，直接导出为目标格式
                if mode == 'convert':
                    stereo_audio = audio
                    repaired_info = {'convert_only': True, 'no_repair_needed': True}
                # 修复处理
                elif is_mono and auto_detect_mono:
                    # 将单音道转换为立体声
                    try:
                        stereo_audio = self._mono_to_stereo(audio, enhance_stereo)
                        repaired_info = {'mono_to_stereo': True, 'enhanced': enhance_stereo}
                    except Exception as e:
                        logger.warning("单声道转立体声失败: %s", e)
                        stereo_audio = audio  # 回退到原始音频
                        repaired_info = {'mono_to_stereo_failed': True, 'error': str(e)}
                elif audio.channels == 2 and enhance_stereo:
                    # 增强立体声效果
                    try:
                        stereo_audio = self._enhance_stereo(audio)
                        repaired_info = {'stereo_enhanced': True}
                    except Exception as e:
                        logger.warning("立体声增强失败: %s", e)
                        stereo_audio = audio  # 回退到原始音频
                        repaired_info = {'stereo_enhance_failed': True, 'error': str(e)}
                else:
                    stereo_audio = audio
                    repaired_info = {'no_repair_needed': True}

                # 音频标准化（仅修复模式）
                if mode == 'repair':
                    try:
                        stereo_audio = normalize(stereo_audio)
                    except Exception as e:
                        logger.warning("音频标准化失败: %s", e)

                # 保存到内存
                output_buffer = io.BytesIO()
                
                # 根据输出格式导出
                export_params = {}
                if output_format in ['mp3', 'm4a', 'ogg']:
                    export_params['bitrate'] = f'{quality}k'
                
                try:
                    stereo_audio.export(output_buffer, format=output_format, **export_params)
                except Exception as e:
                    # 如果指定格式失败，回退到WAV格式
                    logger.warning("导出%s格式失败: %s，回退到WAV格式", output_format, e)
                    output_format = 'wav'
                    stereo_audio.export(output_buffer, format='wav')
                    repaired_info['format_fallback'] = True
                
                # 转换为base64
                base64_data = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
                
                # 获取修复后的音频信息
                try:
                    repaired_audio = AudioSegment.from_file(io.BytesIO(output_buffer.getvalue()))
                    final_info = {
                        'channels': repaired_audio.channels,
                        'sample_rate': repaired_audio.frame_rate,
                        'duration_seconds': len(repaired_audio) / 1000.0,
                        'sample_width': repaired_audio.sample_width,
                        'max_dBFS': repaired_audio.max_dBFS
                    }
                except Exception as e:
                    logger.warning("获取修复后音频信息失败: %s", e)
                    final_info = {'error': '无法获取音频信息'}
                
                return base64_data, {
                    'original_info': original_info,
                    'repaired_info': repaired_info,
                    'final_info': final_info,
                    'original_size': len(file_bytes),
                    'repaired_size': len(output_buffer.getvalue())
                }
                
            finally:
                # 清理临时文件 - 增加重试机制
                self._safe_delete_file(temp_input_path)
                    
        except Exception as e:
            raise Exception(f"音频处理失败: {str(e)}")
    
    def _mono_to_stereo(self, mono_audio, enhance_stereo=True):
        """将单音道转换为立体声"""
        if mono_audio.channels != 1:
            return mono_audio

        # 基本立体声转换
        stereo_audio = AudioSegment.from_mono_audiosegments(mono_audio, mono_audio)

        if enhance_stereo:
            # 增强立体声效果
            # 轻微的声道间延迟和音量差异
            left_channel = stereo_audio.split_to_mono()[0]
            right_channel = stereo_audio.split_to_mono()[1]

            # 添加轻微的延迟效果
            delay_ms = 5  # 5毫秒延迟
            delayed_right = right_channel + AudioSegment.silent(duration=delay_ms)

            # 轻微的音量调整 - 使用 overlay 而不是直接修改
            # 确保左右声道长度一致
            max_length = max(len(left_channel), len(delayed_right))
            left_channel = left_channel + AudioSegment.silent(duration=max_length - len(left_channel))
            delayed_right = delayed_right + AudioSegment.silent(duration=max_length - len(delayed_right))

            # 使用音量增益调整（以dB为单位）
            left_channel = left_channel.apply_gain(-0.5)  # 左声道音量稍微降低 0.5dB
            delayed_right = delayed_right.apply_gain(0.5)  # 右声道音量稍微提高 0.5dB

            # 合并
            stereo_audio = AudioSegment.from_mono_audiosegments(left_channel, delayed_right)

        return stereo_audio
    
    def _enhance_stereo(self, stereo_audio):
        """增强立体声效果"""
        if stereo_audio.channels != 2:
            return stereo_audio

        left, right = stereo_audio.split_to_mono()

        # 增强立体声分离度
        # 通过调整左右声道的差异来增强立体声效果
        # 确保左右声道长度一致
        max_length = max(len(left), len(right))
        if len(left) < max_length:
            left = left + AudioSegment.silent(duration=max_length - len(left))
        if len(right) < max_length:
            right = right + AudioSegment.silent(duration=max_length - len(right))

        # 使用更简单的方法增强立体声：直接调整音量差异
        # 左声道稍微降低，右声道稍微提高
        enhanced_left = left.apply_gain(-0.3)
        enhanced_right = right.apply_gain(0.3)

        # 合并为立体声
        enhanced_stereo = AudioSegment.from_mono_audiosegments(enhanced_left, enhanced_right)

        return enhanced_stereo
    
    def get_audio_info(self, file_data):
        """获取音频文件信息"""
        if not self.ffmpeg_available:
            return {'error': 'ffmpeg未安装，无法处理音频文件。请安装ffmpeg后重试。'}
        
        try:
            # 如果是文件路径，读取文件
            if isinstance(file_data, str) and os.path.exists(file_data):
                with open(file_data, 'rb') as f:
                    file_bytes = f.read()
            else:
                file_bytes = file_data
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as temp_input:
                temp_input.write(file_bytes)
                temp_input_path = temp_input.name
            
            try:
                audio = AudioSegment.from_file(temp_input_path)
                
                return {
                    'channels': audio.channels,
                    'sample_rate': audio.frame_rate,
                    'duration_seconds': len(audio) / 1000.0,
                    'sample_width': audio.sample_width,
                    'max_dBFS': audio.max_dBFS,
                    'file_size': len(file_bytes),
                    'is_mono': audio.channels == 1,
                    'format': self._detect_format(file_bytes)
                }
                
            finally:
                # 清理临时文件 - 增加重试机制
                self._safe_delete_file(temp_input_path)
                    
        except Exception as e:
            return {'error': str(e)}
    
    def _detect_format(self, file_bytes):
        """检测音频文件格式"""
        # 通过文件头检测格式
        if file_bytes.startswith(b'ID3') or file_bytes.startswith(b'\xff\xfb'):
            return 'mp3'
        elif file_bytes.startswith(b'RIFF') and b'WAVE' in file_bytes[:12]:
            return 'wav'
        elif file_bytes.startswith(b'ftyp'):
            return 'm4a'
        elif file_bytes.startswith(b'fLaC'):
            return 'flac'
        elif file_bytes.startswith(b'OggS'):
            return 'ogg'
        else:
            return 'unknown'
    
    def _check_ffmpeg(self):
        """检查 ffmpeg 是否可用：优先 FFMPEG_PATH，其次项目目录内二进制，最后 PATH。"""
        from pydub import AudioSegment

        def _try_set_and_verify(path: str) -> bool:
            try:
                AudioSegment.converter = path
                subprocess.run([path, "-version"], capture_output=True, check=True)
                return True
            except (subprocess.CalledProcessError, FileNotFoundError, OSError):
                return False

        env_path = os.environ.get("FFMPEG_PATH", "").strip()
        if env_path and os.path.isfile(env_path) and _try_set_and_verify(env_path):
            self.ffmpeg_available = True
            logger.info("使用 FFMPEG_PATH: %s", env_path)
            return

        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        local_names = ("ffmpeg.exe", "ffmpeg") if sys.platform == "win32" else ("ffmpeg", "ffmpeg.exe")
        for name in local_names:
            local_ffmpeg = os.path.join(project_root, name)
            if os.path.isfile(local_ffmpeg) and _try_set_and_verify(local_ffmpeg):
                self.ffmpeg_available = True
                logger.info("使用项目目录 ffmpeg: %s", local_ffmpeg)
                return

        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            self.ffmpeg_available = True
            logger.info("使用系统 PATH 中的 ffmpeg")
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.ffmpeg_available = False
            logger.warning("ffmpeg 未找到，音频处理功能可能受限")
            logger.info(
                "Linux 服务器请安装: yum install ffmpeg 或 apt install ffmpeg；也可设置环境变量 FFMPEG_PATH=/绝对路径/ffmpeg"
            )
    
    def _safe_delete_file(self, file_path, max_retries=3):
        """安全删除文件，支持重试机制"""
        import time
        
        for attempt in range(max_retries):
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
                return True
            except (OSError, PermissionError) as e:
                if attempt == max_retries - 1:
                    # 最后一次尝试失败，记录警告但不抛出异常
                    logger.warning("无法删除临时文件 %s: %s", file_path, str(e))
                    return False
                # 等待一段时间后重试
                time.sleep(0.1)
        return False