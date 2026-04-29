import base64
import io
import os

from PIL import Image, ImageEnhance, ImageOps


class ImageConverter:
    def __init__(self, upload_folder, download_folder):
        self.upload_folder = upload_folder
        self.download_folder = download_folder
    
    def allowed_file(self, filename):
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp', 'ico'}
    
    def _repair_image(self, img: Image.Image) -> Image.Image:
        """
        图片修复：按 EXIF 校正方向、自动对比度、轻度锐化。
        """
        img = ImageOps.exif_transpose(img)
        if img.mode == "P":
            img = img.convert("RGBA")
        try:
            if img.mode == "RGBA":
                r, g, b, a = img.split()
                rgb = Image.merge("RGB", (r, g, b))
                rgb = ImageOps.autocontrast(rgb, cutoff=1)
                r, g, b = rgb.split()
                img = Image.merge("RGBA", (r, g, b, a))
            elif img.mode in ("RGB", "L"):
                img = ImageOps.autocontrast(img, cutoff=1)
            else:
                tmp = img.convert("RGB")
                tmp = ImageOps.autocontrast(tmp, cutoff=1)
                img = tmp
        except Exception:
            pass
        return ImageEnhance.Sharpness(img).enhance(1.12)

    def convert_image(self, file_path, output_format, quality=85, mode="convert"):
        """
        转换图片格式并返回 base64 数据；可选先执行修复（方向/对比度/锐化）。

        Args:
            file_path: 输入文件路径
            output_format: 输出格式 (png, jpg, webp, bmp, gif)
            quality: 图片质量 (1-100)，部分格式使用
            mode: convert=仅格式转换；repair=先修复再按目标格式导出

        Returns:
            str: base64 编码的图片数据
        """
        try:
            fmt = (output_format or "").strip().lower()
            pil_format_map = {
                "jpg": "JPEG",
                "jpeg": "JPEG",
                "png": "PNG",
                "webp": "WEBP",
                "bmp": "BMP",
                "gif": "GIF",
                "tif": "TIFF",
                "tiff": "TIFF",
                "ico": "ICO",
            }
            pil_format = pil_format_map.get(fmt, (output_format or "").upper())

            # 兼容前端传 0~1（如 0.85）或 1~100 的质量值
            try:
                q_raw = float(quality)
            except Exception:
                q_raw = 85.0
            if q_raw <= 1.0:
                q_raw *= 100.0
            # PIL JPEG 在高版本通常建议 <=95；WEBP 支持 0~100
            q_jpeg = max(1, min(95, int(round(q_raw))))
            q_webp = max(1, min(100, int(round(q_raw))))

            # 打开图片
            with Image.open(file_path) as img:
                img.load()
                if mode == "repair":
                    img = self._repair_image(img)

                # 处理透明度 (JPEG不支持透明度)
                if fmt in ['jpg', 'jpeg'] and img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                
                # 保存到内存
                output_buffer = io.BytesIO()
                
                # 保存转换后的图片
                save_kwargs = {}
                if fmt in ['jpg', 'jpeg']:
                    save_kwargs['quality'] = q_jpeg
                    save_kwargs['optimize'] = True
                elif fmt == 'png':
                    save_kwargs['optimize'] = True
                elif fmt == 'webp':
                    save_kwargs['quality'] = q_webp
                    save_kwargs['optimize'] = True
                
                img.save(output_buffer, format=pil_format, **save_kwargs)

                base64_data = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
                
                return base64_data
                
        except Exception as e:
            raise Exception(f"处理失败: {str(e)}")
    
    def get_image_info(self, file_path):
        """获取图片信息"""
        try:
            with Image.open(file_path) as img:
                return {
                    'format': img.format,
                    'mode': img.mode,
                    'size': img.size,
                    'file_size': os.path.getsize(file_path)
                }
        except Exception as e:
            return {'error': str(e)}