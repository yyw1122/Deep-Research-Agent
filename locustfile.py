"""压力测试脚本 - 使用 Locust"""
import random
from locust import HttpUser, task, between
import json


class ResearchUser(HttpUser):
    """研究任务用户"""
    wait_time = between(1, 3)

    def on_start(self):
        """初始化"""
        # 创建研究任务
        self.task_id = None
        topics = [
            "人工智能发展趋势",
            "新能源汽车市场分析",
            "碳中和实现路径",
            "量子计算技术",
            "5G应用场景"
        ]
        query = random.choice(topics)

        response = self.client.post(
            "/api/research",
            json={"query": query, "enable_llm": True},
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            data = response.json()
            self.task_id = data.get("task_id")

    @task(3)
    def create_task(self):
        """创建新任务"""
        topics = [
            "区块链技术",
            "云计算发展",
            "大数据应用",
            "物联网安全",
            "虚拟现实"
        ]
        query = random.choice(topics)

        with self.client.post(
            "/api/research",
            json={"query": query, "enable_llm": True},
            headers={"Content-Type": "application/json"},
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                self.task_id = data.get("task_id")
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task(2)
    def check_status(self):
        """检查任务状态"""
        if self.task_id:
            with self.client.get(
                f"/api/research/{self.task_id}",
                catch_response=True
            ) as response:
                if response.status_code == 200:
                    response.success()
                else:
                    response.failure(f"Status check failed: {response.status_code}")

    @task(1)
    def health_check(self):
        """健康检查"""
        self.client.get("/health")

    @task(1)
    def get_stats(self):
        """获取统计"""
        self.client.get("/api/stats")


class StressUser(HttpUser):
    """压力测试用户 - 高并发"""
    wait_time = between(0.1, 0.5)

    @task(10)
    def rapid_requests(self):
        """快速请求"""
        topics = [
            "AI技术",
            "新能源",
            "碳中和",
            "量子计算",
            "自动驾驶"
        ]
        query = random.choice(topics)

        self.client.post(
            "/api/research",
            json={"query": query, "enable_llm": False},
            headers={"Content-Type": "application/json"}
        )


# 运行方式:
# locust -f locustfile.py --host=http://localhost:8000
# 或
# locust -f locustfile.py --host=http://localhost:8000 --headless -u 100 -r 10 -t 60s
