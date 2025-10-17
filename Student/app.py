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
import hashlib
from fastapi import FastAPI, BackgroundTasks

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://aipipe.org/openai/v1")

def validate_secret(secret: str) -> bool:
    # Placeholder for secret validation logic
    return secret == os.getenv("secret")

def generate_unique_repo_name(task: str, secret: str) -> str:
    """Generate unique repo name from task and secret hash"""
    # Take first 8 characters of secret hash for uniqueness
    secret_hash = hashlib.sha256(secret.encode()).hexdigest()[:8]
    # Clean task name: replace spaces and special chars with hyphens
    clean_task = re.sub(r'[^a-zA-Z0-9-]', '-', task.lower())
    clean_task = re.sub(r'-+', '-', clean_task).strip('-')[:50]  # Limit length
    return f"{clean_task}-{secret_hash}"

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

def write_with_llm(task_brief: str = None, checks: list = None):
    if not task_brief:
        return [
            {"name": "index.html", "content": "<h1>Test Page (Fallback)</h1>"},
            {"name": "README.md", "content": "# Fallback Project\n\nAuto-generated fallback.\n\n## License\n\nMIT License"}
        ]
    
    checks_text = "\n".join(f"- {check}" for check in (checks or [])) if checks else "No specific checks provided"
    
    llm_output = call_llm(f"""
You are an expert developer and content creator. Create a complete solution for this task:

TASK BRIEF: {task_brief}

EVALUATION CRITERIA:
{checks_text}

CRITICAL REQUIREMENTS:
1. ALWAYS create a professional README.md file that includes:
   - Clear title and description of what you created
   - How to use/view/run the deliverable
   - Any technical details or dependencies
   - Professional formatting with proper markdown
   - MUST end with a "## License" section that says "MIT License"

2. Create ALL necessary files to fulfill the task:
   - For web apps: HTML, CSS, JS files
   - For data analysis: Python/JS scripts, visualizations, data files
   - For documents: Markdown, HTML, or text files
   - For visualizations: HTML with embedded charts, or image files
   - For any other task: whatever files are needed

3. Code and content quality:
   - Add clear comments and documentation
   - Include error handling where appropriate
   - Make it production-ready and professional
   - Ensure files work together cohesively

4. If the task requires a viewable page (web app, visualization, report):
   - Create an index.html as the entry point
   - Ensure it works standalone in a browser

Return ONLY a JSON array of file objects. ALWAYS include README.md as the first file:
[
  {{"name": "README.md", "content": "# Project Title\\n\\nDescription...\\n\\n## License\\n\\nMIT License"}},
  {{"name": "index.html", "content": "<!DOCTYPE html>..."}},
  {{"name": "script.py", "content": "# Python script\\n..."}},
  {{"name": "data.json", "content": "{{\\"data\\": []}}"}},
  ...additional files as needed...
]

IMPORTANT: Analyze the task type and create appropriate files. Don't assume it's always a web app.
CRITICAL: README.md MUST end with "## License\\n\\nMIT License"
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
        
        # Validate README exists and has license
        readme_found = False
        for f in files:
            if f["name"].lower() == "readme.md":
                readme_found = True
                # Ensure license section exists
                if "## License" not in f["content"]:
                    f["content"] += "\n\n## License\n\nMIT License"
                break
        
        if not readme_found:
            print("WARNING: LLM did not generate README.md, adding default")
            files.insert(0, {
                "name": "README.md",
                "content": f"# {task_brief}\n\nThis project was automatically generated.\n\n## Description\n{task_brief}\n\n## Files\n" + 
                          "\n".join(f"- `{f['name']}`" for f in files) + 
                          "\n\n## Usage\nSee individual files for usage instructions.\n\n## License\n\nMIT License"
            })
        
        # Ensure there's at least one deliverable file
        if len(files) <= 1:  # Only README
            print("WARNING: Only README generated, adding placeholder")
            files.append({
                "name": "index.html",
                "content": f"<!DOCTYPE html><html><head><title>{task_brief}</title></head><body><h1>{task_brief}</h1><p>See README.md for details.</p></body></html>"
            })
        
        return files
    except Exception as e:
        print("Failed to parse LLM output, using fallback:", e)
        return [
            {"name": "README.md", "content": f"# {task_brief}\n\nAuto-generated project.\n\n## Task\n{task_brief}\n\n## License\n\nMIT License"},
            {"name": "index.html", "content": f"<!DOCTYPE html><html><head><title>Task</title></head><body><h1>{task_brief}</h1></body></html>"}
        ]

def notify_evaluation_api(evaluation_url: str, payload: dict, max_retries: int = 3):
    """Notify evaluation API with retry logic for 503 errors and timeouts."""
    import time
    
    for attempt in range(max_retries):
        try:
            # Increase timeout progressively: 15s, 30s, 60s
            timeout = 15 * (2 ** attempt)
            resp = requests.post(evaluation_url, json=payload, timeout=timeout)
            
            if resp.status_code == 200:
                print(f"✅ Evaluation ping successful: {resp.status_code}")
                return True
            elif resp.status_code == 503:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                print(f"⚠️  503 error (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"⚠️  Evaluation ping returned: {resp.status_code} - {resp.text[:200]}")
                # Don't retry on 4xx errors (client errors)
                if 400 <= resp.status_code < 500:
                    return False
                
        except requests.exceptions.Timeout:
            wait_time = 2 ** attempt
            print(f"⏱️  Timeout on attempt {attempt + 1}/{max_retries} (waited {timeout}s)")
            if attempt < max_retries - 1:
                print(f"   Retrying in {wait_time}s...")
                time.sleep(wait_time)
        except requests.exceptions.ConnectionError as e:
            print(f"🔌 Connection error on attempt {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
        except Exception as e:
            print(f"❌ Unexpected error notifying evaluation API: {e}")
            return False
    
    print(f"❌ Failed to notify evaluation API after {max_retries} attempts")
    print(f"📋 Payload attempted: {json.dumps(payload, indent=2)}")
    print(f"🔗 URL attempted: {evaluation_url}")
    print("⚠️  NOTE: Your files were successfully deployed, but the evaluator may not have been notified.")
    return False

def round1(data):
    # Generate unique repo name using task and secret
    repo_name = generate_unique_repo_name(data['task'], data['secret'])
    nonce = data['nonce']
    
    files = write_with_llm(task_brief=data.get("brief"), checks=data.get("checks", []))

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
        notify_evaluation_api(evaluation_url, {
            "status": "completed",
            "round": 1,
            "repo": repo_name,
            "nonce": nonce
        })

def round2(data):
    # Generate same unique repo name using task and secret
    repo_name = generate_unique_repo_name(data['task'], data['secret'])
    nonce = data['nonce']

    # Step 1: Generate new files for round 2 using LLM
    files = write_with_llm(task_brief=data.get("brief"), checks=data.get("checks", []))

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
        notify_evaluation_api(evaluation_url, {
            "status": "completed",
            "round": 2,
            "repo": repo_name,
            "nonce": nonce
        })

app = FastAPI()

# post endpoint to receive json object
@app.post("/student-task")
def recieve_task(data: dict, background_tasks: BackgroundTasks):
    if not validate_secret(data.get("secret", "")):
        return {"error": "Invalid secret"}
    
    # Return 200 immediately after validation
    if data.get("round") == 1:
        background_tasks.add_task(round1, data)
        return {"message": "Round 1 tasks initiated", "status": "processing"}
    elif data.get("round") == 2:
        background_tasks.add_task(round2, data)
        return {"message": "Round 2 tasks initiated", "status": "processing"}
    
    return {"message": "Task received", "data": data}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
