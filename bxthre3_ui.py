#!/usr/bin/env python3
"""
Bxthre3 UI Node - User interface for submitting and monitoring DAGs
"""

import argparse
import json
import socket
import sys
import time
import threading
import yaml
from datetime import datetime
from typing import Dict, List, Optional, Any


class UIConfig:
    """Configuration for UI Node"""
    def __init__(self):
        self.controller_host: str = "127.0.0.1"
        self.controller_port: int = 5000
        self.refresh_interval: int = 2


class UICommunication:
    """Handles communication with Controller"""
    def __init__(self, config: UIConfig):
        self.config = config
        self.socket = None
        
    def connect(self) -> bool:
        """Connect to Controller"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.config.controller_host, self.config.controller_port))
            print(f"[UI] Connected to Controller at {self.config.controller_host}:{self.config.controller_port}")
            return True
        except Exception as e:
            print(f"[UI] Failed to connect to Controller: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from Controller"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
    
    def send_message(self, message: Dict) -> Optional[Dict]:
        """Send message to Controller and receive response"""
        if not self.socket:
            if not self.connect():
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
            print(f"[UI] Communication error: {e}")
            self.disconnect()
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
    
    def submit_dag(self, dag_config: Dict) -> Optional[str]:
        """Submit a DAG to the Controller"""
        message = {
            "type": "submit_dag",
            "dag": dag_config
        }
        response = self.send_message(message)
        
        if response and response.get("status") == "success":
            return response.get("dag_id")
        return None
    
    def get_status(self) -> Optional[Dict]:
        """Get current status from Controller"""
        message = {"type": "get_status"}
        return self.send_message(message)
    
    def get_dag_status(self, dag_id: str) -> Optional[Dict]:
        """Get status of a specific DAG"""
        message = {
            "type": "get_dag_status",
            "dag_id": dag_id
        }
        return self.send_message(message)


class UIFormatter:
    """Formats output for display"""
    @staticmethod
    def print_header(title: str):
        """Print formatted header"""
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")
    
    @staticmethod
    def print_node_status(status: Dict):
        """Print node status information"""
        UIFormatter.print_header("Node Status")
        
        nodes = status.get("nodes", {})
        if not nodes:
            print("No nodes connected.")
            return
        
        print(f"Total Nodes: {len(nodes)}")
        print()
        
        for node_id, node_info in nodes.items():
            print(f"Node: {node_id}")
            print(f"  Status: {node_info.get('status', 'unknown')}")
            print(f"  RAM: {node_info.get('ram_limit', 'N/A')} MB")
            print(f"  Tasks: {node_info.get('task_count', 0)}")
            print()
    
    @staticmethod
    def print_dag_status(status: Dict):
        """Print DAG status information"""
        UIFormatter.print_header("DAG Status")
        
        dags = status.get("dags", {})
        if not dags:
            print("No DAGs submitted.")
            return
        
        for dag_id, dag_info in dags.items():
            print(f"DAG ID: {dag_id}")
            print(f"  Name: {dag_info.get('name', 'unknown')}")
            print(f"  Status: {dag_info.get('status', 'unknown')}")
            print(f"  Progress: {dag_info.get('completed_tasks', 0)}/{dag_info.get('total_tasks', 0)}")
            
            tasks = dag_info.get('tasks', {})
            if tasks:
                print("  Tasks:")
                for task_id, task_info in tasks.items():
                    status_icon = {
                        'pending': '○',
                        'running': '◐',
                        'completed': '●',
                        'failed': '✗'
                    }.get(task_info.get('status', 'pending'), '?')
                    print(f"    {status_icon} {task_id}: {task_info.get('status', 'pending')}")
            print()
    
    @staticmethod
    def print_task_results(results: List[Dict]):
        """Print task execution results"""
        UIFormatter.print_header("Task Results")
        
        for result in results:
            print(f"Task: {result.get('task_id', 'unknown')}")
            print(f"  Module: {result.get('module', 'unknown')}")
            print(f"  Status: {result.get('status', 'unknown')}")
            print(f"  Node: {result.get('node_id', 'unknown')}")
            print(f"  Duration: {result.get('duration', 0):.2f}s")
            
            if 'output' in result:
                print(f"  Output: {result['output']}")
            if 'error' in result:
                print(f"  Error: {result['error']}")
            print()


class UILiveMonitor:
    """Live monitoring of DAG execution"""
    def __init__(self, comm: UICommunication, formatter: UIFormatter):
        self.comm = comm
        self.formatter = formatter
        self.running = False
        self.monitor_thread = None
        self.current_dag_id = None
    
    def start(self, dag_id: Optional[str] = None):
        """Start live monitoring"""
        self.current_dag_id = dag_id
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop(self):
        """Stop live monitoring"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
    
    def _monitor_loop(self):
        """Monitoring loop"""
        while self.running:
            self._update_display()
            time.sleep(self.config.refresh_interval)
    
    def _update_display(self):
        """Update the display"""
        print("\033[2J\033[H", end="")  # Clear screen
        
        self.formatter.print_header(f"Bxthre3 Live Monitor - {datetime.now().strftime('%H:%M:%S')}")
        
        status = self.comm.get_status()
        if status:
            self.formatter.print_node_status(status)
            self.formatter.print_dag_status(status)
        else:
            print("[UI] Unable to fetch status. Controller may be down.")
        
        print("\nPress Ctrl+C to return to menu...")


class UINode:
    """Main UI Node"""
    def __init__(self, config: UIConfig):
        self.config = config
        self.comm = UICommunication(config)
        self.formatter = UIFormatter()
        self.monitor = UILiveMonitor(comm, formatter)
        self.monitor.config = config
    
    def start(self):
        """Start UI Node"""
        print("[UI] Bxthre3 UI Node starting...")
        
        if not self.comm.connect():
            print("[UI] Failed to connect to Controller. Please check Controller is running.")
            sys.exit(1)
        
        print("[UI] Connected successfully!")
        self._run_menu()
    
    def _run_menu(self):
        """Run interactive menu"""
        while True:
            print("\n" + "="*60)
            print("  Bxthre3 UI Menu")
            print("="*60)
            print("1. Submit DAG from file")
            print("2. Submit custom DAG")
            print("3. View status")
            print("4. View specific DAG status")
            print("5. Live monitor")
            print("6. Exit")
            print()
            
            choice = input("Select option: ").strip()
            
            if choice == "1":
                self._submit_dag_from_file()
            elif choice == "2":
                self._submit_custom_dag()
            elif choice == "3":
                self._view_status()
            elif choice == "4":
                self._view_dag_status()
            elif choice == "5":
                self._live_monitor()
            elif choice == "6":
                print("[UI] Exiting...")
                self.comm.disconnect()
                sys.exit(0)
            else:
                print("[UI] Invalid option. Please try again.")
    
    def _submit_dag_from_file(self):
        """Submit DAG from YAML file"""
        file_path = input("Enter DAG file path: ").strip()
        
        try:
            with open(file_path, 'r') as f:
                dag_config = yaml.safe_load(f)
            
            print(f"[UI] Submitting DAG: {dag_config.get('name', 'unnamed')}")
            dag_id = self.comm.submit_dag(dag_config)
            
            if dag_id:
                print(f"[UI] DAG submitted successfully! ID: {dag_id}")
            else:
                print("[UI] Failed to submit DAG.")
        except Exception as e:
            print(f"[UI] Error submitting DAG: {e}")
    
    def _submit_custom_dag(self):
        """Submit a custom DAG"""
        print("[UI] Create custom DAG")
        name = input("DAG name: ").strip()
        
        dag_config = {
            "name": name,
            "tasks": []
        }
        
        # Add tasks
        while True:
            print(f"\nTask {len(dag_config['tasks']) + 1}:")
            task_id = input("Task ID: ").strip()
            module = input("WASM module: ").strip()
            inputs = input("Inputs (comma-separated, leave empty for none): ").strip()
            
            task = {
                "id": task_id,
                "module": module,
                "inputs": [i.strip() for i in inputs.split(",")] if inputs else []
            }
            
            dag_config["tasks"].append(task)
            
            if input("Add another task? (y/n): ").strip().lower() != 'y':
                break
        
        print(f"[UI] Submitting DAG: {name}")
        dag_id = self.comm.submit_dag(dag_config)
        
        if dag_id:
            print(f"[UI] DAG submitted successfully! ID: {dag_id}")
        else:
            print("[UI] Failed to submit DAG.")
    
    def _view_status(self):
        """View overall status"""
        status = self.comm.get_status()
        if status:
            self.formatter.print_node_status(status)
            self.formatter.print_dag_status(status)
        else:
            print("[UI] Unable to fetch status.")
    
    def _view_dag_status(self):
        """View specific DAG status"""
        dag_id = input("Enter DAG ID: ").strip()
        status = self.comm.get_dag_status(dag_id)
        
        if status:
            self.formatter.print_header(f"DAG Status: {dag_id}")
            print(f"Name: {status.get('name', 'unknown')}")
            print(f"Status: {status.get('status', 'unknown')}")
            print(f"Progress: {status.get('completed_tasks', 0)}/{status.get('total_tasks', 0)}")
            
            tasks = status.get('tasks', {})
            if tasks:
                print("\nTasks:")
                for task_id, task_info in tasks.items():
                    print(f"  {task_id}: {task_info.get('status', 'pending')}")
        else:
            print("[UI] DAG not found.")
    
    def _live_monitor(self):
        """Start live monitoring"""
        dag_id = input("Enter DAG ID to monitor (leave empty for all): ").strip() or None
        
        print("\nStarting live monitor... Press Ctrl+C to return to menu.")
        try:
            self.monitor.start(dag_id)
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping monitor...")
            self.monitor.stop()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Bxthre3 UI Node")
    parser.add_argument("--controller", default="127.0.0.1", help="Controller host address")
    parser.add_argument("--port", type=int, default=5000, help="Controller port")
    parser.add_argument("--refresh", type=int, default=2, help="Refresh interval for live monitor")
    
    args = parser.parse_args()
    
    config = UIConfig()
    config.controller_host = args.controller
    config.controller_port = args.port
    config.refresh_interval = args.refresh
    
    ui = UINode(config)
    ui.start()


if __name__ == "__main__":
    main()