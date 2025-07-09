import json
import os
from typing import Dict, Any, Optional

MCP_SERVERS_CONFIG_FILE = os.getenv("MCP_SERVERS_CONFIG_FILE", "mcp_servers.json")
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), MCP_SERVERS_CONFIG_FILE)

class MCPConfigError(Exception):
    """Custom exception for MCP configuration errors."""
    pass

def load_mcp_configurations(config_path: str = CONFIG_FILE_PATH) -> Dict[str, Dict[str, Any]]:
    """
    Loads and validates MCP server configurations from the JSON file.

    Args:
        config_path (str): The path to the MCP servers JSON configuration file.
                           Defaults to CONFIG_FILE_PATH.

    Returns:
        Dict[str, Dict[str, Any]]: A dictionary where keys are server IDs and
                                   values are their configuration dictionaries.

    Raises:
        MCPConfigError: If the config file is not found, is not valid JSON,
                        or if essential configuration fields are missing or invalid.
    """
    if not os.path.exists(config_path):
        raise MCPConfigError(f"Configuration file not found: {config_path}")

    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise MCPConfigError(f"Error decoding JSON from {config_path}: {e}")
    except IOError as e:
        raise MCPConfigError(f"Error reading file {config_path}: {e}")

    if not isinstance(data, dict) or "mcpServers" not in data:
        raise MCPConfigError(f"Invalid configuration structure in {config_path}: 'mcpServers' key is missing or root is not an object.")

    servers = data["mcpServers"]
    if not isinstance(servers, dict):
        raise MCPConfigError(f"'mcpServers' must be a dictionary of server configurations in {config_path}.")

    validated_servers: Dict[str, Dict[str, Any]] = {}
    for server_id, config in servers.items():
        if not isinstance(config, dict):
            raise MCPConfigError(f"Configuration for server '{server_id}' must be a dictionary.")

        # Validate command (mandatory)
        if "command" not in config or not isinstance(config["command"], str) or not config["command"].strip():
            raise MCPConfigError(f"Server '{server_id}': 'command' is missing or invalid.")

        # Validate args (optional, defaults to [])
        args = config.get("args", [])
        if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
            raise MCPConfigError(f"Server '{server_id}': 'args' must be a list of strings.")
        config["args"] = args # Ensure default is set if missing

        # Validate cwd (optional, string)
        if "cwd" in config and (not isinstance(config["cwd"], str) or not config["cwd"].strip()):
            raise MCPConfigError(f"Server '{server_id}': 'cwd' must be a non-empty string if provided.")

        # Validate env (optional, dict of str:str)
        env_vars = config.get("env", {})
        if not isinstance(env_vars, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env_vars.items()):
            raise MCPConfigError(f"Server '{server_id}': 'env' must be a dictionary of string key-value pairs.")
        config["env"] = env_vars

        # Validate enabled (optional, bool, defaults to True)
        enabled = config.get("enabled", True)
        if not isinstance(enabled, bool):
            raise MCPConfigError(f"Server '{server_id}': 'enabled' must be a boolean.")
        config["enabled"] = enabled

        # Validate authentication block (optional)
        auth_config = config.get("authentication")
        if auth_config is not None:
            if not isinstance(auth_config, dict):
                raise MCPConfigError(f"Server '{server_id}': 'authentication' block must be a dictionary.")

            if "token_env_var_name" not in auth_config or \
               not isinstance(auth_config["token_env_var_name"], str) or \
               not auth_config["token_env_var_name"].strip():
                raise MCPConfigError(f"Server '{server_id}': 'authentication.token_env_var_name' is missing or invalid.")

            if "token_source_env_var_name" in auth_config and \
               (not isinstance(auth_config["token_source_env_var_name"], str) or \
                not auth_config["token_source_env_var_name"].strip()):
                 raise MCPConfigError(f"Server '{server_id}': 'authentication.token_source_env_var_name' must be a non-empty string if provided.")

        validated_servers[server_id] = config

    return validated_servers

if __name__ == '__main__':
    # Example usage and basic test
    # Create a dummy mcp_servers.json for testing
    example_config_content = {
        "mcpServers": {
            "test-server-1": {
                "description": "A test server",
                "command": "echo",
                "args": ["Hello", "MCP"],
                "cwd": "/tmp",
                "env": {"TEST_VAR": "TestValue"},
                "enabled": True,
                "authentication": {
                    "type": "api_key",
                    "token_env_var_name": "MCP_API_KEY",
                    "token_source_env_var_name": "SOURCE_API_KEY"
                }
            },
            "test-server-2": {
                "command": "ls",
                "args": ["-la"],
                "enabled": False
            },
            "minimal-server": {
                "command": "pwd"
            }
        }
    }
    example_file_path = os.path.join(os.path.dirname(__file__), "mcp_servers_test_example.json")

    # Fallback for environments where direct file creation in __file__'s dir might be restricted
    try_paths = [
        os.path.join(os.path.dirname(__file__), "mcp_servers_test_example.json"),
        "mcp_servers_test_example.json" # Current working directory
    ]

    example_file_path = None
    for path_option in try_paths:
        try:
            with open(path_option, 'w') as f:
                json.dump(example_config_content, f, indent=2)
            example_file_path = path_option
            print(f"Created dummy config for testing at: {example_file_path}")
            break
        except IOError:
            print(f"Could not create dummy config at {path_option}, trying next.")

    if not example_file_path:
        print("Could not create dummy config file for testing. Skipping live load test.")
    else:
        print(f"\n--- Loading example configuration from: {example_file_path} ---")
        try:
            loaded_config = load_mcp_configurations(config_path=example_file_path)
            print("Configuration loaded successfully:")
            for server_id, conf in loaded_config.items():
                print(f"  Server ID: {server_id}")
                for key, value in conf.items():
                    print(f"    {key}: {value}")
        except MCPConfigError as e:
            print(f"Configuration Error: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
        finally:
            if os.path.exists(example_file_path):
                # os.remove(example_file_path)
                # print(f"Removed dummy config: {example_file_path}")
                # Decided to leave the example file for now for easier inspection if run manually
                print(f"Dummy config file left at: {example_file_path} for inspection.")

    print("\n--- Testing with non-existent file ---")
    try:
        load_mcp_configurations(config_path="non_existent_config.json")
    except MCPConfigError as e:
        print(f"Correctly caught error for non-existent file: {e}")

    # Test invalid JSON
    invalid_json_path = os.path.join(os.path.dirname(__file__), "invalid_mcp_config.json")
    if example_file_path: # only try if we can write files
        try:
            with open(invalid_json_path, 'w') as f:
                f.write("{'mcpServers': { 'bad-json': ") # Intentionally malformed
            print("\n--- Testing with invalid JSON file ---")
            load_mcp_configurations(config_path=invalid_json_path)
        except MCPConfigError as e:
            print(f"Correctly caught error for invalid JSON: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during invalid JSON test: {e}")
        finally:
            if os.path.exists(invalid_json_path):
                os.remove(invalid_json_path)

    # Test missing command
    missing_command_config = {"mcpServers": {"no-command-server": {"args": ["test"]}}}
    if example_file_path: # only try if we can write files
        missing_command_path = os.path.join(os.path.dirname(__file__), "missing_command_config.json")
        try:
            with open(missing_command_path, 'w') as f:
                json.dump(missing_command_config, f)
            print("\n--- Testing with missing command ---")
            load_mcp_configurations(config_path=missing_command_path)
        except MCPConfigError as e:
            print(f"Correctly caught error for missing command: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during missing command test: {e}")
        finally:
            if os.path.exists(missing_command_path):
                os.remove(missing_command_path)

    print("\n--- Loader tests complete ---")
