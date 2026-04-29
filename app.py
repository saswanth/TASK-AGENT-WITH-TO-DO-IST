import os
import re
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, url_for
from markupsafe import Markup
from openai import OpenAI

from main import AITaskAgent, TodoistStore


load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL")
model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
todoist_token = os.getenv("TODOIST_API_TOKEN")
if not todoist_token:
    raise RuntimeError("TODOIST_API_TOKEN is missing in environment")

client: Optional[OpenAI] = None
if api_key:
    client_kwargs: Dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)

store = TodoistStore(todoist_token)
agent = AITaskAgent(store, client, model)

app = Flask(__name__)


@app.template_filter("md_links")
def md_links_filter(text: str) -> Markup:
    """Convert Markdown [label](url) links to HTML <a> tags."""
    escaped = Markup.escape(text)
    linked = re.sub(
        r"\[([^\]]+)\]\((https?://[^\)]+)\)",
        lambda m: f'<a href="{m.group(2)}" target="_blank" rel="noopener noreferrer">{m.group(1)}</a>',
        str(escaped),
    )
    return Markup(linked)


@app.get("/")
def index() -> str:
    tasks = store.list_tasks()
    message = request.args.get("message", "")
    return render_template("index.html", tasks=tasks, message=message)


@app.post("/create")
def create_task() -> str:
    title = (request.form.get("title") or "").strip()
    if not title:
        return redirect(url_for("index", message="Task title cannot be empty."))

    task = store.create_task(title)
    return redirect(url_for("index", message=f"Task created: #{task['id']}"))


@app.post("/delete")
def delete_task() -> str:
    raw_task_id = (request.form.get("task_id") or "").strip()
    if not raw_task_id:
        return redirect(url_for("index", message="Task id cannot be empty."))

    deleted = store.delete_task(raw_task_id)
    if not deleted:
        return redirect(url_for("index", message=f"Task {raw_task_id} not found."))

    return redirect(url_for("index", message=f"Task {raw_task_id} deleted."))


@app.post("/agent")
def agent_command() -> str:
    command = (request.form.get("command") or "").strip()
    if not command:
        return redirect(url_for("index", message="Command cannot be empty."))

    try:
        result = agent.handle(command)
        return redirect(url_for("index", message=result))
    except Exception as exc:
        return redirect(url_for("index", message=f"Agent error: {exc}"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
