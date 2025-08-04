import json

from core import settings
from endpoint.models import Tasks

with open("utils/tasks.json", "r") as file:
    tasks_json = json.load(file)

for tasks_list in tasks_json.values():
    for task in tasks_list:
        task["icon"] = f"https://{settings.S3_ENDPOINT}/static/{task['icon']}"

tasks = tasks_json.get("Daily reward", []) + tasks_json.get("Tasks list", [])
tasks: list[Tasks] = [Tasks.model_validate(task) for task in tasks]

rewards_for_daily: dict[int, int] = {
    1: 500,
    2: 1000,
    3: 2500,
    4: 5000,
    5: 15000,
    6: 25000,
    7: 100000,
    8: 500000,
}
