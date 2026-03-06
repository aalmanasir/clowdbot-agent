import subprocess
from app.config import settings

ALLOWED_SHELL_COMMANDS = {
    "pwd", "ls", "echo", "whoami", "date", "uname", "python3 --version"
}

def is_command_allowed(command: str) -> bool:
    command = command.strip()
    if not command:
        return False
    if command in ALLOWED_SHELL_COMMANDS:
        return True
    first = command.split()[0]
    return first in {"pwd", "ls", "echo", "whoami", "date", "uname"}

def run_command(command: str):
    if not settings.ALLOWED_EXECUTE:
        return {"ok": False, "error": "Shell execution disabled. Set ALLOWED_EXECUTE=true to enable."}

    if not is_command_allowed(command):
        return {
            "ok": False,
            "error": f"Command not allowed. Allowed examples: {sorted(ALLOWED_SHELL_COMMANDS)}"
        }

    try:
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=20
        )
        return {
            "ok": True,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "returncode": completed.returncode
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
