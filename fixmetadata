import os
import re
import json
import glob
import argparse
import subprocess
import logging
import sys
import ctypes
import traceback
import time
from datetime import datetime, timedelta, timezone

# ------------------------- 系统权限检测 -------------------------
def check_admin_privileges():
    """检测是否以管理员权限运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

# ------------------------- 增强型日志系统 -------------------------
class EnhancedLogger:
    def __init__(self):
        self.logger = logging.getLogger('MetaRepair')
        self.logger.setLevel(logging.DEBUG)
        self.log_file = f"RepairLog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        # Windows控制台编码修复
        if sys.stdout.encoding != 'UTF-8':
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')

        # 文件日志格式
        file_formatter = logging.Formatter(
            '[%(asctime)s.%(msecs)03d] [%(levelname)-8s] [%(filename)s:%(lineno)d] %(message)s',
            datefmt='%Y%m%d %H:%M:%S'
        )
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8-sig')
        file_handler.setFormatter(file_formatter)

        # 控制台日志格式
        console_formatter = logging.Formatter('[%(levelname)s] %(message)s')
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

        # 记录环境信息
        self.logger.info(f"System Platform: {sys.platform}")
        self.logger.info(f"Python Version: {sys.version.split()[0]}")
        self.logger.info(f"Admin Privileges: {check_admin_privileges()}")

# ------------------------- 元数据处理器 -------------------------
class MetadataProcessor:
    def __init__(self, logger):
        self.logger = logger
        self.video_tags = {
            '.mp4': ['-QuickTime:CreateDate', '-QuickTime:ModifyDate'],
            '.mov': ['-QuickTime:CreateDate', '-QuickTime:ModifyDate'],
            '.avi': ['-RIFF:DateTimeOriginal'],
            '.wmv': ['-FileCreateDate', '-FileModifyDate']
        }

    def parse_timestamp(self, json_data):
        """深度解析时间信息"""
        time_fields = [
            ('photoTakenTime', 'timestamp'),
            ('creationTime', 'timestamp'),
            ('creationTime', 'formatted'),
            ('modificationTime', 'formatted')
        ]
        
        for main_key, sub_key in time_fields:
            if main_key in json_data and sub_key in json_data[main_key]:
                value = json_data[main_key][sub_key]
                try:
                    if isinstance(value, (int, float)):
                        return int(value)
                    elif value.isdigit():
                        return int(value)
                    else:
                        for fmt in ["%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"]:
                            try:
                                dt = datetime.strptime(value, fmt)
                                return int(dt.replace(tzinfo=timezone.utc).timestamp())
                            except ValueError:
                                continue
                except Exception as e:
                    self.logger.debug(f"时间解析尝试失败: {main_key}.{sub_key} - {str(e)}")
        return None

    def build_time_params(self, file_path, time_str):
        """生成时间参数"""
        ext = os.path.splitext(file_path)[1].lower()
        params = []
        
        # 视频文件特殊处理
        if ext in self.video_tags:
            params.extend([f'{tag}="{time_str}"' for tag in self.video_tags[ext]])
        # 图片文件通用参数
        else:
            params.extend([
                f'-EXIF:DateTimeOriginal="{time_str}"',
                f'-XMP:DateCreated="{time_str}"'
            ])
        
        # 文件系统时间
        params.extend([
            f'-FileCreateDate="{time_str}"',
            f'-FileModifyDate="{time_str}"'
        ])
        return params

# ------------------------- 文件处理器 -------------------------
class FileProcessor:
    def __init__(self, logger):
        self.logger = logger
        
    def match_media_file(self, json_path):
        """增强型文件匹配逻辑"""
        json_name = os.path.basename(json_path)
        directory = os.path.dirname(json_path)
        
        # 正则匹配核心文件名
        pattern = re.compile(
            r'^(.+?)(\.[a-zA-Z0-9]+?)'  # 基础文件名和主扩展名
            r'(\.supp(?:lement)?[^.]*)?\.json$',  # 补充元数据后缀
            re.IGNORECASE
        )
        match = pattern.match(json_name)
        if not match:
            self.logger.warning(f"文件名格式异常: {json_name}")
            return None
            
        base_name = match.group(1) + match.group(2)  # 保留主扩展名
        valid_exts = {'.jpg', '.jpeg', '.png', '.gif', 
                     '.mp4', '.mov', '.heic', '.webp'}
        
        # 三重匹配策略
        for pattern in [
            base_name,                  # 精确匹配
            f"{base_name}.*",           # 扩展名变体
            f"{base_name.split('.')[0]}*"  # 前缀匹配
        ]:
            escaped = glob.escape(pattern)
            candidates = glob.glob(os.path.join(directory, escaped))
            for candidate in candidates:
                ext = os.path.splitext(candidate)[1].lower()
                if ext in valid_exts and not candidate.lower().endswith('.json'):
                    self.logger.debug(f"匹配成功: {candidate}")
                    return os.path.normpath(candidate)
        
        self.logger.warning(f"未找到媒体文件: {json_path}")
        return None

# ------------------------- EXIF执行器 -------------------------
class ExifToolExecutor:
    def __init__(self, logger):
        self.logger = logger
        
    def execute_command(self, cmd_args, file_path):
        """带错误抑制的命令执行"""
        try:
            result = subprocess.run(
                cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding='utf-8',
                errors='replace',
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            self._filter_log(result, file_path)
            
            if result.returncode == 0:
                return True
            elif "File in use" in result.stderr:
                return self._retry_command(cmd_args, file_path)
            return False
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"执行超时: {file_path}")
            return False
            
    def _filter_log(self, result, file_path):
        """过滤次要警告日志"""
        filtered_stderr = '\n'.join(
            line for line in result.stderr.split('\n')
            if 'minor' not in line.lower()
        )
        
        if result.stdout.strip() or filtered_stderr:
            log_msg = f"""
            [EXIF输出] {file_path}
            状态码: {result.returncode}
            输出: {result.stdout.strip()}
            错误: {filtered_stderr}
            """
            self.logger.debug(log_msg)
            
    def _retry_command(self, cmd_args, file_path, max_retries=3):
        """文件锁定重试逻辑"""
        for attempt in range(max_retries):
            try:
                time.sleep(2 ** attempt)
                subprocess.run(cmd_args, check=True)
                self.logger.info(f"重试成功: {file_path}")
                return True
            except Exception as e:
                self.logger.warning(f"重试失败 ({attempt+1}/{max_retries}): {str(e)}")
        return False

# ------------------------- 主流程 -------------------------
def main_process(root_dir, logger):
    processor = MetadataProcessor(logger)
    file_matcher = FileProcessor(logger)
    exif_tool = ExifToolExecutor(logger)
    
    failures = []
    success_count = 0
    
    for root, _, files in os.walk(root_dir):
        for file in files:
            if not file.lower().endswith('.json'):
                continue
            
            json_path = os.path.join(root, file)
            media_file = file_matcher.match_media_file(json_path)
            if not media_file:
                failures.append((json_path, "未匹配到媒体文件"))
                continue
                
            try:
                with open(json_path, 'r', encoding='utf-8-sig') as f:
                    json_data = json.load(f)
                
                timestamp = processor.parse_timestamp(json_data)
                if not timestamp:
                    failures.append((media_file, "无有效时间数据"))
                    continue
                
                # 转换为北京时间
                utc_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                beijing_time = utc_time.astimezone(timezone(timedelta(hours=8)))
                time_str = beijing_time.strftime("%Y:%m:%d %H:%M:%S%z")
                
                # 构建命令（包含 -m 参数）
                cmd = [
                    'exiftool', '-m',
                    '-overwrite_original',
                    '-charset', 'filename=utf8'
                ]
                cmd.extend(processor.build_time_params(media_file, time_str))
                cmd.append(media_file)
                
                if exif_tool.execute_command(cmd, media_file):
                    success_count += 1
                else:
                    failures.append((media_file, "EXIF命令执行失败"))
                    
            except Exception as e:
                logger.error(f"处理异常: {str(e)}")
                failures.append((media_file, f"未处理异常: {str(e)}"))
    
    logger.info(f"处理完成: 成功 {success_count} 个, 失败 {len(failures)} 个")
    return failures

if __name__ == '__main__':
    log_handler = EnhancedLogger()
    logger = log_handler.logger
    
    if not check_admin_privileges():
        logger.warning("建议使用管理员权限运行以获得完整功能")
    
    parser = argparse.ArgumentParser(description='媒体元数据修复工具')
    parser.add_argument('-d', '--directory', required=True, help='目标目录路径')
    args = parser.parse_args()
    
    if not os.path.isdir(args.directory):
        logger.error(f"无效目录: {args.directory}")
        sys.exit(1)
        
    try:
        failures = main_process(os.path.abspath(args.directory), logger)
        if failures:
            error_log = log_handler.log_file.replace('.log', '_ERRORS.log')
            with open(error_log, 'w', encoding='utf-8') as f:
                json.dump(failures, f, indent=2, ensure_ascii=False)
            logger.error(f"错误日志已生成: {error_log}")
            sys.exit(101)
        sys.exit(0)
    except Exception:
        logger.critical(f"致命错误:\n{traceback.format_exc()}")
        sys.exit(1)
