# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "fastapi[standard]",
#   "uvicorn",
#   "requests<3",
# ]
# ///
import re
import requests
import json
import os
import base64
from fastapi import FastAPI

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://aipipe.org/openai/v1")

def validate_secret(secret: str) -> bool:
    # Placeholder for secret validation logic
    return secret == os.getenv("secret")

def create_repo(repo_name: str):
    payload = {
        "name": repo_name,
        "private": False,
        "auto_init": True,
        "license_template": "mit",  
    }
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    
    response = requests.post("https://api.github.com/user/repos", headers=headers, json=payload)
    if response.status_code == 201:
        print(f"Repository {repo_name} created successfully.")
        return True
    elif response.status_code == 422:
        # Repository already exists
        print(f"Repository {repo_name} already exists.")
        return True
    else:
        print(f"Failed to create repository: {response.content}")
        return False

def enable_pages(repo_name: str):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    
    payload = {
        "build_type": "legacy",
        "source": {
            "branch": "main",
            "path": "/"
        }
    }
    
    response = requests.post(
        f"https://api.github.com/repos/22f3000926/{repo_name}/pages", 
        headers=headers, 
        json=payload
    )
    
    if response.status_code == 201:
        print(f"GitHub Pages enabled for {repo_name}.")
    elif response.status_code == 409:
        print(f"GitHub Pages already enabled for {repo_name}.")
    else:
        print(f"Failed to enable Pages: {response.text}")

def get_file_sha(repo_name: str, file_path: str) -> str | None:
    """Get the SHA of a file in the repo if it exists."""
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    response = requests.get(
        f"https://api.github.com/repos/22f3000926/{repo_name}/contents/{file_path}", 
        headers=headers
    )
    if response.status_code == 200:
        return response.json()["sha"]
    return None

def push_files(repo_name: str, files: list[dict], round: int):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    for file in files:
        file_name = file.get("name")
        file_content = file.get("content")

        if not file_name or not file_content:
            continue

        # base64 encode file content
        file_content_b64 = base64.b64encode(file_content.encode('utf-8')).decode('utf-8')

        file_sha = get_file_sha(repo_name, file_name)
        payload = {
            "message": f"Round {round}: Update {file_name}",
            "content": file_content_b64
        }
        if file_sha:
            payload["sha"] = file_sha

        response = requests.put(
            f"https://api.github.com/repos/22f3000926/{repo_name}/contents/{file_name}",
            headers=headers,
            json=payload
        )

        if response.status_code in (200, 201):
            print(f"File {file_name} pushed to {repo_name}.")
        else:
            print(f"Failed to push {file_name}: {response.text}")

def deploy():
    pass

def call_llm(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4.1-mini",
        "input": prompt
    }
    response = requests.post(f"{OPENAI_BASE_URL}/responses", headers=headers, json=payload)
    if response.status_code != 200:
        print("LLM call failed:", response.status_code, response.text)
        return ""
    data = response.json()
    text_output = ""
    for item in data.get("output", []):
        for chunk in item.get("content", []):
            if chunk.get("type") == "output_text":
                text_output += chunk.get("text", "")
    return text_output

def parse_llm_json(llm_text: str):
    try:
        match = re.search(r"\[.*\]", llm_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception as e:
        print("Error parsing LLM output:", e)
    return []

def write_with_llm(task_brief: str = None):
    if not task_brief:
        return [{"name": "index.html", "content": "<h1>Test Page (Fallback)</h1>"}]
    llm_output = call_llm(f"""
    You are a code generator. Create files for this brief: "{task_brief}".
    Return ONLY a JSON array of objects like:
    [{{"name": "index.html", "content": "<html>...</html>"}}]
    """)
    try:
        files = json.loads(llm_output)
        for f in files:
            content = f["content"]
            try:
                # Try decoding as Base64
                decoded = base64.b64decode(content).decode("utf-8")
                f["content"] = decoded
            except Exception:
                # If fails, treat as raw UTF-8 string
                f["content"] = content
        return files
    except Exception as e:
        print("Failed to parse LLM output, using fallback test page:", e)
        return [{"name": "index.html", "content": "<h1>Fallback page</h1>"}]

def round1(data):
    # Use task as the stable repo identifier
    repo_name = data['task']
    nonce = data['nonce']
    
    files = write_with_llm(task_brief=data.get("brief"))

    attachments = data.get("attachments", [])
    for att in attachments:
        name = att["name"]
        url = att["url"]

        # Handle only data: URLs (base64 encoded)
        if url.startswith("data:"):
            base64_data = url.split(",")[1]
            decoded = base64.b64decode(base64_data).decode("utf-8")
            files.append({"name": name, "content": decoded})
        else:
            print(f"Skipping non-base64 attachment: {url}")

    create_repo(repo_name)
    enable_pages(repo_name)
    push_files(repo_name, files, 1)
    deploy()

    # Ping evaluation API with the current nonce
    evaluation_url = data.get("evaluation_url")
    if evaluation_url:
        try:
            resp = requests.post(evaluation_url, json={
                "status": "completed",
                "round": 1,
                "repo": repo_name,
                "nonce": nonce  # Pass back the nonce for this round
            })
            print("Round 1 evaluation ping sent:", resp.status_code)
        except Exception as e:
            print("Failed to notify evaluation API:", e)

def round2(data):
    # Use the same task-based repo name
    repo_name = data['task']
    nonce = data['nonce']

    # Step 1: Generate new files for round 2 using LLM
    files = write_with_llm(task_brief=data.get("brief"))

    attachments = data.get("attachments", [])
    for att in attachments:
        name = att["name"]
        url = att["url"]
        if url.startswith("data:"):
            base64_data = url.split(",")[1]
            decoded = base64.b64decode(base64_data).decode("utf-8")
            files.append({"name": name, "content": decoded})
        else:
            print(f"Skipping non-base64 attachment: {url}")

    # Step 2: Push updated files (will update existing files via SHA)
    push_files(repo_name, files, round=2)

    # Step 3: Optional deploy
    deploy()

    evaluation_url = data.get("evaluation_url")
    if evaluation_url:
        try:
            resp = requests.post(evaluation_url, json={
                "status": "completed",
                "round": 2,
                "repo": repo_name,
                "nonce": nonce  # Pass back the current nonce
            })
            print("Round 2 evaluation ping sent:", resp.status_code)
        except Exception as e:
            print("Failed to notify evaluation API:", e)

app = FastAPI()

# post endpoint to receive json object
@app.post("/student-task")
def recieve_task(data: dict):
    if not validate_secret(data.get("secret", "")):
        return {"error": "Invalid secret"}
    else:
        if data.get("round") == 1:
            round1(data)
            return {"message": "Round 1 tasks initiated"}
        elif data.get("round") == 2:
            round2(data)
            return {"message": "Round 2 tasks initiated"}
        
    return {"message": "Task received", "data": data}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
