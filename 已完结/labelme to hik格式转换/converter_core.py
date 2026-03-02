import json
import os
import glob
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from enum import Enum

class ConversionMode(Enum):
    """转换模式枚举"""
    SINGLE_DETECTION = "single_detection"
    MIXED_ANNOTATION = "mixed_annotation"

class LabelMapping:
    """标签映射管理类"""
    
    def __init__(self):
        self.mappings: Dict[str, Dict[str, str]] = {}  # {label: {detection_name: str, primary: str, secondary: str}}
        self.label_stats: Dict[str, int] = {}  # {label: count}
    
    def add_mapping(self, label: str, detection_name: str, primary: str, secondary: str):
        """添加标签映射关系"""
        self.mappings[label] = {
            "detection_name": detection_name.strip(),
            "primary": primary.strip(),
            "secondary": secondary.strip()
        }
    
    def get_mapping(self, label: str) -> Optional[Dict[str, str]]:
        """获取标签映射关系"""
        return self.mappings.get(label)
    
    def has_mapping(self, label: str) -> bool:
        """检查标签是否有映射关系"""
        return label in self.mappings
    
    def set_label_stats(self, stats: Dict[str, int]):
        """设置标签统计信息"""
        self.label_stats = stats
    
    def get_label_stats(self) -> Dict[str, int]:
        """获取标签统计信息"""
        return self.label_stats
    
    def save_to_file(self, filepath: str):
        """保存映射配置到文件"""
        config_data = {
            "mappings": self.mappings,
            "label_stats": self.label_stats
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
    
    def load_from_file(self, filepath: str) -> bool:
        """从文件加载映射配置"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            self.mappings = config_data.get("mappings", {})
            self.label_stats = config_data.get("label_stats", {})
            return True
        except Exception:
            return False

class LabelmeConverter:
    """Labelme格式转换器"""
    
    def __init__(self):
        self.label_mapping = LabelMapping()
        self.image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']
    
    def scan_labels_from_folder(self, input_folder: str) -> Tuple[List[str], Dict[str, int]]:
        """
        扫描文件夹中所有标签
        
        Args:
            input_folder: 输入文件夹路径
            
        Returns:
            Tuple[List[str], Dict[str, int]]: (唯一标签列表, 标签统计)
        """
        json_files = glob.glob(os.path.join(input_folder, "*.json"))
        all_labels = []
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    labelme_data = json.load(f)
                
                shapes = labelme_data.get('shapes', [])
                for shape in shapes:
                    label = shape.get('label', '').strip()
                    if label:
                        all_labels.append(label)
            except Exception as e:
                print(f"扫描文件 {json_file} 时出错: {str(e)}")
        
        # 统计标签频次
        label_stats = {}
        for label in all_labels:
            label_stats[label] = label_stats.get(label, 0) + 1
        
        # 获取唯一标签列表，按使用频次排序
        unique_labels = sorted(label_stats.keys(), key=lambda x: label_stats[x], reverse=True)
        
        # 更新标签映射管理器
        self.label_mapping.set_label_stats(label_stats)
        
        return unique_labels, label_stats
    
    def set_label_mapping(self, label_mapping: LabelMapping):
        """设置标签映射"""
        self.label_mapping = label_mapping
    
    def _create_mixed_annotation_target(self, label: str, vertices: List[Dict], target_type: int) -> Dict:
        """创建混合标注格式的target对象"""
        # 获取映射关系
        mapping = self.label_mapping.get_mapping(label)
        
        # 确定检测标签名：优先使用用户配置的检测标签名，否则使用原标签名
        detection_name = label  # 默认使用原标签名
        if mapping and mapping.get("detection_name"):
            detection_name = mapping["detection_name"]
        
        target = {
            "value": {
                "TargetType": target_type,
                "Vertex": vertices,
                "PropertyPages": [{
                    "PropertyPageDescript": detection_name
                }]
            }
        }
        
        # 如果有映射关系，添加TagGroups
        if mapping and mapping.get("primary") and mapping.get("secondary"):
            target["value"]["PropertyPages"][0]["TagGroups"] = [{
                "Tags": [{
                    "TagDescript": mapping["primary"],
                    "SubTags": [{
                        "SubTagDescript": mapping["secondary"]
                    }]
                }]
            }]
        
        return target
    
    def _create_single_detection_target(self, label: str, vertices: List[Dict], target_type: int) -> Dict:
        """创建单检测格式的target对象"""
        return {
            "value": {
                "TargetType": target_type,
                "Vertex": vertices,
                "PropertyPages": [{
                    "PropertyPageDescript": label
                }]
            }
        }
    
    def convert_labelme_to_format(self, input_folder: str, output_folder: str, 
                                  mode: ConversionMode = ConversionMode.SINGLE_DETECTION,
                                  progress_callback=None) -> Tuple[bool, str]:
        """
        批量将labelme格式转换为指定格式
        
        Args:
            input_folder: 输入文件夹路径
            output_folder: 输出文件夹路径
            mode: 转换模式
            progress_callback: 进度回调函数
            
        Returns:
            Tuple[bool, str]: (是否成功, 结果消息)
        """
        try:
            # 创建输出文件夹结构
            os.makedirs(output_folder, exist_ok=True)
            result_folder = os.path.join(output_folder, "Result")
            os.makedirs(result_folder, exist_ok=True)
            
            # 获取所有json文件
            json_files = glob.glob(os.path.join(input_folder, "*.json"))
            
            if not json_files:
                return False, "输入文件夹中没有找到JSON文件"
            
            if progress_callback:
                progress_callback(f"找到 {len(json_files)} 个标注文件")
            
            # 存储所有转换后的标注数据
            all_frame_infos = []
            processed_count = 0
            
            for json_file in json_files:
                try:
                    # 读取labelme格式的json文件
                    with open(json_file, 'r', encoding='utf-8') as f:
                        labelme_data = json.load(f)
                    
                    # 提取图片信息
                    image_path = labelme_data.get('imagePath', '')
                    image_width = labelme_data.get('imageWidth', 0)
                    image_height = labelme_data.get('imageHeight', 0)
                    shapes = labelme_data.get('shapes', [])
                    
                    # 查找对应的图片文件
                    image_found = False
                    json_basename = Path(json_file).stem
                    
                    # 首先尝试使用labelme中记录的图片路径
                    if image_path:
                        full_image_path = os.path.join(input_folder, image_path)
                        if os.path.exists(full_image_path):
                            image_found = True
                            source_image_path = full_image_path
                            final_image_name = image_path
                    
                    # 如果没找到，尝试根据json文件名查找同名图片
                    if not image_found:
                        for ext in self.image_extensions:
                            potential_image_path = os.path.join(input_folder, json_basename + ext)
                            if os.path.exists(potential_image_path):
                                image_found = True
                                source_image_path = potential_image_path
                                final_image_name = json_basename + ext
                                break
                    
                    if not image_found:
                        if progress_callback:
                            progress_callback(f"警告: 未找到与 {json_basename} 对应的图片文件")
                        continue
                    
                    # 复制图片到输出文件夹
                    dest_image_path = os.path.join(output_folder, final_image_name)
                    try:
                        shutil.copy2(source_image_path, dest_image_path)
                        if progress_callback:
                            progress_callback(f"✓ 复制图片: {final_image_name}")
                    except Exception as e:
                        if progress_callback:
                            progress_callback(f"✗ 复制图片失败 {final_image_name}: {str(e)}")
                        continue
                    
                    # 构建目标格式的数据结构
                    targets = []
                    
                    for shape in shapes:
                        label = shape.get('label', '')
                        points = shape.get('points', [])
                        shape_type = shape.get('shape_type', '')
                        
                        if not points or not label:
                            continue
                        
                        # 确定目标类型
                        target_type = 1 if shape_type == 'rectangle' else 3  # 1-矩形，3-四边形
                        
                        # 转换坐标为归一化坐标
                        vertices = []
                        
                        if shape_type == 'rectangle' and len(points) == 2:
                            # 矩形：从两个点构建四个顶点
                            x1, y1 = points[0]
                            x2, y2 = points[1]
                            
                            # 确保坐标顺序正确（左上、右上、右下、左下）
                            min_x, max_x = min(x1, x2), max(x1, x2)
                            min_y, max_y = min(y1, y2), max(y1, y2)
                            
                            vertices = [
                                {"fX": min_x / image_width, "fY": min_y / image_height},  # 左上
                                {"fX": max_x / image_width, "fY": min_y / image_height},  # 右上
                                {"fX": max_x / image_width, "fY": max_y / image_height},  # 右下
                                {"fX": min_x / image_width, "fY": max_y / image_height}   # 左下
                            ]
                        elif shape_type == 'polygon' and len(points) >= 3:
                            # 多边形：直接使用给定的点
                            for point in points:
                                vertices.append({
                                    "fX": point[0] / image_width,
                                    "fY": point[1] / image_height
                                })
                            
                            # 如果是四边形，设置target_type为3
                            if len(points) == 4:
                                target_type = 3
                        else:
                            if progress_callback:
                                progress_callback(f"警告: 不支持的形状类型 '{shape_type}' 或点数不正确: {len(points)}")
                            continue
                        
                        # 根据模式创建target对象
                        if mode == ConversionMode.MIXED_ANNOTATION:
                            target = self._create_mixed_annotation_target(label, vertices, target_type)
                        else:
                            target = self._create_single_detection_target(label, vertices, target_type)
                        
                        targets.append(target)
                    
                    # 构建frame info对象
                    frame_info = {
                        "value": {
                            "FrameNum": final_image_name,
                            "mapTargets": targets
                        }
                    }
                    
                    all_frame_infos.append(frame_info)
                    processed_count += 1
                    
                    if progress_callback:
                        progress_callback(f"✓ 处理完成: {json_basename} ({processed_count}/{len(json_files)})")
                
                except Exception as e:
                    if progress_callback:
                        progress_callback(f"✗ 处理失败 {json_file}: {str(e)}")
            
            # 构建最终的输出格式
            if all_frame_infos:
                final_output_data = {
                    "calibInfo": {
                        "VideoChannels": [{
                            "VideoInfo": {
                                "mapFrameInfos": all_frame_infos
                            }
                        }]
                    }
                }
                
                # 根据模式确定输出文件名
                if mode == ConversionMode.MIXED_ANNOTATION:
                    output_filename = "mixed_annotations.json"
                else:
                    output_filename = "merged_annotations.json"
                
                output_json_path = os.path.join(result_folder, output_filename)
                
                with open(output_json_path, 'w', encoding='utf-8') as f:
                    json.dump(final_output_data, f, ensure_ascii=False, indent=2)
                
                success_msg = f"✓ 转换完成！处理了 {len(all_frame_infos)} 个图片的标注\n"
                success_msg += f"✓ 结果保存至: {output_json_path}"
                
                if progress_callback:
                    progress_callback(success_msg)
                
                return True, success_msg
            else:
                error_msg = "✗ 没有成功处理任何标注文件"
                if progress_callback:
                    progress_callback(error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"转换过程中发生错误: {str(e)}"
            if progress_callback:
                progress_callback(error_msg)
            return False, error_msg 