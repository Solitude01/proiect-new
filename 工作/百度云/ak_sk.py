#导入相关依赖包
from tritonv2.client_factory import TritonClientFactory
from tritonv2.constants import LimiterConfig, RequestRateDuration
import json
import cv2
import numpy as np
#医疗产品线
server_uri = "10.20.7.165:8412/ep-abgtrkwz/http"

def extract_prediction_fields(predictions):
    """
    从Prediction对象列表中提取指定字段，组成新的字典列表
    
    参数:
        predictions: 包含Prediction对象的列表
        
    返回:
        提取后的字典列表，每个字典包含bbox、confidence、segmentation、categories字段
    """
    # 遍历每个Prediction对象，提取需要的字段
    extracted = [
        {
            "bbox": pred.bbox,
            "confidence": pred.confidence,
            "segmentation": pred.segmentation,
            "categories": pred.categories  # 若需要进一步处理Category对象，可在此处添加逻辑
        }
        for pred in predictions
    ]
    return extracted


def draw_predictions_on_image(image_path, predictions, output_path):
    """
    在图像上绘制预测框、置信度和类别名称，并保存
    
    参数:
        image_path: 原始图像路径
        predictions: 包含Prediction对象的列表
        output_path: 处理后图像的保存路径
    """
    #print('开始读取图像11111111111111111111111111')
    # 读取图像（OpenCV默认读取为BGR格式）
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"无法读取图像: {image_path}")

    # 遍历每个预测结果
    for pred in predictions:
        # 1. 提取需要的信息
        #print('打印出pred的相关信息')
        #print(pred)
        bbox = pred['bbox']  # 格式：[x1, y1, x2, y2]（可能为浮点数）
        confidence = pred['confidence']  # 置信度
        #print('打印置信度的类型')
        #print(type(confidence))
        if confidence < 0.3:
            continue
            print(bbox)
        # 提取类别名称（假设categories列表中至少有一个元素）
        #print('开始打印category的相关数据')
        category_name = pred['categories'][0].name if pred['categories'] else "Unknown"

        # 2. 处理边界框坐标（转换为整数，OpenCV绘制需要整数坐标）
        x1, y1, x2, y2 = map(int, bbox)
        # 确保坐标在图像范围内（避免越界）
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(image.shape[1], x2)
        y2 = min(image.shape[0], y2)

        # 3. 绘制边界框（红色，线宽2）
        cv2.rectangle(
            img=image,
            pt1=(x1, y1),
            pt2=(x2, y2),
            color=(0, 0, 255),  # BGR格式，(0,0,255)为红色
            thickness=2
        )

        # 4. 准备标注文本（类别名称 + 置信度）
        label = f"{category_name}: {confidence:.2f}"  # 保留两位小数
        # 文本位置（框的左上角上方，避免超出图像顶部）
        text_x = x1
        text_y = y1 - 10 if y1 > 10 else y1 + 20

        # 绘制文本背景（黑色矩形，增强可读性）
        (text_width, text_height), _ = cv2.getTextSize(
            text=label,
            fontFace=cv2.FONT_HERSHEY_SIMPLEX,
            fontScale=0.5,
            thickness=1
        )
        cv2.rectangle(
            img=image,
            pt1=(text_x, text_y - text_height - 5),
            pt2=(text_x + text_width + 5, text_y + 5),
            color=(0, 0, 0),  # 黑色背景
            thickness=-1  # 填充矩形
        )

        # 绘制文本（白色）
        cv2.putText(
            img=image,
            text=label,
            org=(text_x, text_y),
            fontFace=cv2.FONT_HERSHEY_SIMPLEX,
            fontScale=0.5,
            color=(255, 255, 255),  # 白色文本
            thickness=1,
            lineType=cv2.LINE_AA
        )

    # 5. 保存处理后的图像
    cv2.imwrite(output_path, image)
    print(f"处理后的图像已保存至: {output_path}")

#空箱检测
server_uri = "10.20.7.165:8412/ep-raxhuzcd/http"

#10.10.99.159:8412/ep-uwxhgjaw/http
triton_client = TritonClientFactory.create_http_client(
server_url=server_uri,
limiter_config=LimiterConfig(limit=1, interval=RequestRateDuration.SECOND, delay=True),)

# 导入相关依赖包
from windmillendpointv1.client.gaea.api   import ModelInferRequest, ModelMetaData, InferConfig
from windmillendpointv1.client.gaea.infer import infer
with open(r"/data/projects/Test/NotEmpty0617.jpg", "rb") as f:
    image_buffer = f.read()
meta_json = {"image_id": "00001", "camera_id": "00002"}
model_req = ModelMetaData(**meta_json)
model_request = ModelInferRequest(meta=model_req, image_buffer=image_buffer, model_name="ensemble", infer_config=InferConfig())

try :
    result = infer(triton_client, req=model_request)
    print('-----------------------结果为--------------------')
    print(result)
    for i in range(len(result)):
        predictions = extract_prediction_fields(result[i].predictions)
        print(predictions)
        #调用函数（替换为你的图像路径和输出路径）
        draw_predictions_on_image(image_path="/data/projects/Test/NotEmpty0617.jpg",
                                  predictions=predictions,
                                  output_path="/data/projects/Test/NotEmpty0617.jpg")
except Exception as e:
    print(e)
