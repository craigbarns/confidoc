"""ConfiDoc Backend — Load Testing Script.

Usage:
    pip install locust
    locust -f scripts/locustfile.py --host=http://localhost:8000
"""

import os

from locust import HttpUser, between, task


class ConfiDocUser(HttpUser):
    wait_time = between(1, 5)

    def on_start(self):
        """Authentification avant le test de charge."""
        self.email = os.getenv("LOCUST_USER_EMAIL", "admin@confidoc.local")
        self.password = os.getenv("LOCUST_USER_PASSWORD", "Admin123!")

        response = self.client.post(
            "/api/v1/auth/login", json={"email": self.email, "password": self.password}
        )

        if response.status_code == 200:
            token = response.json().get("access_token")
            self.client.headers.update({"Authorization": f"Bearer {token}"})
        else:
            print(f"Failed to authenticate: {response.status_code}")

    @task(3)
    def list_documents(self):
        self.client.get("/api/v1/documents/")

    @task(1)
    def get_dashboard_stats(self):
        self.client.get("/api/v1/documents/stats/dashboard")

    @task(1)
    def list_clients(self):
        self.client.get("/api/v1/documents/clients")
