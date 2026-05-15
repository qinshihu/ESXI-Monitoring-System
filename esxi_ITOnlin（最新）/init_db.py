#!/usr/bin/env python3
"""
数据库初始化脚本
用于创建MySQL表结构和InfluxDB bucket
"""
import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, text
from influxdb_client import InfluxDBClient, Bucket, Organization
from sqlalchemy.orm import sessionmaker

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入配置和模型
from config import settings
from database import ESXIHost, VirtualMachine, Alert, Base

def init_mysql():
    """初始化数据库（支持SQLite和MySQL）"""
    db_type = "SQLite" if settings.DATABASE_URL.startswith('sqlite') else "MySQL"
    print(f"初始化{db_type}数据库...")
    
    # 创建数据库引擎
    connect_args = {}
    if settings.DATABASE_URL.startswith('sqlite'):
        connect_args = {'check_same_thread': False}
    
    engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
    
    try:
        # 检查数据库连接
        with engine.connect() as conn:
            if settings.DATABASE_URL.startswith('sqlite'):
                # SQLite不需要特殊查询
                pass
            else:
                conn.execute(text("SELECT 1"))
        print(f"{db_type}连接成功")
        
        # 创建所有表
        Base.metadata.create_all(bind=engine)
        print(f"{db_type}表结构创建成功")
        
        # 初始化示例ESXI主机数据
        Session = sessionmaker(bind=engine)
        with Session() as session:
            # 检查是否已有主机数据
            existing_hosts = session.query(ESXIHost).count()
            if existing_hosts == 0:
                # 从环境变量解析ESXI主机列表
                try:
                    # 安全检查：确保settings有esxi_hosts_list属性
                    if hasattr(settings, 'esxi_hosts_list') and settings.esxi_hosts_list:
                        for host_info in settings.esxi_hosts_list:
                            # 安全检查：确保host_info有必要的键
                            if all(k in host_info for k in ['name', 'ip', 'username', 'password']):
                                # 检查数据库模型字段名称
                                host_data = {
                                    'name': host_info['name'],
                                    'ip_address': host_info.get('ip', host_info.get('ip_address')),
                                    'username': host_info['username'],
                                    'password': host_info['password'],
                                    'status': 'offline'
                                }
                                host = ESXIHost(**host_data)
                                session.add(host)
                        
                        session.commit()
                        print(f"初始化了 {len(settings.esxi_hosts_list)} 个ESXI主机")
                    else:
                        print("⚠️ 未找到ESXI主机配置，跳过主机数据初始化")
                except Exception as e:
                    print(f"⚠️ 初始化ESXI主机数据失败，但将继续: {str(e)}")
                    # 回滚事务但不中断程序
                    session.rollback()
            else:
                print(f"已存在 {existing_hosts} 个ESXI主机，跳过初始化")
                
    except Exception as e:
        print(f"{db_type}初始化失败: {str(e)}")
        raise

def init_influxdb():
    """初始化InfluxDB"""
    print("初始化InfluxDB...")
    
    # 创建InfluxDB客户端
    client = InfluxDBClient(
        url=settings.INFLUXDB_URL,
        token=settings.INFLUXDB_TOKEN,
        org=settings.INFLUXDB_ORG
    )
    
    try:
        # 检查连接
        health = client.health()
        if health.status != 'pass':
            raise Exception(f"InfluxDB健康检查失败: {health.status}")
        print("InfluxDB连接成功")
        
        # 获取组织ID
        orgs_api = client.organizations_api()
        orgs = orgs_api.find_organizations(org=settings.INFLUXDB_ORG)
        if not orgs:
            # 创建组织
            org = orgs_api.create_organization(Organization(name=settings.INFLUXDB_ORG))
            org_id = org.id
            print(f"创建InfluxDB组织: {settings.INFLUXDB_ORG}")
        else:
            org_id = orgs[0].id
            print(f"使用现有InfluxDB组织: {settings.INFLUXDB_ORG}")
        
        # 检查bucket是否存在
        buckets_api = client.buckets_api()
        buckets = buckets_api.find_buckets(bucket=settings.INFLUXDB_BUCKET)
        
        if not buckets or not any(b.name == settings.INFLUXDB_BUCKET for b in buckets.buckets):
            # 创建bucket
            bucket = buckets_api.create_bucket(
                bucket_name=settings.INFLUXDB_BUCKET,
                org_id=org_id
            )
            print(f"创建InfluxDB bucket: {settings.INFLUXDB_BUCKET}")
        else:
            print(f"使用现有InfluxDB bucket: {settings.INFLUXDB_BUCKET}")
            
        # 测试写入示例数据
        write_api = client.write_api()
        from influxdb_client.client.write_api import SYNCHRONOUS
        
        # 写入示例CPU使用率数据
        write_api.write(
            bucket=settings.INFLUXDB_BUCKET,
            org=settings.INFLUXDB_ORG,
            record=[
                {
                    "measurement": "cpu_usage",
                    "tags": {"host": "esxi-01", "type": "host"},
                    "time": datetime.utcnow().isoformat(),
                    "fields": {"value": 0.0}
                }
            ],
            write_precision="s",
            write_mode=SYNCHRONOUS
        )
        print("InfluxDB写入测试成功")
        
    except Exception as e:
        print(f"InfluxDB初始化失败: {str(e)}")
        raise
    finally:
        # 关闭客户端
        client.close()

def check_redis():
    """检查Redis连接"""
    print("检查Redis连接...")
    
    import redis
    
    try:
        # 创建Redis客户端
        redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True
        )
        
        # 测试连接
        redis_client.ping()
        print("Redis连接成功")
        
        # 设置示例键
        redis_client.setex("monitoring:init_test", 3600, "success")
        print("Redis写入测试成功")
        
    except Exception as e:
        print(f"Redis连接失败: {str(e)}")
        raise
    finally:
        # 关闭连接
        if 'redis_client' in locals():
            redis_client.close()

def main():
    """主函数"""
    print(f"开始数据库初始化 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 初始化数据库（支持SQLite和MySQL）
        init_mysql()
        
        # 只有在启用时才初始化InfluxDB
        if hasattr(settings, 'INFLUXDB_ENABLED') and settings.INFLUXDB_ENABLED:
            try:
                init_influxdb()
            except Exception as e:
                print(f"⚠️ InfluxDB初始化失败，但将继续: {str(e)}")
        else:
            print("⚠️ InfluxDB未启用，跳过初始化")
        
        # 只有在启用时才检查Redis
        if hasattr(settings, 'REDIS_ENABLED') and settings.REDIS_ENABLED:
            try:
                check_redis()
            except Exception as e:
                print(f"⚠️ Redis连接失败，但将继续: {str(e)}")
        else:
            print("⚠️ Redis未启用，跳过检查")
        
        print("\n✅ 数据库初始化成功！")
        print("\n接下来可以启动应用程序了:")
        print("  python main.py")
        
    except Exception as e:
        print(f"\n❌ 数据库初始化失败: {str(e)}")
        print("\n请检查以下内容:")
        print("  1. 确保数据库服务正在运行")
        if hasattr(settings, 'INFLUXDB_ENABLED') and settings.INFLUXDB_ENABLED:
            print("  2. 确保InfluxDB服务正在运行")
        if hasattr(settings, 'REDIS_ENABLED') and settings.REDIS_ENABLED:
            print("  3. 确保Redis服务正在运行")
        print("  4. 检查.env文件中的配置是否正确")
        sys.exit(1)

if __name__ == "__main__":
    main()