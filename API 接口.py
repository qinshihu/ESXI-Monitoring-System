from fastapi import FastAPI
from pydantic import BaseModel
import influxdb_client

app = FastAPI()

# 连接InfluxDB
client = influxdb_client.InfluxDBClient(
    url="http://localhost:8086",
    token="your_token",
    org="your_org"
)
query_api = client.query_api()

# 定义响应模型
class HostStatus(BaseModel):
    name: str
    cpu_usage: float
    memory_usage: float
    status: str

# 获取主机状态列表
@app.get("/api/hosts", response_model=list[HostStatus])
async def get_hosts():
    # 从InfluxDB查询最新CPU/内存数据
    query = '''
    from(bucket: "esxi_monitor")
      |> range(start: -1m)
      |> filter(fn: (r) => r._measurement == "cpu_usage" or r._measurement == "memory_usage")
      |> last()
    '''
    result = query_api.query(query=query)
    
    # 处理结果并返回（实际需解析InfluxDB响应）
    return [
        {"name": "esxi-01", "cpu_usage": 68.5, "memory_usage": 75.2, "status": "running"},
        {"name": "esxi-02", "cpu_usage": 45.1, "memory_usage": 62.3, "status": "running"}
    ]

# 获取告警列表
@app.get("/api/alerts")
async def get_alerts():
    # 从数据库查询未处理的告警
    return [
        {"id": 1, "title": "CPU使用率过高", "host": "esxi-03", "time": "10分钟前", "level": "error"}
    ]
