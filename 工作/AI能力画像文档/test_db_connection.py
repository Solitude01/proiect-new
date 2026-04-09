"""
数据库连接测试脚本
用于验证数据库连接和表结构
"""

import pymysql
from db_config import get_all_database_configs
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_database_connection(config, region: str):
    """测试单个数据库连接"""
    try:
        connection = pymysql.connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            database=config.database,
            charset='utf8mb4',
            connect_timeout=10
        )

        with connection.cursor() as cursor:
            # 测试查询
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            logger.info(f"✓ {region} 数据库连接成功")

            # 检查表是否存在
            cursor.execute("SHOW TABLES")
            tables = [table[f'Tables_in_{config.database}'] for table in cursor.fetchall()]
            logger.info(f"  现有表: {tables}")

            # 检查ai_projects表结构
            if 'ai_projects' in tables:
                cursor.execute("DESCRIBE ai_projects")
                columns = cursor.fetchall()
                logger.info(f"  ai_projects表结构:")
                for col in columns:
                    logger.info(f"    {col['Field']}: {col['Type']}")

        connection.close()
        return True

    except pymysql.Error as e:
        logger.error(f"✗ {region} 数据库连接失败: {e}")
        return False
    except Exception as e:
        logger.error(f"✗ {region} 数据库测试出错: {e}")
        return False


def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("开始测试数据库连接...")
    logger.info("=" * 50)

    configs = get_all_database_configs()
    results = {}

    for region, config in configs.items():
        logger.info(f"\n测试 {region} 数据库 ({config.host}:{config.port})")
        results[region] = test_database_connection(config, region)

    logger.info("\n" + "=" * 50)
    logger.info("测试结果汇总:")
    for region, success in results.items():
        status = "✓ 成功" if success else "✗ 失败"
        logger.info(f"  {region}: {status}")
    logger.info("=" * 50)

    # 如果所有连接都成功，尝试执行建表脚本
    if all(results.values()):
        logger.info("\n所有数据库连接成功！")
        logger.info("请手动执行 create_tables.sql 脚本创建表结构：")
        logger.info(f"  mysql -h {configs['nantong'].host} -u {configs['nantong'].user} -p{configs['nantong'].password} {configs['nantong'].database} < create_tables.sql")
    else:
        logger.info("\n部分数据库连接失败，请检查网络和配置。")


if __name__ == "__main__":
    main()
