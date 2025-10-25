# 安装PyVmomi
# pip install pyvmomi

from pyVim.connect import SmartConnectNoSSL, Disconnect
import ssl

# 忽略SSL证书验证（生产环境建议配置证书）
ssl_context = ssl._create_unverified_context()

# 连接ESXI主机或vCenter
def connect_to_esxi(host, user, pwd):
    try:
        conn = SmartConnectNoSSL(
            host=host,
            user=user,
            pwd=pwd,
            sslContext=ssl_context
        )
        return conn
    except Exception as e:
        print(f"连接失败: {e}")
        return None

# 获取主机CPU使用率
def get_host_cpu_usage(host_system):
    cpu_usage = host_system.summary.quickStats.overallCpuUsage
    cpu_total = host_system.hardware.cpuInfo.hz * host_system.hardware.cpuInfo.numCpuCores
    return (cpu_usage / (cpu_total / 1024)) * 100  # 转换为百分比

# 示例：采集esxi-01的数据
conn = connect_to_esxi("esxi-01.example.com", "root", "your_password")
if conn:
    content = conn.RetrieveContent()
    host = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.HostSystem], True
    ).view[0]
    cpu_usage = get_host_cpu_usage(host)
    print(f"CPU使用率: {cpu_usage:.2f}%")
    Disconnect(conn)
