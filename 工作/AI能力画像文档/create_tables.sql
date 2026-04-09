-- AI能力画像数据库建表脚本
-- 适用于南通和无锡两个MySQL实例

-- 使用数据库
USE ai_project_data;

-- 项目主表
CREATE TABLE IF NOT EXISTS ai_projects (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
    project_name VARCHAR(255) NOT NULL COMMENT '项目名称',
    factory_name VARCHAR(100) COMMENT '工厂名称',
    project_goal TEXT COMMENT '项目目标',
    benefit_desc TEXT COMMENT '收益描述',
    ok_image_desc TEXT COMMENT 'OK图片描述',
    ng_image_desc TEXT COMMENT 'NG图片描述',
    application_scenario TEXT COMMENT '应用场景简述',
    processing_object TEXT COMMENT '处理对象(输入)',
    core_functions JSON COMMENT '核心功能',
    output_interface TEXT COMMENT '输出形式/接口',
    deployment_method TEXT COMMENT '部署方式',
    sync_status ENUM('pending','synced','failed') DEFAULT 'pending' COMMENT '同步状态',
    source_region VARCHAR(50) DEFAULT 'nantong' COMMENT '数据来源区域',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_project_name (project_name),
    INDEX idx_factory (factory_name),
    INDEX idx_sync_status (sync_status),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI项目数据表';

-- 同步任务表
CREATE TABLE IF NOT EXISTS sync_tasks (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '任务ID',
    task_type ENUM('excel_import','ai_analyze','db_sync','export_excel') NOT NULL COMMENT '任务类型',
    status ENUM('pending','running','completed','failed') DEFAULT 'pending' COMMENT '任务状态',
    total_count INT DEFAULT 0 COMMENT '总数量',
    processed_count INT DEFAULT 0 COMMENT '已处理数量',
    error_message TEXT COMMENT '错误信息',
    source_file VARCHAR(500) COMMENT '源文件路径',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    completed_at TIMESTAMP NULL COMMENT '完成时间',
    INDEX idx_status (status),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='同步任务表';

-- 同步日志表
CREATE TABLE IF NOT EXISTS sync_logs (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '日志ID',
    task_id INT COMMENT '关联的sync_tasks.id',
    log_level ENUM('info','warning','error') DEFAULT 'info' COMMENT '日志级别',
    message TEXT COMMENT '日志消息',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_task (task_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='同步日志表';

-- 工厂信息表（用于筛选）
CREATE TABLE IF NOT EXISTS factories (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '工厂ID',
    factory_code VARCHAR(50) UNIQUE NOT NULL COMMENT '工厂编码',
    factory_name VARCHAR(100) NOT NULL COMMENT '工厂名称',
    region VARCHAR(50) COMMENT '所属区域',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否启用',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_code (factory_code),
    INDEX idx_name (factory_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='工厂信息表';

-- 插入示例工厂数据
INSERT IGNORE INTO factories (factory_code, factory_name, region) VALUES
('NT001', '南通工厂A', '南通'),
('NT002', '南通工厂B', '南通'),
('WX001', '无锡工厂A', '无锡'),
('WX002', '无锡工厂B', '无锡');
