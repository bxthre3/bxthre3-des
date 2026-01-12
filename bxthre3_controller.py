#!/usr/bin/env python3
"""
Bxthre3 Controller Node - Central coordinator for distributed task execution
"""

import argparse
import json
import socket
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Any, Set


class ControllerConfig:
    """Configuration for Controller Node"""
    def __init__(self):
        self.host: str = "0.0.0.0"
        self.port: int = 5000
        self.max_connections: int = 100
        self.task_timeout: int = 300  # 5 minutes


class Node:
    """Represents a connected compute node"""
    def __init__(self, node_id: str, conn: socket.socket, addr: tuple, ram_limit: int):
        self.node_id = node_id
        self.conn = conn
        self.addr = addr
        self.ram_limit = ram_limit
        self.status = "idle"
        self.current_task = None
        self.task_count = 0
        self.last_heartbeat = time.time()
        self.completed_tasks = []
    
    def update_heartbeat(self):
        """Update last heartbeat timestamp"""
        self.last_heartbeat = time.time()
    
    def is_alive(self) -> bool:
        """Check if node is alive"""
        return time.time() - self.last_heartbeat < 60  # 60 second timeout
    
    def to_dict(self) -> Dict:
        """Convert node to dictionary"""
        return {
            "node_id": self.node_id,
            "addr": f"{self.addr[0]}:{self.addr[1]}",
            "ram_limit": self.ram_limit,
            "status": self.status,
            "current_task": self.current_task,
            "task_count": self.task_count,
            "last_heartbeat": self.last_heartbeat
        }


class DAG:
    """Represents a Directed Acyclic Graph of tasks"""
    def __init__(self, dag_id: str, name: str, tasks: List[Dict]):
        self.dag_id = dag_id
        self.name = name
        self.tasks = tasks
        self.status = "pending"
        self.task_results = {}
        self.task_dependencies = self._build_dependencies()
        self.created_at = time.time()
        self.started_at = None
        self.completed_at = None
    
    def _build_dependencies(self) -> Dict[str, List[str]]:
        """Build task dependency graph"""
        deps = {}
        for task in self.tasks:
            task_id = task["id"]
            deps[task_id] = task.get("depends_on", [])
        return deps
    
    def get_ready_tasks(self) -> List[Dict]:
        """Get tasks that are ready to execute (all dependencies completed)"""
        ready = []
        for task in self.tasks:
            task_id = task["id"]
            if task_id in self.task_results:
                continue  # Already completed
            
            # Check if all dependencies are completed
            deps = self.task_dependencies.get(task_id, [])
            if all(dep_id in self.task_results for dep_id in deps):
                ready.append(task)
        
        return ready
    
    def update_task_result(self, task_id: str, result: Dict):
        """Update result for a task"""
        self.task_results[task_id] = result
        
        # Update DAG status
        if len(self.task_results) == len(self.tasks):
            self.status = "completed"
            self.completed_at = time.time()
        elif self.status == "pending":
            self.status = "running"
            if not self.started_at:
                self.started_at = time.time()
    
    def is_complete(self) -> bool:
        """Check if DAG is complete"""
        return len(self.task_results) == len(self.tasks)
    
    def to_dict(self) -> Dict:
        """Convert DAG to dictionary"""
        task_status = {}
        for task in self.tasks:
            task_id = task["id"]
            if task_id in self.task_results:
                task_status[task_id] = {
                    "status": "completed" if self.task_results[task_id].get("success") else "failed",
                    "result": self.task_results[task_id]
                }
            else:
                task_status[task_id] = {"status": "pending"}
        
        return {
            "dag_id": self.dag_id,
            "name": self.name,
            "status": self.status,
            "total_tasks": len(self.tasks),
            "completed_tasks": len(self.task_results),
            "tasks": task_status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at
        }


class TaskScheduler:
    """Schedules tasks to available nodes"""
    def __init__(self):
        self.task_queue = deque()
        self.pending_tasks: Dict[str, Dict] = {}  # task_id -> task
        self.running_tasks: Dict[str, Dict] = {}  # task_id -> (node_id, task, start_time)
    
    def add_task(self, task: Dict, dag_id: str):
        """Add task to scheduling queue"""
        task_id = task["id"]
        task["dag_id"] = dag_id
        self.task_queue.append(task)
        self.pending_tasks[task_id] = task
    
    def get_next_task(self, node_id: str) -> Optional[Dict]:
        """Get next task for a node"""
        if not self.task_queue:
            return None
        
        task = self.task_queue.popleft()
        task_id = task["id"]
        
        del self.pending_tasks[task_id]
        self.running_tasks[task_id] = {
            "node_id": node_id,
            "task": task,
            "start_time": time.time()
        }
        
        return task
    
    def complete_task(self, task_id: str, result: Dict):
        """Mark task as complete"""
        if task_id in self.running_tasks:
            del self.running_tasks[task_id]
    
    def fail_task(self, task_id: str):
        """Handle task failure"""
        if task_id in self.running_tasks:
            task_info = self.running_tasks[task_id]
            task = task_info["task"]
            del self.running_tasks[task_id]
            # Re-queue failed tasks
            self.task_queue.append(task)
            self.pending_tasks[task["id"]] = task


class ControllerNode:
    """Main Controller Node"""
    def __init__(self, config: ControllerConfig):
        self.config = config
        self.nodes: Dict[str, Node] = {}
        self.dags: Dict[str, DAG] = {}
        self.scheduler = TaskScheduler()
        self.running = False
        self.server_socket = None
        self.node_lock = threading.Lock()
        self.dag_lock = threading.Lock()
        self.scheduler_lock = threading.Lock()
    
    def start(self):
        """Start Controller Node"""
        print("[Controller] Bxthre3 Controller Node starting...")
        
        # Start server socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.config.host, self.config.port))
        self.server_socket.listen(self.config.max_connections)
        
        self.running = True
        
        print(f"[Controller] Listening on {self.config.host}:{self.config.port}")
        
        # Start scheduler thread
        scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        scheduler_thread.start()
        
        # Start health check thread
        health_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        health_thread.start()
        
        # Accept connections
        self._accept_loop()
    
    def _accept_loop(self):
        """Accept incoming connections"""
        while self.running:
            try:
                conn, addr = self.server_socket.accept()
                print(f"[Controller] New connection from {addr}")
                
                # Start handler thread for this connection
                handler_thread = threading.Thread(
                    target=self._handle_connection,
                    args=(conn, addr),
                    daemon=True
                )
                handler_thread.start()
            except Exception as e:
                if self.running:
                    print(f"[Controller] Error accepting connection: {e}")
    
    def _handle_connection(self, conn: socket.socket, addr: tuple):
        """Handle connection from node or UI"""
        try:
            while self.running:
                # Receive message length
                length_data = self._recv_exact(conn, 4)
                if not length_data:
                    break
                
                length = int.from_bytes(length_data, byteorder='big')
                
                # Receive message
                message_data = self._recv_exact(conn, length)
                message = json.loads(message_data.decode('utf-8'))
                
                # Process message and get response
                response = self._process_message(message, conn, addr)
                
                # Send response
                response_data = json.dumps(response).encode('utf-8')
                response_length = len(response_data).to_bytes(4, byteorder='big')
                conn.sendall(response_length + response_data)
                
        except Exception as e:
            print(f"[Controller] Error handling connection from {addr}: {e}")
        finally:
            conn.close()
            print(f"[Controller] Connection closed: {addr}")
    
    def _recv_exact(self, conn: socket.socket, n: int) -> Optional[bytes]:
        """Receive exactly n bytes"""
        data = bytearray()
        while len(data) < n:
            packet = conn.recv(n - len(data))
            if not packet:
                return None
            data.extend(packet)
        return bytes(data)
    
    def _process_message(self, message: Dict, conn: socket.socket, addr: tuple) -> Dict:
        """Process incoming message"""
        msg_type = message.get("type")
        
        if msg_type == "register_node":
            return self._handle_register_node(message, conn, addr)
        elif msg_type == "heartbeat":
            return self._handle_heartbeat(message)
        elif msg_type == "get_task":
            return self._handle_get_task(message)
        elif msg_type == "task_result":
            return self._handle_task_result(message)
        elif msg_type == "submit_dag":
            return self._handle_submit_dag(message)
        elif msg_type == "get_status":
            return self._handle_get_status()
        elif msg_type == "get_dag_status":
            return self._handle_get_dag_status(message)
        else:
            return {"status": "error", "message": f"Unknown message type: {msg_type}"}
    
    def _handle_register_node(self, message: Dict, conn: socket.socket, addr: tuple) -> Dict:
        """Handle node registration"""
        node_id = message.get("node_id")
        ram_limit = message.get("ram_limit", 128)
        
        with self.node_lock:
            # Create new node
            node = Node(node_id, conn, addr, ram_limit)
            self.nodes[node_id] = node
        
        print(f"[Controller] Node registered: {node_id} (RAM: {ram_limit}MB)")
        return {"status": "success", "message": "Registered"}
    
    def _handle_heartbeat(self, message: Dict) -> Dict:
        """Handle heartbeat from node"""
        node_id = message.get("node_id")
        
        with self.node_lock:
            if node_id in self.nodes:
                self.nodes[node_id].update_heartbeat()
                return {"status": "success"}
        
        return {"status": "error", "message": "Node not found"}
    
    def _handle_get_task(self, message: Dict) -> Dict:
        """Handle task request from node"""
        node_id = message.get("node_id")
        
        with self.scheduler_lock:
            task = self.scheduler.get_next_task(node_id)
        
        if task:
            with self.node_lock:
                if node_id in self.nodes:
                    self.nodes[node_id].status = "busy"
                    self.nodes[node_id].current_task = task["id"]
            
            print(f"[Controller] Assigned task {task['id']} to node {node_id}")
            return {"status": "success", "task": task}
        else:
            return {"status": "success", "task": None}
    
    def _handle_task_result(self, message: Dict) -> Dict:
        """Handle task result from node"""
        node_id = message.get("node_id")
        task_id = message.get("task_id")
        result = message.get("result", {})
        
        # Update scheduler
        with self.scheduler_lock:
            if result.get("success"):
                self.scheduler.complete_task(task_id, result)
            else:
                self.scheduler.fail_task(task_id)
        
        # Update DAG
        dag_id = result.get("dag_id")
        if dag_id:
            with self.dag_lock:
                if dag_id in self.dags:
                    self.dags[dag_id].update_task_result(task_id, result)
                    print(f"[Controller] Task {task_id} completed for DAG {dag_id}")
        
        # Update node
        with self.node_lock:
            if node_id in self.nodes:
                self.nodes[node_id].status = "idle"
                self.nodes[node_id].current_task = None
                self.nodes[node_id].task_count += 1
                self.nodes[node_id].completed_tasks.append({
                    "task_id": task_id,
                    "result": result,
                    "timestamp": time.time()
                })
        
        # Schedule more tasks for this DAG
        if dag_id:
            self._schedule_dag_tasks(dag_id)
        
        return {"status": "success"}
    
    def _handle_submit_dag(self, message: Dict) -> Dict:
        """Handle DAG submission"""
        dag_config = message.get("dag")
        dag_id = str(uuid.uuid4())[:8]
        
        dag = DAG(
            dag_id=dag_id,
            name=dag_config.get("name", "unnamed"),
            tasks=dag_config.get("tasks", [])
        )
        
        with self.dag_lock:
            self.dags[dag_id] = dag
        
        print(f"[Controller] DAG submitted: {dag.name} (ID: {dag_id})")
        
        # Schedule initial tasks
        self._schedule_dag_tasks(dag_id)
        
        return {"status": "success", "dag_id": dag_id}
    
    def _handle_get_status(self) -> Dict:
        """Handle status request"""
        with self.node_lock, self.dag_lock:
            nodes_info = {node_id: node.to_dict() for node_id, node in self.nodes.items()}
            dags_info = {dag_id: dag.to_dict() for dag_id, dag in self.dags.items()}
        
        return {
            "status": "success",
            "nodes": nodes_info,
            "dags": dags_info,
            "timestamp": time.time()
        }
    
    def _handle_get_dag_status(self, message: Dict) -> Dict:
        """Handle specific DAG status request"""
        dag_id = message.get("dag_id")
        
        with self.dag_lock:
            if dag_id in self.dags:
                return {
                    "status": "success",
                    "dag": self.dags[dag_id].to_dict()
                }
        
        return {"status": "error", "message": "DAG not found"}
    
    def _schedule_dag_tasks(self, dag_id: str):
        """Schedule ready tasks for a DAG"""
        with self.dag_lock:
            if dag_id not in self.dags:
                return
            
            dag = self.dags[dag_id]
            ready_tasks = dag.get_ready_tasks()
        
        # Add ready tasks to scheduler
        with self.scheduler_lock:
            for task in ready_tasks:
                if task["id"] not in self.scheduler.pending_tasks and task["id"] not in self.scheduler.running_tasks:
                    self.scheduler.add_task(task, dag_id)
                    print(f"[Controller] Scheduled task {task['id']} for DAG {dag_id}")
    
    def _scheduler_loop(self):
        """Main scheduler loop"""
        while self.running:
            # Check all DAGs for ready tasks
            with self.dag_lock:
                dag_ids = list(self.dags.keys())
            
            for dag_id in dag_ids:
                self._schedule_dag_tasks(dag_id)
            
            time.sleep(1)
    
    def _health_check_loop(self):
        """Health check loop for nodes"""
        while self.running:
            dead_nodes = []
            
            with self.node_lock:
                for node_id, node in self.nodes.items():
                    if not node.is_alive():
                        dead_nodes.append(node_id)
                        print(f"[Controller] Node {node_id} is dead, removing...")
            
            # Remove dead nodes
            for node_id in dead_nodes:
                with self.node_lock:
                    if node_id in self.nodes:
                        # Re-queue any running tasks
                        node = self.nodes[node_id]
                        for task_id, task_info in self.scheduler.running_tasks.items():
                            if task_info["node_id"] == node_id:
                                task = task_info["task"]
                                self.scheduler.task_queue.append(task)
                                self.scheduler.pending_tasks[task["id"]] = task
                                del self.scheduler.running_tasks[task_id]
                        
                        del self.nodes[node_id]
            
            time.sleep(30)  # Check every 30 seconds
    
    def stop(self):
        """Stop Controller Node"""
        print("[Controller] Stopping...")
        self.running = False
        
        if self.server_socket:
            self.server_socket.close()
        
        # Close all node connections
        with self.node_lock:
            for node in self.nodes.values():
                try:
                    node.conn.close()
                except:
                    pass


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Bxthre3 Controller Node")
    parser.add_argument("--host", default="0.0.0.0", help="Host address to bind to")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on")
    parser.add_argument("--max-connections", type=int, default=100, help="Maximum number of connections")
    
    args = parser.parse_args()
    
    config = ControllerConfig()
    config.host = args.host
    config.port = args.port
    config.max_connections = args.max_connections
    
    controller = ControllerNode(config)
    
    try:
        controller.start()
    except KeyboardInterrupt:
        print("\n[Controller] Received interrupt signal")
        controller.stop()
    except Exception as e:
        print(f"[Controller] Error: {e}")
        controller.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()