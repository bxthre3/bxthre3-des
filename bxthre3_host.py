#!/usr/bin/env python3
"""
Bxthre3 Host Node - Executes tasks using WASM modules
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from typing import Dict, Optional, Any


class HostConfig:
    """Configuration for Host Node"""
    def __init__(self):
        self.controller_host: str = "127.0.0.1"
        self.controller_port: int = 5000
        self.ram_limit: int = 128
        self.node_id: str = ""
        self.wasm_runtime: str = ""
        self.wasm_modules_dir: str = ""
        self.heartbeat_interval: int = 30


class WasmExecutor:
    """Executes WASM modules using Wasm3 runtime"""
    def __init__(self, wasm_runtime: str, modules_dir: str):
        self.wasm_runtime = wasm_runtime
        self.modules_dir = modules_dir
    
    def execute(self, module_name: str, inputs: list = None) -> Dict[str, Any]:
        """Execute a WASM module"""
        module_path = os.path.join(self.modules_dir, module_name)
        
        if not os.path.exists(module_path):
            return {
                "success": False,
                "error": f"WASM module not found: {module_path}"
            }
        
        if not os.path.exists(self.wasm_runtime):
            return {
                "success": False,
                "error": f"WASM runtime not found: {self.wasm_runtime}"
            }
        
        try:
            # Prepare inputs
            input_args = []
            if inputs:
                for inp in inputs:
                    if isinstance(inp, str):
                        input_args.append(inp)
                    else:
                        input_args.append(str(inp))
            
            # Execute WASM module
            start_time = time.time()
            
            cmd = [self.wasm_runtime, module_path] + input_args
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            duration = time.time() - start_time
            
            if result.returncode == 0:
                output = result.stdout.strip()
                return {
                    "success": True,
                    "output": output,
                    "duration": duration,
                    "module": module_name
                }
            else:
                return {
                    "success": False,
                    "error": result.stderr.strip() or "Unknown error",
                    "duration": duration,
                    "module": module_name
                }
        
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Task execution timeout",
                "module": module_name
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "module": module_name
            }


class HostCommunication:
    """Handles communication with Controller"""
    def __init__(self, config: HostConfig):
        self.config = config
        self.socket = None
        self.connected = False
    
    def connect(self) -> bool:
        """Connect to Controller"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.config.controller_host, self.config.controller_port))
            
            # Register with controller
            register_message = {
                "type": "register_node",
                "node_id": self.config.node_id,
                "ram_limit": self.config.ram_limit
            }
            
            response = self.send_message(register_message)
            
            if response and response.get("status") == "success":
                self.connected = True
                print(f"[Host] Connected to Controller at {self.config.controller_host}:{self.config.controller_port}")
                return True
            else:
                print(f"[Host] Failed to register: {response}")
                return False
        
        except Exception as e:
            print(f"[Host] Connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from Controller"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
            self.connected = False
    
    def send_message(self, message: Dict) -> Optional[Dict]:
        """Send message to Controller and receive response"""
        if not self.socket or not self.connected:
            return None
        
        try:
            # Send message
            data = json.dumps(message).encode('utf-8')
            length = len(data).to_bytes(4, byteorder='big')
            self.socket.sendall(length + data)
            
            # Receive response
            response_length = int.from_bytes(self._recv_exact(4), byteorder='big')
            response_data = self._recv_exact(response_length)
            response = json.loads(response_data.decode('utf-8'))
            
            return response
        except Exception as e:
            print(f"[Host] Communication error: {e}")
            self.connected = False
            return None
    
    def _recv_exact(self, n: int) -> bytes:
        """Receive exactly n bytes"""
        data = bytearray()
        while len(data) < n:
            packet = self.socket.recv(n - len(data))
            if not packet:
                raise ConnectionError("Connection closed")
            data.extend(packet)
        return bytes(data)
    
    def request_task(self) -> Optional[Dict]:
        """Request a task from Controller"""
        message = {"type": "get_task", "node_id": self.config.node_id}
        response = self.send_message(message)
        
        if response and response.get("status") == "success":
            return response.get("task")
        return None
    
    def submit_result(self, task_id: str, result: Dict, dag_id: str = None):
        """Submit task result to Controller"""
        message = {
            "type": "task_result",
            "node_id": self.config.node_id,
            "task_id": task_id,
            "result": {
                "success": result.get("success", False),
                "output": result.get("output", ""),
                "error": result.get("error", ""),
                "duration": result.get("duration", 0),
                "dag_id": dag_id
            }
        }
        return self.send_message(message)
    
    def send_heartbeat(self):
        """Send heartbeat to Controller"""
        message = {
            "type": "heartbeat",
            "node_id": self.config.node_id
        }
        return self.send_message(message)


class HostNode:
    """Main Host Node"""
    def __init__(self, config: HostConfig):
        self.config = config
        self.comm = HostCommunication(config)
        self.executor = None
        self.running = False
        self.heartbeat_thread = None
    
    def start(self):
        """Start Host Node"""
        print(f"[Host] Bxthre3 Host Node starting...")
        print(f"[Host] Node ID: {self.config.node_id}")
        print(f"[Host] RAM Limit: {self.config.ram_limit}MB")
        
        # Find WASM runtime
        self.config.wasm_runtime = self._find_wasm_runtime()
        if not self.config.wasm_runtime:
            print("[Host] ERROR: WASM runtime not found!")
            print("[Host] Please ensure Wasm3 is installed in wasm_modules/m3/")
            sys.exit(1)
        
        print(f"[Host] WASM Runtime: {self.config.wasm_runtime}")
        
        # Set WASM modules directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.config.wasm_modules_dir = os.path.join(script_dir, "wasm_modules")
        
        # Create executor
        self.executor = WasmExecutor(self.config.wasm_runtime, self.config.wasm_modules_dir)
        
        # Connect to Controller
        if not self.comm.connect():
            print("[Host] Failed to connect to Controller. Retrying...")
            # Retry connection
            for attempt in range(5):
                time.sleep(5)
                print(f"[Host] Connection attempt {attempt + 1}/5...")
                if self.comm.connect():
                    break
            else:
                print("[Host] Failed to connect after 5 attempts. Exiting.")
                sys.exit(1)
        
        # Start heartbeat thread
        self.running = True
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        
        # Start task execution loop
        self._task_loop()
    
    def _find_wasm_runtime(self) -> Optional[str]:
        """Find Wasm3 runtime"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Possible locations
        possible_paths = [
            os.path.join(script_dir, "wasm_modules", "m3", "wasm3"),
            os.path.join(script_dir, "wasm_modules", "m3", "build", "wasm3"),
            os.path.join(script_dir, "wasm_modules", "wasm3"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        # Check if it's in PATH
        if shutil.which("wasm3"):
            return "wasm3"
        
        return None
    
    def _heartbeat_loop(self):
        """Send periodic heartbeats to Controller"""
        while self.running:
            try:
                self.comm.send_heartbeat()
            except Exception as e:
                print(f"[Host] Heartbeat error: {e}")
            time.sleep(self.config.heartbeat_interval)
    
    def _task_loop(self):
        """Main task execution loop"""
        print("[Host] Ready to execute tasks...")
        
        while self.running:
            try:
                # Request task
                task = self.comm.request_task()
                
                if task:
                    self._execute_task(task)
                else:
                    # No task available, wait a bit
                    time.sleep(2)
                
                # Check connection
                if not self.comm.connected:
                    print("[Host] Connection lost, attempting to reconnect...")
                    self.comm.disconnect()
                    time.sleep(5)
                    if not self.comm.connect():
                        print("[Host] Reconnection failed, will retry...")
                        continue
            
            except KeyboardInterrupt:
                print("[Host] Received interrupt signal")
                break
            except Exception as e:
                print(f"[Host] Error in task loop: {e}")
                time.sleep(1)
        
        self.running = False
        self.comm.disconnect()
    
    def _execute_task(self, task: Dict):
        """Execute a task"""
        task_id = task.get("id", "unknown")
        module_name = task.get("module", "")
        inputs = task.get("inputs", [])
        dag_id = task.get("dag_id", "")
        
        print(f"[Host] Executing task: {task_id} (module: {module_name})")
        
        # Execute WASM module
        result = self.executor.execute(module_name, inputs)
        
        # Submit result
        print(f"[Host] Task {task_id} completed: {result.get('success', False)}")
        self.comm.submit_result(task_id, result, dag_id)
    
    def stop(self):
        """Stop Host Node"""
        print("[Host] Stopping...")
        self.running = False
        self.comm.disconnect()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Bxthre3 Host Node")
    parser.add_argument("--controller", default="127.0.0.1", help="Controller host address")
    parser.add_argument("--port", type=int, default=5000, help="Controller port")
    parser.add_argument("--ram-limit", type=int, default=128, help="RAM limit in MB")
    parser.add_argument("--node-id", help="Custom node ID (auto-generated if not provided)")
    
    args = parser.parse_args()
    
    config = HostConfig()
    config.controller_host = args.controller
    config.controller_port = args.port
    config.ram_limit = args.ram_limit
    
    # Generate node ID if not provided
    if args.node_id:
        config.node_id = args.node_id
    else:
        import uuid
        config.node_id = f"host-{uuid.uuid4().hex[:8]}"
    
    host = HostNode(config)
    
    try:
        host.start()
    except KeyboardInterrupt:
        print("\n[Host] Received interrupt signal")
        host.stop()
    except Exception as e:
        print(f"[Host] Error: {e}")
        host.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()