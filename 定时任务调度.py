from apscheduler.schedulers.background import BackgroundScheduler

# 每30秒采集一次主机数据
def collect_host_data():
    hosts = ["esxi-01", "esxi-02", "esxi-03"]
    for host in hosts:
        data = get_host_metrics(host)  # 采集数据
        save_to_influxdb(data)  # 存入数据库

# 启动定时任务
scheduler = BackgroundScheduler()
scheduler.add_job(collect_host_data, 'interval', seconds=30)
scheduler.start()
