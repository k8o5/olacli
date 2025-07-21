#!/usr/bin/env python3
import os
import requests
import subprocess
import json
import re
import argparse
import base64
import time
from typing import List, Dict, Optional

# NEW: Import BeautifulSoup for parsing HTML
try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Fehler: Das 'BeautifulSoup' Modul wird benötigt. Bitte installieren: pip install beautifulsoup4")
    exit(1)

try:
    import readline
except ImportError:
    try:
        import pyreadline3 as readline
    except ImportError:
        print("Hinweis: Für eine bessere Eingabe mit Befehlshistorie, installieren Sie 'pyreadline3' (pip install pyreadline3)")
        readline = None

# --- Most functions are the same, new function is added below ---

def call_ollama_api_stream(messages: List[Dict], model: str, max_retries: int = 3, verbose: bool = True) -> str:
    # (Identical to previous version)
    data = { "model": model, "messages": messages, "stream": True }
    url = "http://localhost:11434/api/chat"
    for attempt in range(max_retries):
        try:
            with requests.post(url, json=data, stream=True, timeout=60) as response:
                response.raise_for_status()
                full_response = ""
                for chunk in response.iter_lines():
                    if chunk:
                        decoded_chunk = chunk.decode('utf-8')
                        json_chunk = json.loads(decoded_chunk)
                        content = json_chunk.get("message", {}).get("content", "")
                        full_response += content
                        if verbose:
                            print(content, end="", flush=True)
                return full_response
        except requests.exceptions.RequestException as e:
            if verbose: print(f"\nError calling Ollama API: {e}")
            if attempt == max_retries - 1: return None

def extract_code_block(response_text: str) -> tuple:
    # (Identical to previous version)
    filename_match = re.search(r"filename: (.*?)\n", response_text)
    filename = filename_match.group(1).strip() if filename_match else None
    code_match = re.search(r"```(.*?)\n(.*?)```", response_text, re.DOTALL)
    if code_match:
        language = code_match.group(1).strip().lower()
        code = code_match.group(2).strip()
        return filename, language, code
    return filename, None, None

# --- NEW FUNCTION: The Web Tool ---
def fetch_url_content(url: str) -> str:
    """Fetches and extracts clean text from a URL."""
    try:
        print(f"\n\n🤖 Accessing web page: {url}...")
        headers = { # Act like a real browser
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Use BeautifulSoup to parse HTML and get clean text
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
        
        text = soup.get_text(separator='\n', strip=True)
        # Limit the text to a reasonable size to not overwhelm the AI
        max_length = 8000
        print(f"✅ Web page content fetched and cleaned.")
        return text[:max_length]

    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching URL: {e}")
        return f"Error: Could not fetch the URL. The error was: {e}"

def handle_response(ai_response: str, messages: List[Dict], model: str):
    """
    Handles AI responses, now with a web tool, shell commands, and file-saving.
    """
    # --- NEW: Check for the web tool command first ---
    tool_match = re.search(r'\[TOOL_WEB\]\s*(https?://[^\s\]]+)', ai_response)
    if tool_match:
        url = tool_match.group(1)
        web_content = fetch_url_content(url)
        
        # Now, make a second call to the AI with the web content
        # We add the web content as if it's new information from the user
        web_context_prompt = (
            f"Here is the text content from the URL {url}:\n\n"
            f"--- WEB CONTENT ---\n{web_content}\n--- END WEB CONTENT ---\n\n"
            "Based on this content, please answer my original question."
        )
        
        # Add this context to the messages history
        messages.append({"role": "user", "content": web_context_prompt})
        
        print("\n\n🤖 Analyzing web content to find the answer...")
        final_response = call_ollama_api_stream(messages, model)
        if final_response:
            messages.append({"role": "assistant", "content": final_response})
            # We can even re-run handle_response in case the AI wants to do something
            # with the info (like save it to a file), but for now, we'll just print.
        return # Stop processing here

    # --- Existing logic for code blocks ---
    filename, language, code = extract_code_block(ai_response)
    if not code:
        return

    if language in ["bash", "sh", "shell"]:
        print(f"\n\n🤖 AI suggests a shell command.")
        execute_and_debug_command(code, messages, model)
        return

    # (The rest of the file-saving logic remains the same)
    print(f"\n\n🤖 AI suggests a {language} program.")
    # ... rest of the function is identical to the previous version ...
    if not filename: filename = generate_filename(code, language, model)
    try:
        dir_name = os.path.dirname(filename);
        if dir_name: os.makedirs(dir_name, exist_ok=True)
        with open(filename, "w") as f: f.write(code)
        print(f"\n✅ Code saved to {filename}")
    except Exception as e:
        print(f"\n❌ Error saving file: {e}"); return
    run_messages = [{"role": "system", "content": "Provide ONLY the shell command to run the given file in the specified language."}, {"role": "user", "content": f"Command to run '{filename}' in {language}?"}]
    print("\n🤖 Generating run command...", end=""); run_command_response = call_ollama_api_stream(run_messages, model=model, verbose=False); print(" Done.")
    if not run_command_response: print("\n❌ Could not generate a run command."); return
    _, _, run_command = extract_code_block(run_command_response)
    if not run_command: run_command = run_command_response.strip().replace('`', '')
    execute_and_debug_command(run_command, messages, model, original_code=code, filename=filename, language=language)

# (Other helper functions like execute_and_debug_command, generate_filename, etc. are unchanged)
def execute_and_debug_command(command_to_run: str, messages: List[Dict], model: str, original_code: Optional[str] = None, filename: Optional[str] = None, language: Optional[str] = None):
    # (Identical to previous version)
    current_command = command_to_run
    while True:
        confirm = input(f"\n👉 Execute: '{current_command}'? [y/N]: ").strip().lower()
        if confirm != 'y': break
        try:
            print("-" * 20 + " EXECUTION START " + "-" * 20)
            result = subprocess.run(current_command, shell=True, check=True, capture_output=True, text=True)
            print("\n✅ Success! Output:\n"); print(result.stdout)
            messages.append({"role": "user", "content": f"Command `{current_command}` was successful. Output:\n```\n{result.stdout}\n```"})
            break
        except subprocess.CalledProcessError as e:
            print(f"\n❌ Error: {e}\nStderr:\n{e.stderr}")
            debug_confirm = input("\n🐛 Debug this error? [y/N]: ").strip().lower()
            if debug_confirm != 'y': break
            if filename and original_code: debug_prompt = f"Command `{current_command}` failed on `{filename}`. Error:\n```\n{e.stderr}\n```\nOriginal code:\n```{language}\n{original_code}\n```\nProvide a fix."
            else: debug_prompt = f"Command `{current_command}` failed. Error:\n```\n{e.stderr}\n```\nProvide the corrected command."
            debug_messages = messages + [{"role": "user", "content": debug_prompt}]
            print("\n🤖 AI is debugging..."); debug_response = call_ollama_api_stream(debug_messages, model);
            if debug_response: messages.append({"role": "assistant", "content": debug_response}); handle_response(debug_response, messages, model)
            else: print("\n❌ No debug response.")
            break
        except Exception as e: print(f"\n❌ Unexpected error: {e}"); break
def generate_filename(code: str, language: str, model: str) -> str:
    # (Identical to previous version)
    print("\n\n🤖 Generating filename..."); prompt=f"Suggest a concise, snake_case filename for this '{language}' code. Respond ONLY with the filename.\n\nCode:\n```\n{code}\n```"
    messages=[{"role":"user", "content":prompt}]; filename_response=call_ollama_api_stream(messages, model, verbose=False)
    if filename_response:
        match=re.search(r'([\w_./-]+\.\w+)', filename_response)
        if match: clean_name=match.group(1).strip(); print(f"🤖 Filename: {clean_name}"); return clean_name
    fallback_name=f"generated_code_{int(time.time())}.{language or 'txt'}"; print(f"⚠️ Fallback: {fallback_name}"); return fallback_name

def main():
    parser = argparse.ArgumentParser(description="olacli: AI chat with web access and code execution.")
    parser.add_argument("--model", default="gemma3:latest", help="Ollama model to use.")
    # (Other arguments are the same)
    parser.add_argument("--prompt", help="One-shot prompt to send (non-interactive).")
    parser.add_argument("--image", help="Path to an image file for vision models.")
    parser.add_argument("--load-history", action="store_true", help="Load previous chat history.")
    parser.add_argument("--save-history", action="store_true", help="Save chat history on exit.")
    args = parser.parse_args()
    
    # --- UPDATED SYSTEM PROMPT ---
    system_message = {
        "role": "system",
        "content": (
            "You are a helpful assistant with tools. "
            "To access real-time information from the internet, respond with a tool command: `[TOOL_WEB] https://<url_to_browse>`\n"
            "For shell commands, use ```bash blocks. "
            "For code to be saved, use ```language blocks and optionally suggest a `filename:`."
        )
    }
    
    # The rest of main() is mostly the same, just initializing things
    CMD_HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".olacli_cmd_history")
    if readline:
        try: readline.read_history_file(CMD_HISTORY_FILE)
        except FileNotFoundError: pass

    print(f"\nWelcome to Ollama CLI! Using model: {args.model}")
    print("Now with web access! Try 'what is the price of Bitcoin?'")
    
    messages = [system_message]
    if args.load_history: # ... load history logic ...
        pass
    
    # Main loop (unchanged)
    while True:
        try:
            prompt = input("\nYou: ").strip()
            if prompt.lower() in ["exit", "quit"]:
                if readline: readline.write_history_file(CMD_HISTORY_FILE)
                break
            
            messages.append({"role": "user", "content": prompt})

            print("\nAI: ", end="")
            ai_response = call_ollama_api_stream(messages, model=args.model)
            if ai_response:
                messages.append({"role": "assistant", "content": ai_response})
                handle_response(ai_response, messages, args.model)
        except (KeyboardInterrupt, EOFError):
            if readline: readline.write_history_file(CMD_HISTORY_FILE)
            print("\nExiting...")
            break

if __name__ == "__main__":
    main()
