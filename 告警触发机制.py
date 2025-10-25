# 示例：检查CPU阈值并触发告警
def check_cpu_threshold(host_name, cpu_usage):
    threshold = 85  # 阈值85%
    if cpu_usage > threshold:
        # 写入告警到数据库
        alert = {
            "title": "CPU使用率过高",
            "host": host_name,
            "message": f"当前CPU使用率{cpu_usage:.2f}%，超过阈值{threshold}%",
            "level": "error",
            "time": datetime.now()
        }
        db.alerts.insert_one(alert)  # 假设用MongoDB存储告警
        # 发送企业微信通知（调用机器人API）
        send_wechat_alert(alert)
