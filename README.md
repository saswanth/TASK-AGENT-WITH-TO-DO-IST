# AI Task Agent

A simple AI-powered task agent that can:
- Create task
- Delete task
- List task

Now includes a browser UI.

## Setup

1. Install dependencies:

```powershell
pip install -r requirements.txt
```

2. Ensure `.env` contains your API key and model.

## Run CLI

```powershell
python main.py
```

Then type requests like:
- `create task buy milk`
- `list tasks`
- `delete task 1`
- `please add a task to prepare report by friday`

Type `exit` to quit.

## Run Web UI

```powershell
python app.py
```

Open this URL in your browser:

`http://127.0.0.1:5000`
