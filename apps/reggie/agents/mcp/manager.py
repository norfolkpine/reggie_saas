import json
import logging
import os
import subprocess
import threading
import time
from typing import Any, Dict, Optional, Tuple

from .loader import MCPConfigError, load_mcp_configurations

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Define example_config_content if not already defined
example_config_content = {
    "example_key": "example_value"
    # Add more fields as needed for your test config
}


class MCPManager:
    """
    Manages MCP server subprocesses based on configurations.
    Handles starting, stopping, and monitoring these processes.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initializes the MCPManager.

        Args:
            config_path (Optional[str]): Path to the MCP server configuration file.
                                         If None, uses the default path from loader.py.
        """
        self.config_path = config_path
        self.servers_config: Dict[str, Dict[str, Any]] = {}
        self.active_processes: Dict[str, subprocess.Popen] = {}
        self.process_threads: Dict[str, threading.Thread] = {}  # For log streaming
        self._load_configs()

    def _load_configs(self):
        """Loads configurations using the loader."""
        try:
            self.servers_config = (
                load_mcp_configurations(self.config_path) if self.config_path else load_mcp_configurations()
            )
            logger.info(f"Successfully loaded {len(self.servers_config)} server configurations.")
        except MCPConfigError as e:
            logger.error(f"Failed to load MCP configurations: {e}")
            # self.servers_config will remain empty, preventing operations.
            raise  # Re-raise to make it clear on instantiation if configs are bad

    def _stream_log(self, process: subprocess.Popen, server_id: str, stream_name: str):
        """Helper to stream stdout/stderr from a process."""
        stream = getattr(process, stream_name)
        if stream:
            for line in iter(stream.readline, b""):
                logger.info(f"[{server_id}-{stream_name.upper()}]: {line.decode().strip()}")
            stream.close()

    def start_server(self, server_id: str) -> bool:
        """
        Starts a specific MCP server if it's configured and enabled, and not already running.

        Args:
            server_id (str): The ID of the server to start.

        Returns:
            bool: True if the server was started successfully or is already running, False otherwise.
        """
        if server_id in self.active_processes and self.get_server_status(server_id)[0] == "running":
            logger.info(f"Server '{server_id}' is already running (PID: {self.active_processes[server_id].pid}).")
            return True

        if server_id not in self.servers_config:
            logger.error(f"Server ID '{server_id}' not found in configuration.")
            return False

        config = self.servers_config[server_id]
        if not config.get("enabled", True):
            logger.info(f"Server '{server_id}' is disabled in configuration. Will not start.")
            return False

        command = [config["command"]] + config.get("args", [])
        cwd = config.get("cwd")
        custom_env = os.environ.copy()
        custom_env.update(config.get("env", {}))

        # Authentication handling
        auth_config = config.get("authentication")
        if auth_config:
            token_env_var_name = auth_config.get("token_env_var_name")
            token_source_env_var_name = auth_config.get("token_source_env_var_name")

            token_value: Optional[str] = None
            if token_source_env_var_name:
                token_value = os.getenv(token_source_env_var_name)
                if not token_value:
                    logger.warning(
                        f"Server '{server_id}': Auth token environment variable '{token_source_env_var_name}' "
                        "is specified as source but not found in the manager's environment."
                    )
            else:
                # If no specific source, assume the token might be globally available
                # or the manager expects it to be directly set in `custom_env` if needed.
                # This part might need more sophisticated logic if tokens are fetched dynamically.
                # For now, we rely on token_source_env_var_name or pre-set env vars.
                logger.info(
                    f"Server '{server_id}': No 'token_source_env_var_name'. "
                    f"Ensure '{token_env_var_name}' is available if needed by the subprocess, "
                    "possibly via direct 'env' config or manager's environment."
                )

            if token_value and token_env_var_name:
                custom_env[token_env_var_name] = token_value
                logger.info(f"Server '{server_id}': Provided token to subprocess via env var '{token_env_var_name}'.")
            elif not token_value and token_env_var_name and token_env_var_name not in custom_env:
                logger.warning(
                    f"Server '{server_id}': Token for '{token_env_var_name}' was not found from source "
                    f"'{token_source_env_var_name}' and is not otherwise in environment for subprocess."
                )

        try:
            logger.info(f"Starting server '{server_id}': {' '.join(command)}")
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=custom_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # shell=False is default and recommended for security with list of args
            )
            self.active_processes[server_id] = process
            logger.info(f"Server '{server_id}' started with PID: {process.pid}.")

            # Start threads to stream logs
            stdout_thread = threading.Thread(target=self._stream_log, args=(process, server_id, "stdout"), daemon=True)
            stderr_thread = threading.Thread(target=self._stream_log, args=(process, server_id, "stderr"), daemon=True)
            stdout_thread.start()
            stderr_thread.start()
            self.process_threads[server_id] = (stdout_thread, stderr_thread)

            return True
        except FileNotFoundError:
            logger.error(
                f"Error starting server '{server_id}': Command '{config['command']}' not found. Ensure it's in PATH or an absolute path."
            )
            return False
        except PermissionError:
            logger.error(f"Error starting server '{server_id}': Permission denied for command '{config['command']}'.")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred while starting server '{server_id}': {e}")
            return False

    def stop_server(self, server_id: str, timeout: int = 10) -> bool:
        """
        Stops a specific MCP server.

        Args:
            server_id (str): The ID of the server to stop.
            timeout (int): Time in seconds to wait for graceful termination before force killing.

        Returns:
            bool: True if the server was stopped successfully, False otherwise.
        """
        if server_id not in self.active_processes:
            logger.info(f"Server '{server_id}' is not currently active or managed.")
            return False

        process = self.active_processes[server_id]
        logger.info(f"Stopping server '{server_id}' (PID: {process.pid})...")

        try:
            process.terminate()  # SIGTERM
            process.wait(timeout=timeout)
            logger.info(f"Server '{server_id}' (PID: {process.pid}) terminated gracefully.")
        except subprocess.TimeoutExpired:
            logger.warning(
                f"Server '{server_id}' (PID: {process.pid}) did not terminate in {timeout}s. Sending SIGKILL."
            )
            process.kill()  # SIGKILL
            try:
                process.wait(timeout=timeout)  # Wait for kill to complete
                logger.info(f"Server '{server_id}' (PID: {process.pid}) killed.")
            except subprocess.TimeoutExpired:
                logger.error(
                    f"Server '{server_id}' (PID: {process.pid}) failed to die even after SIGKILL. This is unusual."
                )
                # Should not happen often, but good to log
            except Exception as e:  # Catch other potential errors during wait after kill
                logger.error(f"Error waiting for process {server_id} after kill: {e}")

        except Exception as e:
            logger.error(f"Error during termination of server '{server_id}': {e}")
            # Even if there's an error, remove it from active_processes if it's likely dead
            if process.poll() is not None:  # Check if process actually died
                del self.active_processes[server_id]
                if server_id in self.process_threads:
                    del self.process_threads[server_id]  # Clean up threads too
                return True
            return False

        # Cleanup
        if server_id in self.active_processes:
            del self.active_processes[server_id]
        if server_id in self.process_threads:
            # Threads are daemon, will exit, but good to remove reference
            del self.process_threads[server_id]
        return True

    def get_server_status(self, server_id: str) -> Tuple[str, Optional[int]]:
        """
        Gets the status of a specific MCP server.

        Args:
            server_id (str): The ID of the server.

        Returns:
            Tuple[str, Optional[int]]: A tuple of (status_string, pid).
                                       Status can be "running", "stopped", "not_configured", "disabled".
                                       PID is the process ID if running, else None.
        """
        if server_id not in self.servers_config:
            return "not_configured", None

        if not self.servers_config[server_id].get("enabled", True):
            return "disabled", None

        if server_id in self.active_processes:
            process = self.active_processes[server_id]
            if process.poll() is None:  # Still running
                return "running", process.pid
            else:  # Process terminated on its own
                logger.info(
                    f"Server '{server_id}' (PID: {process.pid}) found terminated with code {process.returncode}. Cleaning up."
                )
                self.stop_server(server_id)  # Ensure proper cleanup
                return "stopped", None  # Now it's considered stopped by manager

        return "stopped", None

    def start_all_enabled_servers(self):
        """Starts all MCP servers that are enabled in the configuration."""
        if not self.servers_config:
            logger.warning("No server configurations loaded. Cannot start any servers.")
            return

        logger.info("Starting all enabled MCP servers...")
        for server_id, config in self.servers_config.items():
            if config.get("enabled", True):
                status, _ = self.get_server_status(server_id)
                if status != "running":
                    self.start_server(server_id)
                else:
                    logger.info(f"Server '{server_id}' is already running. Skipping start.")
            else:
                logger.info(f"Server '{server_id}' is disabled. Skipping.")
        logger.info("Finished attempt to start all enabled servers.")

    def stop_all_servers(self, timeout: int = 10):
        """
        Stops all currently active MCP servers managed by this instance.

        Args:
            timeout (int): Timeout for each server's graceful termination.
        """
        logger.info("Stopping all active MCP servers...")
        # Iterate over a copy of keys as stop_server modifies self.active_processes
        active_server_ids = list(self.active_processes.keys())
        for server_id in active_server_ids:
            self.stop_server(server_id, timeout)
        logger.info("Finished stopping all active servers.")

    def get_all_statuses(self) -> Dict[str, Tuple[str, Optional[int]]]:
        """
        Gets the status of all configured MCP servers.
        """
        statuses = {}
        for server_id in self.servers_config.keys():
            statuses[server_id] = self.get_server_status(server_id)
        return statuses


if __name__ == "__main__":
    logger.info("MCP Manager Example Usage")

    # Create a dummy mcp_servers.json for testing the manager
    # This example config is self-contained for the manager's __main__ block.
    # For general use, the mcp_servers.json file in the same directory is primary.
    example_config_content_for_manager_main = {  # Renamed to avoid confusion with the actual file's content
        "mcpServers": {
            "echo-fast": {
                "description": "A fast echo server that exits quickly.",
                "command": "python",  # Assuming python is in PATH
                "args": [
                    "-c",
                    "import sys, time; print('Echo fast says hello to MCP!'); sys.stdout.flush(); time.sleep(0.5); print('Echo fast exiting.'); sys.exit(0)",
                ],
                "enabled": True,
            },
            "echo-slow": {
                "description": "A slow echo server that runs for a bit.",
                "command": "python",
                "args": [
                    "-c",
                    "import sys, time; print('Echo slow says hello!'); sys.stdout.flush(); time.sleep(5); print('Echo slow exiting.'); sys.exit(0)",
                ],
                "enabled": True,
                "authentication": {
                    "token_env_var_name": "MY_ECHO_TOKEN",
                    "token_source_env_var_name": "MANAGER_HAS_THIS_TOKEN",
                },
            },
            "disabled-server": {"command": "echo", "args": ["This should not run"], "enabled": False},
            "error-command": {"command": "nonexistentcommand123xyz", "args": [], "enabled": True},
        }
    }

    # Attempt to create the test config file in various locations
    # Preferable to create it next to loader.py, but fallback to CWD
    config_dir = os.path.dirname(os.path.abspath(__file__))  # apps/reggie/agents/mcp
    manager_test_config_file = os.path.join(config_dir, "mcp_servers_manager_test.json")

    created_test_config = False
    try:
        with open(manager_test_config_file, "w") as f:
            json.dump(example_config_content_for_manager_main, f, indent=2)
        logger.info(f"Created dummy config for manager testing at: {manager_test_config_file}")
        created_test_config = True
    except IOError as e:
        manager_test_config_file = "mcp_servers_manager_test.json"  # Fallback to CWD
        try:
            with open(manager_test_config_file, "w") as f:
                json.dump(example_config_content_for_manager_main, f, indent=2)
            logger.info(f"Created dummy config for manager testing at: {manager_test_config_file} (CWD)")
            created_test_config = True
        except IOError as e_cwd:
            logger.error(
                f"Could not create dummy config in {config_dir} or CWD: {e}, {e_cwd}. Manager test may fail or use default mcp_servers.json if present."
            )

    if created_test_config:
        # Set a dummy token for the echo-slow server to pick up
        os.environ["MANAGER_HAS_THIS_TOKEN"] = "secret_token_for_echo_slow"

        manager = MCPManager(config_path=manager_test_config_file)

        print("\n--- Initial Statuses ---")
        print(manager.get_all_statuses())

        print("\n--- Starting 'echo-fast' ---")
        manager.start_server("echo-fast")
        time.sleep(1)  # Give it a moment to run and exit
        print(f"Status of 'echo-fast': {manager.get_server_status('echo-fast')}")  # Should be stopped as it exits

        print("\n--- Starting 'echo-slow' (runs for 5s) ---")
        manager.start_server("echo-slow")
        print(f"Status of 'echo-slow': {manager.get_server_status('echo-slow')}")

        print("\n--- Attempting to start 'disabled-server' ---")
        manager.start_server("disabled-server")
        print(f"Status of 'disabled-server': {manager.get_server_status('disabled-server')}")

        print("\n--- Attempting to start 'error-command' ---")
        manager.start_server("error-command")  # Should log an error
        print(f"Status of 'error-command': {manager.get_server_status('error-command')}")

        print("\n--- Statuses after some starts ---")
        print(manager.get_all_statuses())

        print("\n--- Waiting for 'echo-slow' to potentially finish (approx 5s total runtime)... ---")
        time.sleep(5)  # Wait for echo-slow to self-terminate
        print(f"Status of 'echo-slow' after waiting: {manager.get_server_status('echo-slow')}")

        print("\n--- Starting all enabled servers (echo-fast might restart if not already cleaned up) ---")
        # manager.start_server("echo-fast") # Ensure it is started again for stop_all_servers test
        # manager.start_server("echo-slow") # Start it again for stop_all test
        # Actually, let's test start_all_enabled_servers properly
        print("Stopping echo-fast if it's running from previous test to ensure clean start_all test")
        manager.stop_server("echo-fast")  # ensure it's stopped
        print("Stopping echo-slow if it's running from previous test to ensure clean start_all test")
        manager.stop_server("echo-slow")  # ensure it's stopped
        time.sleep(0.5)

        manager.start_all_enabled_servers()
        time.sleep(1)  # Give them a moment to start
        print("\n--- Statuses after starting all ---")
        print(manager.get_all_statuses())

        print("\n--- Stopping all servers ---")
        manager.stop_all_servers(timeout=2)  # Short timeout for test

        print("\n--- Final Statuses ---")
        print(manager.get_all_statuses())

        # Cleanup dummy env var
        if "MANAGER_HAS_THIS_TOKEN" in os.environ:
            del os.environ["MANAGER_HAS_THIS_TOKEN"]

        # Optionally remove the test config file
        # For now, leave it for inspection if run manually
        logger.info(f"Manager test complete. Test config file at: {manager_test_config_file}")
        # if os.path.exists(manager_test_config_file):
        # os.remove(manager_test_config_file)

    else:
        logger.error("Skipping manager live tests as test config file could not be created.")

    logger.info("MCP Manager Example Usage Finished.")
