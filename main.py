import json
import os
import re
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from openai import OpenAI


TODOIST_API_BASE = "https://api.todoist.com/api/v1"


class TodoistStore:
    def __init__(self, token: str) -> None:
        self.token = token
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def create_task(self, title: str) -> Dict[str, Any]:
        resp = requests.post(
            f"{TODOIST_API_BASE}/tasks",
            headers=self._headers,
            json={"content": title},
            timeout=10,
        )
        resp.raise_for_status()
        task = resp.json()
        return {"id": task["id"], "title": task["content"]}

    def delete_task(self, task_id: str) -> bool:
        resp = requests.delete(
            f"{TODOIST_API_BASE}/tasks/{task_id}",
            headers=self._headers,
            timeout=10,
        )
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        return True

    def list_tasks(self) -> List[Dict[str, Any]]:
        resp = requests.get(
            f"{TODOIST_API_BASE}/tasks",
            headers=self._headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        # API returns either a list or {results: [...], next_cursor: ...}
        items = data.get("results", data) if isinstance(data, dict) else data
        return [{"id": t["id"], "title": t.get("content", "")} for t in items]


class AITaskAgent:
    def __init__(self, store: TodoistStore, client: Optional[OpenAI], model: str) -> None:
        self.store = store
        self.client = client
        self.model = model

    def _plan_action_local(self, user_input: str) -> Dict[str, Any]:
        text = user_input.strip()
        lowered = text.lower()

        delete_match = re.search(r"(?:delete|remove)\s+(?:task\s*)?#?(\d+)", lowered)
        if not delete_match:
            delete_match = re.search(r"task\s*#?(\d+)\s*(?:delete|remove)", lowered)
        if delete_match:
            return {
                "action": "delete_task",
                "title": None,
                "task_id": delete_match.group(1),
            }

        create_patterns = [
            r"^(?:please\s+)?(?:create|add|new)\s+(?:a\s+)?task(?:\s*(?:to|:|-))?\s*(.+)$",
            r"^(?:please\s+)?(?:create|add)\s+(.+)$",
        ]
        for pattern in create_patterns:
            create_match = re.search(pattern, text, flags=re.IGNORECASE)
            if create_match:
                title = create_match.group(1).strip()
                if title:
                    return {
                        "action": "create_task",
                        "title": title,
                        "task_id": None,
                    }

        if any(keyword in lowered for keyword in ["list", "show", "all tasks", "tasks"]):
            return {"action": "list_tasks", "title": None, "task_id": None}

        return {"action": "list_tasks", "title": None, "task_id": None}

    def _plan_action(self, user_input: str) -> Dict[str, Any]:
        if self.client is None:
            return self._plan_action_local(user_input)

        system_prompt = (
            "You are a task command router. Return JSON only with one action. "
            "Supported actions: create_task, delete_task, list_tasks. "
            "JSON schema: {\"action\": string, \"title\": string|null, \"task_id\": string|null}. "
            "Rules: "
            "- For create_task, set title. "
            "- For delete_task, set task_id. "
            "- For list_tasks, title/task_id must be null. "
            "- If unclear, default to list_tasks."
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
                temperature=0,
            )
        except Exception:
            # If API auth/network fails, keep task operations usable via local parsing.
            return self._plan_action_local(user_input)

        content = response.choices[0].message.content or "{}"
        try:
            action_data = json.loads(content)
        except json.JSONDecodeError:
            return {"action": "list_tasks", "title": None, "task_id": None}

        action = action_data.get("action")
        if action not in {"create_task", "delete_task", "list_tasks"}:
            return {"action": "list_tasks", "title": None, "task_id": None}

        return {
            "action": action,
            "title": action_data.get("title"),
            "task_id": action_data.get("task_id"),
        }

    def handle(self, user_input: str) -> str:
        action_data = self._plan_action(user_input)
        action = action_data["action"]

        if action == "create_task":
            title = (action_data.get("title") or "").strip()
            if not title:
                return "I could not find a valid task title to create."
            task = self.store.create_task(title)
            return f"Task created: #{task['id']} - {task['title']}"

        if action == "delete_task":
            task_id = str(action_data.get("task_id") or "").strip()
            if not task_id:
                return "I could not find a valid task id to delete."
            deleted = self.store.delete_task(task_id)
            if not deleted:
                return f"Task #{task_id} was not found."
            return f"Task #{task_id} deleted."

        tasks = self.store.list_tasks()
        if not tasks:
            return "No tasks found."
        lines = ["Tasks:"]
        lines.extend(f"- #{t['id']}: {t.get('title', '')}" for t in tasks)
        return "\n".join(lines)


def main() -> None:
    load_dotenv()
    todoist_token = os.getenv("TODOIST_API_TOKEN")
    if not todoist_token:
        raise RuntimeError("TODOIST_API_TOKEN is missing in environment")

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    client: Optional[OpenAI] = None
    if api_key:
        client_kwargs: Dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)
    else:
        print("OPENAI_API_KEY not set. Running in local parser mode.")

    store = TodoistStore(todoist_token)
    agent = AITaskAgent(store, client, model)

    print("AI Task Agent ready. Type your request or 'exit'.")

    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break

        try:
            result = agent.handle(user_input)
            print(f"Agent: {result}")
        except Exception as exc:  # Keep loop alive for transient API errors.
            print(f"Agent error: {exc}")


if __name__ == "__main__":
    main()
