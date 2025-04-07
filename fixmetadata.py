import os
import re
import json
import glob
import argparse
import subprocess
import logging
import sys
from datetime import datetime, timedelta

# ------------------------- 日志配置 -------------------------
def setup_logger():
    """配置双日志系统（主日志+错误日志）"""
    logger = logging.getLogger('GooglePhotoRepair')
    logger.setLevel(logging.DEBUG)

    log_file = f"PhotoRepair_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)-8s] %(message)s')

    # 文件日志（记录所有信息）
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    # 控制台日志（仅关键信息）
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(message)s'))
    console_handler.setLevel(logging.INFO)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger, log_file

# ------------------------- 核心功能 -------------------------
def enhanced_parse_time(json_path):
    """增强版时间解析（兼容所有已知格式）"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        timestamp = None
        
        # 深度搜索时间字段
        time_sources = [
            ('photoTakenTime', 'timestamp'),
            ('creationTime', 'timestamp'),
            ('photoTakenTime', 'formatted'),
            ('creationTime', 'formatted')
        ]
        
        for main_key, sub_key in time_sources:
            if value := data.get(main_key, {}).get(sub_key):
                try:
                    if isinstance(value, (int, float)):
                        timestamp = int(value)
                        break
                    elif isinstance(value, str) and value.isdigit():
                        timestamp = int(value)
                        break
                    else:
                        dt = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                        timestamp = int(dt.timestamp())
                        break
                except (ValueError, TypeError):
                    continue

        if not timestamp:
            logging.warning(f"未找到有效时间源: {json_path}")
            return None
        
        # UTC转北京时间
        beijing_time = datetime.utcfromtimestamp(timestamp) + timedelta(hours=8)
        return beijing_time.strftime("%Y:%m:%d %H:%M:%S")
    
    except Exception as e:
        logging.error(f"时间解析失败 [{json_path}] {type(e).__name__}: {str(e)}")
        return None

def safe_geo_parse(json_path):
    """安全地理坐标解析"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        geo = data.get('geoData', {})
        lat = float(geo.get('latitude', 0.0))
        lon = float(geo.get('longitude', 0.0))
        
        if abs(lat) < 1e-6 and abs(lon) < 1e-6:
            return None
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            logging.warning(f"无效坐标 [{json_path}] lat={lat} lon={lon}")
            return None
        return (lat, lon)
    
    except Exception as e:
        logging.warning(f"地理解析失败 [{json_path}] {type(e).__name__}: {str(e)}")
        return None

def build_geo_params(lat, lon, ext):
    """地理参数生成（自动适配文件类型）"""
    params = []
    params.extend([
        f'-XMP:GPSLatitude={abs(lat)}',
        f'-XMP:GPSLongitude={abs(lon)}'
    ])
    
    if ext.lower() != '.gif':
        params.extend([
            f'-GPSLatitude={abs(lat)}',
            f'-GPSLatitudeRef={"N" if lat >=0 else "S"}',
            f'-GPSLongitude={abs(lon)}',
            f'-GPSLongitudeRef={"E" if lon >=0 else "W"}'
        ])
    return params

def smart_file_matcher(json_name, directory):
    """增强型文件匹配（移除最后两个扩展段）"""
    # 匹配形如：memory.mp4.su.json → memory.mp4
    base_pattern = re.match(
        r'^(.*)\.[^.]+\.[^.]+\.json$',
        json_name,
        re.IGNORECASE
    )
    
    if not base_pattern:
        logging.warning(f"非标准JSON文件名: {json_name}")
        return None

    core_name = base_pattern.group(1)
    valid_exts = {'.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mov', '.heic', '.webp'}
    
    # 三级匹配策略
    patterns = [
        core_name,          # 精确匹配（memory.mp4）
        f"{core_name}.*",    # 扩展名变体（memory.mp4.bak）
        f"{core_name.split('.')[0]}*"  # 前缀匹配（memory*）
    ]
    
    for pattern in patterns:
        escaped = glob.escape(pattern)
        for candidate in glob.glob(os.path.join(directory, escaped)):
            ext = os.path.splitext(candidate)[1].lower()
            if ext in valid_exts and not candidate.lower().endswith('.json'):
                return candidate
    return None

def robust_exiftool_exec(cmd, file_path, logger):
    """带双重修复机制的exiftool执行"""
    error_log = []
    
    def run_command(cmd_args):
        return subprocess.run(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
    
    # 首次尝试（添加-m参数）
    cmd.insert(1, '-m')  # 在exiftool后插入-m参数
    result = run_command(cmd)
    
    if result.returncode == 0:
        logger.info(f"成功更新: {file_path}")
        return True, None
    
    first_error = result.stderr.strip()
    logger.warning(f"首次失败 [{file_path}]\n   错误信息: {first_error}")
    
    try:
        logger.info(f"尝试修复: 清空 {file_path} 的元数据...")
        clean_cmd = ['exiftool', '-m', '-overwrite_original', '-all=', file_path]
        clean_result = run_command(clean_cmd)
        
        if clean_result.returncode != 0:
            error_msg = f"清空元数据失败: {clean_result.stderr.strip()}"
            logger.error(error_msg)
            return False, error_msg
        
        retry_result = run_command(cmd)
        if retry_result.returncode == 0:
            logger.info(f"修复后成功: {file_path}")
            return True, None
        
        error_msg = f"最终失败: {retry_result.stderr.strip()}"
        logger.error(error_msg)
        return False, error_msg
        
    except Exception as e:
        error_msg = f"意外错误: {str(e)}"
        logger.error(error_msg)
        return False, error_msg

# ------------------------- 主流程 -------------------------
def process_directory(root_dir, logger):
    failure_list = []
    processed_count = 0
    
    for root, _, files in os.walk(root_dir):
        for file in files:
            if not file.lower().endswith('.json'):
                continue
            
            json_path = os.path.join(root, file)
            media_file = smart_file_matcher(file, root)
            
            if not media_file:
                logger.warning(f"未找到媒体文件: {json_path}")
                failure_list.append((json_path, "未找到对应媒体文件"))
                continue
            
            time_data = enhanced_parse_time(json_path)
            geo_data = safe_geo_parse(json_path)
            
            if not time_data and not geo_data:
                logger.warning(f"无有效元数据: {json_path}")
                failure_list.append((media_file, "无有效元数据"))
                continue
            
            exif_cmd = ['exiftool', '-overwrite_original', '-charset', 'filename=utf8']
            if time_data:
                exif_cmd.extend([
                    f'-AllDates={time_data}',
                    f'-FileCreateDate={time_data}',
                    f'-FileModifyDate={time_data}'
                ])
            if geo_data:
                file_ext = os.path.splitext(media_file)[1]
                exif_cmd.extend(build_geo_params(*geo_data, file_ext))
            exif_cmd.append(media_file)
            
            success, error = robust_exiftool_exec(exif_cmd, media_file, logger)
            if not success:
                failure_list.append((media_file, error))
            else:
                processed_count += 1
    
    logger.info(f"处理完成，成功更新 {processed_count} 个文件")
    return failure_list

def generate_failure_log(failures, log_path):
    if not failures:
        return
    
    failure_log = os.path.join(os.path.dirname(log_path), 
                              f"FAILURES_{os.path.basename(log_path)}")
    
    with open(failure_log, 'w', encoding='utf-8') as f:
        f.write("失败文件列表：\n")
        f.write("="*50 + "\n")
        for path, reason in failures:
            f.write(f"文件路径: {path}\n")
            f.write(f"失败原因: {reason}\n")
            f.write("-"*50 + "\n")
    
    print(f"\n错误文件日志已生成: {failure_log}")

def main():
    logger, log_path = setup_logger()
    
    parser = argparse.ArgumentParser(
        description='Google相册元数据修复工具（安全跳过版）',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '-d', '--directory',
        required=True,
        help='指定目标目录路径\n示例:\n  -d "D:/Google Photos"\n  -d "./我的照片"'
    )
    
    args = parser.parse_args()
    target_dir = os.path.abspath(args.directory)
    
    if not os.path.isdir(target_dir):
        logger.error(f"无效目录: {target_dir}")
        sys.exit(1)
    
    try:
        logger.info("="*60)
        logger.info(f"开始处理目录: {target_dir}")
        failed_files = process_directory(target_dir, logger)
        logger.info("="*60)
        
        if failed_files:
            generate_failure_log(failed_files, log_path)
            sys.exit(101)
        else:
            logger.info("所有文件处理成功！")
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"未处理的异常: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()
