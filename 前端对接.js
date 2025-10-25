// 原代码中生成随机数据的部分，替换为API请求
async function loadHostData() {
    try {
        const response = await fetch('/api/hosts');
        const hosts = await response.json();
        // 更新页面UI
        renderHosts(hosts);
    } catch (error) {
        console.error('加载主机数据失败:', error);
    }
}

// 页面加载时调用
loadHostData();
// 定时刷新（如每30秒）
setInterval(loadHostData, 30000);
