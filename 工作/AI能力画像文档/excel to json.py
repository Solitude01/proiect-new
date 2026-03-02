import pandas as pd
import json

def excel_to_json(excel_path, output_json_path=None):
    """
    将Excel文件的A-J列转换为JSON格式
    """
    # 读取Excel文件，只读取A-J列
    df = pd.read_excel(
        excel_path,
        usecols='C:L',  # 读取A到J列（共10列）
        engine='openpyxl'
    )
    
    # Excel中的实际列名（10列）       
       # '结余时间（小时/月）',  '收益（万元/年）',
    expected_columns = [
        '项目名称',
        '工厂名称',
        '项目目标',
        '收益描述',
        'OK图片描述',
        'NG图片描述',
        '应用场景简述',
        '处理对象(输入)',
        '核心功能',
        '输出形式/接口'
    ]
    
    # 确保列名正确
    if len(df.columns) == len(expected_columns):
        df.columns = expected_columns
    
    # 将DataFrame转换为字典列表
    data = df.to_dict(orient='records')
    
    # 如果指定了输出路径，保存为JSON文件
    if output_json_path:
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✓ JSON文件已保存到: {output_json_path}")
        print(f"✓ 总共转换了 {len(data)} 条记录")
    
    return data


if __name__ == "__main__":
    # Excel文件路径
    excel_file = r"D:\proiect\工作\AI能力画像文档\2025-12-1最新数据-上传.xlsx"
    
    # 输出JSON文件路径
    json_file = r"D:\proiect\工作\AI能力画像文档\2025-12-1最新数据-上传-无收益.json"
    
    try:
        result = excel_to_json(excel_file, json_file)
        
        # 显示一条完整记录作为示例
        print("\n示例记录:")
        print("-" * 50)
        for key, value in result[0].items():
            print(f"{key}: {value}")
        
    except Exception as e:
        print(f"❌ 错误: {str(e)}")