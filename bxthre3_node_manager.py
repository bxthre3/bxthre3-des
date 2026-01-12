#!/usr/bin/env python3
"""
Bxthre3 Node Manager - Manages multiple logical nodes based on available RAM
"""

import argparse
import os
import psutil
import subprocess
import sys
import time
import uuid
from typing import Dict, List, Optional


class NodeManagerConfig:
    """Configuration for Node Manager"""
    def __init__(self):
        self.ram_per_node: int = 128  # MB
        self.controller_host: str = "127.0.0.1"
        self.controller_port: int = 5000
        self.device_id: str = ""
        self.min_free_ram: int = 512  # MB - minimum RAM to keep free for system
        self.check_interval: int = 30  # seconds between checks
        self.host_script: str = ""


class LogicalNode:
    """Represents a logical node (Host instance)"""
    def __init__(self, node_id: str, ram_limit: int, process: subprocess.Popen):
        self.node_id = node_id
        self.ram_limit = ram_limit
        self.process = process
        self.created_at = time.time()
        self.status = "running"
    
    def is_alive(self) -> bool:
        """Check if node process is alive"""
        if self.process:
            return self.process.poll() is None
        return False
    
    def stop(self):
        """Stop the node process"""
        if self.process and self.is_alive():
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.status = "stopped"


class NodeManager:
    """Manages multiple logical nodes"""
    def __init__(self, config: NodeManagerConfig):
        self.config = config
        self.nodes: Dict[str, LogicalNode] = {}
        self.running = False
        
        # Get device ID
        self.config.device_id = self._get_device_id()
        
        # Find host script
        self.config.host_script = self._find_host_script()
        
        if not self.config.host_script:
            print("[NodeManager] ERROR: Host script not found!")
            sys.exit(1)
    
    def _get_device_id(self) -> str:
        """Generate or get device ID"""
        try:
            import hashlib
            hostname = os.uname().nodename
            device_id = hashlib.md5(hostname.encode()).hexdigest()[:8]
            return f"dev-{device_id}"
        except:
            return f"dev-{uuid.uuid4().hex[:8]}"
    
    def _find_host_script(self) -> Optional[str]:
        """Find the host script"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        possible_paths = [
            os.path.join(script_dir, "bxthre3_host.py"),
            os.path.join(os.getcwd(), "bxthre3_host.py"),
            "./bxthre3_host.py"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def _get_available_ram(self) -> int:
        """Get available RAM in MB"""
        try:
            # Use psutil to get available memory
            mem = psutil.virtual_memory()
            available_mb = mem.available // (1024 * 1024)
            return available_mb
        except Exception as e:
            print(f"[NodeManager] Error getting RAM info: {e}")
            return 1024  # Default to 1GB
    
    def _can_start_node(self) -> bool:
        """Check if we can start a new node"""
        available_ram = self._get_available_ram()
        usable_ram = available_ram - self.config.min_free_ram
        
        return usable_ram >= self.config.ram_per_node
    
    def _calculate_max_nodes(self) -> int:
        """Calculate maximum number of nodes we can run"""
        available_ram = self._get_available_ram()
        usable_ram = available_ram - self.config.min_free_ram
        
        if usable_ram <= 0:
            return 0
        
        max_nodes = usable_ram // self.config.ram_per_node
        return max_nodes
    
    def _start_logical_node(self, node_index: int) -> Optional[LogicalNode]:
        """Start a new logical node"""
        node_id = f"{self.config.device_id}-{node_index}"
        
        print(f"[NodeManager] Starting logical node: {node_id} (RAM: {self.config.ram_per_node}MB)")
        
        try:
            # Start host process
            process = subprocess.Popen(
                [sys.executable, self.config.host_script,
                 "--controller", self.config.controller_host,
                 "--port", str(self.config.controller_port),
                 "--ram-limit", str(self.config.ram_per_node),
                 "--node-id", node_id],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            node = LogicalNode(node_id, self.config.ram_per_node, process)
            return node
        
        except Exception as e:
            print(f"[NodeManager] Failed to start node {node_id}: {e}")
            return None
    
    def _stop_idle_nodes(self):
        """Stop nodes that have been idle for too long"""
        idle_timeout = 300  # 5 minutes
        current_time = time.time()
        
        # In a real implementation, we'd track idle time via Controller API
        # For now, we'll just stop nodes that are no longer needed based on RAM
        
        target_nodes = self._calculate_max_nodes()
        current_nodes = len(self.nodes)
        
        if current_nodes > target_nodes:
            nodes_to_stop = current_nodes - target_nodes
            
            # Get sorted nodes (oldest first)
            sorted_nodes = sorted(self.nodes.values(), key=lambda n: n.created_at)
            
            for i in range(nodes_to_stop):
                node = sorted_nodes[i]
                print(f"[NodeManager] Stopping idle node: {node.node_id}")
                node.stop()
                del self.nodes[node.node_id]
    
    def _cleanup_dead_nodes(self):
        """Clean up dead node processes"""
        dead_nodes = []
        
        for node_id, node in self.nodes.items():
            if not node.is_alive():
                dead_nodes.append(node_id)
                print(f"[NodeManager] Removing dead node: {node_id}")
        
        for node_id in dead_nodes:
            del self.nodes[node_id]
    
    def _scale_nodes(self):
        """Scale nodes based on available RAM"""
        max_nodes = self._calculate_max_nodes()
        current_nodes = len(self.nodes)
        
        print(f"[NodeManager] Current nodes: {current_nodes}, Max nodes: {max_nodes}")
        
        # Scale up
        if current_nodes < max_nodes:
            nodes_to_add = max_nodes - current_nodes
            node_index = current_nodes
            
            for i in range(nodes_to_add):
                node = self._start_logical_node(node_index + i)
                if node:
                    self.nodes[node.node_id] = node
                    time.sleep(1)  # Small delay between starting nodes
        
        # Scale down
        elif current_nodes > max_nodes:
            self._stop_idle_nodes()
    
    def start(self):
        """Start Node Manager"""
        print("[NodeManager] Bxthre3 Node Manager starting...")
        print(f"[NodeManager] Device ID: {self.config.device_id}")
        print(f"[NodeManager] RAM per node: {self.config.ram_per_node}MB")
        print(f"[NodeManager] Controller: {self.config.controller_host}:{self.config.controller_port}")
        
        # Get available RAM
        available_ram = self._get_available_ram()
        print(f"[NodeManager] Available RAM: {available_ram}MB")
        
        # Calculate max nodes
        max_nodes = self._calculate_max_nodes()
        print(f"[NodeManager] Maximum logical nodes: {max_nodes}")
        
        if max_nodes == 0:
            print("[NodeManager] WARNING: Not enough RAM to start any nodes!")
            print(f"[NodeManager] Minimum required: {self.config.min_free_ram + self.config.ram_per_node}MB")
            sys.exit(1)
        
        self.running = True
        
        # Initial scaling
        self._scale_nodes()
        
        # Main loop
        print("[NodeManager] Node Manager running. Press Ctrl+C to stop.")
        
        try:
            while self.running:
                # Cleanup dead nodes
                self._cleanup_dead_nodes()
                
                # Scale nodes based on RAM
                self._scale_nodes()
                
                # Print status
                print(f"[NodeManager] Status: {len(self.nodes)} active nodes")
                
                # Wait before next check
                time.sleep(self.config.check_interval)
        
        except KeyboardInterrupt:
            print("\n[NodeManager] Received interrupt signal")
        
        # Stop all nodes
        self.stop()
    
    def stop(self):
        """Stop Node Manager and all nodes"""
        print("[NodeManager] Stopping all nodes...")
        self.running = False
        
        for node_id, node in self.nodes.items():
            print(f"[NodeManager] Stopping node: {node_id}")
            node.stop()
        
        self.nodes.clear()
        print("[NodeManager] All nodes stopped.")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Bxthre3 Node Manager")
    parser.add_argument("--controller", default="127.0.0.1", help="Controller host address")
    parser.add_argument("--port", type=int, default=5000, help="Controller port")
    parser.add_argument("--ram-per-node", type=int, default=128, help="RAM per logical node in MB")
    parser.add_argument("--min-free-ram", type=int, default=512, help="Minimum free RAM in MB")
    
    args = parser.parse_args()
    
    config = NodeManagerConfig()
    config.controller_host = args.controller
    config.controller_port = args.port
    config.ram_per_node = args.ram_per_node
    config.min_free_ram = args.min_free_ram
    
    # Get controller from environment if set
    if "BXTHRE3_CONTROLLER" in os.environ:
        config.controller_host = os.environ["BXTHRE3_CONTROLLER"]
    
    manager = NodeManager(config)
    
    try:
        manager.start()
    except Exception as e:
        print(f"[NodeManager] Error: {e}")
        manager.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()