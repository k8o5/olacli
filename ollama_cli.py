#!/usr/bin/env python3
import os
import requests
import subprocess
import json
import re
import argparse

def call_ollama_api_stream(messages, model="codellama"):
    """Calls the Ollama API with a chat history and streams the response."""
    data = {
        "model": model,
        "messages": messages,
        "stream": True
    }
    url = "http://localhost:11434/api/chat"
    
    try:
        with requests.post(url, json=data, stream=True) as response:
            response.raise_for_status()
            full_response = ""
            for chunk in response.iter_lines():
                if chunk:
                    decoded_chunk = chunk.decode('utf-8')
                    json_chunk = json.loads(decoded_chunk)
                    content = json_chunk.get("message", {}).get("content", "")
                    full_response += content
                    print(content, end="", flush=True)
            return full_response
    except requests.exceptions.RequestException as e:
        print(f"Error calling Ollama API: {e}")
        return None

def extract_code_block(response_text):
    """Extracts a code block, its language, and an optional filename from the AI's response."""
    filename_match = re.search(r"filename: (.*?)\n", response_text)
    filename = filename_match.group(1).strip() if filename_match else None

    code_match = re.search(r"```(.*?)\n(.*?)```", response_text, re.DOTALL)
    if code_match:
        language = code_match.group(1).strip()
        code = code_match.group(2).strip()
        return filename, language, code
    return filename, None, None

def main():
    """Main function for the AI assistant."""
    parser = argparse.ArgumentParser(description="Ollama CLI")
    parser.add_argument("--model", default="codellama", help="The Ollama model to use.")
    args = parser.parse_args()

    print(f"\nWelcome to your personal Ollama CLI! (Using model: {args.model})")
    print("Type 'exit' or 'quit' to end the conversation.")

    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant that can execute shell commands and write code. When asked to perform an action that requires a shell command, please respond with the command in a ```bash\n...``` block. When asked to write code, you can specify a filename with 'filename: path/to/file.ext' before the code block. Please respond with the code in a ```<language>\n...``` block."
        }
    ]

    while True:
        prompt = input("\nYou: ")
        if prompt.lower() in ["exit", "quit"]:
            break

        messages.append({"role": "user", "content": prompt})

        print("\nAI: ", end="")
        ai_response = call_ollama_api_stream(messages, model=args.model)
        if ai_response:
            messages.append({"role": "assistant", "content": ai_response})

            filename, language, code = extract_code_block(ai_response)

            if code:
                if language == "bash" or not language:
                    # ... (self-debugging loop for bash commands remains the same)
                    while True:
                        confirm = input(f"\nExecute the following command? [y/N]: \n{code}\n")
                        if confirm.lower() == 'y':
                            try:
                                result = subprocess.run(code, shell=True, check=True, capture_output=True, text=True)
                                print("\nCommand executed successfully.")
                                print("Output:\n", result.stdout)
                                break
                            except subprocess.CalledProcessError as e:
                                print(f"\nError executing command: {e}")
                                print("Stderr:\n", e.stderr)
                                debug_confirm = input("\nDo you want to try to debug this error? [y/N]: ")
                                if debug_confirm.lower() == 'y':
                                    debug_messages = messages + [
                                        {
                                            "role": "user",
                                            "content": f"The previous command failed with the following error:\n{e.stderr}\n\nPlease provide a corrected command."
                                        }
                                    ]
                                    print("\nAI: ", end="")
                                    debug_response = call_ollama_api_stream(debug_messages, model=args.model)
                                    if debug_response:
                                        messages.append({"role": "assistant", "content": debug_response})
                                        _, _, code = extract_code_block(debug_response)
                                        if not code:
                                            print("\nAI could not provide a fix.")
                                            break
                                else:
                                    break
                        else:
                            break
                else:
                    if filename:
                        os.makedirs(os.path.dirname(filename), exist_ok=True)
                        with open(filename, "w") as f:
                            f.write(code)
                        print(f"\nCode saved to {filename}")
                    else:
                        filename = input(f"\nSave code as (e.g., my_code.{language}): ")
                        if filename:
                            with open(filename, "w") as f:
                                f.write(code)
                            print(f"\nCode saved to {filename}")

                    if filename:
                        run_confirm = input(f"\nDo you want to try to run this {language} code? [y/N]: ")
                        if run_confirm.lower() == 'y':
                            # ... (AI-powered run command logic remains the same)
                            run_messages = [
                                {
                                    "role": "system",
                                    "content": "You are an expert at running code in various languages. Given a filename and a language, provide the shell command to run the code."
                                },
                                {
                                    "role": "user",
                                    "content": f"How do I run the file '{filename}' which is written in {language}?"
                                }
                            ]
                            print("\nAI: ", end="")
                            run_command_response = call_ollama_api_stream(run_messages, model=args.model)
                            if run_command_response:
                                messages.append({"role": "assistant", "content": run_command_response})
                                _, _, run_command = extract_code_block(run_command_response)
                                if run_command:
                                    # This is where the self-debugging loop for generated code would go
                                    # For now, we'll just execute it once
                                    confirm = input(f"\nExecute the following command? [y/N]: \n{run_command}\n")
                                    if confirm.lower() == 'y':
                                        try:
                                            subprocess.run(run_command, shell=True, check=True)
                                            print("\nCommand executed successfully.")
                                        except subprocess.CalledProcessError as e:
                                            print(f"\nError executing command: {e}")

if __name__ == "__main__":
    main()
